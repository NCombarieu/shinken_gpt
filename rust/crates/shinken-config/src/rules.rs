//! Compiled dependency graphs and notification escalation rules.
use crate::{flag, list, positive, required, semantic, value, Attributes, LoadError, MonitoringConfig};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

pub fn host_key(host: &str) -> String { format!("H:{host}") }
pub fn service_key(host: &str, service: &str) -> String { format!("S:{host}\0{service}") }

#[derive(Clone, Debug)]
pub struct Dependency {
    pub master: String,
    pub execution: BTreeSet<u8>,
    pub notification: BTreeSet<u8>,
    pub period: String,
    pub inherits_parent: bool,
}
#[derive(Clone, Debug, Default)]
pub struct Dependencies {
    pub edges: BTreeMap<String, Vec<Dependency>>,
    pub parents: BTreeMap<String, Vec<String>>,
    pub soft_states: bool,
    pub translate_passive_hosts: bool,
}
#[derive(Clone, Debug)]
pub struct Escalation {
    pub contacts: Vec<String>,
    pub first: u32,
    pub last: u32,
    pub first_ms: Option<u64>,
    pub last_ms: u64,
    pub interval_ms: Option<u64>,
    pub period: String,
    pub options: BTreeSet<char>,
}
impl Escalation {
    pub fn matches(&self, number: u32, elapsed_ms: u64, option: char) -> bool {
        let range = if let Some(first) = self.first_ms {
            elapsed_ms >= first && (self.last_ms == 0 || elapsed_ms <= self.last_ms)
        } else {
            number >= self.first && (self.last == 0 || number <= self.last)
        };
        range && self.options.contains(&option)
    }
}
pub(crate) fn acyclic(graph: &BTreeMap<String, Vec<String>>, label: &str) -> Result<(), LoadError> {
    // Kahn's algorithm avoids overflowing the stack on large configuration trees.
    let mut indegree = BTreeMap::<String, usize>::new();
    for (node, next) in graph {
        indegree.entry(node.clone()).or_default();
        for target in next { *indegree.entry(target.clone()).or_default() += 1; }
    }
    let mut queue: VecDeque<_> = indegree.iter().filter(|(_, n)| **n == 0).map(|(k, _)| k.clone()).collect();
    let mut count = 0;
    while let Some(node) = queue.pop_front() {
        count += 1;
        for next in graph.get(&node).into_iter().flatten() {
            let n = indegree.get_mut(next).expect("graph node");
            *n -= 1;
            if *n == 0 { queue.push_back(next.clone()); }
        }
    }
    if count != indegree.len() { return Err(semantic(format!("{label} cycle"))); }
    Ok(())
}
pub(crate) fn select_hosts(a: &Attributes, prefix: &str, m: &MonitoringConfig) -> Result<BTreeSet<String>, LoadError> {
    let mut selected = BTreeSet::new();
    let mut excluded = BTreeSet::new();
    for token in list(value(a, &format!("{prefix}host_name"), "")) {
        let (negative, name) = token.strip_prefix('!').map_or((false, token), |n| (true, n));
        let target = if negative { &mut excluded } else { &mut selected };
        if name == "*" { target.extend(m.hosts.keys().cloned()); }
        else if m.hosts.contains_key(name) { target.insert(name.to_owned()); }
        else { return Err(semantic(format!("unknown host {name}"))); }
    }
    for token in list(value(a, &format!("{prefix}hostgroup_name"), "")) {
        let (negative, name) = token.strip_prefix('!').map_or((false, token), |n| (true, n));
        let target = if negative { &mut excluded } else { &mut selected };
        if name == "*" { target.extend(m.hostgroups.values().flatten().cloned()); }
        else { target.extend(m.hostgroups.get(name).ok_or_else(|| semantic(format!("unknown hostgroup {name}")))?.iter().cloned()); }
    }
    Ok(selected.difference(&excluded).cloned().collect())
}
fn select_objects(a: &Attributes, prefix: &str, service: bool, m: &MonitoringConfig) -> Result<BTreeSet<String>, LoadError> {
    let hosts = select_hosts(a, prefix, m)?;
    if !service { return Ok(hosts.iter().map(|h| host_key(h)).collect()); }
    let mut selected = BTreeSet::new();
    let mut excluded = BTreeSet::new();
    for token in list(value(a, &format!("{prefix}service_description"), "")) {
        let (negative, name) = token.strip_prefix('!').map_or((false, token), |n| (true, n));
        let target = if negative { &mut excluded } else { &mut selected };
        for host in &hosts {
            let matches: Vec<_> = m.services.iter().filter(|s| &s.host_name == host && (name == "*" || s.description == name)).collect();
            if matches.is_empty() && name != "*" { return Err(semantic(format!("unknown service {host}/{name}"))); }
            target.extend(matches.iter().map(|s| service_key(host, &s.description)));
        }
    }
    for token in list(value(a, &format!("{prefix}servicegroup_name"), "")) {
        let (negative, name) = token.strip_prefix('!').map_or((false, token), |n| (true, n));
        let target = if negative { &mut excluded } else { &mut selected };
        if name == "*" {
            target.extend(m.servicegroups.values().flatten().map(|(h,s)| service_key(h,s)));
        } else {
            target.extend(m.servicegroups.get(name).ok_or_else(|| semantic(format!("unknown servicegroup {name}")))?.iter().map(|(h,s)| service_key(h,s)));
        }
    }
    Ok(selected.difference(&excluded).cloned().collect())
}
fn criteria(a: &Attributes, key: &str, service: bool) -> Result<BTreeSet<u8>, LoadError> {
    let mut result = BTreeSet::new();
    let raw = value(a, key, "n");
    if raw == "n" { return Ok(result); }
    for token in list(raw) {
        let code = match (service, token) {
            (_, "o") => 0, (true, "w") | (false, "d") => 1,
            (true, "c") | (false, "u") => 2, (true, "u") => 3, (_, "p") => 4,
            _ => return Err(semantic(format!("invalid {key}: {token}"))),
        };
        result.insert(code);
    }
    Ok(result)
}
pub(crate) fn dependencies(resolved: &[(&str, Attributes)], settings: &Attributes, m: &MonitoringConfig) -> Result<Dependencies, LoadError> {
    let mut output = Dependencies {
        soft_states: flag(settings, "soft_state_dependencies", false)?,
        translate_passive_hosts: flag(settings, "translate_passive_host_checks", false)?,
        ..Dependencies::default()
    };
    for (name, host) in &m.hosts {
        let parents: Vec<_> = list(value(&host.attributes, "parents", "")).map(str::to_owned).collect();
        for parent in &parents {
            if !m.hosts.contains_key(parent) { return Err(semantic(format!("host {name} has unknown parent {parent}"))); }
        }
        output.parents.insert(name.clone(), parents);
    }
    acyclic(&output.parents, "host parent")?;
    let mut total = 0;
    for (kind, a) in resolved {
        if !["hostdependency", "servicedependency"].contains(kind) { continue; }
        let service = *kind == "servicedependency";
        let masters = select_objects(a, "", service, m)?;
        let mut child_attrs = a.clone();
        let same_host = service && flag(a, "explode_hostgroup", false)?;
        if service && !a.keys().any(|k| k.starts_with("dependent_host") || k == "dependent_servicegroup_name") {
            for name in ["host_name", "hostgroup_name"] {
                if let Some(v) = a.get(name) { child_attrs.insert(format!("dependent_{name}"), v.clone()); }
            }
        }
        let children = select_objects(&child_attrs, "dependent_", service, m)?;
        if masters.is_empty() || children.is_empty() { return Err(semantic(format!("{kind} has an empty object selection"))); }
        let period = value(a, "dependency_period", "").to_owned();
        m.periods.validate_use(&period, "")?;
        let execution = criteria(a, "execution_failure_criteria", service)?;
        let notification = criteria(a, "notification_failure_criteria", service)?;
        let inherits_parent = flag(a, "inherits_parent", false)?;
        for child in &children {
            for master in &masters {
                if same_host && child.split('\0').next() != master.split('\0').next() { continue; }
                total += 1;
                if total > 100_000 { return Err(semantic("dependency expansion exceeds 100000 edges")); }
                output.edges.entry(child.clone()).or_default().push(Dependency {
                    master: master.clone(), execution: execution.clone(), notification: notification.clone(),
                    period: period.clone(), inherits_parent,
                });
            }
        }
    }
    let graph = output.edges.iter().map(|(k,v)| (k.clone(), v.iter().map(|d| d.master.clone()).collect())).collect();
    acyclic(&graph, "dependency")?;
    Ok(output)
}
fn escalation(a: &Attributes, host: bool, m: &MonitoringConfig) -> Result<Escalation, LoadError> {
    let integer = |key: &str, fallback| value(a, key, fallback).parse::<u32>().map_err(|_| semantic(format!("invalid {key}")));
    let first = integer("first_notification", "1")?;
    let last = integer("last_notification", "0")?;
    let milliseconds = |key: &str| -> Result<u64, LoadError> {
        Ok((positive(value(a, key, "0"), key, true)? * m.interval_length * 1000.0).round() as u64)
    };
    let first_ms = if a.contains_key("first_notification_time") { Some(milliseconds("first_notification_time")?) } else { None };
    let last_ms = milliseconds("last_notification_time")?;
    if (first_ms.is_none() && last != 0 && last < first) || first_ms.is_some_and(|n| last_ms != 0 && last_ms < n) {
        return Err(semantic("escalation ends before it starts"));
    }
    if a.contains_key("last_notification_time") && first_ms.is_none() {
        return Err(semantic("last_notification_time needs first_notification_time"));
    }
    let mut contacts: BTreeSet<_> = list(value(a, "contacts", "")).map(str::to_owned).collect();
    for group in list(value(a, "contact_groups", "")) {
        contacts.extend(m.contactgroups.get(group).ok_or_else(|| semantic(format!("unknown contactgroup {group}")))?.iter().cloned());
    }
    for name in &contacts { if !m.contacts.contains_key(name) { return Err(semantic(format!("unknown escalation contact {name}"))); } }
    if contacts.is_empty() { return Err(semantic("escalation requires contacts or contact_groups")); }
    let period = value(a, "escalation_period", "").to_owned();
    m.periods.validate_use(&period, "")?;
    Ok(Escalation {
        contacts: contacts.into_iter().collect(), first, last, first_ms, last_ms, period,
        interval_ms: a.get("notification_interval").map(|_| milliseconds("notification_interval")).transpose()?,
        options: crate::notification::options(a, "escalation_options", host)?,
    })
}
pub(crate) fn escalations(resolved: &[(&str, Attributes)], m: &MonitoringConfig) -> Result<BTreeMap<String, Vec<Escalation>>, LoadError> {
    let mut result = BTreeMap::<String, Vec<Escalation>>::new();
    let mut named = BTreeMap::new();
    for (kind, a) in resolved {
        if *kind == "escalation" {
            let name = required(a, "escalation_name")?;
            if named.insert(name, a).is_some() { return Err(semantic(format!("duplicate escalation {name}"))); }
        }
        if ["hostescalation", "serviceescalation"].contains(kind) {
            let host = *kind == "hostescalation";
            let selected = select_objects(a, "", !host, m)?;
            if selected.is_empty() { return Err(semantic(format!("{kind} selects no objects"))); }
            let rule = escalation(a, host, m)?;
            for key in selected { result.entry(key).or_default().push(rule.clone()); }
        }
    }
    for (key, host, a) in m.hosts.values().map(|h| (host_key(&h.name), true, &h.attributes))
        .chain(m.services.iter().map(|s| (service_key(&s.host_name, &s.description), false, &s.attributes))) {
        for name in list(value(a, "escalations", "")) {
            let attrs = named.get(name).ok_or_else(|| semantic(format!("unknown escalation {name}")))?;
            result.entry(key.clone()).or_default().push(escalation(attrs, host, m)?);
        }
    }
    Ok(result)
}
pub(crate) fn validate_handlers(resolved: &[(&str, Attributes)], settings: &Attributes, m: &MonitoringConfig) -> Result<(), LoadError> {
    let check = |command: &str| -> Result<(), LoadError> {
        if !command.is_empty() && !m.commands.contains_key(command.split('!').next().unwrap_or("")) {
            return Err(semantic(format!("unknown event handler command {command}")));
        }
        Ok(())
    };
    for key in ["global_host_event_handler", "global_service_event_handler"] { check(value(settings, key, ""))?; }
    for (_, a) in resolved.iter().filter(|(kind,_)| ["host", "service"].contains(kind)) {
        flag(a, "event_handler_enabled", true)?;
        check(value(a, "event_handler", ""))?;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use crate::{build_monitoring_config, parse_objects, LoadedConfig};
    fn compile(input: &str) -> Result<crate::MonitoringConfig, crate::LoadError> {
        build_monitoring_config(&LoadedConfig {
            objects: parse_objects("rules.cfg", input).unwrap(), ..LoadedConfig::default()
        })
    }
    #[test]
    fn graph_errors_and_criteria_are_rejected() {
        let hosts = "define host {\n host_name a\n}\ndefine host {\n host_name b\n}\n";
        let edge = |master, child, criteria| format!(
            "define hostdependency {{\n host_name {master}\n dependent_host_name {child}\n execution_failure_criteria {criteria}\n}}\n");
        let valid = format!("{hosts}{}", edge("a", "b", "d,p"));
        let m = compile(&valid).unwrap();
        assert_eq!(m.dependencies.edges["H:b"][0].execution.len(), 2);
        assert!(compile(&format!("{valid}{}", edge("b","a","d"))).unwrap_err().to_string().contains("cycle"));
        assert!(compile(&format!("{hosts}{}", edge("missing","b","d"))).is_err());
        assert!(compile(&format!("{hosts}{}", edge("a","b","c"))).is_err());
        assert!(compile("define host {\n host_name a\n parents b\n}\ndefine host {\n host_name b\n parents a\n}\n").is_err());
    }
    #[test]
    fn nested_groups_and_wildcard_selection_expand_before_rules() {
        let m = compile("define host {\n host_name a\n}\ndefine host {\n host_name b\n}\ndefine hostgroup {\n hostgroup_name all\n members *\n}\ndefine service {\n hostgroup_name *\n service_description ping\n}\ndefine servicegroup {\n servicegroup_name first\n members a,ping\n}\ndefine servicegroup {\n servicegroup_name second\n members b,ping\n servicegroup_members first\n}\ndefine contact {\n contact_name operator\n}\ndefine contactgroup {\n contactgroup_name base\n members operator\n}\ndefine contactgroup {\n contactgroup_name nested\n contactgroup_members base\n}\ndefine serviceescalation {\n servicegroup_name second\n first_notification 2\n contact_groups nested\n}\n").unwrap();
        assert_eq!(m.services.len(),2);
        assert_eq!(m.servicegroups["second"].len(),2);
        assert_eq!(m.contactgroups["nested"], ["operator"]);
        assert_eq!(m.escalations.len(),2);
        assert!(m.escalations["S:a\0ping"][0].matches(2,0,'c'));
        assert!(!m.escalations["S:a\0ping"][0].matches(1,0,'c'));
    }
    #[test]
    fn named_time_escalations_and_unknown_handlers() {
        let input = "define contact {\n contact_name operator\n}\ndefine escalation {\n escalation_name late\n first_notification_time 1\n last_notification_time 2\n contacts operator\n}\ndefine host {\n host_name a\n escalations late\n}\n";
        let m = compile(input).unwrap();
        let e = &m.escalations["H:a"][0];
        assert!(!e.matches(99,59_999,'d'));
        assert!(e.matches(1,60_000,'d'));
        assert!(!e.matches(1,120_001,'d'));
        assert!(compile("define host {\n host_name a\n event_handler missing\n}\n").is_err());
        assert!(compile("define contact {\n contact_name duplicate\n}\ndefine contact {\n contact_name duplicate\n}\n").is_err());
    }
}
