//! Captured state-change actions; global handler precedes the object's handler.
use crate::{execute, now_ms, Engine, EngineError, Snapshot};
use shinken_config::Attributes;
use std::{collections::BTreeSet, time::Duration};
use tokio::{task::JoinSet, time};

#[derive(Clone)]
pub(crate) struct Event {
    pub key: String,
    commands: Vec<String>,
    macros: Attributes,
}
impl Engine {
    pub(crate) fn queue_handler(&self, state: &mut Snapshot, key: &str, soft_recovery: bool) {
        let d = &self.definitions[key];
        let r = &state.objects[key];
        if !state.event_handlers_enabled.unwrap_or(self.config.enable_event_handlers)
            || !r.event_handler_enabled.unwrap_or(d.attributes.get("event_handler_enabled").is_none_or(|v| v == "1")) {
            return;
        }
        let global = if d.service.is_none() { &self.config.global_host_event_handler } else { &self.config.global_service_event_handler };
        let local = d.attributes.get("event_handler").map_or("", String::as_str);
        let commands: Vec<_> = [global.as_str(), local].into_iter().filter(|s| !s.is_empty()).map(str::to_owned).collect();
        if commands.is_empty() { return; }
        if state.events.len() >= 10_000 {
            state.dropped_event_handlers = state.dropped_event_handlers.saturating_add(1);
            eprintln!("event handler queue full; skipped {key}");
            return;
        }
        let mut macros = self.object_macros(state, key);
        if soft_recovery {
            let name = if d.service.is_some() { "$SERVICESTATETYPE$" } else { "$HOSTSTATETYPE$" };
            macros.insert(name.into(), "SOFT".into());
        }
        state.events.push_back(Event { key: key.into(), commands, macros });
    }
    async fn run_handler(&self, event: Event) -> String {
        let d = &self.definitions[&event.key];
        for command in &event.commands {
            let result = execute::run_with(&self.config, d, command, &event.macros, self.config.event_handler_timeout_ms).await;
            if result.code != 0 { eprintln!("event handler {command} failed for {}: {}", event.key, result.output); }
            if let Some(r) = self.state.write().await.objects.get_mut(&event.key) {
                r.last_event_handler = now_ms() / 1000;
                r.last_event_handler_code = result.code;
            }
        }
        event.key
    }
    pub async fn drain_event_handlers(&self) {
        loop {
            let event = self.state.write().await.events.pop_front();
            let Some(event) = event else { break; };
            self.run_handler(event).await;
        }
    }
    pub async fn run_event_handlers_forever(&self) -> Result<(), EngineError> {
        let mut tick = time::interval(Duration::from_millis(50));
        tick.set_missed_tick_behavior(time::MissedTickBehavior::Skip);
        let mut tasks = JoinSet::new();
        let mut busy = BTreeSet::new();
        loop {
            tokio::select! {
                result = tasks.join_next(), if !tasks.is_empty() => {
                    if let Some(result) = result { busy.remove(&result?); }
                },
                _ = tick.tick() => {
                    while tasks.len() < 4 {
                        let mut state = self.state.write().await;
                        let Some(pos) = state.events.iter().position(|e| !busy.contains(&e.key)) else { break; };
                        let event = state.events.remove(pos).expect("queued event");
                        drop(state);
                        busy.insert(event.key.clone());
                        let engine = self.clone();
                        tasks.spawn(async move { engine.run_handler(event).await });
                    }
                }
            }
        }
    }
}
