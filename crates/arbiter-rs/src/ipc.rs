use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use tracing::{debug, error, info};

/// Message sent from Arbiter to Python daemons
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DaemonMessage {
    pub message_type: String,  // "config", "restart", "stop", "status"
    pub config_version: u64,
    pub data: serde_json::Value,
}

/// Response from Python daemon
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DaemonResponse {
    pub status: String,  // "ok", "error"
    pub message: String,
}

/// IPC client for communicating with Python daemons
pub struct DaemonClient {
    base_url: String,  // e.g., "http://localhost:7770"
    daemon_name: String,
    client: reqwest::Client,
}

impl DaemonClient {
    pub fn new(daemon_name: &str, host: &str, port: u16) -> Self {
        Self {
            base_url: format!("http://{}:{}", host, port),
            daemon_name: daemon_name.to_string(),
            client: reqwest::Client::new(),
        }
    }

    /// Send configuration to a daemon
    pub async fn send_config(&self, config_version: u64, config_json: &serde_json::Value) -> Result<()> {
        let msg = DaemonMessage {
            message_type: "config".to_string(),
            config_version,
            data: config_json.clone(),
        };

        let url = format!("{}/api/config", self.base_url);
        debug!("Sending config to {} [v{}]", self.daemon_name, config_version);

        let resp = self
            .client
            .post(&url)
            .json(&msg)
            .send()
            .await?
            .json::<DaemonResponse>()
            .await?;

        if resp.status == "ok" {
            info!("{} accepted config v{}", self.daemon_name, config_version);
            Ok(())
        } else {
            Err(anyhow!(
                "{} rejected config: {}",
                self.daemon_name,
                resp.message
            ))
        }
    }

    /// Request daemon status
    pub async fn status(&self) -> Result<DaemonResponse> {
        let url = format!("{}/api/status", self.base_url);
        debug!("Checking status of {}", self.daemon_name);

        let resp = self
            .client
            .get(&url)
            .send()
            .await?
            .json::<DaemonResponse>()
            .await?;

        Ok(resp)
    }

    /// Stop a daemon gracefully
    pub async fn stop(&self) -> Result<()> {
        let url = format!("{}/api/stop", self.base_url);
        info!("Stopping {}", self.daemon_name);

        let resp = self
            .client
            .post(&url)
            .send()
            .await?
            .json::<DaemonResponse>()
            .await?;

        if resp.status == "ok" {
            Ok(())
        } else {
            Err(anyhow!("Failed to stop {}: {}", self.daemon_name, resp.message))
        }
    }
}

/// Broadcast configuration to all daemons
pub async fn broadcast_config(
    daemons: &[(String, String, u16)],  // (name, host, port)
    config_version: u64,
    config_json: &serde_json::Value,
) -> Result<Vec<(String, Result<()>)>> {
    let mut results = Vec::new();

    for (name, host, port) in daemons {
        let client = DaemonClient::new(name, host, *port);
        let result = client.send_config(config_version, config_json).await;
        results.push((name.clone(), result));
    }

    Ok(results)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_daemon_client_creation() {
        let client = DaemonClient::new("scheduler", "localhost", 7771);
        assert_eq!(client.daemon_name, "scheduler");
        assert_eq!(client.base_url, "http://localhost:7771");
    }

    #[test]
    fn test_message_serialization() -> Result<()> {
        let msg = DaemonMessage {
            message_type: "config".to_string(),
            config_version: 1,
            data: serde_json::json!({"test": true}),
        };

        let json = serde_json::to_string(&msg)?;
        assert!(json.contains("config_version"));
        Ok(())
    }
}
