use std::{fs, path::PathBuf, process::ExitCode};

use clap::{Parser, Subcommand};
use shinken_config::load_config_tree;
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
    /// Validate one Livestatus query read from a file.
    LivestatusCheck { path: PathBuf },
}

fn main() -> ExitCode {
    match run(Cli::parse()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run(cli: Cli) -> Result<(), Box<dyn std::error::Error>> {
    match cli.command {
        Command::ConfigCheck { path } => {
            let loaded = load_config_tree(&path)?;
            println!(
                "OK: {} object definition(s) in {} file(s)",
                loaded.objects.len(),
                loaded.files.len()
            );
        }
        Command::LivestatusCheck { path } => {
            let input = fs::read_to_string(path)?;
            let query = parse_query(&input)?;
            println!("OK: GET {}", query.table);
        }
    }
    Ok(())
}
