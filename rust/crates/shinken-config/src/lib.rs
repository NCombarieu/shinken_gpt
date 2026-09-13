//! Parser for the object-definition layer of Nagios/Shinken configuration.
//!
//! Directives intentionally remain ordered and are not collapsed into a map:
//! duplicates and ordering are part of the compatibility corpus.

use std::{
    collections::{BTreeSet, HashMap, HashSet},
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
    pub resource_macros: HashMap<String, String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MonitoringConfig {
    pub commands: HashMap<String, CommandConfig>,
    pub hosts: HashMap<String, HostConfig>,
    pub services: Vec<ServiceConfig>,
    pub resource_macros: HashMap<String, String>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CommandConfig {
    pub name: String,
    pub command_line: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HostConfig {
    pub name: String,
    pub address: String,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ServiceConfig {
    pub host_name: String,
    pub description: String,
    pub check_command: String,
    pub max_check_attempts: u32,
    pub check_interval_seconds: u64,
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
    #[error("invalid monitoring definition: {0}")]
    Semantic(String),
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
                return Err(ParseError::MissingOpeningBrace { path, line, kind });
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
        return Err(ParseError::MissingOpeningBrace { path, line, kind });
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
    let mut resource_macros = HashMap::new();
    for path in &files {
        let input = read_to_string(path)?;
        resource_macros.extend(parse_resource_macros(&input));
        if input.lines().any(is_definition_line) {
            objects.extend(parse_objects(path, &input)?);
        }
    }
    Ok(LoadedConfig {
        files,
        objects,
        resource_macros,
    })
}

/// Turn parsed Nagios/Shinken objects into the subset required by the first
/// standalone Rust engine. `use` inheritance is resolved before extraction.
pub fn build_monitoring_config(loaded: &LoadedConfig) -> Result<MonitoringConfig, LoadError> {
    let templates: HashMap<_, _> = loaded
        .objects
        .iter()
        .filter_map(|object| {
            directive_value(object, "name").map(|name| ((object.kind.as_str(), name), object))
        })
        .collect();
    let mut commands = HashMap::new();
    let mut hosts = HashMap::new();
    let mut services = Vec::new();
    let mut hostgroups = HashMap::new();

    for object in &loaded.objects {
        if object.kind == "hostgroup" {
            let directives = resolved_directives(object, &templates, &mut HashSet::new())?;
            if let (Some(name), Some(members)) = (
                directive_value_from(&directives, "hostgroup_name"),
                directive_value_from(&directives, "members"),
            ) {
                hostgroups.insert(
                    name.to_owned(),
                    members
                        .split(',')
                        .map(str::trim)
                        .filter(|member| !member.is_empty())
                        .map(str::to_owned)
                        .collect::<Vec<_>>(),
                );
            }
        }
    }

    for object in &loaded.objects {
        let directives = resolved_directives(object, &templates, &mut HashSet::new())?;
        match object.kind.as_str() {
            "command" => {
                let name = required(&directives, "command_name", "command")?;
                let command_line = required(&directives, "command_line", "command")?;
                commands.insert(
                    name.to_owned(),
                    CommandConfig {
                        name: name.to_owned(),
                        command_line: command_line.to_owned(),
                    },
                );
            }
            "host" if directive_value_from(&directives, "register") != Some("0") => {
                let name = required(&directives, "host_name", "host")?;
                let address = directive_value_from(&directives, "address").unwrap_or(name);
                hosts.insert(
                    name.to_owned(),
                    HostConfig {
                        name: name.to_owned(),
                        address: address.to_owned(),
                    },
                );
            }
            "service" if directive_value_from(&directives, "register") != Some("0") => {
                let host_names = match directive_value_from(&directives, "host_name") {
                    Some(host_names) => host_names
                        .split(',')
                        .map(str::trim)
                        .filter(|name| !name.is_empty())
                        .map(str::to_owned)
                        .collect(),
                    None => directive_value_from(&directives, "hostgroup_name")
                        .and_then(|group| hostgroups.get(group))
                        .cloned()
                        .unwrap_or_default(),
                };
                if host_names.is_empty() {
                    continue;
                }
                let description = required(&directives, "service_description", "service")?;
                let check_command = required(&directives, "check_command", "service")?;
                let max_check_attempts = directive_value_from(&directives, "max_check_attempts")
                    .map(parse_u32)
                    .transpose()?
                    .unwrap_or(3);
                let check_interval_seconds = directive_value_from(&directives, "check_interval")
                    .map(parse_interval_seconds)
                    .transpose()?
                    .unwrap_or(60);
                for host_name in host_names {
                    services.push(ServiceConfig {
                        host_name,
                        description: description.to_owned(),
                        check_command: check_command.to_owned(),
                        max_check_attempts,
                        check_interval_seconds,
                    });
                }
            }
            _ => {}
        }
    }
    Ok(MonitoringConfig {
        commands,
        hosts,
        services,
        resource_macros: loaded.resource_macros.clone(),
    })
}

fn is_definition_line(line: &&str) -> bool {
    let line = line.trim_start();
    line.starts_with("define ") || line.starts_with("define\t")
}

fn parse_resource_macros(input: &str) -> HashMap<String, String> {
    input
        .lines()
        .filter_map(|line| {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') || line.starts_with(';') {
                return None;
            }
            let (name, value) = line.split_once('=')?;
            let name = name.trim();
            (name.starts_with('$') && name.ends_with('$'))
                .then(|| (name.to_owned(), value.trim().to_owned()))
        })
        .collect()
}

fn resolved_directives<'a>(
    object: &'a ObjectDefinition,
    templates: &HashMap<(&'a str, &'a str), &'a ObjectDefinition>,
    visiting: &mut HashSet<(&'a str, &'a str)>,
) -> Result<Vec<Directive>, LoadError> {
    let mut directives = Vec::new();
    if let Some(parent_name) = directive_value(object, "use") {
        let key = (object.kind.as_str(), parent_name);
        if !visiting.insert(key) {
            return Err(LoadError::Semantic(format!(
                "cyclic template use: {parent_name}"
            )));
        }
        let parent = templates.get(&key).ok_or_else(|| {
            LoadError::Semantic(format!("unknown {} template: {parent_name}", object.kind))
        })?;
        directives.extend(resolved_directives(parent, templates, visiting)?);
        visiting.remove(&key);
    }
    for directive in &object.directives {
        if directive.name != "use" {
            directives.retain(|existing| existing.name != directive.name);
            directives.push(directive.clone());
        }
    }
    Ok(directives)
}

fn required<'a>(directives: &'a [Directive], name: &str, kind: &str) -> Result<&'a str, LoadError> {
    directive_value_from(directives, name)
        .ok_or_else(|| LoadError::Semantic(format!("{kind} requires {name}")))
}

fn directive_value(object: &ObjectDefinition, name: &str) -> Option<&str> {
    directive_value_from(&object.directives, name)
}

fn directive_value_from<'a>(directives: &'a [Directive], name: &str) -> Option<&'a str> {
    directives
        .iter()
        .rev()
        .find(|directive| directive.name == name)
        .map(|directive| directive.value.as_str())
}

fn parse_u32(value: &str) -> Result<u32, LoadError> {
    value
        .parse()
        .map_err(|_| LoadError::Semantic(format!("invalid max_check_attempts: {value}")))
}

fn parse_interval_seconds(value: &str) -> Result<u64, LoadError> {
    let minutes: u64 = value
        .parse()
        .map_err(|_| LoadError::Semantic(format!("invalid check_interval: {value}")))?;
    Ok(minutes.saturating_mul(60).max(1))
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
            && path.extension().is_some_and(|extension| extension == "cfg")
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
    use std::{collections::HashMap, fs};

    use super::{
        build_monitoring_config, load_config_tree, parse_objects, Directive, ObjectDefinition,
    };

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
                    Directive {
                        name: "host_name".into(),
                        value: "router-01".into(),
                        line: 4
                    },
                    Directive {
                        name: "service_description".into(),
                        value: "HTTP health".into(),
                        line: 5
                    },
                    Directive {
                        name: "_DETAIL".into(),
                        value: "value;kept #kept".into(),
                        line: 6
                    },
                    Directive {
                        name: "contacts".into(),
                        value: "alice".into(),
                        line: 7
                    },
                    Directive {
                        name: "contacts".into(),
                        value: "bob".into(),
                        line: 8
                    },
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

    #[test]
    fn resolves_service_templates_and_builds_an_executable_model() {
        let objects = parse_objects(
            "objects.cfg",
            "define command {\n command_name check_dummy\n command_line printf 'OK'\n}\n\
             define host {\n host_name edge\n address 192.0.2.10\n}\n\
             define service {\n name generic\n register 0\n max_check_attempts 5\n}\n\
             define service {\n use generic\n host_name edge\n service_description ping\n check_command check_dummy\n}\n",
        )
        .unwrap();
        let model = build_monitoring_config(&super::LoadedConfig {
            files: Vec::new(),
            objects,
            resource_macros: HashMap::new(),
        })
        .unwrap();
        assert_eq!(model.hosts["edge"].address, "192.0.2.10");
        assert_eq!(model.services[0].max_check_attempts, 5);
        assert_eq!(model.commands["check_dummy"].command_line, "printf 'OK'");
    }

    #[test]
    fn preserves_resource_macros_without_parsing_them_as_objects() {
        let macros = super::parse_resource_macros("$USER1$=/opt/plugins\n# comment\n");
        assert_eq!(macros["$USER1$"], "/opt/plugins");
    }
}
