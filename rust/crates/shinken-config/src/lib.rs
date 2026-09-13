//! Configuration front end for the standalone engine.
//! Files are read in include order. Object syntax is retained for diagnostics;
//! runtime support is reported separately from successful parsing.

use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
};
use thiserror::Error;

pub type Attributes = BTreeMap<String, String>;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Directive {
    pub name: String,
    pub value: String,
    pub line: usize,
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ObjectDefinition {
    pub kind: String,
    pub directives: Vec<Directive>,
    pub line: usize,
    pub source: PathBuf,
}
#[derive(Clone, Debug, Default)]
pub struct LoadedConfig {
    pub files: Vec<PathBuf>,
    pub objects: Vec<ObjectDefinition>,
    pub resource_macros: Attributes,
    pub settings: Attributes,
}
#[derive(Debug, Error)]
#[error("{path}:{line}: {message}", path = path.display())]
pub struct ParseError {
    pub path: PathBuf,
    pub line: usize,
    pub message: String,
}
#[derive(Debug, Error)]
pub enum LoadError {
    #[error("cannot read {path}: {source}", path = path.display())]
    Io {
        path: PathBuf,
        source: std::io::Error,
    },
    #[error(transparent)]
    Parse(#[from] ParseError),
    #[error("invalid configuration: {0}")]
    Semantic(String),
}
fn semantic(message: impl Into<String>) -> LoadError {
    LoadError::Semantic(message.into())
}
fn io_error(path: &Path, source: std::io::Error) -> LoadError {
    LoadError::Io {
        path: path.to_path_buf(),
        source,
    }
}

/// Shinken terminates a directive at an unescaped semicolon, even in quotes.
fn uncomment(line: &str) -> String {
    let mut output = String::new();
    for c in line.chars() {
        if c == ';' {
            if output.ends_with('\\') {
                output.pop();
            } else {
                break;
            }
        }
        output.push(c);
    }
    output
}

type Document = (Vec<ObjectDefinition>, Vec<(String, String)>);
fn parse_document(path: &Path, input: &str) -> Result<Document, ParseError> {
    let error = |line, message: &str| ParseError {
        path: path.to_path_buf(),
        line,
        message: message.to_owned(),
    };
    let mut objects = Vec::new();
    let mut globals = Vec::new();
    let mut current: Option<ObjectDefinition> = None;
    let mut opening_brace = false;
    let mut continuation = String::new();
    let mut first_line = 0;
    for (offset, raw) in input.lines().enumerate() {
        let line = offset + 1;
        let clean = uncomment(raw);
        let clean = clean.trim();
        if clean.starts_with('#') || clean.is_empty() {
            continue;
        }
        if continuation.is_empty() {
            first_line = line;
        }
        if let Some(part) = clean.strip_suffix('\\') {
            continuation.push_str(part);
            continue;
        }
        continuation.push_str(clean);
        let text = std::mem::take(&mut continuation);
        let text = text.trim();
        if opening_brace {
            if text != "{" {
                return Err(error(line, "expected opening brace"));
            }
            opening_brace = false;
            continue;
        }
        if text == "}" {
            objects.push(
                current
                    .take()
                    .ok_or_else(|| error(line, "unexpected closing brace"))?,
            );
        } else if text.starts_with("define ") || text.starts_with("define\t") {
            if current.is_some() {
                return Err(error(line, "nested object definition"));
            }
            let header = text[6..].trim();
            let empty = header.ends_with("{}");
            let has_brace = empty || header.ends_with('{');
            let kind = if empty {
                &header[..header.len() - 2]
            } else if has_brace {
                &header[..header.len() - 1]
            } else {
                header
            };
            let kind = kind.trim();
            if kind.is_empty() || kind.contains(char::is_whitespace) {
                return Err(error(line, "expected one object type after define"));
            }
            let object = ObjectDefinition {
                kind: kind.to_owned(),
                directives: Vec::new(),
                line: first_line,
                source: path.to_path_buf(),
            };
            if empty {
                objects.push(object);
            } else {
                current = Some(object);
                opening_brace = !has_brace;
            }
        } else if let Some(object) = &mut current {
            let (name, value) = match text.find(char::is_whitespace) {
                Some(i) => (&text[..i], text[i..].trim()),
                None => (text, ""),
            };
            object.directives.push(Directive {
                name: name.to_owned(),
                value: value.to_owned(),
                line: first_line,
            });
        } else if let Some((key, value)) = text.split_once('=') {
            if key.trim().is_empty() || value.trim().is_empty() {
                return Err(error(line, "global directive needs a name and value"));
            }
            globals.push((key.trim().to_owned(), value.trim().to_owned()));
        } else {
            return Err(error(
                line,
                "expected object definition or name=value directive",
            ));
        }
    }
    if !continuation.is_empty() {
        return Err(error(first_line, "unfinished continuation"));
    }
    if let Some(object) = current {
        return Err(error(object.line, "unclosed object"));
    }
    Ok((objects, globals))
}

pub fn parse_objects(
    path: impl AsRef<Path>,
    input: &str,
) -> Result<Vec<ObjectDefinition>, ParseError> {
    parse_document(path.as_ref(), input).map(|(objects, _)| objects)
}

pub fn load_config_tree(main: impl AsRef<Path>) -> Result<LoadedConfig, LoadError> {
    let mut loader = Loader::default();
    loader.file(main.as_ref())?;
    Ok(loader.loaded)
}
#[derive(Default)]
struct Loader {
    loaded: LoadedConfig,
    files: BTreeSet<PathBuf>,
    directories: BTreeSet<PathBuf>,
}
impl Loader {
    fn file(&mut self, path: &Path) -> Result<(), LoadError> {
        let path = fs::canonicalize(path).map_err(|e| io_error(path, e))?;
        if !self.files.insert(path.clone()) {
            return Ok(());
        }
        let input = fs::read_to_string(&path).map_err(|e| io_error(&path, e))?;
        let (objects, globals) = parse_document(&path, &input)?;
        self.loaded.files.push(path.clone());
        self.loaded.objects.extend(objects);
        let base = path.parent().unwrap_or(Path::new("."));
        for (key, value) in globals {
            match key.as_str() {
                "cfg_file" | "resource_file" => self.file(&base.join(value))?,
                "cfg_dir" => self.directory(&base.join(value))?,
                _ if key.starts_with('$') && key.ends_with('$') => {
                    self.loaded.resource_macros.insert(key, value);
                }
                _ => {
                    self.loaded.settings.insert(key, value);
                }
            }
        }
        Ok(())
    }
    fn directory(&mut self, path: &Path) -> Result<(), LoadError> {
        let canonical = fs::canonicalize(path).map_err(|e| io_error(path, e))?;
        if !self.directories.insert(canonical.clone()) {
            return Ok(());
        }
        let mut entries = fs::read_dir(&canonical)
            .map_err(|e| io_error(path, e))?
            .map(|entry| entry.map(|e| e.path()))
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| io_error(path, e))?;
        entries.sort();
        for entry in entries {
            let metadata = fs::metadata(&entry).map_err(|e| io_error(&entry, e))?;
            if metadata.is_dir() {
                self.directory(&entry)?;
            } else if metadata.is_file() && entry.extension().is_some_and(|v| v == "cfg") {
                self.file(&entry)?;
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct CheckConfig {
    pub command: String,
    pub interval_ms: u64,
    pub retry_ms: u64,
    pub timeout_ms: u64,
    pub max_attempts: u32,
    pub active: bool,
    pub passive: bool,
}
#[derive(Clone, Debug)]
pub struct CommandConfig {
    pub name: String,
    pub command_line: String,
}
#[derive(Clone, Debug)]
pub struct HostConfig {
    pub name: String,
    pub address: String,
    pub check: CheckConfig,
    pub attributes: Attributes,
}
#[derive(Clone, Debug)]
pub struct ServiceConfig {
    pub host_name: String,
    pub description: String,
    pub check: CheckConfig,
    pub attributes: Attributes,
}
#[derive(Clone, Debug)]
pub struct MonitoringConfig {
    pub commands: BTreeMap<String, CommandConfig>,
    pub hosts: BTreeMap<String, HostConfig>,
    pub services: Vec<ServiceConfig>,
    pub hostgroups: BTreeMap<String, Vec<String>>,
    pub servicegroups: BTreeMap<String, Vec<(String, String)>>,
    pub contactgroups: BTreeMap<String, Vec<String>>,
    pub contacts: BTreeMap<String, Attributes>,
    pub resource_macros: Attributes,
    pub interval_length: f64,
    pub max_output_bytes: usize,
    pub warnings: Vec<String>,
    pub execute_host_checks: bool,
    pub execute_service_checks: bool,
    pub accept_passive_host_checks: bool,
    pub accept_passive_service_checks: bool,
}
fn attrs(object: &ObjectDefinition) -> Attributes {
    object
        .directives
        .iter()
        .map(|d| (d.name.clone(), d.value.clone()))
        .collect()
}
fn list(value: &str) -> impl Iterator<Item = &str> {
    value.split(',').map(str::trim).filter(|s| !s.is_empty())
}
fn required<'a>(a: &'a Attributes, key: &str) -> Result<&'a str, LoadError> {
    a.get(key)
        .map(String::as_str)
        .filter(|s| !s.is_empty())
        .ok_or_else(|| semantic(format!("missing {key}")))
}
fn value<'a>(a: &'a Attributes, key: &str, fallback: &'a str) -> &'a str {
    a.get(key).map(String::as_str).unwrap_or(fallback)
}
fn positive(value: &str, name: &str, zero: bool) -> Result<f64, LoadError> {
    let n = value
        .parse::<f64>()
        .map_err(|_| semantic(format!("invalid {name}: {value}")))?;
    if !n.is_finite() || n < 0.0 || (!zero && n == 0.0) || n > 31_536_000.0 {
        return Err(semantic(format!("invalid {name}: {value}")));
    }
    Ok(n)
}
fn flag(a: &Attributes, name: &str, default: bool) -> Result<bool, LoadError> {
    match a.get(name).map(String::as_str) {
        None => Ok(default),
        Some("0") => Ok(false),
        Some("1") => Ok(true),
        Some(v) => Err(semantic(format!("{name} must be 0 or 1, got {v}"))),
    }
}
fn check(
    a: &Attributes,
    globals: &Attributes,
    interval: f64,
    host: bool,
) -> Result<CheckConfig, LoadError> {
    let timeout_key = if host {
        "host_check_timeout"
    } else {
        "service_check_timeout"
    };
    let max_attempts = value(a, "max_check_attempts", "3")
        .parse::<u32>()
        .map_err(|_| semantic("invalid max_check_attempts"))?;
    if max_attempts == 0 {
        return Err(semantic("max_check_attempts must be positive"));
    }
    let command = value(a, "check_command", "").to_owned();
    let active = flag(a, "active_checks_enabled", !command.is_empty())?;
    if active && command.is_empty() {
        return Err(semantic("active object has no check_command"));
    }
    Ok(CheckConfig {
        command,
        interval_ms: (positive(value(a, "check_interval", "5"), "check_interval", true)?
            * interval
            * 1000.0)
            .round() as u64,
        retry_ms: (positive(value(a, "retry_interval", "1"), "retry_interval", false)?
            * interval
            * 1000.0)
            .round()
            .max(1.0) as u64,
        timeout_ms: (positive(value(globals, timeout_key, "60"), timeout_key, false)? * 1000.0)
            .round()
            .max(1.0) as u64,
        max_attempts,
        active,
        passive: flag(a, "passive_checks_enabled", true)?,
    })
}
type Templates = BTreeMap<(String, String), Attributes>;
fn resolve(
    kind: &str,
    own: &Attributes,
    templates: &Templates,
    visiting: &mut BTreeSet<(String, String)>,
) -> Result<Attributes, LoadError> {
    let mut result = Attributes::new();
    for parent in list(value(own, "use", "")) {
        let key = (kind.to_owned(), parent.to_owned());
        if !visiting.insert(key.clone()) {
            return Err(semantic(format!("template cycle: {kind}/{parent}")));
        }
        let inherited = resolve(
            kind,
            templates
                .get(&key)
                .ok_or_else(|| semantic(format!("unknown template {kind}/{parent}")))?,
            templates,
            visiting,
        )?;
        for (k, v) in inherited {
            if k != "name" && k != "register" && k != "use" {
                result.entry(k).or_insert(v);
            }
        }
        visiting.remove(&key);
    }
    for (key, v) in own {
        if let Some(extra) = v.strip_prefix('+') {
            let base = result.entry(key.clone()).or_default();
            if !base.is_empty() && !extra.is_empty() {
                base.push(',');
            }
            base.push_str(extra);
        } else if v == "null" {
            result.remove(key);
        } else {
            result.insert(key.clone(), v.clone());
        }
    }
    Ok(result)
}
fn group_members(
    name: &str,
    groups: &BTreeMap<String, Attributes>,
    visiting: &mut BTreeSet<String>,
) -> Result<BTreeSet<String>, LoadError> {
    if !visiting.insert(name.to_owned()) {
        return Err(semantic(format!("hostgroup cycle: {name}")));
    }
    let a = groups
        .get(name)
        .ok_or_else(|| semantic(format!("unknown hostgroup {name}")))?;
    let mut result: BTreeSet<String> = list(value(a, "members", "")).map(str::to_owned).collect();
    for child in list(value(a, "hostgroup_members", "")) {
        result.extend(group_members(child, groups, visiting)?);
    }
    visiting.remove(name);
    Ok(result)
}
pub fn build_monitoring_config(loaded: &LoadedConfig) -> Result<MonitoringConfig, LoadError> {
    let mut templates = Templates::new();
    for o in &loaded.objects {
        let a = attrs(o);
        if let Some(name) = a.get("name") {
            if templates
                .insert((o.kind.clone(), name.clone()), a.clone())
                .is_some()
            {
                return Err(semantic(format!("duplicate template {}/{name}", o.kind)));
            }
        }
    }
    let mut resolved = Vec::new();
    for o in &loaded.objects {
        let own = attrs(o);
        let a = resolve(&o.kind, &own, &templates, &mut BTreeSet::new())
            .map_err(|e| semantic(format!("{}:{}: {e}", o.source.display(), o.line)))?;
        // register is an object-local property; a template cannot suppress its children.
        if value(&own, "register", "1") != "0" {
            resolved.push((o.kind.as_str(), a));
        }
    }
    let interval_length = positive(
        value(&loaded.settings, "interval_length", "60"),
        "interval_length",
        false,
    )?;
    let output_bytes = value(&loaded.settings, "max_plugins_output_length", "65536")
        .parse::<usize>()
        .map_err(|_| semantic("invalid max_plugins_output_length"))?;
    if !(1..=16_777_216).contains(&output_bytes) {
        return Err(semantic(
            "max_plugins_output_length must be between 1 and 16777216",
        ));
    }
    let mut model = MonitoringConfig {
        commands: BTreeMap::new(),
        hosts: BTreeMap::new(),
        services: Vec::new(),
        contacts: BTreeMap::new(),
        hostgroups: BTreeMap::new(),
        servicegroups: BTreeMap::new(),
        contactgroups: BTreeMap::new(),
        resource_macros: loaded.resource_macros.clone(),
        interval_length,
        max_output_bytes: output_bytes,
        warnings: Vec::new(),
        execute_host_checks: flag(&loaded.settings, "execute_host_checks", true)?,
        execute_service_checks: flag(&loaded.settings, "execute_service_checks", true)?,
        accept_passive_host_checks: flag(&loaded.settings, "accept_passive_host_checks", true)?,
        accept_passive_service_checks: flag(
            &loaded.settings,
            "accept_passive_service_checks",
            true,
        )?,
    };
    let mut groups = BTreeMap::new();
    let mut contactgroups: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut unsupported = BTreeSet::new();
    for (kind, a) in &resolved {
        match *kind {
            "command" => {
                let name = required(a, "command_name")?.to_owned();
                let command = CommandConfig {
                    name: name.clone(),
                    command_line: required(a, "command_line")?.to_owned(),
                };
                if model.commands.insert(name.clone(), command).is_some() {
                    return Err(semantic(format!("duplicate command {name}")));
                }
            }
            "host" => {
                let name = required(a, "host_name")?.to_owned();
                let host = HostConfig {
                    name: name.clone(),
                    address: value(a, "address", &name).to_owned(),
                    check: check(a, &loaded.settings, interval_length, true)?,
                    attributes: a.clone(),
                };
                if model.hosts.insert(name.clone(), host).is_some() {
                    return Err(semantic(format!("duplicate host {name}")));
                }
            }
            "hostgroup" => {
                groups.insert(required(a, "hostgroup_name")?.to_owned(), a.clone());
            }
            "contact" => {
                model
                    .contacts
                    .insert(required(a, "contact_name")?.to_owned(), a.clone());
            }
            "contactgroup" => {
                if a.contains_key("contactgroup_members") {
                    return Err(semantic("nested contactgroups are not implemented"));
                }
                let name = required(a, "contactgroup_name")?;
                if contactgroups
                    .insert(
                        name.to_owned(),
                        list(value(a, "members", "")).map(str::to_owned).collect(),
                    )
                    .is_some()
                {
                    return Err(semantic(format!("duplicate contactgroup {name}")));
                }
            }
            "timeperiod" => {
                if value(a, "timeperiod_name", "") == "24x7" {
                    let days = [
                        "monday",
                        "tuesday",
                        "wednesday",
                        "thursday",
                        "friday",
                        "saturday",
                        "sunday",
                    ];
                    if days.iter().any(|day| value(a, day, "") != "00:00-24:00")
                        || a.keys().any(|key| {
                            !days.contains(&key.as_str())
                                && !["timeperiod_name", "name", "alias", "register", "use"]
                                    .contains(&key.as_str())
                        })
                    {
                        return Err(semantic("24x7 must cover every day without exceptions"));
                    }
                }
            }
            "service" | "servicegroup" => {}
            _ => {
                unsupported.insert(kind.to_string());
            }
        }
    }
    for host in model.hosts.values() {
        for group in list(value(&host.attributes, "hostgroups", "")) {
            let g = groups.entry(group.to_owned()).or_default();
            let members = g.entry("members".to_owned()).or_default();
            if !members.is_empty() {
                members.push(',');
            }
            members.push_str(&host.name);
        }
    }
    for name in groups.keys() {
        let members = group_members(name, &groups, &mut BTreeSet::new())?;
        for host in &members {
            if !model.hosts.contains_key(host) {
                return Err(semantic(format!(
                    "hostgroup {name} references unknown host {host}"
                )));
            }
        }
        model
            .hostgroups
            .insert(name.clone(), members.into_iter().collect());
    }
    let mut service_keys = BTreeSet::new();
    for (kind, a) in &resolved {
        if *kind != "service" {
            continue;
        }
        let mut selected = BTreeSet::new();
        let mut excluded = BTreeSet::new();
        for host in list(value(a, "host_name", "")) {
            if host == "*" {
                selected.extend(model.hosts.keys().cloned());
            } else if let Some(exclude) = host.strip_prefix('!') {
                excluded.insert(exclude.to_owned());
            } else {
                selected.insert(host.to_owned());
            }
        }
        for group in list(value(a, "hostgroup_name", "")) {
            let (negative, name) = match group.strip_prefix('!') {
                Some(name) => (true, name),
                None => (false, group),
            };
            let members = model
                .hostgroups
                .get(name)
                .ok_or_else(|| semantic(format!("unknown hostgroup {name}")))?;
            if negative {
                excluded.extend(members.iter().cloned());
            } else {
                selected.extend(members.iter().cloned());
            }
        }
        let description = required(a, "service_description")?;
        if selected.is_empty() && value(a, "hostgroup_name", "").is_empty() {
            return Err(semantic(format!(
                "service {description} has no host selector"
            )));
        }
        for host in selected.difference(&excluded) {
            if !model.hosts.contains_key(host) {
                return Err(semantic(format!(
                    "service {description} references unknown host {host}"
                )));
            }
            if !service_keys.insert((host.clone(), description.to_owned())) {
                return Err(semantic(format!("duplicate service {host}/{description}")));
            }
            model.services.push(ServiceConfig {
                host_name: host.clone(),
                description: description.to_owned(),
                check: check(a, &loaded.settings, interval_length, false)?,
                attributes: a.clone(),
            });
        }
    }
    for (kind, a) in &resolved {
        if *kind == "servicegroup" {
            let name = required(a, "servicegroup_name")?;
            if a.contains_key("servicegroup_members") {
                return Err(semantic("nested servicegroups are not implemented"));
            }
            let entries: Vec<_> = list(value(a, "members", "")).collect();
            if entries.len() % 2 != 0 {
                return Err(semantic(format!(
                    "servicegroup {name} members must be host,service pairs"
                )));
            }
            let mut pairs = Vec::new();
            for pair in entries.chunks_exact(2) {
                let pair = (pair[0].to_owned(), pair[1].to_owned());
                if !service_keys.contains(&pair) {
                    return Err(semantic(format!(
                        "servicegroup {name} references unknown service"
                    )));
                }
                pairs.push(pair);
            }
            if model.servicegroups.insert(name.into(), pairs).is_some() {
                return Err(semantic(format!("duplicate servicegroup {name}")));
            }
        }
    }
    for s in &model.services {
        for name in list(value(&s.attributes, "servicegroups", "")) {
            model
                .servicegroups
                .entry(name.into())
                .or_default()
                .push((s.host_name.clone(), s.description.clone()));
        }
    }
    for group in model.servicegroups.values_mut() {
        group.sort();
        group.dedup();
    }
    for (name, a) in &model.contacts {
        for group in list(value(a, "contactgroups", "")) {
            contactgroups
                .entry(group.into())
                .or_default()
                .push(name.clone());
        }
    }
    for group in contactgroups.values_mut() {
        group.sort();
        group.dedup();
        for name in group.iter() {
            if !model.contacts.contains_key(name) {
                return Err(semantic(format!("unknown contact {name}")));
            }
        }
    }
    model.contactgroups = contactgroups.clone();
    for (name, c, a) in model
        .hosts
        .values()
        .map(|h| (h.name.as_str(), &h.check, &h.attributes))
        .chain(
            model
                .services
                .iter()
                .map(|s| (s.description.as_str(), &s.check, &s.attributes)),
        )
    {
        if name.contains(['\0', ';']) {
            return Err(semantic(
                "host/service names cannot contain NUL or semicolons",
            ));
        }
        for group in list(value(a, "contact_groups", "")) {
            if !contactgroups.contains_key(group) {
                return Err(semantic(format!("unknown contactgroup {group}")));
            }
        }
        for contact in list(value(a, "contacts", "")) {
            if !model.contacts.contains_key(contact) {
                return Err(semantic(format!("unknown contact {contact}")));
            }
        }
        if !c.command.is_empty()
            && !model
                .commands
                .contains_key(c.command.split('!').next().unwrap_or(""))
        {
            return Err(semantic(format!(
                "{name} references unknown check command {}",
                c.command
            )));
        }
        if !["", "24x7"].contains(&value(a, "check_period", "")) {
            return Err(semantic(format!("{name}: check_period {} is not supported yet; refusing to run outside the configured period",value(a,"check_period",""))));
        }
    }
    for h in model.hosts.values_mut() {
        expand_contacts(&mut h.attributes, &contactgroups);
    }
    for s in &mut model.services {
        expand_contacts(&mut s.attributes, &contactgroups);
    }
    if !unsupported.is_empty() {
        model.warnings.push(format!(
            "Objects retained as configuration only (not executed): {}",
            unsupported.into_iter().collect::<Vec<_>>().join(", ")
        ));
    }
    model.warnings.push("Notifications, event handlers, dependency logic and flapping detection are not implemented in this alpha.".to_owned());
    model
        .services
        .sort_by(|a, b| (&a.host_name, &a.description).cmp(&(&b.host_name, &b.description)));
    Ok(model)
}
fn expand_contacts(a: &mut Attributes, groups: &BTreeMap<String, Vec<String>>) {
    let mut contacts: BTreeSet<String> =
        list(value(a, "contacts", "")).map(str::to_owned).collect();
    for group in list(value(a, "contact_groups", "")) {
        if let Some(members) = groups.get(group) {
            contacts.extend(members.iter().cloned());
        }
    }
    a.insert(
        "contacts".to_owned(),
        contacts.into_iter().collect::<Vec<_>>().join(","),
    );
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn children_are_registered_and_multiple_templates_resolve_in_order() {
        let objects = parse_objects("objects.cfg", "define host {\n name first\n register 0 ; template\n address 192.0.2.1\n}\ndefine host {\n name second\n register 0\n address 192.0.2.2\n}\ndefine host {\n use first,second\n host_name edge\n}\n").unwrap();
        let m = build_monitoring_config(&LoadedConfig {
            objects,
            ..LoadedConfig::default()
        })
        .unwrap();
        assert_eq!(m.hosts["edge"].address, "192.0.2.1");
        assert!(!m.hosts.contains_key("first"));
    }
    #[test]
    fn recursion_resources_symlinks_and_inline_comments() {
        let tmp = tempfile::tempdir().unwrap();
        fs::create_dir_all(tmp.path().join("objects/nested")).unwrap();
        fs::write(
            tmp.path().join("main.cfg"),
            "cfg_dir=objects\nresource_file=resource.cfg\n",
        )
        .unwrap();
        fs::write(
            tmp.path().join("resource.cfg"),
            "$USER1$=/usr/lib/nagios/plugins\n",
        )
        .unwrap();
        fs::write(
            tmp.path().join("objects/nested/host.cfg"),
            "define host{\n host_name edge ; comment\n}\n",
        )
        .unwrap();
        std::os::unix::fs::symlink(
            tmp.path().join("objects"),
            tmp.path().join("objects/nested/loop"),
        )
        .unwrap();
        let loaded = load_config_tree(tmp.path().join("main.cfg")).unwrap();
        assert_eq!(loaded.files.len(), 3);
        assert_eq!(loaded.resource_macros["$USER1$"], "/usr/lib/nagios/plugins");
        assert_eq!(build_monitoring_config(&loaded).unwrap().hosts.len(), 1);
    }
    #[test]
    fn malformed_documents_and_unknown_hosts_fail_explicitly() {
        assert!(parse_objects("bad.cfg", "defin host {\n}\n").is_err());
        let objects = parse_objects(
            "bad.cfg",
            "define service{\n host_name missing\n service_description ping\n}\n",
        )
        .unwrap();
        assert!(build_monitoring_config(&LoadedConfig {
            objects,
            ..LoadedConfig::default()
        })
        .is_err());
    }
    #[test]
    fn escaped_semicolons_and_continuations_preserve_command() {
        let o=parse_objects("command.cfg","define command{\n command_name test\n command_line printf 'OK'\\; \\\nexit 0 ; comment\n}\n").unwrap();
        assert_eq!(o[0].directives[1].value, "printf 'OK'; exit 0");
    }
    #[test]
    fn additive_lists_null_and_template_cycles() {
        let a = Attributes::from([
            ("use".into(), "p".into()),
            ("contacts".into(), "+bob".into()),
            ("address".into(), "null".into()),
        ]);
        let t = Templates::from([(
            ("host".into(), "p".into()),
            Attributes::from([
                ("contacts".into(), "alice".into()),
                ("address".into(), "x".into()),
            ]),
        )]);
        let r = resolve("host", &a, &t, &mut BTreeSet::new()).unwrap();
        assert_eq!(r["contacts"], "alice,bob");
        assert!(!r.contains_key("address"));
        let t = Templates::from([(
            ("host".into(), "p".into()),
            Attributes::from([("use".into(), "p".into())]),
        )]);
        assert!(resolve("host", &a, &t, &mut BTreeSet::new()).is_err());
    }
}
