//! Parser for the object-definition layer of Nagios/Shinken configuration.
//!
//! Directives intentionally remain ordered and are not collapsed into a map:
//! duplicates and ordering are part of the compatibility corpus.

use std::{
    collections::BTreeSet,
    fs,
    path::{Path, PathBuf},
};

use thiserror::Error;

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Directive {
    pub name: String,
    pub value: String,
    pub line: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ObjectDefinition {
    pub kind: String,
    pub directives: Vec<Directive>,
    pub line: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LoadedConfig {
    pub files: Vec<PathBuf>,
    pub objects: Vec<ObjectDefinition>,
}

#[derive(Debug, Error)]
pub enum LoadError {
    #[error("cannot read {path}: {source}")]
    Io {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error(transparent)]
    Parse(#[from] ParseError),
}

#[derive(Debug, Error, Eq, PartialEq)]
pub enum ParseError {
    #[error("{path}:{line}: expected '{{' after define {kind}")]
    MissingOpeningBrace {
        path: PathBuf,
        line: usize,
        kind: String,
    },
    #[error("{path}:{line}: unexpected content outside an object: {content}")]
    UnexpectedContent {
        path: PathBuf,
        line: usize,
        content: String,
    },
    #[error("{path}:{line}: directive has no value: {name}")]
    MissingDirectiveValue {
        path: PathBuf,
        line: usize,
        name: String,
    },
    #[error("{path}:{line}: nested object definition")]
    NestedObject { path: PathBuf, line: usize },
    #[error("{path}:{line}: closing brace without an object")]
    UnexpectedClosingBrace { path: PathBuf, line: usize },
    #[error("{path}:{line}: object is not closed")]
    UnclosedObject { path: PathBuf, line: usize },
}

/// Parse Nagios/Shinken `define kind { ... }` object blocks.
///
/// Comments are recognized when the first non-whitespace character is `#` or
/// `;`. Inline characters are retained because command lines may contain them.
pub fn parse_objects(
    path: impl AsRef<Path>,
    input: &str,
) -> Result<Vec<ObjectDefinition>, ParseError> {
    let path = path.as_ref().to_path_buf();
    let mut objects = Vec::new();
    let mut current: Option<ObjectDefinition> = None;
    let mut pending: Option<(String, usize)> = None;

    for (offset, raw_line) in input.lines().enumerate() {
        let line = offset + 1;
        let text = raw_line.trim();
        if text.is_empty() || text.starts_with('#') || text.starts_with(';') {
            continue;
        }

        if let Some((kind, define_line)) = pending.take() {
            if text != "{" {
                return Err(ParseError::MissingOpeningBrace {
                    path,
                    line,
                    kind,
                });
            }
            current = Some(ObjectDefinition {
                kind,
                directives: Vec::new(),
                line: define_line,
            });
            continue;
        }

        if text.starts_with("define ") || text.starts_with("define\t") {
            if current.is_some() {
                return Err(ParseError::NestedObject { path, line });
            }
            let rest = &text["define".len()..];
            let rest = rest.trim_start();
            let (kind, has_brace) = match rest.strip_suffix('{') {
                Some(kind) => (kind.trim(), true),
                None => (rest.trim(), false),
            };
            if kind.is_empty() {
                return Err(ParseError::UnexpectedContent {
                    path,
                    line,
                    content: text.to_owned(),
                });
            }
            if has_brace {
                current = Some(ObjectDefinition {
                    kind: kind.to_owned(),
                    directives: Vec::new(),
                    line,
                });
            } else {
                pending = Some((kind.to_owned(), line));
            }
            continue;
        }

        if text == "}" {
            let Some(object) = current.take() else {
                return Err(ParseError::UnexpectedClosingBrace { path, line });
            };
            objects.push(object);
            continue;
        }

        let Some(object) = current.as_mut() else {
            return Err(ParseError::UnexpectedContent {
                path,
                line,
                content: text.to_owned(),
            });
        };
        let Some(split_at) = text.find(char::is_whitespace) else {
            return Err(ParseError::MissingDirectiveValue {
                path,
                line,
                name: text.to_owned(),
            });
        };
        let name = &text[..split_at];
        let value = text[split_at..].trim_start();
        if value.is_empty() {
            return Err(ParseError::MissingDirectiveValue {
                path,
                line,
                name: name.to_owned(),
            });
        }
        object.directives.push(Directive {
            name: name.to_owned(),
            value: value.to_owned(),
            line,
        });
    }

    if let Some((kind, line)) = pending {
        return Err(ParseError::MissingOpeningBrace {
            path,
            line,
            kind,
        });
    }
    if let Some(object) = current {
        return Err(ParseError::UnclosedObject {
            path,
            line: object.line,
        });
    }
    Ok(objects)
}

/// Load every object referenced by `cfg_file` and `cfg_dir` in a main config.
/// Relative paths are resolved from the main config's directory and `cfg_dir`
/// traversal is recursive and deterministic.
pub fn load_config_tree(main_config: impl AsRef<Path>) -> Result<LoadedConfig, LoadError> {
    let main_config = main_config.as_ref();
    let input = read_to_string(main_config)?;
    let base = main_config.parent().unwrap_or_else(|| Path::new("."));
    let mut files = BTreeSet::new();

    for raw_line in input.lines() {
        let line = raw_line.trim();
        if line.is_empty() || line.starts_with('#') || line.starts_with(';') {
            continue;
        }
        let Some((name, value)) = line.split_once('=') else {
            continue;
        };
        let path = resolve_path(base, value.trim());
        match name.trim() {
            "cfg_file" => {
                files.insert(path);
            }
            "cfg_dir" => collect_cfg_files(&path, &mut files)?,
            _ => {}
        }
    }

    let files: Vec<_> = files.into_iter().collect();
    let mut objects = Vec::new();
    for path in &files {
        objects.extend(parse_objects(path, &read_to_string(path)?)?);
    }
    Ok(LoadedConfig { files, objects })
}

fn resolve_path(base: &Path, value: &str) -> PathBuf {
    let path = Path::new(value);
    if path.is_absolute() {
        path.to_path_buf()
    } else {
        base.join(path)
    }
}

fn collect_cfg_files(directory: &Path, files: &mut BTreeSet<PathBuf>) -> Result<(), LoadError> {
    let entries = fs::read_dir(directory).map_err(|source| LoadError::Io {
        path: directory.to_path_buf(),
        source,
    })?;
    for entry in entries {
        let entry = entry.map_err(|source| LoadError::Io {
            path: directory.to_path_buf(),
            source,
        })?;
        let file_type = entry.file_type().map_err(|source| LoadError::Io {
            path: entry.path(),
            source,
        })?;
        let path = entry.path();
        if file_type.is_dir() {
            collect_cfg_files(&path, files)?;
        } else if file_type.is_file()
            && path
                .extension()
                .is_some_and(|extension| extension == "cfg")
        {
            files.insert(path);
        }
    }
    Ok(())
}

fn read_to_string(path: &Path) -> Result<String, LoadError> {
    fs::read_to_string(path).map_err(|source| LoadError::Io {
        path: path.to_path_buf(),
        source,
    })
}

#[cfg(test)]
mod tests {
    use std::fs;

    use super::{load_config_tree, parse_objects, Directive, ObjectDefinition};

    #[test]
    fn preserves_order_duplicates_values_and_source_lines() {
        let input = r#"
# comment
define service {
    host_name router-01
    service_description HTTP health
    _DETAIL value;kept #kept
    contacts alice
    contacts bob
}
"#;
        let objects = parse_objects("objects.cfg", input).unwrap();
        assert_eq!(
            objects,
            vec![ObjectDefinition {
                kind: "service".into(),
                line: 3,
                directives: vec![
                    Directive { name: "host_name".into(), value: "router-01".into(), line: 4 },
                    Directive { name: "service_description".into(), value: "HTTP health".into(), line: 5 },
                    Directive { name: "_DETAIL".into(), value: "value;kept #kept".into(), line: 6 },
                    Directive { name: "contacts".into(), value: "alice".into(), line: 7 },
                    Directive { name: "contacts".into(), value: "bob".into(), line: 8 },
                ],
            }]
        );
    }

    #[test]
    fn accepts_opening_brace_on_the_next_line() {
        let objects = parse_objects("objects.cfg", "define host\n{\n host_name edge\n}\n").unwrap();
        assert_eq!(objects[0].kind, "host");
        assert_eq!(objects[0].directives[0].value, "edge");
    }

    #[test]
    fn loads_cfg_file_and_recursive_cfg_dir() {
        let temp = tempfile::tempdir().unwrap();
        let objects = temp.path().join("objects");
        let nested = objects.join("nested");
        fs::create_dir_all(&nested).unwrap();
        fs::write(
            temp.path().join("main.cfg"),
            "cfg_file=one.cfg\ncfg_dir=objects\n",
        )
        .unwrap();
        fs::write(
            temp.path().join("one.cfg"),
            "define host {\n host_name one\n}\n",
        )
        .unwrap();
        fs::write(
            objects.join("two.cfg"),
            "define host {\n host_name two\n}\n",
        )
        .unwrap();
        fs::write(
            nested.join("three.cfg"),
            "define host {\n host_name three\n}\n",
        )
        .unwrap();
        fs::write(nested.join("ignored.txt"), "not config").unwrap();

        let loaded = load_config_tree(temp.path().join("main.cfg")).unwrap();
        assert_eq!(loaded.files.len(), 3);
        assert_eq!(loaded.objects.len(), 3);
    }
}
