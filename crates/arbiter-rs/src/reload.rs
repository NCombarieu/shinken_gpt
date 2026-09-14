use anyhow::Result;
use notify::{Watcher, RecursiveMode, Result as NotifyResult};
use notify::recommended_watcher;
use std::path::PathBuf;
use std::sync::mpsc;
use tracing::{debug, info, warn};

/// Reload event
#[derive(Debug, Clone)]
pub enum ReloadEvent {
    ConfigChanged,
    ManualReload,
    Shutdown,
}

/// Watch configuration files for changes and trigger reloads
pub struct ConfigWatcher {
    config_files: Vec<PathBuf>,
    tx: mpsc::Sender<ReloadEvent>,
}

impl ConfigWatcher {
    /// Create a new config watcher
    pub fn new(config_files: Vec<PathBuf>) -> (Self, mpsc::Receiver<ReloadEvent>) {
        let (tx, rx) = mpsc::channel();

        (
            Self { config_files, tx },
            rx,
        )
    }

    /// Start watching configuration files
    pub fn watch(&self) -> Result<()> {
        info!("Starting file watcher for {} config files", self.config_files.len());

        let (tx, rx) = mpsc::channel();
        let mut watcher = recommended_watcher(move |res: NotifyResult<notify::Event>| {
            match res {
                Ok(event) => {
                    if event.kind.is_modify() {
                        debug!("Config file modified: {:?}", event.paths);
                        let _ = tx.send(());
                    }
                }
                Err(e) => warn!("Watch error: {}", e),
            }
        })?;

        // Watch each config file and its directory
        for config_file in &self.config_files {
            if let Some(dir) = config_file.parent() {
                debug!("Watching directory: {:?}", dir);
                watcher.watch(dir, RecursiveMode::NonRecursive)?;
            }
        }

        // Listen for changes and send reload events
        let tx = self.tx.clone();
        std::thread::spawn(move || {
            for _ in rx.iter() {
                debug!("Config file change detected, queuing reload");
                let _ = tx.send(ReloadEvent::ConfigChanged);
            }
        });

        Ok(())
    }

    /// Get reload event receiver
    pub fn receiver(&self) -> mpsc::Receiver<ReloadEvent> {
        let (_tx, rx) = mpsc::channel();

        // Note: In production, you'd use a broadcast channel
        // This is simplified for demo
        rx
    }
}

/// Reload coordinator
pub struct ReloadCoordinator {
    watcher: ConfigWatcher,
}

impl ReloadCoordinator {
    pub fn new(config_files: Vec<PathBuf>) -> Self {
        let (watcher, _) = ConfigWatcher::new(config_files);
        Self { watcher }
    }

    /// Start reload coordination
    pub async fn start(&self) -> Result<()> {
        info!("Starting reload coordinator");
        self.watcher.watch()?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    use std::fs;

    #[test]
    fn test_config_watcher_creation() -> Result<()> {
        let tmp_dir = TempDir::new()?;
        let config_file = tmp_dir.path().join("test.cfg");
        fs::write(&config_file, "")?;

        let (watcher, _rx) = ConfigWatcher::new(vec![config_file]);
        assert_eq!(watcher.config_files.len(), 1);
        Ok(())
    }
}
