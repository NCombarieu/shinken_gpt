//! Native monitoring runtime; configuration and Livestatus are independent crates.
mod commands;
mod execute;
mod notifications;
mod server;
mod tables;
pub use server::UnixEndpoint;

use serde::{Deserialize, Serialize};
use shinken_config::{Attributes, CheckConfig, MonitoringConfig};
use shinken_core::ServiceStatus;
use shinken_model::{CheckState, StateType};
use std::{
    collections::{BTreeMap, VecDeque},
    fs,
    io::Write,
    path::Path,
    sync::Arc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use thiserror::Error;
use tokio::{sync::RwLock, task::JoinSet, time};

#[derive(Debug, Error)]
pub enum EngineError {
    #[error("{0}")]
    Invalid(String),
    #[error("I/O: {0}")]
    Io(#[from] std::io::Error),
    #[error("retention: {0}")]
    Retention(#[from] serde_json::Error),
    #[error("check task failed: {0}")]
    Task(#[from] tokio::task::JoinError),
}
#[derive(Clone)]
pub struct Engine {
    config: Arc<MonitoringConfig>,
    definitions: Arc<BTreeMap<String, Definition>>,
    state: Arc<RwLock<Snapshot>>,
    max_concurrent: usize,
    started: u64,
}
#[derive(Clone)]
struct Definition {
    notification: shinken_config::NotificationConfig,
    host: String,
    service: Option<String>,
    check: CheckConfig,
    attributes: Attributes,
}
#[derive(Clone, Serialize, Deserialize)]
struct Runtime {
    #[serde(default)]
    notification: notifications::NotificationState,
    status: ServiceStatus,
    output: String,
    long_output: String,
    perf_data: String,
    last_check: u64,
    next_check_ms: u64,
    last_state_change: u64,
    last_hard_state_change: u64,
    last_state: u8,
    hard_state: u8,
    last_hard_state: u8,
    last_times: [u64; 4],
    execution_time: f64,
    latency: f64,
    check_type: u8,
    active: bool,
    passive: bool,
    acknowledgement: u8,
    #[serde(skip)]
    executing: bool,
    #[serde(skip)]
    force: bool,
    #[serde(skip)]
    generation: u64,
}
impl Runtime {
    fn new(check: &CheckConfig) -> Self {
        Self {
            notification: notifications::NotificationState::default(),
            status: ServiceStatus::new(check.max_attempts),
            output: "PENDING".into(),
            long_output: String::new(),
            perf_data: String::new(),
            last_check: 0,
            next_check_ms: 0,
            last_state_change: 0,
            last_hard_state_change: 0,
            last_state: 0,
            hard_state: 0,
            last_hard_state: 0,
            last_times: [0; 4],
            execution_time: 0.0,
            latency: 0.0,
            check_type: 0,
            active: check.active,
            passive: check.passive,
            acknowledgement: 0,
            executing: false,
            force: false,
            generation: 0,
        }
    }
}
#[derive(Clone, Serialize, Deserialize)]
struct Comment {
    id: u64,
    key: String,
    author: String,
    comment: String,
    entry_time: u64,
    persistent: bool,
    entry_type: u8,
}
#[derive(Clone, Serialize, Deserialize)]
struct Downtime {
    id: u64,
    key: String,
    author: String,
    comment: String,
    entry_time: u64,
    start_time: u64,
    end_time: u64,
}
#[derive(Clone, Serialize, Deserialize)]
struct LogEntry {
    time: u64,
    key: String,
    state: u8,
    state_type: String,
    attempt: u32,
    output: String,
}
#[derive(Clone, Serialize, Deserialize)]
struct Snapshot {
    #[serde(default)]
    notifications_enabled: Option<bool>,
    version: u32,
    objects: BTreeMap<String, Runtime>,
    comments: Vec<Comment>,
    downtimes: Vec<Downtime>,
    log: VecDeque<LogEntry>,
    next_id: u64,
    host_checks: bool,
    service_checks: bool,
    passive_hosts: bool,
    passive_services: bool,
    last_command_check: u64,
}
pub(crate) fn host_key(host: &str) -> String {
    format!("H:{host}")
}
pub(crate) fn service_key(host: &str, service: &str) -> String {
    format!("S:{host}\0{service}")
}
pub(crate) fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |d| u64::try_from(d.as_millis()).unwrap_or(u64::MAX))
}
pub(crate) fn numeric(state: CheckState) -> u8 {
    match state {
        CheckState::Ok => 0,
        CheckState::Warning => 1,
        CheckState::Critical => 2,
        CheckState::Unknown => 3,
    }
}
pub(crate) fn members(a: &Attributes, key: &str) -> Vec<String> {
    a.get(key)
        .into_iter()
        .flat_map(|v| v.split(','))
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .collect()
}
impl Engine {
    pub fn new(config: MonitoringConfig, max_concurrent: usize) -> Result<Self, EngineError> {
        if !(1..=1024).contains(&max_concurrent) {
            return Err(EngineError::Invalid(
                "concurrency must be between 1 and 1024".into(),
            ));
        }
        let mut definitions = BTreeMap::new();
        for h in config.hosts.values() {
            definitions.insert(
                host_key(&h.name),
                Definition {
                    notification: h.notification.clone(),
                    host: h.name.clone(),
                    service: None,
                    check: h.check.clone(),
                    attributes: h.attributes.clone(),
                },
            );
        }
        for s in &config.services {
            definitions.insert(
                service_key(&s.host_name, &s.description),
                Definition {
                    notification: s.notification.clone(),
                    host: s.host_name.clone(),
                    service: Some(s.description.clone()),
                    check: s.check.clone(),
                    attributes: s.attributes.clone(),
                },
            );
        }
        let objects = definitions
            .iter()
            .map(|(k, d)| (k.clone(), Runtime::new(&d.check)))
            .collect();
        let started = now_ms() / 1000;
        let notifications_enabled = Some(config.enable_notifications);
        let host_checks = config.execute_host_checks;
        let service_checks = config.execute_service_checks;
        let passive_hosts = config.accept_passive_host_checks;
        let passive_services = config.accept_passive_service_checks;
        Ok(Self {
            config: Arc::new(config),
            definitions: Arc::new(definitions),
            max_concurrent,
            started,
            state: Arc::new(RwLock::new(Snapshot {
                notifications_enabled,
                version: 1,
                objects,
                comments: Vec::new(),
                downtimes: Vec::new(),
                log: VecDeque::new(),
                next_id: 1,
                host_checks,
                service_checks,
                passive_hosts,
                passive_services,
                last_command_check: started,
            })),
        })
    }
    pub async fn restore(&self, path: &Path) -> Result<(), EngineError> {
        let bytes = match fs::read(path) {
            Ok(v) => v,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(e) => return Err(e.into()),
        };
        if bytes.len() > 64 * 1024 * 1024 {
            return Err(EngineError::Invalid("retention exceeds 64 MiB".into()));
        }
        let mut saved: Snapshot = serde_json::from_slice(&bytes)?;
        if saved.version != 1 {
            return Err(EngineError::Invalid("unsupported retention version".into()));
        }
        let mut state = self.state.write().await;
        for (key, current) in &mut state.objects {
            if let Some(mut old) = saved.objects.remove(key) {
                old.status.max_attempts = current.status.max_attempts;
                old.status.attempt = old.status.attempt.clamp(1, old.status.max_attempts);
                old.next_check_ms = now_ms();
                *current = old;
            }
        }
        state.comments = saved
            .comments
            .into_iter()
            .filter(|c| c.persistent && self.definitions.contains_key(&c.key))
            .collect();
        state.downtimes = saved
            .downtimes
            .into_iter()
            .filter(|d| d.end_time > now_ms() / 1000 && self.definitions.contains_key(&d.key))
            .collect();
        state.log = saved
            .log
            .into_iter()
            .rev()
            .take(10_000)
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect();
        state.next_id = saved.next_id.max(
            state
                .comments
                .iter()
                .map(|c| c.id)
                .chain(state.downtimes.iter().map(|d| d.id))
                .max()
                .unwrap_or(0)
                .saturating_add(1),
        );
        state.host_checks = saved.host_checks;
        state.service_checks = saved.service_checks;
        state.passive_hosts = saved.passive_hosts;
        state.passive_services = saved.passive_services;
        state.notifications_enabled = saved.notifications_enabled;
        Ok(())
    }
    pub async fn save(&self, path: &Path) -> Result<(), EngineError> {
        let snapshot = self.state.read().await.clone();
        let parent = path
            .parent()
            .filter(|p| !p.as_os_str().is_empty())
            .unwrap_or(Path::new("."));
        let mut file = tempfile::NamedTempFile::new_in(parent)?;
        serde_json::to_writer(&mut file, &snapshot)?;
        file.flush()?;
        file.as_file().sync_all()?;
        file.persist(path).map_err(|e| EngineError::Io(e.error))?;
        fs::File::open(parent)?.sync_all()?;
        Ok(())
    }
    /// Bounded one-shot execution, including hosts. Passive-only objects remain pending.
    pub async fn run_all_checks(&self) -> Result<(), EngineError> {
        let keys: Vec<_> = self.definitions.keys().cloned().collect();
        let mut tasks = JoinSet::new();
        for key in keys {
            if tasks.len() >= self.max_concurrent {
                if let Some(result) = tasks.join_next().await {
                    result?;
                }
            }
            if let Some(generation) = self.claim(&key, true).await {
                let engine = self.clone();
                tasks.spawn(async move { engine.run_check(key, generation).await });
            }
        }
        while let Some(result) = tasks.join_next().await {
            result?;
        }
        Ok(())
    }
    pub async fn run_forever(&self) -> Result<(), EngineError> {
        let mut tick = time::interval(Duration::from_millis(100));
        tick.set_missed_tick_behavior(time::MissedTickBehavior::Skip);
        let mut tasks = JoinSet::new();
        loop {
            tokio::select! {
                result=tasks.join_next(),if !tasks.is_empty()=>{if let Some(result)=result{result?;}},
                _=tick.tick()=>{
                    for key in self.check_order().await {
                        if tasks.len()>=self.max_concurrent {break;}
                        if let Some(generation)=self.claim(&key,false).await {
                            let engine=self.clone();
                            tasks.spawn(async move {engine.run_check(key,generation).await});
                        }
                    }
                }
            }
        }
    }
    async fn check_order(&self) -> Vec<String> {
        let state = self.state.read().await;
        let mut keys: Vec<_> = state.objects.keys().cloned().collect();
        keys.sort_by_key(|key| state.objects[key].next_check_ms);
        keys
    }
    async fn claim(&self, key: &str, once: bool) -> Option<u64> {
        let definition = &self.definitions[key];
        let mut state = self.state.write().await;
        let global = if definition.service.is_some() {
            state.service_checks
        } else {
            state.host_checks
        };
        let r = state.objects.get_mut(key)?;
        let now = now_ms();
        let due = once || (now >= r.next_check_ms && (r.last_check == 0 || r.next_check_ms > 0));
        if r.executing
            || !due
            || definition.check.command.is_empty()
            || !(r.force || r.active && global)
        {
            return None;
        }
        r.executing = true;
        let period = definition
            .attributes
            .get("check_period")
            .map_or("", String::as_str);
        let zone = definition
            .attributes
            .get("use_timezone")
            .map_or("", String::as_str);
        if !r.force && !self.config.periods.allows(period, zone, now / 1000) {
            r.executing = false;
            r.next_check_ms = self
                .config
                .periods
                .next_opening(period, zone, now / 1000)
                .map_or(now.saturating_add(86_400_000), |t| t.saturating_mul(1000));
            return None;
        }
        r.force = false;
        r.latency = if r.next_check_ms > 0 {
            now.saturating_sub(r.next_check_ms) as f64 / 1000.0
        } else {
            0.0
        };
        Some(r.generation)
    }
    async fn run_check(&self, key: String, generation: u64) {
        let d = &self.definitions[&key];
        let result = execute::run(&self.config, d).await;
        let mut state = self.state.write().await;
        if let Some(r) = state.objects.get_mut(&key) {
            r.executing = false;
            if r.generation != generation {
                return;
            }
        }
        self.apply_result(&mut state, &key, result, false, now_ms() / 1000);
    }
    fn apply_result(
        &self,
        state: &mut Snapshot,
        key: &str,
        mut result: execute::PluginResult,
        passive: bool,
        at: u64,
    ) {
        let d = &self.definitions[key];
        if d.service.is_none() && !passive {
            result.code = if result.code == 0 { 0 } else { 1 };
        }
        let Some(r) = state.objects.get_mut(key) else {
            return;
        };
        let previous = r.status;
        if previous.state == CheckState::Ok && result.code != 0 {
            r.notification.problem_since_ms = at.saturating_mul(1000);
        }
        let next = CheckState::from_plugin_status(i32::from(result.code));
        r.status = r.status.apply_result(next);
        if passive {
            r.status.state_type = StateType::Hard;
            r.status.attempt = 1;
            r.generation = r.generation.wrapping_add(1);
        }
        let changed = previous.state != r.status.state || r.last_check == 0;
        if changed {
            r.last_state = numeric(previous.state);
            r.last_state_change = at;
            if r.acknowledgement == 1 || next == CheckState::Ok {
                r.acknowledgement = 0;
            }
        }
        if r.status.state_type == StateType::Hard && r.hard_state != numeric(next) {
            r.last_hard_state = r.hard_state;
            r.hard_state = numeric(next);
            r.last_hard_state_change = at;
        }
        r.last_times[usize::from(result.code.min(3))] = at;
        r.last_check = at;
        r.output = result.output.clone();
        r.long_output = result.long_output;
        r.perf_data = result.perf_data;
        r.execution_time = result.elapsed;
        r.check_type = u8::from(passive);
        let interval = if r.status.state_type == StateType::Soft {
            d.check.retry_ms
        } else {
            d.check.interval_ms
        };
        r.next_check_ms = if interval == 0 {
            0
        } else {
            now_ms().saturating_add(interval)
        };
        if changed || previous.state_type != r.status.state_type {
            state.log.push_back(LogEntry {
                time: at,
                key: key.into(),
                state: result.code,
                state_type: if r.status.state_type == StateType::Hard {
                    "HARD"
                } else {
                    "SOFT"
                }
                .into(),
                attempt: r.status.attempt,
                output: result.output,
            });
            if state.log.len() > 10_000 {
                state.log.pop_front();
            }
        }
        if next == CheckState::Ok {
            state
                .comments
                .retain(|c| c.key != key || c.entry_type != 4 || c.persistent);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use shinken_config::{build_monitoring_config, parse_objects, LoadedConfig};

    #[tokio::test]
    async fn frequent_checks_do_not_starve_pending_objects() {
        let mut input =
            "define command {\n command_name up\n command_line printf UP\n}\n".to_owned();
        for i in 0..6 {
            input.push_str(&format!(
                "define host {{\n host_name h{i}\n check_command up\n check_interval 0.0001\n}}\n"
            ));
        }
        let config = build_monitoring_config(&LoadedConfig {
            objects: parse_objects("fairness.cfg", &input).unwrap(),
            ..LoadedConfig::default()
        })
        .unwrap();
        let engine = Engine::new(config, 1).unwrap();
        let running = engine.clone();
        let worker = tokio::spawn(async move { running.run_forever().await });
        let result = time::timeout(Duration::from_secs(3), async {
            loop {
                if engine
                    .state
                    .read()
                    .await
                    .objects
                    .values()
                    .all(|r| r.last_check > 0)
                {
                    break;
                }
                time::sleep(Duration::from_millis(20)).await;
            }
        })
        .await;
        worker.abort();
        let _ = worker.await;
        assert!(result.is_ok(), "a frequent check starved pending hosts");
    }
}
