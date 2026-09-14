use crate::{
    host_key, members, now_ms, numeric, service_key, Definition, Engine, Runtime, Snapshot,
};
use serde_json::{json, Value};
use shinken_livestatus::{execute, Query, QueryError, Row};
use shinken_model::StateType;
use std::collections::BTreeMap;

const TABLES: &[&str] = &[
    "status",
    "hosts",
    "services",
    "hostgroups",
    "servicegroups",
    "contacts",
    "contactgroups",
    "commands",
    "comments",
    "downtimes",
    "log",
    "columns",
];
fn fields(row: &mut Row, names: &str, value: Value) {
    for name in names.split_whitespace() {
        row.insert(name.into(), value.clone());
    }
}
fn put(row: &mut Row, name: &str, value: impl serde::Serialize) {
    row.insert(name.into(), json!(value));
}
fn object_schema() -> Row {
    let mut r = Row::new();
    fields(&mut r,"name host_name description display_name alias address check_command check_period notification_period event_handler plugin_output long_plugin_output perf_data notes notes_expanded notes_url notes_url_expanded action_url action_url_expanded icon_image icon_image_expanded icon_image_alt",json!(""));
    fields(&mut r,"last_event_handler last_event_handler_exit_code execution_dependencies_failed notification_dependencies_failed state state_type last_state last_hard_state hard_state current_attempt max_check_attempts last_check next_check last_update last_state_change last_hard_state_change last_notification current_notification_number check_type check_options has_been_checked is_executing active_checks_enabled checks_enabled accept_passive_checks acknowledged acknowledgement_type notifications_enabled event_handler_enabled flap_detection_enabled is_flapping scheduled_downtime_depth check_freshness obsess_over_host obsess_over_service process_performance_data in_check_period in_notification_period num_services num_services_ok num_services_warn num_services_crit num_services_unknown num_services_pending last_time_up last_time_down last_time_unreachable last_time_ok last_time_warning last_time_critical last_time_unknown",json!(0));
    fields(&mut r,"execution_time latency check_interval retry_interval notification_interval first_notification_delay low_flap_threshold high_flap_threshold percent_state_change",json!(0.0));
    fields(&mut r,"contacts contact_groups groups parents childs services services_with_state services_with_info comments comments_with_info downtimes downtimes_with_info custom_variable_names custom_variable_values modified_attributes_list depends_exec depends_notify",json!([]));
    r
}
fn schema(table: &str) -> Option<Row> {
    let mut r = Row::new();
    match table {
        "hosts" => r = object_schema(),
        "services" => {
            r = object_schema();
            for (name, v) in object_schema() {
                r.insert(format!("host_{name}"), v);
            }
        }
        "status" => {
            fields(&mut r, "program_version livestatus_version", json!(""));
            fields(&mut r,"configuration_reloads last_reload dropped_event_handlers accept_passive_host_checks accept_passive_service_checks check_external_commands check_host_freshness check_service_freshness enable_event_handlers enable_flap_detection enable_notifications execute_host_checks execute_service_checks last_command_check last_log_rotation nagios_pid obsess_over_hosts obsess_over_services process_performance_data program_start num_hosts num_services",json!(0));
            put(&mut r, "interval_length", 0.0);
        }
        "hostgroups" | "servicegroups" => {
            fields(&mut r, "name alias notes notes_url action_url", json!(""));
            fields(&mut r, "members members_with_state", json!([]));
            fields(&mut r,"num_hosts num_hosts_up num_hosts_down num_hosts_unreach num_hosts_pending num_services num_services_ok num_services_warn num_services_crit num_services_unknown num_services_pending num_services_hard_ok num_services_hard_warn num_services_hard_crit num_services_hard_unknown worst_host_state worst_service_state worst_service_hard_state",json!(0));
        }
        "contactgroups" => {
            fields(&mut r, "name alias", json!(""));
            put(&mut r, "members", json!([]));
        }
        "contacts" => {
            fields(&mut r,"name alias email pager service_notification_period host_notification_period address1 address2 address3 address4 address5",json!(""));
            fields(&mut r,"id can_submit_commands host_notifications_enabled service_notifications_enabled in_host_notification_period in_service_notification_period last_update",json!(0));
            fields(&mut r,"groups modified_attributes_list custom_variable_names custom_variable_values host_notification_commands service_notification_commands",json!([]));
        }
        "commands" => {
            fields(&mut r, "name line", json!(""));
        }
        "comments" | "downtimes" => {
            fields(
                &mut r,
                "author comment host_name service_description",
                json!(""),
            );
            fields(&mut r, "id entry_time", json!(0));
            if table == "comments" {
                fields(
                    &mut r,
                    "entry_type expires expire_time persistent source type",
                    json!(0),
                );
            } else {
                fields(
                    &mut r,
                    "start_time end_time fixed triggered_by duration is_in_effect",
                    json!(0),
                );
            }
            for (name, v) in object_schema() {
                r.insert(format!("host_{name}"), v);
            }
            for (name, v) in schema("services").expect("known table") {
                r.insert(format!("service_{name}"), v);
            }
        }
        "log" => {
            fields(&mut r,"type host_name service_description plugin_output message options state_type contact_name",json!(""));
            fields(&mut r, "class time state", json!(0));
        }
        "columns" => {
            fields(&mut r, "table name type description", json!(""));
        }
        _ => return None,
    }
    Some(r)
}
fn contact_visible(d: &Definition, user: Option<&str>, engine: &Engine) -> bool {
    user.is_none_or(|u| {
        members(&d.attributes, "contacts").iter().any(|v| v == u)
            || d.service.is_some()
                && members(&engine.config.hosts[&d.host].attributes, "contacts")
                    .iter()
                    .any(|v| v == u)
    })
}
fn object_row(d: &Definition, r: &Runtime, state: &Snapshot, key: &str, engine: &Engine) -> Row {
    let mut row = object_schema();
    let a = &d.attributes;
    // Configuration metadata is exposed separately from unsupported runtime features.
    for (name, v) in a {
        if row.get(name).is_some_and(Value::is_string) {
            put(&mut row, name, v);
        }
        if [
            "notification_interval",
            "first_notification_delay",
            "low_flap_threshold",
            "high_flap_threshold",
        ]
        .contains(&name.as_str())
        {
            if let Ok(n) = v.parse::<f64>() {
                put(&mut row, name, n);
            }
        }
    }
    put(&mut row, "name", &d.host);
    put(&mut row, "host_name", &d.host);
    if let Some(service) = &d.service {
        put(&mut row, "description", service);
    }
    put(
        &mut row,
        "display_name",
        a.get("display_name")
            .map(String::as_str)
            .unwrap_or(d.service.as_deref().unwrap_or(&d.host)),
    );
    put(&mut row, "alias", a.get("alias").unwrap_or(&d.host));
    put(&mut row, "address", &engine.config.hosts[&d.host].address);
    for name in ["notes", "notes_url", "action_url", "icon_image"] {
        let value = a
            .get(name)
            .cloned()
            .unwrap_or_default()
            .replace("$HOSTNAME$", &d.host)
            .replace("$HOSTADDRESS$", &engine.config.hosts[&d.host].address)
            .replace("$SERVICEDESC$", d.service.as_deref().unwrap_or(""));
        put(&mut row, &format!("{name}_expanded"), value);
    }
    put(&mut row, "check_command", &d.check.command);
    put(&mut row, "event_handler_enabled", u8::from(r.event_handler_enabled.unwrap_or(a.get("event_handler_enabled").is_none_or(|v| v == "1"))));
    put(&mut row, "last_event_handler", r.last_event_handler);
    put(&mut row, "last_event_handler_exit_code", r.last_event_handler_code);
    for (name, notification) in [("execution_dependencies_failed", false), ("notification_dependencies_failed", true)] {
        put(&mut row, name, u8::from(engine.dependency_failed(state, key, notification, now_ms() / 1000)));
    }
    for (name, notification) in [("depends_exec", false), ("depends_notify", true)] {
        let masters: Vec<Value> = engine.config.dependencies.edges.get(key).into_iter().flatten()
            .filter(|dep| !(if notification { &dep.notification } else { &dep.execution }).is_empty())
            .map(|dep| {
                let master = &engine.definitions[&dep.master];
                if let Some(service) = &master.service { json!([master.host, service]) } else { json!(master.host) }
            }).collect();
        put(&mut row, name, masters);
    }
    put(
        &mut row,
        "notifications_enabled",
        u8::from(r.notification.enabled.unwrap_or(d.notification.enabled)),
    );
    put(
        &mut row,
        "last_notification",
        r.notification.last_notification,
    );
    put(
        &mut row,
        "current_notification_number",
        r.notification.number,
    );
    put(
        &mut row,
        "in_notification_period",
        u8::from(engine.config.periods.allows(
            &d.notification.period,
            a.get("use_timezone").map_or("", String::as_str),
            now_ms() / 1000,
        )),
    );
    put(
        &mut row,
        "check_interval",
        d.check.interval_ms as f64 / (engine.config.interval_length * 1000.0),
    );
    put(
        &mut row,
        "retry_interval",
        d.check.retry_ms as f64 / (engine.config.interval_length * 1000.0),
    );
    put(&mut row, "state", numeric(r.status.state));
    put(
        &mut row,
        "state_type",
        u8::from(r.status.state_type == StateType::Hard),
    );
    put(&mut row, "hard_state", r.hard_state);
    put(&mut row, "last_hard_state", r.last_hard_state);
    put(&mut row, "last_state", r.last_state);
    put(&mut row, "current_attempt", r.status.attempt);
    put(&mut row, "max_check_attempts", r.status.max_attempts);
    put(&mut row, "has_been_checked", u8::from(r.last_check > 0));
    put(&mut row, "last_check", r.last_check);
    put(&mut row, "last_update", r.last_check);
    put(&mut row, "next_check", r.next_check_ms / 1000);
    put(&mut row, "last_state_change", r.last_state_change);
    put(&mut row, "last_hard_state_change", r.last_hard_state_change);
    put(&mut row, "is_executing", u8::from(r.executing));
    put(&mut row, "check_type", r.check_type);
    put(&mut row, "active_checks_enabled", u8::from(r.active));
    put(
        &mut row,
        "checks_enabled",
        u8::from(
            r.active
                && if d.service.is_some() {
                    state.service_checks
                } else {
                    state.host_checks
                },
        ),
    );
    put(
        &mut row,
        "accept_passive_checks",
        u8::from(
            r.passive
                && if d.service.is_some() {
                    state.passive_services
                } else {
                    state.passive_hosts
                },
        ),
    );
    put(&mut row, "acknowledged", u8::from(r.acknowledgement > 0));
    put(&mut row, "acknowledgement_type", r.acknowledgement);
    put(&mut row, "plugin_output", &r.output);
    put(&mut row, "long_plugin_output", &r.long_output);
    put(&mut row, "perf_data", &r.perf_data);
    put(&mut row, "execution_time", r.execution_time);
    put(&mut row, "latency", r.latency);
    put(
        &mut row,
        "in_check_period",
        u8::from(engine.config.periods.allows(
            a.get("check_period").map_or("", String::as_str),
            a.get("use_timezone").map_or("", String::as_str),
            now_ms() / 1000,
        )),
    );
    for (i, name) in [
        "last_time_ok",
        "last_time_warning",
        "last_time_critical",
        "last_time_unknown",
    ]
    .into_iter()
    .enumerate()
    {
        put(&mut row, name, r.last_times[i]);
    }
    for (i, name) in ["last_time_up", "last_time_down", "last_time_unreachable"]
        .into_iter()
        .enumerate()
    {
        put(&mut row, name, r.last_times[i]);
    }
    for name in ["contacts", "contact_groups", "parents"] {
        put(&mut row, name, members(a, name));
    }
    let custom: Vec<_> = a.iter().filter(|(k, _)| k.starts_with('_')).collect();
    put(
        &mut row,
        "custom_variable_names",
        custom
            .iter()
            .map(|(k, _)| k.trim_start_matches('_').to_ascii_uppercase())
            .collect::<Vec<_>>(),
    );
    put(
        &mut row,
        "custom_variable_values",
        custom.iter().map(|(_, v)| *v).collect::<Vec<_>>(),
    );
    let comments: Vec<_> = state.comments.iter().filter(|c| c.key == key).collect();
    put(
        &mut row,
        "comments",
        comments.iter().map(|c| c.id).collect::<Vec<_>>(),
    );
    put(
        &mut row,
        "comments_with_info",
        comments
            .iter()
            .map(|c| json!([c.id, c.author, c.comment]))
            .collect::<Vec<_>>(),
    );
    let now = now_ms() / 1000;
    let downtimes: Vec<_> = state
        .downtimes
        .iter()
        .filter(|d| d.key == key && d.end_time > now)
        .collect();
    put(
        &mut row,
        "downtimes",
        downtimes.iter().map(|d| d.id).collect::<Vec<_>>(),
    );
    put(
        &mut row,
        "downtimes_with_info",
        downtimes
            .iter()
            .map(|d| json!([d.id, d.author, d.comment]))
            .collect::<Vec<_>>(),
    );
    put(
        &mut row,
        "scheduled_downtime_depth",
        downtimes.iter().filter(|d| d.start_time <= now).count(),
    );
    row
}
fn count_states(group: &mut Row, rows: &[&Row], host: bool) {
    let prefix = if host { "hosts" } else { "services" };
    put(group, &format!("num_{prefix}"), rows.len());
    let names: &[&str] = if host {
        &["up", "down", "unreach"]
    } else {
        &["ok", "warn", "crit", "unknown"]
    };
    put(
        group,
        &format!("num_{prefix}_pending"),
        rows.iter().filter(|r| r["has_been_checked"] == 0).count(),
    );
    for (code, name) in names.iter().enumerate() {
        put(
            group,
            &format!("num_{prefix}_{name}"),
            rows.iter()
                .filter(|r| r["has_been_checked"] == 1 && r["state"] == json!(code))
                .count(),
        );
        if !host {
            put(
                group,
                &format!("num_services_hard_{name}"),
                rows.iter()
                    .filter(|r| r["has_been_checked"] == 1 && r["hard_state"] == json!(code))
                    .count(),
            );
        }
    }
    put(
        group,
        if host {
            "worst_host_state"
        } else {
            "worst_service_state"
        },
        rows.iter()
            .filter_map(|r| r["state"].as_u64())
            .max()
            .unwrap_or(0),
    );
    if !host {
        put(
            group,
            "worst_service_hard_state",
            rows.iter()
                .filter_map(|r| r["hard_state"].as_u64())
                .max()
                .unwrap_or(0),
        );
    }
}
impl Engine {
    pub async fn query(&self, query: &Query) -> Result<Vec<u8>, QueryError> {
        let expected = schema(&query.table)
            .ok_or_else(|| QueryError(format!("unknown table {}", query.table)))?;
        let state = self.state.read().await;
        let user = query.auth_user.as_deref();
        let mut all = BTreeMap::new();
        for (key, d) in self.definitions.iter() {
            all.insert(
                key.clone(),
                object_row(d, &state.objects[key], &state, key, self),
            );
        }
        // Host aggregates and service joins use only authorized services.
        for h in self.config.hosts.keys() {
            let services: Vec<_> = self
                .config
                .services
                .iter()
                .filter(|s| s.host_name == *h)
                .filter(|s| {
                    contact_visible(
                        &self.definitions[&service_key(h, &s.description)],
                        user,
                        self,
                    )
                })
                .collect();
            let refs: Vec<_> = services
                .iter()
                .map(|s| &all[&service_key(h, &s.description)])
                .collect();
            let mut summary = Row::new();
            count_states(&mut summary, &refs, false);
            let with_state: Vec<_> = services
                .iter()
                .map(|s| {
                    json!([
                        s.description,
                        all[&service_key(h, &s.description)]["state"],
                        all[&service_key(h, &s.description)]["has_been_checked"]
                    ])
                })
                .collect();
            let with_info: Vec<_> = services
                .iter()
                .map(|s| {
                    json!([
                        s.description,
                        all[&service_key(h, &s.description)]["state"],
                        all[&service_key(h, &s.description)]["has_been_checked"],
                        all[&service_key(h, &s.description)]["plugin_output"]
                    ])
                })
                .collect();
            let row = all.get_mut(&host_key(h)).expect("known host");
            row.extend(summary);
            put(
                row,
                "services",
                services.iter().map(|s| &s.description).collect::<Vec<_>>(),
            );
            put(row, "services_with_state", with_state);
            put(row, "services_with_info", with_info);
            put(
                row,
                "groups",
                self.config
                    .hostgroups
                    .iter()
                    .filter(|(_, v)| v.contains(h))
                    .map(|(n, _)| n)
                    .collect::<Vec<_>>(),
            );
            put(
                row,
                "childs",
                self.config
                    .hosts
                    .values()
                    .filter(|c| members(&c.attributes, "parents").contains(h))
                    .map(|c| &c.name)
                    .collect::<Vec<_>>(),
            );
        }
        for s in &self.config.services {
            let host = all[&host_key(&s.host_name)].clone();
            let row = all
                .get_mut(&service_key(&s.host_name, &s.description))
                .expect("known service");
            for (k, v) in host {
                row.insert(format!("host_{k}"), v);
            }
            put(
                row,
                "groups",
                self.config
                    .servicegroups
                    .iter()
                    .filter(|(_, m)| m.contains(&(s.host_name.clone(), s.description.clone())))
                    .map(|(n, _)| n)
                    .collect::<Vec<_>>(),
            );
        }
        let visible = |key: &str| {
            self.definitions
                .get(key)
                .is_some_and(|d| contact_visible(d, user, self))
        };
        let hosts: Vec<_> = self
            .config
            .hosts
            .keys()
            .filter(|h| visible(&host_key(h)))
            .map(|h| all[&host_key(h)].clone())
            .collect();
        let services: Vec<_> = self
            .config
            .services
            .iter()
            .filter(|s| visible(&service_key(&s.host_name, &s.description)))
            .map(|s| all[&service_key(&s.host_name, &s.description)].clone())
            .collect();
        let rows = match query.table.as_str() {
            "hosts" => hosts,
            "services" => services,
            "status" => {
                let mut r = expected.clone();
                put(
                    &mut r,
                    "program_version",
                    format!("shinken-rs {}", env!("CARGO_PKG_VERSION")),
                );
                put(
                    &mut r,
                    "livestatus_version",
                    format!("shinken-rs {}", env!("CARGO_PKG_VERSION")),
                );
                put(&mut r, "nagios_pid", std::process::id());
                put(&mut r, "program_start", self.started);
                put(&mut r, "configuration_reloads", state.reloads);
                put(&mut r, "last_reload", state.last_reload);
                put(&mut r, "dropped_event_handlers", state.dropped_event_handlers);
                put(&mut r, "enable_event_handlers", u8::from(state.event_handlers_enabled.unwrap_or(self.config.enable_event_handlers)));
                put(&mut r, "last_command_check", state.last_command_check);
                put(&mut r, "interval_length", self.config.interval_length);
                put(
                    &mut r,
                    "enable_notifications",
                    u8::from(
                        state
                            .notifications_enabled
                            .unwrap_or(self.config.enable_notifications),
                    ),
                );
                put(&mut r, "check_external_commands", 1);
                put(&mut r, "execute_host_checks", u8::from(state.host_checks));
                put(
                    &mut r,
                    "execute_service_checks",
                    u8::from(state.service_checks),
                );
                put(
                    &mut r,
                    "accept_passive_host_checks",
                    u8::from(state.passive_hosts),
                );
                put(
                    &mut r,
                    "accept_passive_service_checks",
                    u8::from(state.passive_services),
                );
                put(&mut r, "num_hosts", hosts.len());
                put(&mut r, "num_services", services.len());
                vec![r]
            }
            "hostgroups" | "servicegroups" => {
                let host = query.table == "hostgroups";
                let mut result = Vec::new();
                let names: Vec<_> = if host {
                    self.config.hostgroups.keys().collect()
                } else {
                    self.config.servicegroups.keys().collect()
                };
                for name in names {
                    let mut r = expected.clone();
                    put(&mut r, "name", name);
                    put(&mut r, "alias", name);
                    let hs: Vec<_> = if host {
                        hosts
                            .iter()
                            .filter(|h| {
                                self.config.hostgroups[name].iter().any(|n| h["name"] == *n)
                            })
                            .collect()
                    } else {
                        Vec::new()
                    };
                    let sv: Vec<_> = services
                        .iter()
                        .filter(|s| {
                            if host {
                                self.config.hostgroups[name]
                                    .iter()
                                    .any(|h| s["host_name"] == *h)
                            } else {
                                self.config.servicegroups[name]
                                    .iter()
                                    .any(|(h, d)| s["host_name"] == *h && s["description"] == *d)
                            }
                        })
                        .collect();
                    if user.is_some() && hs.is_empty() && sv.is_empty() {
                        continue;
                    }
                    count_states(&mut r, &hs, true);
                    count_states(&mut r, &sv, false);
                    if host {
                        put(
                            &mut r,
                            "members",
                            hs.iter().map(|h| h["name"].clone()).collect::<Vec<_>>(),
                        );
                        put(
                            &mut r,
                            "members_with_state",
                            hs.iter()
                                .map(|h| json!([h["name"], h["state"], h["has_been_checked"]]))
                                .collect::<Vec<_>>(),
                        );
                    } else {
                        put(
                            &mut r,
                            "members",
                            sv.iter()
                                .map(|s| json!([s["host_name"], s["description"]]))
                                .collect::<Vec<_>>(),
                        );
                        put(
                            &mut r,
                            "members_with_state",
                            sv.iter()
                                .map(|s| {
                                    json!([
                                        s["host_name"],
                                        s["description"],
                                        s["state"],
                                        s["has_been_checked"]
                                    ])
                                })
                                .collect::<Vec<_>>(),
                        );
                    }
                    result.push(r);
                }
                result
            }
            "contacts" => self
                .config
                .contacts
                .iter()
                .filter(|(name, _)| user.is_none_or(|u| u == name.as_str()))
                .map(|(name, a)| {
                    let mut r = expected.clone();
                    put(&mut r, "name", name);
                    for (k, v) in a {
                        if r.get(k).is_some_and(Value::is_string) {
                            put(&mut r, k, v);
                        }
                    }
                    if let Some(routes) = self.config.notification_routes.get(name) {
                        for (kind, routes) in [("host", &routes.host), ("service", &routes.service)]
                        {
                            put(
                                &mut r,
                                &format!("{kind}_notifications_enabled"),
                                u8::from(routes.iter().any(|r| r.enabled)),
                            );
                            put(
                                &mut r,
                                &format!("{kind}_notification_commands"),
                                routes.iter().map(|r| &r.command).collect::<Vec<_>>(),
                            );
                            put(
                                &mut r,
                                &format!("in_{kind}_notification_period"),
                                u8::from(routes.iter().any(|r| {
                                    self.config.periods.allows(&r.period, "", now_ms() / 1000)
                                })),
                            );
                        }
                    }
                    put(
                        &mut r,
                        "can_submit_commands",
                        u8::from(a.get("can_submit_commands").is_none_or(|v| v == "1")),
                    );
                    put(
                        &mut r,
                        "groups",
                        self.config
                            .contactgroups
                            .iter()
                            .filter(|(_, m)| m.contains(name))
                            .map(|(n, _)| n)
                            .collect::<Vec<_>>(),
                    );
                    r
                })
                .collect(),
            "contactgroups" => self
                .config
                .contactgroups
                .iter()
                .filter(|(_, m)| user.is_none_or(|u| m.iter().any(|n| n == u)))
                .map(|(name, m)| {
                    let mut r = expected.clone();
                    put(&mut r, "name", name);
                    put(&mut r, "alias", name);
                    put(
                        &mut r,
                        "members",
                        m.iter()
                            .filter(|n| user.is_none_or(|u| u == n.as_str()))
                            .collect::<Vec<_>>(),
                    );
                    r
                })
                .collect(),
            "commands" => {
                if user.is_some() {
                    Vec::new()
                } else {
                    self.config
                        .commands
                        .values()
                        .map(|c| {
                            Row::from([
                                ("name".into(), json!(c.name)),
                                ("line".into(), json!(c.command_line)),
                            ])
                        })
                        .collect()
                }
            }
            "comments" | "downtimes" => {
                let mut result = Vec::new();
                let base = |key: &str| {
                    let d = &self.definitions[key];
                    let mut r = expected.clone();
                    put(&mut r, "host_name", &d.host);
                    put(
                        &mut r,
                        "service_description",
                        d.service.as_deref().unwrap_or(""),
                    );
                    for (k, v) in &all[&host_key(&d.host)] {
                        r.insert(format!("host_{k}"), v.clone());
                    }
                    if d.service.is_some() {
                        for (k, v) in &all[key] {
                            r.insert(format!("service_{k}"), v.clone());
                        }
                    }
                    r
                };
                if query.table == "comments" {
                    for c in state.comments.iter().filter(|c| visible(&c.key)) {
                        let mut r = base(&c.key);
                        put(&mut r, "id", c.id);
                        put(&mut r, "author", &c.author);
                        put(&mut r, "comment", &c.comment);
                        put(&mut r, "entry_time", c.entry_time);
                        put(&mut r, "entry_type", c.entry_type);
                        put(&mut r, "persistent", u8::from(c.persistent));
                        put(&mut r, "source", 1);
                        put(
                            &mut r,
                            "type",
                            if self.definitions[&c.key].service.is_some() {
                                2
                            } else {
                                1
                            },
                        );
                        result.push(r);
                    }
                } else {
                    for d in state
                        .downtimes
                        .iter()
                        .filter(|d| visible(&d.key) && d.end_time > now_ms() / 1000)
                    {
                        let mut r = base(&d.key);
                        put(&mut r, "id", d.id);
                        put(&mut r, "author", &d.author);
                        put(&mut r, "comment", &d.comment);
                        put(&mut r, "entry_time", d.entry_time);
                        put(&mut r, "start_time", d.start_time);
                        put(&mut r, "end_time", d.end_time);
                        put(&mut r, "fixed", 1);
                        put(&mut r, "duration", d.end_time - d.start_time);
                        put(
                            &mut r,
                            "is_in_effect",
                            u8::from(d.start_time <= now_ms() / 1000),
                        );
                        result.push(r);
                    }
                }
                result
            }
            "log" => state
                .log
                .iter()
                .filter(|l| self.definitions.contains_key(&l.key) && visible(&l.key))
                .map(|l| {
                    let d = &self.definitions[&l.key];
                    let mut r = expected.clone();
                    let kind = if d.service.is_some() {
                        "SERVICE ALERT"
                    } else {
                        "HOST ALERT"
                    };
                    put(&mut r, "class", 1);
                    put(&mut r, "time", l.time);
                    put(&mut r, "type", kind);
                    put(&mut r, "state", l.state);
                    put(&mut r, "host_name", &d.host);
                    put(
                        &mut r,
                        "service_description",
                        d.service.as_deref().unwrap_or(""),
                    );
                    put(&mut r, "plugin_output", &l.output);
                    put(&mut r, "state_type", &l.state_type);
                    put(
                        &mut r,
                        "message",
                        format!(
                            "[{}] {kind}: {};{};{};{};{};{}",
                            l.time,
                            d.host,
                            d.service.as_deref().unwrap_or(""),
                            l.state,
                            l.state_type,
                            l.attempt,
                            l.output
                        ),
                    );
                    r
                })
                .collect(),
            "columns" => TABLES
                .iter()
                .flat_map(|table| {
                    schema(table)
                        .expect("known table")
                        .into_iter()
                        .map(move |(name, v)| {
                            Row::from([
                                ("table".into(), json!(table)),
                                ("name".into(), json!(name)),
                                (
                                    "type".into(),
                                    json!(if v.is_array() {
                                        "list"
                                    } else if v.is_f64() {
                                        "float"
                                    } else if v.is_number() {
                                        "int"
                                    } else {
                                        "string"
                                    }),
                                ),
                                ("description".into(), json!("shinken-rs column")),
                            ])
                        })
                })
                .collect(),
            _ => Vec::new(),
        };
        execute(query, &rows, &expected)
    }
}
