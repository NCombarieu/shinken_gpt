use clap::{Parser, Subcommand};
use shinken_config::{build_monitoring_config, load_config_tree, MonitoringConfig};
use shinken_engine::{Engine, EngineError, LiveEngine, UnixEndpoint};
use shinken_livestatus::parse_query;
use std::{fs, path::PathBuf, process::ExitCode, time::Duration};
use tokio::{net::TcpListener, task::JoinSet};

#[derive(Debug, Parser)]
#[command(
    name = "shinken-rs",
    version,
    about = "Native Rust monitoring engine (experimental)"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}
#[derive(Debug, Subcommand)]
enum Command {
    /// Validate includes, templates, object references and supported scheduling semantics.
    ConfigCheck { path: PathBuf },
    /// Execute monitoring plugins and expose a Livestatus backend for Thruk.
    Run {
        config: PathBuf,
        /// Run all active checks once and print hosts/services as JSON.
        #[arg(long)]
        once: bool,
        #[arg(long, default_value = "/tmp/shinken-rs-live.sock")]
        livestatus_unix: PathBuf,
        #[arg(long)]
        no_livestatus_unix: bool,
        /// Trusted-network endpoint. Livestatus itself has no transport authentication.
        #[arg(long)]
        livestatus_tcp: Option<String>,
        #[arg(long, default_value_t = 16)]
        max_concurrent_checks: usize,
        /// Atomic retention; restored at startup, saved every 30 s and at shutdown.
        #[arg(long)]
        state_file: Option<PathBuf>,
    },
    /// Validate Livestatus request syntax.
    LivestatusCheck { path: PathBuf },
}
#[tokio::main]
async fn main() -> ExitCode {
    match run(Cli::parse()).await {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("error: {error}");
            ExitCode::FAILURE
        }
    }
}
fn configuration(path: PathBuf) -> Result<MonitoringConfig, shinken_config::LoadError> {
    let loaded = load_config_tree(path)?;
    let config = build_monitoring_config(&loaded)?;
    for warning in &config.warnings {
        eprintln!("warning: {warning}");
    }
    eprintln!(
        "Loaded {} hosts, {} services, {} commands from {} files",
        config.hosts.len(),
        config.services.len(),
        config.commands.len(),
        loaded.files.len()
    );
    Ok(config)
}
async fn shutdown() -> Result<(), EngineError> {
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())?;
    tokio::select! {
        r=tokio::signal::ctrl_c()=>r?,
        _=terminate.recv()=>{},
    }
    Ok(())
}
async fn run(cli: Cli) -> Result<(), Box<dyn std::error::Error>> {
    match cli.command {
        Command::ConfigCheck { path } => {
            configuration(path)?;
            println!("OK");
        }
        Command::LivestatusCheck { path } => {
            let query = parse_query(&fs::read_to_string(path)?)?;
            println!("OK: GET {}", query.table);
        }
        Command::Run {
            config,
            once,
            livestatus_unix,
            no_livestatus_unix,
            livestatus_tcp,
            max_concurrent_checks,
            state_file,
        } => {
            let mut engine = Engine::new(configuration(config.clone())?, max_concurrent_checks)?;
            if let Some(path) = &state_file {
                engine.restore(path).await?;
            }
            if once {
                engine.run_all_checks().await?;
                if let Some(path) = &state_file {
                    engine.save(path).await?;
                }
                let hosts=engine.query(&parse_query("GET hosts\nColumns: name state state_type has_been_checked plugin_output\nOutputFormat: json\nColumnHeaders: on\n\n")?).await?;
                let services=engine.query(&parse_query("GET services\nColumns: host_name description state state_type has_been_checked plugin_output\nOutputFormat: json\nColumnHeaders: on\n\n")?).await?;
                println!(
                    "{{\"hosts\":{},\"services\":{}}}",
                    String::from_utf8(hosts)?,
                    String::from_utf8(services)?
                );
                return Ok(());
            }
            if no_livestatus_unix && livestatus_tcp.is_none() {
                return Err("at least one Livestatus endpoint is required".into());
            }
            // Bind every endpoint before starting checks; bind errors are startup failures.
            let unix = if no_livestatus_unix {
                None
            } else {
                Some(UnixEndpoint::bind(&livestatus_unix)?)
            };
            let tcp = match livestatus_tcp {
                Some(address) => Some(TcpListener::bind(address).await?),
                None => None,
            };
            let live = LiveEngine::new(engine.clone());
            let mut tasks = JoinSet::new();
            if let Some(endpoint) = unix {
                eprintln!("Livestatus Unix: {}", livestatus_unix.display());
                let engine = live.clone();
                tasks.spawn(async move { engine.serve_unix(endpoint).await });
            }
            if let Some(listener) = tcp {
                eprintln!("Livestatus TCP: {}", listener.local_addr()?);
                let engine = live.clone();
                tasks.spawn(async move { engine.serve_tcp(listener).await });
            }
            let mut workers = runtime_tasks(&engine, state_file.clone());
            let mut hangup =
                tokio::signal::unix::signal(tokio::signal::unix::SignalKind::hangup())?;
            let mut control = tokio::time::interval(Duration::from_millis(100));
            let stopping = shutdown();
            tokio::pin!(stopping);
            let result = loop {
                let reload = tokio::select! {
                    result = &mut stopping => break result,
                    result = tasks.join_next() => break task_result(result),
                    result = workers.join_next() => break task_result(result),
                    _ = hangup.recv() => true,
                    _ = control.tick() => engine.take_reload_request().await,
                };
                if !reload {
                    continue;
                }
                let path = config.clone();
                let candidate = tokio::task::spawn_blocking(move || configuration(path)).await;
                let candidate = match candidate {
                    Ok(Ok(config)) => Engine::new(config, max_concurrent_checks),
                    Ok(Err(error)) => {
                        eprintln!("configuration reload rejected: {error}");
                        continue;
                    }
                    Err(error) => {
                        eprintln!("configuration reload failed: {error}");
                        continue;
                    }
                };
                let next = match candidate {
                    Ok(engine) => engine,
                    Err(error) => {
                        eprintln!("configuration reload rejected: {error}");
                        continue;
                    }
                };
                workers.shutdown().await;
                engine = live.replace(next).await;
                workers = runtime_tasks(&engine, state_file.clone());
                eprintln!("configuration reload complete");
            };
            workers.shutdown().await;
            tasks.shutdown().await;
            if let Some(path) = &state_file {
                engine.save(path).await?;
            }
            result?;
        }
    }
    Ok(())
}

fn task_result(
    result: Option<Result<Result<(), EngineError>, tokio::task::JoinError>>,
) -> Result<(), EngineError> {
    match result {
        Some(Ok(Err(error))) => Err(error),
        Some(Err(error)) => Err(EngineError::Task(error)),
        _ => Err(EngineError::Invalid(
            "runtime task stopped unexpectedly".into(),
        )),
    }
}
fn runtime_tasks(engine: &Engine, state_file: Option<PathBuf>) -> JoinSet<Result<(), EngineError>> {
    let mut tasks = JoinSet::new();
    let scheduler = engine.clone();
    tasks.spawn(async move { scheduler.run_forever().await });
    let notifier = engine.clone();
    tasks.spawn(async move { notifier.run_notifications_forever().await });
    let handlers = engine.clone();
    tasks.spawn(async move { handlers.run_event_handlers_forever().await });
    if let Some(path) = state_file {
        let engine = engine.clone();
        tasks.spawn(async move {
            let mut tick = tokio::time::interval(Duration::from_secs(30));
            tick.tick().await;
            loop {
                tick.tick().await;
                engine.save(&path).await?;
            }
            #[allow(unreachable_code)]
            Ok::<(), EngineError>(())
        });
    }
    tasks
}
