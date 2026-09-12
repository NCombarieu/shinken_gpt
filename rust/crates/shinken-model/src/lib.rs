//! Domain types shared by the Rust Shinken components.

use serde::{Deserialize, Serialize};

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum CheckState {
    Ok,
    Warning,
    Critical,
    Unknown,
}

impl CheckState {
    #[must_use]
    pub const fn from_plugin_status(status: i32) -> Self {
        match status {
            0 => Self::Ok,
            1 => Self::Warning,
            2 => Self::Critical,
            _ => Self::Unknown,
        }
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum StateType {
    Soft,
    Hard,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct CheckRequest {
    pub id: u64,
    pub command_line: String,
    pub timeout_seconds: u64,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct CheckResult {
    pub id: u64,
    pub state: CheckState,
    pub output: String,
    pub execution_time_millis: u64,
}

#[cfg(test)]
mod tests {
    use super::CheckState;

    #[test]
    fn unknown_plugin_statuses_map_to_unknown() {
        assert_eq!(CheckState::from_plugin_status(3), CheckState::Unknown);
        assert_eq!(CheckState::from_plugin_status(127), CheckState::Unknown);
        assert_eq!(CheckState::from_plugin_status(-1), CheckState::Unknown);
    }
}

