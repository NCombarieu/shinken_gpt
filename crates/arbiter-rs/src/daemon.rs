use crate::config::ConfigManager;
use crate::ipc::broadcast_config;
use anyhow::Result;
use tracing::{info, debug, error};

/// Main Shinken Arbiter daemon
pub struct Arbiter {
    config_mgr: ConfigManager,
    name: String,
    daemons: Vec<(String, String, u16)>,  // (name, host, port)
}

impl Arbiter {
    /// Create a new arbiter
    pub fn new(config_mgr: ConfigManager, name: Option<String>) -> Result<Self> {
        let arbiter_name = name.unwrap_or_else(|| "Arbiter".to_string());

        Ok(Self {
            config_mgr,
            name: arbiter_name,
            daemons: vec![
                ("scheduler".to_string(), "localhost".to_string(), 7771),
                ("poller".to_string(), "localhost".to_string(), 7772),
                ("broker".to_string(), "localhost".to_string(), 7773),
                ("receiver".to_string(), "localhost".to_string(), 7774),
                ("reactionner".to_string(), "localhost".to_string(), 7775),
            ],
        })
    }

    /// Main run loop
    pub async fn run(&self) -> Result<()> {
        info!("Starting {}", self.name);

        // Load initial config
        self.config_mgr.validate()?;
        info!("Configuration validated successfully");

        // Get initial config as JSON
        let config_lock = self.config_mgr.get();
        let config = config_lock.read();
        let config_json = serde_json::json!({
            "hosts": config.hosts,
            "services": config.services,
            "contacts": config.contacts,
            "commands": config.commands,
            "version": config.version,
        });
        drop(config);

        // Send config to all daemons
        info!("Distributing configuration to {} daemons", self.daemons.len());
        let results = broadcast_config(&self.daemons, self.config_mgr.version(), &config_json).await?;

        for (daemon_name, result) in results {
            match result {
                Ok(_) => info!("{} accepted configuration", daemon_name),
                Err(e) => error!("{} configuration failed: {}", daemon_name, e),
            }
        }

        // TODO: Watch for config changes and reload
        // TODO: Monitor daemon health
        // TODO: Handle graceful shutdown

        info!("{} running", self.name);

        // Keep running until signal
        tokio::signal::ctrl_c().await?;
        info!("Shutting down {}", self.name);

        Ok(())
    }

    /// Reload configuration and redistribute to daemons
    pub async fn reload(&self) -> Result<()> {
        info!("Reloading configuration (Arbiter: {})", self.name);

        // Atomic reload (this is where Rust shines!)
        self.config_mgr.reload()?;

        // Serialize config efficiently (serde >> pickle)
        let config_lock = self.config_mgr.get();
        let config = config_lock.read();
        let config_json = serde_json::json!({
            "hosts": config.hosts,
            "services": config.services,
            "contacts": config.contacts,
            "commands": config.commands,
            "version": config.version,
        });
        drop(config);

        // Broadcast to all daemons in parallel (tokio >> GIL)
        info!("Broadcasting new configuration v{} to daemons", self.config_mgr.version());
        let results = broadcast_config(&self.daemons, self.config_mgr.version(), &config_json).await?;

        // Check results
        let mut failures = 0;
        for (daemon_name, result) in results {
            match result {
                Ok(_) => debug!("{} reloaded successfully", daemon_name),
                Err(e) => {
                    error!("{} reload failed: {}", daemon_name, e);
                    failures += 1;
                }
            }
        }

        if failures > 0 {
            error!("Reload completed with {} daemon failures", failures);
        } else {
            info!("Reload completed successfully");
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    use std::fs;

    #[tokio::test]
    async fn test_arbiter_creation() -> Result<()> {
        let tmp_dir = TempDir::new()?;
        let config_file = tmp_dir.path().join("test.cfg");
        fs::write(&config_file, "")?;

        let config_mgr = ConfigManager::new(&[config_file])?;
        let arbiter = Arbiter::new(config_mgr, Some("TestArbiter".to_string()))?;

        assert_eq!(arbiter.name, "TestArbiter");
        assert_eq!(arbiter.daemons.len(), 5);  // scheduler, poller, broker, receiver, reactionner

        Ok(())
    }
}
