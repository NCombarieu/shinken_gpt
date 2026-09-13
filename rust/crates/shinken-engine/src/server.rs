use crate::{Engine, EngineError};
use shinken_livestatus::{fixed16_response, parse_query, ResponseHeader};
use std::{
    fs, io,
    os::unix::fs::{FileTypeExt, MetadataExt, PermissionsExt},
    path::{Path, PathBuf},
    sync::Arc,
    time::Duration,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncRead, AsyncWrite, AsyncWriteExt, BufReader},
    net::{TcpListener, UnixListener},
    sync::Semaphore,
    task::JoinSet,
    time,
};

/// Refuse an existing path. Cleanup checks device/inode so it cannot unlink a replacement.
pub struct UnixEndpoint {
    listener: UnixListener,
    path: PathBuf,
    device: u64,
    inode: u64,
}
impl UnixEndpoint {
    pub fn bind(path: &Path) -> Result<Self, EngineError> {
        let listener = UnixListener::bind(path)?;
        let metadata = fs::symlink_metadata(path)?;
        let endpoint = Self {
            listener,
            path: path.into(),
            device: metadata.dev(),
            inode: metadata.ino(),
        };
        fs::set_permissions(path, fs::Permissions::from_mode(0o660))?;
        Ok(endpoint)
    }
}
impl Drop for UnixEndpoint {
    fn drop(&mut self) {
        if let Ok(m) = fs::symlink_metadata(&self.path) {
            if m.file_type().is_socket() && m.dev() == self.device && m.ino() == self.inode {
                let _ = fs::remove_file(&self.path);
            }
        }
    }
}
impl Engine {
    pub async fn serve_tcp(&self, listener: TcpListener) -> Result<(), EngineError> {
        let permits = Arc::new(Semaphore::new(128));
        let mut tasks = JoinSet::new();
        loop {
            tokio::select! {
                accepted=listener.accept()=>{
                    let (stream,_)=accepted?;
                    let Ok(permit)=permits.clone().try_acquire_owned() else{continue;};
                    let engine=self.clone();
                    tasks.spawn(async move{let _permit=permit;let _=engine.handle(stream).await;});
                },
                result=tasks.join_next(),if !tasks.is_empty()=>{if let Some(result)=result{result?;}},
            }
        }
    }
    pub async fn serve_unix(&self, endpoint: UnixEndpoint) -> Result<(), EngineError> {
        let permits = Arc::new(Semaphore::new(128));
        let mut tasks = JoinSet::new();
        loop {
            tokio::select! {
                accepted=endpoint.listener.accept()=>{
                    let (stream,_)=accepted?;
                    let Ok(permit)=permits.clone().try_acquire_owned() else{continue;};
                    let engine=self.clone();
                    tasks.spawn(async move{let _permit=permit;let _=engine.handle(stream).await;});
                },
                result=tasks.join_next(),if !tasks.is_empty()=>{if let Some(result)=result{result?;}},
            }
        }
    }
    async fn handle<S: AsyncRead + AsyncWrite + Unpin>(&self, stream: S) -> io::Result<()> {
        let mut stream = BufReader::new(stream);
        loop {
            let request = time::timeout(Duration::from_secs(15), read_request(&mut stream))
                .await
                .map_err(|_| {
                    io::Error::new(io::ErrorKind::TimedOut, "Livestatus request timed out")
                })??;
            if request.is_empty() {
                return Ok(());
            }
            let fixed = request
                .lines()
                .any(|l| l.trim() == "ResponseHeader: fixed16");
            let mut keep_alive = false;
            let response = if request.starts_with("COMMAND ") {
                let commands = request
                    .lines()
                    .filter(|l| !l.starts_with("ResponseHeader:"))
                    .collect::<Vec<_>>()
                    .join("\n");
                match self.command(&commands).await {
                    Ok(()) => {
                        if fixed {
                            fixed16_response(200, b"")
                        } else {
                            Vec::new()
                        }
                    }
                    Err(e) => error_response(400, &e.to_string(), fixed),
                }
            } else {
                match parse_query(&request) {
                    Ok(query) => {
                        keep_alive = query.keep_alive;
                        if keep_alive && query.response_header == ResponseHeader::Off {
                            keep_alive = false;
                            error_response(400, "KeepAlive requires ResponseHeader: fixed16", fixed)
                        } else {
                            match self.query(&query).await {
                                Ok(body) => body,
                                Err(e) => error_response(400, &e.to_string(), fixed),
                            }
                        }
                    }
                    Err(e) => error_response(400, &e.to_string(), fixed),
                }
            };
            time::timeout(Duration::from_secs(15), async {
                stream.get_mut().write_all(&response).await?;
                stream.get_mut().flush().await
            })
            .await
            .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "Livestatus write timed out"))??;
            if !keep_alive {
                return Ok(());
            }
        }
    }
}
fn error_response(code: u16, message: &str, fixed: bool) -> Vec<u8> {
    let body = format!("{message}\n");
    if fixed {
        fixed16_response(code, body.as_bytes())
    } else {
        format!("{code} {body}").into_bytes()
    }
}
async fn read_request<S: AsyncRead + Unpin>(reader: &mut BufReader<S>) -> io::Result<String> {
    let mut bytes = Vec::new();
    loop {
        let available = reader.fill_buf().await?;
        if available.is_empty() {
            break;
        }
        let n = available
            .iter()
            .position(|b| *b == b'\n')
            .map_or(available.len(), |i| i + 1);
        if bytes.len() + n > 64 * 1024 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidData,
                "request exceeds 64 KiB",
            ));
        }
        bytes.extend_from_slice(&available[..n]);
        reader.consume(n);
        if bytes.ends_with(b"\n\n") || bytes.ends_with(b"\r\n\r\n") {
            break;
        }
    }
    String::from_utf8(bytes).map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))
}
