use std::{fs, path::PathBuf, process::ExitCode};

use clap::{Parser, Subcommand};
use shinken_config::{build_monitoring_config, load_config_tree};
use shinken_engine::Engine;
use shinken_livestatus::parse_query;

#[derive(Debug, Parser)]
#[command(name = "shinken-rs", version, about = "Rust implementation of Shinken")]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Debug, Subcommand)]
enum Command {
    /// Load a main config and all of its cfg_file/cfg_dir object definitions.
    ConfigCheck { path: PathBuf },
    /// Start the Rust monitoring engine and its Livestatus endpoints.
    Run {
        /// Main Nagios/Shinken configuration that contains cfg_file/cfg_dir.
        config: PathBuf,
        /// Run every configured check once, print nothing else, then exit.
        #[arg(long)]
        once: bool,
        /// Unix socket exposed to Thruk/Livestatus clients.
        #[arg(long, default_value = "/tmp/shinken-rs-live.sock")]
        livestatus_unix: PathBuf,
        /// Optional TCP endpoint, for example 127.0.0.1:6557.
        #[arg(long)]
        livestatus_tcp: Option<String>,
    },
    /// Validate one Livestatus query read from a file.
    LivestatusCheck { path: PathBuf },
}

#[tokio::main]
async fn main() -> ExitCode {
    match run(Cli::parse()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}

async fn run(cli: Cli) -> Result<(), Box<dyn std::error::Error>> {
    match cli.command {
        Command::ConfigCheck { path } => {
            let loaded = load_config_tree(&path)?;
            let config = build_monitoring_config(&loaded)?;
            println!(
                "OK: {} object(s), {} host(s), {} service(s), {} command(s) in {} file(s)",
                loaded.objects.len(),
                config.hosts.len(),
                config.services.len(),
                config.commands.len(),
                loaded.files.len()
            );
        }
        Command::LivestatusCheck { path } => {
            let input = fs::read_to_string(path)?;
            let query = parse_query(&input)?;
            println!("OK: GET {}", query.table);
        }
        Command::Run {
            config,
            once,
            livestatus_unix,
            livestatus_tcp,
        } => {
            let loaded = load_config_tree(config)?;
            let engine = Engine::new(build_monitoring_config(&loaded)?);
            if once {
                engine.run_all_checks().await;
                return Ok(());
            }
            let unix_engine = engine.clone();
            let mut servers = tokio::task::JoinSet::new();
            servers.spawn(async move { unix_engine.serve_unix(livestatus_unix).await });
            if let Some(address) = livestatus_tcp {
                let tcp_engine = engine.clone();
                servers.spawn(async move { tcp_engine.serve_tcp(&address).await });
            }
            tokio::select! {
                _ = engine.run_forever() => {}
                _ = tokio::signal::ctrl_c() => {}
                Some(result) = servers.join_next() => result??,
            }
        }
    }
    Ok(())
}
