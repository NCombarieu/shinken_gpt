//! Standalone monitoring engine: execution, state and Livestatus serving.

use std::{
    collections::BTreeMap,
    path::Path,
    sync::Arc,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use serde_json::{json, Value};
use shinken_config::{CommandConfig, HostConfig, MonitoringConfig, ServiceConfig};
use shinken_core::ServiceStatus;
use shinken_livestatus::{fixed16_response, parse_query, OutputFormat, Query, ResponseHeader};
use shinken_model::{CheckState, StateType};
use thiserror::Error;
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    net::{TcpListener, TcpStream, UnixListener, UnixStream},
    process::Command,
    sync::RwLock,
    task::JoinSet,
    time,
};

#[derive(Clone)]
pub struct Engine {
    config: Arc<MonitoringConfig>,
    services: Arc<RwLock<Vec<ServiceRuntime>>>,
}

#[derive(Clone, Debug)]
struct ServiceRuntime {
    definition: ServiceConfig,
    status: ServiceStatus,
    output: String,
    last_check: u64,
    last_execution_millis: u64,
}

#[derive(Debug, Error)]
pub enum EngineError {
    #[error("unknown command {0}")]
    UnknownCommand(String),
    #[error("service {0} references unknown host")]
    UnknownHost(String),
    #[error("cannot bind Livestatus socket: {0}")]
    Bind(#[from] std::io::Error),
}

impl Engine {
    #[must_use]
    pub fn new(config: MonitoringConfig) -> Self {
        let services = config
            .services
            .iter()
            .cloned()
            .map(|definition| ServiceRuntime {
                status: ServiceStatus::new(definition.max_check_attempts),
                definition,
                output: "PENDING".to_owned(),
                last_check: 0,
                last_execution_millis: 0,
            })
            .collect();
        Self {
            config: Arc::new(config),
            services: Arc::new(RwLock::new(services)),
        }
    }

    /// Execute all configured active service checks concurrently.
    pub async fn run_all_checks(&self) {
        let count = self.services.read().await.len();
        let mut tasks = JoinSet::new();
        for index in 0..count {
            let engine = self.clone();
            tasks.spawn(async move { engine.run_service(index).await });
        }
        while tasks.join_next().await.is_some() {}
    }

    /// Execute checks that have reached their configured check interval.
    pub async fn run_due_checks(&self) {
        let now = unix_seconds();
        let due: Vec<_> = self
            .services
            .read()
            .await
            .iter()
            .enumerate()
            .filter_map(|(index, service)| {
                let interval = service.definition.check_interval_seconds;
                (service.last_check == 0 || now.saturating_sub(service.last_check) >= interval)
                    .then_some(index)
            })
            .collect();
        let mut tasks = JoinSet::new();
        for index in due {
            let engine = self.clone();
            tasks.spawn(async move { engine.run_service(index).await });
        }
        while tasks.join_next().await.is_some() {}
    }

    /// Run the scheduling loop until the process receives Ctrl-C.
    pub async fn run_forever(&self) {
        let mut tick = time::interval(Duration::from_secs(1));
        loop {
            tick.tick().await;
            self.run_due_checks().await;
        }
    }

    pub async fn serve_tcp(&self, address: &str) -> Result<(), EngineError> {
        let listener = TcpListener::bind(address).await?;
        loop {
            let (stream, _) = listener.accept().await?;
            let engine = self.clone();
            tokio::spawn(async move { engine.handle_tcp(stream).await });
        }
    }

    pub async fn serve_unix(&self, path: impl AsRef<Path>) -> Result<(), EngineError> {
        let path = path.as_ref();
        if path.exists() {
            std::fs::remove_file(path)?;
        }
        let listener = UnixListener::bind(path)?;
        loop {
            let (stream, _) = listener.accept().await?;
            let engine = self.clone();
            tokio::spawn(async move { engine.handle_unix(stream).await });
        }
    }

    async fn run_service(&self, index: usize) {
        let definition = match self.services.read().await.get(index).cloned() {
            Some(service) => service.definition,
            None => return,
        };
        let result = self.execute(&definition).await;
        let mut services = self.services.write().await;
        let Some(service) = services.get_mut(index) else {
            return;
        };
        service.last_check = unix_seconds();
        match result {
            Ok((state, output, elapsed)) => {
                service.status = service.status.apply_result(state);
                service.output = output;
                service.last_execution_millis = elapsed;
            }
            Err(error) => {
                service.status = service.status.apply_result(CheckState::Unknown);
                service.output = format!("UNKNOWN: {error}");
                service.last_execution_millis = 0;
            }
        }
    }

    async fn execute(
        &self,
        service: &ServiceConfig,
    ) -> Result<(CheckState, String, u64), EngineError> {
        let host = self
            .config
            .hosts
            .get(&service.host_name)
            .ok_or_else(|| EngineError::UnknownHost(service.host_name.clone()))?;
        let (command_name, arguments) = split_command(&service.check_command);
        let command = self
            .config
            .commands
            .get(command_name)
            .ok_or_else(|| EngineError::UnknownCommand(command_name.to_owned()))?;
        let command_line = render_command(command, host, arguments, &self.config.resource_macros);
        let started = std::time::Instant::now();
        let child = Command::new("/bin/sh")
            .arg("-c")
            .arg(command_line)
            .output();
        let output = time::timeout(Duration::from_secs(60), child)
            .await
            .map_err(|_| EngineError::UnknownCommand("check timeout".to_owned()))?
            .map_err(EngineError::Bind)?;
        let state = CheckState::from_plugin_status(output.status.code().unwrap_or(3));
        let mut text = String::from_utf8_lossy(&output.stdout).trim_end().to_owned();
        let stderr = String::from_utf8_lossy(&output.stderr).trim_end().to_owned();
        if !stderr.is_empty() {
            if !text.is_empty() {
                text.push_str(" | ");
            }
            text.push_str(&stderr);
        }
        if text.is_empty() {
            text = state_name(state).to_owned();
        }
        let elapsed = u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX);
        Ok((state, text, elapsed))
    }

    async fn handle_tcp(&self, stream: TcpStream) {
        let _ = self.handle_connection(stream).await;
    }

    async fn handle_unix(&self, stream: UnixStream) {
        let _ = self.handle_connection(stream).await;
    }

    async fn handle_connection<S>(&self, stream: S) -> Result<(), std::io::Error>
    where
        S: tokio::io::AsyncRead + tokio::io::AsyncWrite + Unpin,
    {
        let mut reader = BufReader::new(stream);
        let mut request = String::new();
        loop {
            let mut line = String::new();
            if reader.read_line(&mut line).await? == 0 || line == "\n" || line == "\r\n" {
                break;
            }
            request.push_str(&line);
        }
        let mut stream = reader.into_inner();
        let response = match parse_query(&request) {
            Ok(query) => self.render_query(&query).await,
            Err(error) => format!("400 {error}\n").into_bytes(),
        };
        stream.write_all(&response).await
    }

    async fn render_query(&self, query: &Query) -> Vec<u8> {
        let rows = match query.table.as_str() {
            "hosts" => self.host_rows().await,
            "services" => self.service_rows().await,
            "status" => vec![status_row()],
            _ => Vec::new(),
        };
        let rows: Vec<_> = rows
            .into_iter()
            .filter(|row| query.filters.iter().all(|filter| matches_filter(row, filter)))
            .take(query.limit.unwrap_or(usize::MAX))
            .collect();
        let body = encode_rows(&rows, query);
        if query.response_header == ResponseHeader::Fixed16 {
            fixed16_response(200, &body)
        } else {
            body
        }
    }

    async fn host_rows(&self) -> Vec<Row> {
        let services = self.services.read().await;
        self.config
            .hosts
            .values()
            .map(|host| {
                let state = services
                    .iter()
                    .filter(|service| service.definition.host_name == host.name)
                    .map(|service| numeric_state(service.status.state))
                    .max()
                    .unwrap_or(0);
                row([
                    ("name", json!(host.name)),
                    ("host_name", json!(host.name)),
                    ("address", json!(host.address)),
                    ("state", json!(state)),
                ])
            })
            .collect()
    }

    async fn service_rows(&self) -> Vec<Row> {
        self.services
            .read()
            .await
            .iter()
            .map(|service| {
                row([
                    ("host_name", json!(service.definition.host_name)),
                    ("description", json!(service.definition.description)),
                    ("state", json!(numeric_state(service.status.state))),
                    ("state_type", json!(numeric_state_type(service.status.state_type))),
                    ("current_attempt", json!(service.status.attempt)),
                    ("max_check_attempts", json!(service.status.max_attempts)),
                    ("plugin_output", json!(service.output)),
                    ("last_check", json!(service.last_check)),
                    ("execution_time", json!(service.last_execution_millis as f64 / 1000.0)),
                ])
            })
            .collect()
    }
}

type Row = BTreeMap<String, Value>;

fn row<const N: usize>(entries: [(&str, Value); N]) -> Row {
    entries
        .into_iter()
        .map(|(key, value)| (key.to_owned(), value))
        .collect()
}

fn status_row() -> Row {
    row([("program_version", json!(env!("CARGO_PKG_VERSION"))), ("num_hosts", json!(0))])
}

fn encode_rows(rows: &[Row], query: &Query) -> Vec<u8> {
    let columns = if query.columns.is_empty() {
        rows.first()
            .map(|row| row.keys().cloned().collect())
            .unwrap_or_default()
    } else {
        query.columns.clone()
    };
    match query.output_format {
        OutputFormat::Json | OutputFormat::WrappedJson => {
            let values: Vec<_> = rows
                .iter()
                .map(|row| {
                    Value::Array(
                        columns
                            .iter()
                            .map(|column| row.get(column).cloned().unwrap_or(Value::Null))
                            .collect(),
                    )
                })
                .collect();
            let value = if query.output_format == OutputFormat::WrappedJson {
                json!({"columns": columns, "data": values})
            } else if query.column_headers {
                json!([Value::Array(columns.into_iter().map(Value::String).collect()), values])
            } else {
                Value::Array(values)
            };
            serde_json::to_vec(&value).unwrap_or_else(|_| b"[]".to_vec())
        }
        OutputFormat::Csv | OutputFormat::Python => rows
            .iter()
            .map(|row| {
                let values: Vec<_> = columns
                    .iter()
                    .map(|column| stringify_value(row.get(column)))
                    .collect();
                values.join(";") + "\n"
            })
            .collect::<String>()
            .into_bytes(),
    }
}

fn stringify_value(value: Option<&Value>) -> String {
    match value {
        Some(Value::String(value)) => value.replace('\n', "\\n"),
        Some(value) => value.to_string(),
        None => String::new(),
    }
}

fn matches_filter(row: &Row, filter: &str) -> bool {
    let mut parts = filter.split_whitespace();
    let Some(column) = parts.next() else {
        return true;
    };
    let Some(operator) = parts.next() else {
        return true;
    };
    let value = parts.collect::<Vec<_>>().join(" ");
    let actual = stringify_value(row.get(column));
    match operator {
        "=" => actual == value,
        "!=" => actual != value,
        ">=" => actual >= value,
        "<=" => actual <= value,
        ">" => actual > value,
        "<" => actual < value,
        _ => true,
    }
}

fn split_command(command: &str) -> (&str, Vec<&str>) {
    let mut parts = command.split('!');
    (parts.next().unwrap_or_default(), parts.collect())
}

fn render_command(
    command: &CommandConfig,
    host: &HostConfig,
    arguments: Vec<&str>,
    resource_macros: &std::collections::HashMap<String, String>,
) -> String {
    let mut line = command
        .command_line
        .replace("$HOSTNAME$", &host.name)
        .replace("$HOSTADDRESS$", &host.address);
    for (index, argument) in arguments.into_iter().enumerate() {
        line = line.replace(&format!("$ARG{}$", index + 1), argument);
    }
    for _ in 0..8 {
        let expanded = resource_macros
            .iter()
            .fold(line.clone(), |current, (name, value)| {
                current.replace(name, value)
            });
        if expanded == line {
            break;
        }
        line = expanded;
    }
    line
}

fn unix_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |duration| duration.as_secs())
}

const fn numeric_state(state: CheckState) -> u8 {
    match state {
        CheckState::Ok => 0,
        CheckState::Warning => 1,
        CheckState::Critical => 2,
        CheckState::Unknown => 3,
    }
}

const fn numeric_state_type(state_type: StateType) -> u8 {
    match state_type {
        StateType::Soft => 0,
        StateType::Hard => 1,
    }
}

const fn state_name(state: CheckState) -> &'static str {
    match state {
        CheckState::Ok => "OK",
        CheckState::Warning => "WARNING",
        CheckState::Critical => "CRITICAL",
        CheckState::Unknown => "UNKNOWN",
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use shinken_config::{CommandConfig, HostConfig, MonitoringConfig, ServiceConfig};
    use shinken_livestatus::parse_query;

    use super::{render_command, Engine};

    #[test]
    fn renders_standard_host_and_argument_macros() {
        let command = CommandConfig {
            name: "check_ping".into(),
            command_line: "check_ping -H $HOSTADDRESS$ -w $ARG1$".into(),
        };
        let host = HostConfig {
            name: "edge".into(),
            address: "192.0.2.10".into(),
        };
        assert_eq!(
            render_command(&command, &host, vec!["100,20%"], &HashMap::new()),
            "check_ping -H 192.0.2.10 -w 100,20%"
        );
    }

    #[tokio::test]
    async fn executes_a_check_and_exposes_it_to_livestatus() {
        let engine = Engine::new(MonitoringConfig {
            commands: HashMap::from([(
                "check_dummy".into(),
                CommandConfig {
                    name: "check_dummy".into(),
                    command_line: "printf 'healthy'; exit 0".into(),
                },
            )]),
            hosts: HashMap::from([(
                "edge".into(),
                HostConfig {
                    name: "edge".into(),
                    address: "192.0.2.10".into(),
                },
            )]),
            services: vec![ServiceConfig {
                host_name: "edge".into(),
                description: "dummy".into(),
                check_command: "check_dummy".into(),
                max_check_attempts: 1,
                check_interval_seconds: 60,
            }],
            resource_macros: HashMap::new(),
        });
        engine.run_all_checks().await;
        let query = parse_query("GET services\nColumns: host_name description state plugin_output\nOutputFormat: json\n\n").unwrap();
        let response = engine.render_query(&query).await;
        assert_eq!(response, br#"[["edge","dummy",0,"healthy"]]"#);
    }
}
