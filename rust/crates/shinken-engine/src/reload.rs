//! Live requests share a generation slot. A validated replacement keeps endpoints open.
use crate::{now_ms, Engine};
use std::sync::Arc;
use tokio::sync::RwLock;

#[derive(Clone)]
pub struct LiveEngine {
    pub(crate) current: Arc<RwLock<Engine>>,
}
impl LiveEngine {
    pub fn new(engine: Engine) -> Self {
        Self {
            current: Arc::new(RwLock::new(engine)),
        }
    }
    /// Call only after stopping the old generation's check/notification/handler workers.
    pub async fn replace(&self, mut next: Engine) -> Engine {
        let mut current = self.current.write().await;
        next.inherit_runtime(&current).await;
        *current = next.clone();
        next
    }
}
impl Engine {
    pub async fn take_reload_request(&self) -> bool {
        std::mem::take(&mut self.state.write().await.reload_requested)
    }
    async fn inherit_runtime(&mut self, previous: &Engine) {
        let mut saved = previous.state.read().await.clone();
        let mut next = self.state.write().await;
        let now = now_ms();
        for (key, r) in &mut next.objects {
            if let Some(mut old) = saved.objects.remove(key) {
                let previous_definition = &previous.definitions[key];
                if old.active == previous_definition.check.active {
                    old.active = r.active;
                }
                if old.passive == previous_definition.check.passive {
                    old.passive = r.passive;
                }
                old.status.max_attempts = r.status.max_attempts;
                old.status.attempt = old.status.attempt.clamp(1, old.status.max_attempts);
                old.executing = false;
                old.generation = old.generation.wrapping_add(1);
                old.notification.reset_transient();
                if let Some((at, force)) = old.scheduled.take() {
                    old.next_check_ms = at;
                    old.force = force;
                } else if !old.force {
                    old.next_check_ms = now;
                }
                *r = old;
            }
        }
        next.comments = saved
            .comments
            .into_iter()
            .filter(|c| self.definitions.contains_key(&c.key))
            .collect();
        next.downtimes = saved
            .downtimes
            .into_iter()
            .filter(|d| self.definitions.contains_key(&d.key) && d.end_time > now / 1000)
            .collect();
        next.log = saved.log;
        next.next_id = saved.next_id;
        next.last_command_check = saved.last_command_check;
        next.event_handlers_enabled = saved.event_handlers_enabled;
        next.dropped_event_handlers = saved
            .dropped_event_handlers
            .saturating_add(saved.events.len() as u64);
        next.reloads = saved.reloads.saturating_add(1);
        next.last_reload = now / 1000;
        let reconcile = |runtime, old, new| if runtime == old { new } else { runtime };
        next.host_checks = reconcile(
            saved.host_checks,
            previous.config.execute_host_checks,
            self.config.execute_host_checks,
        );
        next.service_checks = reconcile(
            saved.service_checks,
            previous.config.execute_service_checks,
            self.config.execute_service_checks,
        );
        next.passive_hosts = reconcile(
            saved.passive_hosts,
            previous.config.accept_passive_host_checks,
            self.config.accept_passive_host_checks,
        );
        next.passive_services = reconcile(
            saved.passive_services,
            previous.config.accept_passive_service_checks,
            self.config.accept_passive_service_checks,
        );
        next.notifications_enabled = Some(reconcile(
            saved
                .notifications_enabled
                .unwrap_or(previous.config.enable_notifications),
            previous.config.enable_notifications,
            self.config.enable_notifications,
        ));
        self.started = previous.started;
    }
}
