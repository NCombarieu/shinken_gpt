use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tracing::{debug, info};

/// Represents a Shinken configuration object (Host, Service, etc.)
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfigObject {
    pub object_type: String,
    pub name: String,
    pub properties: HashMap<String, String>,
}

/// In-memory representation of Shinken configuration
#[derive(Debug, Clone)]
pub struct Config {
    pub hosts: Vec<ConfigObject>,
    pub services: Vec<ConfigObject>,
    pub contacts: Vec<ConfigObject>,
    pub commands: Vec<ConfigObject>,
    pub templates: HashMap<String, ConfigObject>,
    pub version: u64,
}

/// Thread-safe configuration manager with atomic reloading
pub struct ConfigManager {
    config_files: Vec<PathBuf>,
    current: Arc<parking_lot::RwLock<Config>>,
    version: Arc<std::sync::atomic::AtomicU64>,
}

impl ConfigManager {
    /// Create a new config manager and load initial config
    pub fn new(config_files: &[PathBuf]) -> Result<Self> {
        let mgr = Self {
            config_files: config_files.to_vec(),
            current: Arc::new(parking_lot::RwLock::new(Config {
                hosts: Vec::new(),
                services: Vec::new(),
                contacts: Vec::new(),
                commands: Vec::new(),
                templates: HashMap::new(),
                version: 0,
            })),
            version: Arc::new(std::sync::atomic::AtomicU64::new(0)),
        };

        mgr.reload()?;
        Ok(mgr)
    }

    /// Reload configuration from files (atomic operation)
    pub fn reload(&self) -> Result<()> {
        info!("Loading configuration from {} files", self.config_files.len());

        let config = Config {
            hosts: Vec::new(),
            services: Vec::new(),
            contacts: Vec::new(),
            commands: Vec::new(),
            templates: HashMap::new(),
            version: self.version.load(std::sync::atomic::Ordering::Relaxed) + 1,
        };

        // Parse each config file (simplified for demo)
        for config_file in &self.config_files {
            debug!("Parsing: {:?}", config_file);

            if !config_file.exists() {
                return Err(anyhow!("Config file not found: {:?}", config_file));
            }

            // In real implementation, parse Nagios cfg format here
            // For now, we just track that we tried to load it
            debug!("Successfully parsed: {:?}", config_file);
        }

        info!(
            "Configuration loaded: {} hosts, {} services",
            config.hosts.len(),
            config.services.len()
        );

        // Atomic swap (this is the key Rust advantage over Python pickle!)
        let mut current = self.current.write();
        *current = config.clone();
        self.version
            .store(config.version, std::sync::atomic::Ordering::Release);

        info!("Configuration reload complete (v{})", config.version);
        Ok(())
    }

    /// Get current configuration (read-only)
    pub fn get(&self) -> Arc<parking_lot::RwLock<Config>> {
        Arc::clone(&self.current)
    }

    /// Get current configuration version
    pub fn version(&self) -> u64 {
        self.version.load(std::sync::atomic::Ordering::Acquire)
    }

    /// Check if configuration has changed
    pub fn has_changed_since(&self, version: u64) -> bool {
        self.version() > version
    }

    /// Validate configuration without reloading
    pub fn validate(&self) -> Result<()> {
        info!("Validating configuration...");

        for config_file in &self.config_files {
            if !config_file.exists() {
                return Err(anyhow!("Config file not found: {:?}", config_file));
            }
        }

        info!("Configuration validation successful");
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::TempDir;

    #[test]
    fn test_config_reload() -> Result<()> {
        let tmp_dir = TempDir::new()?;
        let config_file = tmp_dir.path().join("test.cfg");
        fs::write(&config_file, "# test config")?;

        let mgr = ConfigManager::new(&[config_file])?;
        assert_eq!(mgr.version(), 1);

        // Reload should increment version
        mgr.reload()?;
        assert_eq!(mgr.version(), 2);

        Ok(())
    }

    #[test]
    fn test_config_validate() -> Result<()> {
        let tmp_dir = TempDir::new()?;
        let config_file = tmp_dir.path().join("test.cfg");
        fs::write(&config_file, "")?;

        let mgr = ConfigManager::new(&[config_file])?;
        assert!(mgr.validate().is_ok());

        Ok(())
    }
}
