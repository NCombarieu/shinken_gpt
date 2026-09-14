//! Best-effort native notifications. Successful deliveries are retained per contact/command.
use crate::{execute, host_key, members, now_ms, numeric, Engine, EngineError, Snapshot};
use serde::{Deserialize, Serialize};
use shinken_config::{option_for, Attributes};
use shinken_model::StateType;
use std::collections::BTreeMap;
use std::time::Duration;
use tokio::{task::JoinSet, time};

#[derive(Clone, Default, Serialize, Deserialize)]
pub(crate) struct NotificationState {
    pub enabled: Option<bool>,
    pub last_notification: u64,
    pub number: u32,
    pub problem_since_ms: u64,
    #[serde(default)]
    round_state: Option<u8>,
    #[serde(default)]
    round_at_ms: u64,
    #[serde(default)]
    round_interval_ms: u64,
    #[serde(default)]
    incident: u64,
    deliveries: BTreeMap<String, Delivery>,
    #[serde(skip)]
    sending: bool,
    #[serde(skip)]
    retry_after_ms: u64,
}
#[derive(Clone, Serialize, Deserialize)]
struct Delivery {
    #[serde(default)]
    number: u32,
    state: u8,
    at_ms: u64,
}
impl NotificationState {
    pub(crate) fn begin_problem(&mut self, at: u64) {
        self.problem_since_ms = at;
        self.incident = self.incident.wrapping_add(1);
        self.round_state = None;
        self.number = 0;
        self.deliveries.clear();
    }
    pub(crate) fn reset_transient(&mut self) {
        self.sending = false;
        self.retry_after_ms = 0;
    }
}
struct Job {
    id: String,
    command: String,
    macros: Attributes,
}
struct Plan {
    key: String,
    state: u8,
    number: u32,
    interval_ms: u64,
    incident: u64,
    jobs: Vec<Job>,
}
fn state_name(code: u8, host: bool) -> &'static str {
    if host {
        match code {
            0 => "UP",
            1 => "DOWN",
            _ => "UNREACHABLE",
        }
    } else {
        match code {
            0 => "OK",
            1 => "WARNING",
            2 => "CRITICAL",
            _ => "UNKNOWN",
        }
    }
}
impl Engine {
    pub async fn run_notifications_forever(&self) -> Result<(), EngineError> {
        let mut tick = time::interval(Duration::from_millis(200));
        tick.set_missed_tick_behavior(time::MissedTickBehavior::Skip);
        let mut tasks = JoinSet::new();
        loop {
            tokio::select! {
                result=tasks.join_next(),if !tasks.is_empty()=>{if let Some(result)=result{result?;}},
                _=tick.tick()=>{
                    for key in self.definitions.keys(){
                        if tasks.len()>=4{break;}
                        if let Some(plan)=self.claim_notification(key).await{
                            let engine=self.clone();tasks.spawn(async move{engine.deliver(plan).await});
                        }
                    }
                }
            }
        }
    }
    async fn claim_notification(&self, key: &str) -> Option<Plan> {
        let now = now_ms();
        let mut state = self.state.write().await;
        let r = &state.objects[key];
        let d = &self.definitions[key];
        if r.notification.sending
            || r.notification.retry_after_ms > now
            || !state
                .notifications_enabled
                .unwrap_or(self.config.enable_notifications)
            || !r.notification.enabled.unwrap_or(d.notification.enabled)
            || r.last_check == 0
            || r.status.state_type != StateType::Hard
        {
            return None;
        }
        if self.dependency_failed(&state, key, true, now / 1000) { return None; }
        let code = numeric(r.status.state);
        let host = d.service.is_none();
        let option = option_for(code, host);
        if code > 0
            && now
                < r.notification
                    .problem_since_ms
                    .saturating_add(d.notification.first_delay_ms)
        {
            return None;
        }
        if code > 0 && r.acknowledgement > 0 {
            return None;
        }
        if state.downtimes.iter().any(|dt| {
            (dt.key == key || (!host && dt.key == host_key(&d.host)))
                && dt.start_time <= now / 1000
                && dt.end_time > now / 1000
        }) {
            return None;
        }
        if !host {
            let h = &state.objects[&host_key(&d.host)];
            if h.last_check > 0 && numeric(h.status.state) != 0 {
                return None;
            }
        }
        let zone = d.attributes.get("use_timezone").map_or("", String::as_str);
        if !self
            .config
            .periods
            .allows(&d.notification.period, zone, now / 1000)
        {
            return None;
        }
        let new_round = r.notification.round_state != Some(code)
            || (code > 0 && r.notification.round_interval_ms > 0
                && now >= r.notification.round_at_ms.saturating_add(r.notification.round_interval_ms));
        let number = if code == 0 { 0 } else if new_round {
            r.notification.number.saturating_add(1)
        } else { r.notification.number };
        let elapsed = now.saturating_sub(r.notification.problem_since_ms);
        let escalations: Vec<_> = self.config.escalations.get(key).into_iter().flatten()
            .filter(|e| e.matches(number, elapsed, option) && self.config.periods.allows(&e.period, zone, now / 1000)).collect();
        if escalations.is_empty() && !d.notification.options.contains(&option) { return None; }
        let interval_ms = escalations.iter().filter_map(|e| e.interval_ms).min().unwrap_or(d.notification.interval_ms);
        let contacts: std::collections::BTreeSet<_> = if code == 0 {
            // Recovery reaches every successful recipient of this incident, including earlier escalations.
            self.config.contacts.keys().cloned().collect()
        } else if escalations.is_empty() {
            members(&d.attributes, "contacts").into_iter().collect()
        } else { escalations.iter().flat_map(|e| e.contacts.iter().cloned()).collect() };
        let mut jobs = Vec::new();
        for contact in contacts {
            let Some(routes) = self.config.notification_routes.get(&contact) else { continue; };
            for route in if host { &routes.host } else { &routes.service } {
                if !route.enabled || !route.options.contains(&option)
                    || !self.config.periods.allows(&route.period, "", now / 1000) { continue; }
                let last = r.notification.deliveries.get(&route.id);
                if code == 0 {
                    if last.is_none_or(|last| last.state == 0) { continue; }
                } else if last.is_some_and(|last| last.state == code && last.number == number) {
                    continue;
                }
                let mut macros = self.notification_macros(&state, key, &contact, code);
                macros.insert("$NOTIFICATIONNUMBER$".into(), number.to_string());
                jobs.push(Job { id: route.id.clone(), command: route.command.clone(), macros });
            }
        }
        if jobs.is_empty() {
            return None;
        }
        let incident = r.notification.incident;
        state.objects.get_mut(key)?.notification.sending = true;
        Some(Plan {
            number, interval_ms, incident,
            key: key.into(),
            state: code,
            jobs,
        })
    }
    async fn deliver(&self, plan: Plan) {
        let mut delivered = Vec::new();
        let d = &self.definitions[&plan.key];
        for job in plan.jobs {
            let result = execute::run_with(
                &self.config,
                d,
                &job.command,
                &job.macros,
                self.config.notification_timeout_ms,
            )
            .await;
            if result.code == 0 {
                delivered.push(job.id);
            } else {
                eprintln!(
                    "notification failed for {} / {}: {}",
                    d.host, job.id, result.output
                );
            }
        }
        let now = now_ms();
        let mut state = self.state.write().await;
        let Some(r) = state.objects.get_mut(&plan.key) else {
            return;
        };
        r.notification.sending = false;
        r.notification.retry_after_ms = now.saturating_add(1000);
        if r.notification.incident != plan.incident { return; }
        if !delivered.is_empty() {
            for id in delivered {
                r.notification.deliveries.insert(
                    id,
                    Delivery {
                        number: plan.number,
                        state: plan.state,
                        at_ms: now,
                    },
                );
            }
            r.notification.last_notification = now / 1000;
            if r.notification.round_state != Some(plan.state) || r.notification.number != plan.number {
                r.notification.round_at_ms = now;
                r.notification.round_interval_ms = plan.interval_ms;
            }
            r.notification.round_state = Some(plan.state);
            r.notification.number = plan.number;
        }
    }
    pub(crate) fn object_macros(&self, state: &Snapshot, key: &str) -> Attributes {
        let d = &self.definitions[key];
        let mut result = Attributes::new();
        let now = now_ms() / 1000;
        for (prefix, key, host) in [
            ("HOST", host_key(&d.host), true),
            ("SERVICE", key.to_owned(), false),
        ] {
            if prefix == "SERVICE" && d.service.is_none() {
                continue;
            }
            let r = &state.objects[&key];
            let code = numeric(r.status.state);
            for (suffix, value) in [
                ("STATE", state_name(code, host).to_owned()),
                ("STATEID", code.to_string()),
                (
                    "STATETYPE",
                    if r.status.state_type == StateType::Hard {
                        "HARD"
                    } else {
                        "SOFT"
                    }
                    .into(),
                ),
                ("ATTEMPT", r.status.attempt.to_string()),
                ("OUTPUT", r.output.clone()),
                ("PERFDATA", r.perf_data.clone()),
                (
                    "DURATIONSEC",
                    now.saturating_sub(r.last_state_change).to_string(),
                ),
            ] {
                result.insert(format!("{}{prefix}{suffix}$", '$'), value);
            }
            result.insert(format!("$LONG{prefix}OUTPUT$"), r.long_output.clone());
        }
        result.insert(
            "$LONGDATETIME$".into(),
            self.config
                .periods
                .format_time(now, "%a %b %d %H:%M:%S %Z %Y"),
        );
        result.insert(
            "$SHORTDATETIME$".into(),
            self.config.periods.format_time(now, "%m-%d-%Y %H:%M:%S"),
        );
        result.insert(
            "$DATE$".into(),
            self.config.periods.format_time(now, "%m-%d-%Y"),
        );
        result.insert(
            "$TIME$".into(),
            self.config.periods.format_time(now, "%H:%M:%S"),
        );
        result
    }
    fn notification_macros(
        &self,
        state: &Snapshot,
        key: &str,
        contact: &str,
        code: u8,
    ) -> Attributes {
        let r = &state.objects[key];
        let mut result = self.object_macros(state, key);
        let a = &self.config.contacts[contact];
        for suffix in [
            "NAME", "ALIAS", "EMAIL", "PAGER", "ADDRESS1", "ADDRESS2", "ADDRESS3", "ADDRESS4",
            "ADDRESS5", "ADDRESS6",
        ] {
            let value = if suffix == "NAME" {
                contact.to_owned()
            } else {
                a.get(&suffix.to_ascii_lowercase())
                    .cloned()
                    .unwrap_or_default()
            };
            result.insert(format!("$CONTACT{suffix}$"), value);
        }
        for (name, value) in a {
            if let Some(name) = name.strip_prefix('_') {
                result.insert(
                    format!("$_CONTACT{}$", name.to_ascii_uppercase()),
                    value.clone(),
                );
            }
        }
        result.insert(
            "$NOTIFICATIONTYPE$".into(),
            if code == 0 { "RECOVERY" } else { "PROBLEM" }.into(),
        );
        result.insert(
            "$NOTIFICATIONNUMBER$".into(),
            r.notification.number.saturating_add(1).to_string(),
        );
        result
    }
}
