use anyhow::Result;
use clap::Parser;
use std::path::PathBuf;
use tracing::{info, warn};

mod config;
mod reload;
mod ipc;
mod daemon;

use config::ConfigManager;
use daemon::Arbiter;

#[derive(Parser, Debug)]
#[command(name = "shinken-arbiter")]
#[command(about = "High-performance Shinken Arbiter daemon (Rust)", long_about = None)]
struct Args {
    /// Config files to load
    #[arg(short, long, required = true)]
    config: Vec<PathBuf>,

    /// Daemon mode (fork to background)
    #[arg(short, long)]
    daemon: bool,

    /// Verbose logging
    #[arg(short, long)]
    verbose: bool,

    /// Debug logging
    #[arg(long)]
    debug: bool,

    /// JSON structured logs
    #[arg(long)]
    json_logs: bool,

    /// Verify config and exit
    #[arg(short = 'v', long)]
    verify_only: bool,

    /// Arbiter name (optional)
    #[arg(short = 'n', long)]
    name: Option<String>,

    /// Replace previous running arbiter
    #[arg(short = 'r', long)]
    replace: bool,
}

#[tokio::main]
async fn main() -> Result<()> {
    let args = Args::parse();

    // Setup logging
    setup_logging(&args)?;

    info!("Shinken Arbiter (Rust) v{}", env!("CARGO_PKG_VERSION"));

    // Load configuration
    let config_mgr = ConfigManager::new(&args.config)?;

    if args.verify_only {
        info!("Configuration verification successful");
        return Ok(());
    }

    // Create and run arbiter
    let arbiter = Arbiter::new(config_mgr, args.name)?;
    arbiter.run().await?;

    Ok(())
}

fn setup_logging(args: &Args) -> Result<()> {
    let level = if args.debug {
        "debug"
    } else if args.verbose {
        "info"
    } else {
        "warn"
    };

    if args.json_logs {
        // JSON structured logging
        tracing_subscriber::fmt()
            .json()
            .with_env_filter(level)
            .init();
    } else {
        // Human-readable logging
        tracing_subscriber::fmt()
            .pretty()
            .with_env_filter(level)
            .init();
    }

    Ok(())
}
