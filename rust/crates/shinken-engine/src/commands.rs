//! External commands supported by the native runtime; unsupported actions fail explicitly.
use crate::{
    execute::PluginResult, host_key, now_ms, service_key, Comment, Downtime, Engine, EngineError,
    Snapshot,
};
fn invalid(s: impl Into<String>) -> EngineError {
    EngineError::Invalid(s.into())
}
fn number(s: &str) -> Result<u64, EngineError> {
    s.parse()
        .map_err(|_| invalid(format!("invalid unsigned integer {s}")))
}
fn flag(s: &str) -> Result<bool, EngineError> {
    match s {
        "0" => Ok(false),
        "1" => Ok(true),
        _ => Err(invalid("expected 0 or 1")),
    }
}
fn count(args: &[&str], n: usize) -> Result<(), EngineError> {
    if args.len() != n {
        Err(invalid(format!(
            "expected {n} arguments, got {}",
            args.len()
        )))
    } else {
        Ok(())
    }
}
impl Engine {
    /// Apply a batch atomically: any invalid command leaves all runtime state unchanged.
    pub async fn command(&self, input: &str) -> Result<(), EngineError> {
        let mut current = self.state.write().await;
        let mut next = current.clone();
        let mut n = 0;
        for line in input.lines().filter(|l| !l.trim().is_empty()) {
            n += 1;
            if n > 1000 {
                return Err(invalid("command batch exceeds 1000 commands"));
            }
            let line = line.strip_prefix("COMMAND ").unwrap_or(line).trim();
            let (stamp, body) = line
                .strip_prefix('[')
                .and_then(|s| s.split_once(']'))
                .ok_or_else(|| invalid("expected [timestamp] COMMAND;arguments"))?;
            let stamp = number(stamp)?;
            if stamp > now_ms() / 1000 + 300 {
                return Err(invalid("command timestamp is in the future"));
            }
            let (name, rest) = body
                .trim_start()
                .split_once(';')
                .unwrap_or((body.trim_start(), ""));
            let args: Vec<_> = if rest.is_empty() {
                Vec::new()
            } else {
                rest.split(';').collect()
            };
            self.apply_command(&mut next, name, &args, stamp)?;
        }
        if n == 0 {
            return Err(invalid("empty command batch"));
        }
        next.last_command_check = now_ms() / 1000;
        *current = next;
        Ok(())
    }
    fn target<'a>(
        &self,
        name: &str,
        args: &'a [&'a str],
    ) -> Result<(String, &'a [&'a str]), EngineError> {
        let service = name.contains("SVC") || name.contains("SERVICE_CHECK_RESULT");
        let n = if service { 2 } else { 1 };
        if args.len() < n {
            return Err(invalid("missing host or service name"));
        }
        let key = if service {
            service_key(args[0], args[1])
        } else {
            host_key(args[0])
        };
        if !self.definitions.contains_key(&key) {
            return Err(invalid("unknown host or service"));
        }
        Ok((key, &args[n..]))
    }
    fn apply_command(
        &self,
        state: &mut Snapshot,
        name: &str,
        args: &[&str],
        stamp: u64,
    ) -> Result<(), EngineError> {
        if ["ENABLE_NOTIFICATIONS", "DISABLE_NOTIFICATIONS"].contains(&name) {
            count(args, 0)?;
            state.notifications_enabled = Some(name == "ENABLE_NOTIFICATIONS");
            return Ok(());
        }
        let global = match name {
            "START_EXECUTING_HOST_CHECKS" => Some((&mut state.host_checks, true)),
            "STOP_EXECUTING_HOST_CHECKS" => Some((&mut state.host_checks, false)),
            "START_EXECUTING_SVC_CHECKS" => Some((&mut state.service_checks, true)),
            "STOP_EXECUTING_SVC_CHECKS" => Some((&mut state.service_checks, false)),
            "START_ACCEPTING_PASSIVE_HOST_CHECKS" => Some((&mut state.passive_hosts, true)),
            "STOP_ACCEPTING_PASSIVE_HOST_CHECKS" => Some((&mut state.passive_hosts, false)),
            "START_ACCEPTING_PASSIVE_SVC_CHECKS" => Some((&mut state.passive_services, true)),
            "STOP_ACCEPTING_PASSIVE_SVC_CHECKS" => Some((&mut state.passive_services, false)),
            _ => None,
        };
        if let Some((setting, value)) = global {
            count(args, 0)?;
            *setting = value;
            return Ok(());
        }
        if [
            "DEL_HOST_COMMENT",
            "DEL_SVC_COMMENT",
            "DEL_HOST_DOWNTIME",
            "DEL_SVC_DOWNTIME",
        ]
        .contains(&name)
        {
            count(args, 1)?;
            let id = number(args[0])?;
            let svc = name.contains("SVC");
            if name.ends_with("COMMENT") {
                let pos = state
                    .comments
                    .iter()
                    .position(|c| c.id == id && self.definitions[&c.key].service.is_some() == svc)
                    .ok_or_else(|| invalid("unknown comment id"))?;
                state.comments.remove(pos);
            } else {
                let pos = state
                    .downtimes
                    .iter()
                    .position(|d| d.id == id && self.definitions[&d.key].service.is_some() == svc)
                    .ok_or_else(|| invalid("unknown downtime id"))?;
                state.downtimes.remove(pos);
            }
            return Ok(());
        }
        let supported = [
            "ENABLE_HOST_NOTIFICATIONS",
            "DISABLE_HOST_NOTIFICATIONS",
            "ENABLE_SVC_NOTIFICATIONS",
            "DISABLE_SVC_NOTIFICATIONS",
            "PROCESS_HOST_CHECK_RESULT",
            "PROCESS_SERVICE_CHECK_RESULT",
            "ENABLE_HOST_CHECK",
            "DISABLE_HOST_CHECK",
            "ENABLE_SVC_CHECK",
            "DISABLE_SVC_CHECK",
            "ENABLE_PASSIVE_HOST_CHECKS",
            "DISABLE_PASSIVE_HOST_CHECKS",
            "ENABLE_PASSIVE_SVC_CHECKS",
            "DISABLE_PASSIVE_SVC_CHECKS",
            "SCHEDULE_HOST_CHECK",
            "SCHEDULE_SVC_CHECK",
            "SCHEDULE_FORCED_HOST_CHECK",
            "SCHEDULE_FORCED_SVC_CHECK",
            "ACKNOWLEDGE_HOST_PROBLEM",
            "ACKNOWLEDGE_SVC_PROBLEM",
            "REMOVE_HOST_ACKNOWLEDGEMENT",
            "REMOVE_SVC_ACKNOWLEDGEMENT",
            "ADD_HOST_COMMENT",
            "ADD_SVC_COMMENT",
            "DEL_ALL_HOST_COMMENTS",
            "DEL_ALL_SVC_COMMENTS",
            "SCHEDULE_HOST_DOWNTIME",
            "SCHEDULE_SVC_DOWNTIME",
        ];
        if !supported.contains(&name) {
            return Err(invalid(format!("unsupported external command {name}")));
        }
        let (key, args) = self.target(name, args)?;
        match name {
            "ENABLE_HOST_NOTIFICATIONS"
            | "DISABLE_HOST_NOTIFICATIONS"
            | "ENABLE_SVC_NOTIFICATIONS"
            | "DISABLE_SVC_NOTIFICATIONS" => {
                count(args, 0)?;
                state
                    .objects
                    .get_mut(&key)
                    .expect("known key")
                    .notification
                    .enabled = Some(name.starts_with("ENABLE"));
            }
            "PROCESS_HOST_CHECK_RESULT" | "PROCESS_SERVICE_CHECK_RESULT" => {
                if args.len() < 2 {
                    return Err(invalid("expected return code and plugin output"));
                }
                let code = number(args[0])?;
                let host = self.definitions[&key].service.is_none();
                if code > if host { 2 } else { 3 } {
                    return Err(invalid("invalid passive result code"));
                }
                if !state.objects[&key].passive
                    || !(if host {
                        state.passive_hosts
                    } else {
                        state.passive_services
                    })
                {
                    return Err(invalid("passive checks disabled"));
                }
                if stamp < state.objects[&key].last_check {
                    return Err(invalid("stale passive result"));
                }
                let output = args[1..].join(";").replace("\\n", "\n");
                if output.len() > self.config.max_output_bytes {
                    return Err(invalid("passive output exceeds configured limit"));
                }
                self.apply_result(
                    state,
                    &key,
                    PluginResult::from_text(code as u8, &output, 0.0),
                    true,
                    stamp,
                );
            }
            "ENABLE_HOST_CHECK" | "DISABLE_HOST_CHECK" | "ENABLE_SVC_CHECK"
            | "DISABLE_SVC_CHECK" => {
                count(args, 0)?;
                let r = state.objects.get_mut(&key).expect("known key");
                r.active = name.starts_with("ENABLE");
                if r.active {
                    r.next_check_ms = now_ms();
                }
            }
            "ENABLE_PASSIVE_HOST_CHECKS"
            | "DISABLE_PASSIVE_HOST_CHECKS"
            | "ENABLE_PASSIVE_SVC_CHECKS"
            | "DISABLE_PASSIVE_SVC_CHECKS" => {
                count(args, 0)?;
                state.objects.get_mut(&key).expect("known key").passive =
                    name.starts_with("ENABLE");
            }
            "SCHEDULE_HOST_CHECK"
            | "SCHEDULE_SVC_CHECK"
            | "SCHEDULE_FORCED_HOST_CHECK"
            | "SCHEDULE_FORCED_SVC_CHECK" => {
                count(args, 1)?;
                let time = number(args[0])?
                    .checked_mul(1000)
                    .ok_or_else(|| invalid("check time overflow"))?;
                if self.definitions[&key].check.command.is_empty() {
                    return Err(invalid("object has no active check command"));
                }
                let r = state.objects.get_mut(&key).expect("known key");
                r.next_check_ms = time.max(1);
                r.force = name.contains("FORCED");
            }
            "ACKNOWLEDGE_HOST_PROBLEM" | "ACKNOWLEDGE_SVC_PROBLEM" => {
                if args.len() < 5 {
                    return Err(invalid("expected sticky;notify;persistent;author;comment"));
                }
                let sticky = number(args[0])?;
                if !(1..=2).contains(&sticky) {
                    return Err(invalid("sticky must be 1 or 2"));
                }
                if flag(args[1])? {
                    return Err(invalid(
                        "acknowledgement notifications are not implemented; use notify=0",
                    ));
                }
                let persistent = flag(args[2])?;
                let r = state.objects.get_mut(&key).expect("known key");
                if r.last_check == 0 || r.status.state == shinken_model::CheckState::Ok {
                    return Err(invalid("cannot acknowledge a healthy or pending object"));
                }
                r.acknowledgement = sticky as u8;
                state.comments.push(Comment {
                    id: state.next_id,
                    key,
                    author: args[3].into(),
                    comment: args[4..].join(";"),
                    entry_time: stamp,
                    persistent,
                    entry_type: 4,
                });
                state.next_id += 1;
            }
            "REMOVE_HOST_ACKNOWLEDGEMENT" | "REMOVE_SVC_ACKNOWLEDGEMENT" => {
                count(args, 0)?;
                state
                    .objects
                    .get_mut(&key)
                    .expect("known key")
                    .acknowledgement = 0;
                state
                    .comments
                    .retain(|c| c.key != key || c.entry_type != 4 || c.persistent);
            }
            "ADD_HOST_COMMENT" | "ADD_SVC_COMMENT" => {
                if args.len() < 3 {
                    return Err(invalid("expected persistent;author;comment"));
                }
                state.comments.push(Comment {
                    id: state.next_id,
                    key,
                    author: args[1].into(),
                    comment: args[2..].join(";"),
                    entry_time: stamp,
                    persistent: flag(args[0])?,
                    entry_type: 1,
                });
                state.next_id += 1;
            }
            "DEL_ALL_HOST_COMMENTS" | "DEL_ALL_SVC_COMMENTS" => {
                count(args, 0)?;
                state.comments.retain(|c| c.key != key);
            }
            "SCHEDULE_HOST_DOWNTIME" | "SCHEDULE_SVC_DOWNTIME" => {
                if args.len() < 7 {
                    return Err(invalid(
                        "expected start;end;fixed;trigger;duration;author;comment",
                    ));
                }
                let start = number(args[0])?;
                let end = number(args[1])?;
                let _duration = number(args[4])?;
                if !flag(args[2])? || number(args[3])? != 0 {
                    return Err(invalid("only fixed, untriggered downtimes are implemented"));
                }
                if end <= start || end <= now_ms() / 1000 {
                    return Err(invalid("invalid downtime interval"));
                }
                state.downtimes.retain(|d| d.end_time > now_ms() / 1000);
                state.downtimes.push(Downtime {
                    id: state.next_id,
                    key,
                    author: args[5].into(),
                    comment: args[6..].join(";"),
                    entry_time: stamp,
                    start_time: start,
                    end_time: end,
                });
                state.next_id += 1;
            }
            _ => return Err(invalid("unsupported command")),
        }
        if state.comments.len() + state.downtimes.len() > 10_000 {
            return Err(invalid("comment/downtime limit reached"));
        }
        Ok(())
    }
}
