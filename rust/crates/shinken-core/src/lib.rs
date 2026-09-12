//! Deterministic scheduling rules with no process or network dependencies.

use shinken_model::{CheckState, StateType};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ServiceStatus {
    pub state: CheckState,
    pub state_type: StateType,
    pub attempt: u32,
    pub max_attempts: u32,
}

impl ServiceStatus {
    #[must_use]
    pub const fn new(max_attempts: u32) -> Self {
        let max_attempts = if max_attempts == 0 { 1 } else { max_attempts };
        Self {
            state: CheckState::Ok,
            state_type: StateType::Hard,
            attempt: 1,
            max_attempts,
        }
    }

    /// Apply the core Nagios retry rule for an active service check.
    #[must_use]
    pub fn apply_result(self, state: CheckState) -> Self {
        if state == CheckState::Ok {
            return Self::new(self.max_attempts);
        }
        if state != self.state || self.state_type == StateType::Hard {
            return Self {
                state,
                state_type: if self.max_attempts <= 1 {
                    StateType::Hard
                } else {
                    StateType::Soft
                },
                attempt: 1,
                max_attempts: self.max_attempts,
            };
        }
        let attempt = self.attempt.saturating_add(1).min(self.max_attempts);
        Self {
            state,
            state_type: if attempt >= self.max_attempts {
                StateType::Hard
            } else {
                StateType::Soft
            },
            attempt,
            max_attempts: self.max_attempts,
        }
    }
}

#[cfg(test)]
mod tests {
    use shinken_model::{CheckState, StateType};

    use super::ServiceStatus;

    #[test]
    fn problem_becomes_hard_after_max_attempts() {
        let first = ServiceStatus::new(3).apply_result(CheckState::Critical);
        assert_eq!((first.state_type, first.attempt), (StateType::Soft, 1));
        let second = first.apply_result(CheckState::Critical);
        assert_eq!((second.state_type, second.attempt), (StateType::Soft, 2));
        let third = second.apply_result(CheckState::Critical);
        assert_eq!((third.state_type, third.attempt), (StateType::Hard, 3));
    }

    #[test]
    fn recovery_is_immediately_hard() {
        let problem = ServiceStatus::new(3)
            .apply_result(CheckState::Critical)
            .apply_result(CheckState::Critical);
        let recovered = problem.apply_result(CheckState::Ok);
        assert_eq!(recovered, ServiceStatus::new(3));
    }
}
