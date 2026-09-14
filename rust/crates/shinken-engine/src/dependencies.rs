//! Dependency gates use retained HARD states unless soft_state_dependencies is enabled.
use crate::{host_key, now_ms, numeric, Engine, Snapshot};
use std::collections::BTreeSet;

impl Engine {
    pub(crate) fn dependency_failed(&self, state: &Snapshot, key: &str, notification: bool, at: u64) -> bool {
        let mut pending = vec![key];
        let mut visited = BTreeSet::new();
        while let Some(key) = pending.pop() {
            if !visited.insert(key) { continue; }
            for dep in self.config.dependencies.edges.get(key).into_iter().flatten() {
                if !self.config.periods.allows(&dep.period, "", at) { continue; }
                let Some(master) = state.objects.get(&dep.master) else { return true; };
                let code = if master.last_check == 0 { 4 }
                    else if self.config.dependencies.soft_states { numeric(master.status.state) }
                    else { master.hard_state };
                let criteria = if notification { &dep.notification } else { &dep.execution };
                if criteria.contains(&code) { return true; }
                if dep.inherits_parent { pending.push(&dep.master); }
            }
        }
        false
    }
    pub(crate) fn parents_down(&self, state: &Snapshot, host: &str) -> bool {
        let parents = &self.config.dependencies.parents[host];
        !parents.is_empty() && parents.iter().all(|parent| {
            state.objects.get(&host_key(parent)).is_some_and(|r| r.last_check > 0 && numeric(r.status.state) != 0)
        })
    }
    pub(crate) fn refresh_children(&self, state: &mut Snapshot, host: &str) {
        // Confirm reachability with a real host check after an upstream transition.
        for (child, parents) in &self.config.dependencies.parents {
            if parents.iter().any(|p| p == host) {
                if let Some(r) = state.objects.get_mut(&host_key(child)) {
                    if r.active {
                        let at = now_ms();
                        if r.executing { r.scheduled = Some((at, false)); }
                        else { r.next_check_ms = at; }
                    }
                }
            }
        }
    }
}
