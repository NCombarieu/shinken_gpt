use std::{collections::BTreeSet, io, os::unix::process::CommandExt, process::Stdio, time::{Duration, Instant}};
use nix::{sys::signal::{killpg, Signal}, unistd::Pid};
use shinken_config::{Attributes, MonitoringConfig};
use tokio::{io::{AsyncRead, AsyncReadExt}, process::Command, time};
use crate::Definition;

pub(crate) struct PluginResult {
    pub code:u8,pub output:String,pub long_output:String,pub perf_data:String,pub elapsed:f64,
}
impl PluginResult {
    pub(crate) fn from_text(code:u8,text:&str,elapsed:f64)->Self {
        let mut lines=text.lines();
        let first=lines.next().unwrap_or("");
        let (output,first_perf)=first.split_once('|').unwrap_or((first,""));
        let mut long=Vec::new();let mut perf=vec![first_perf.trim().to_owned()];
        for line in lines {
            let (message,data)=line.split_once('|').unwrap_or((line,""));
            if !message.is_empty(){long.push(message.to_owned());}
            if !data.trim().is_empty(){perf.push(data.trim().to_owned());}
        }
        Self{code,output:if output.is_empty(){"(no plugin output)".into()}else{output.trim_end().into()},
            long_output:long.join("\n"),perf_data:perf.into_iter().filter(|s|!s.is_empty()).collect::<Vec<_>>().join(" "),elapsed}
    }
    fn failure(message:String,elapsed:f64)->Self {
        Self{code:3,output:format!("UNKNOWN: {message}"),long_output:String::new(),perf_data:String::new(),elapsed}
    }
}
fn arguments(command:&str)->Vec<String> {
    let mut parts=vec![String::new()];let mut chars=command.chars().peekable();
    while let Some(c)=chars.next() {
        if c=='\\'&&chars.peek()==Some(&'!') {
            chars.next();parts.last_mut().expect("one part").push('!');
        } else if c=='!' {parts.push(String::new());}
        else {parts.last_mut().expect("one part").push(c);}
    }
    parts
}
fn substitute(text:&str,macros:&Attributes)->Result<String,String> {
    let mut result=String::new();let mut rest=text;
    while let Some(start)=rest.find('$') {
        result.push_str(&rest[..start]);rest=&rest[start+1..];
        if let Some(end)=rest.find('$') {
            let name=&rest[..end];
            if !name.is_empty()&&name.chars().all(|c|c.is_ascii_uppercase()||c.is_ascii_digit()||c=='_') {
                let key=format!("{}{}{}","$",name,"$");
                result.push_str(macros.get(&key).ok_or_else(||format!("unresolved macro {key}"))?);
                rest=&rest[end+1..];continue;
            }
        }
        result.push('$');
    }
    result.push_str(rest);Ok(result)
}
fn render(config:&MonitoringConfig,d:&Definition)->Result<String,String> {
    let parts=arguments(&d.check.command);
    let command=config.commands.get(&parts[0]).ok_or_else(||format!("unknown command {}",parts[0]))?;
    let host=&config.hosts[&d.host];let mut macros=config.resource_macros.clone();
    macros.insert("$HOSTNAME$".into(),host.name.clone());
    macros.insert("$HOSTADDRESS$".into(),host.address.clone());
    macros.insert("$HOSTALIAS$".into(),host.attributes.get("alias").cloned().unwrap_or_else(||host.name.clone()));
    macros.insert("$SERVICEDESC$".into(),d.service.clone().unwrap_or_default());
    macros.insert("$TIMET$".into(),(crate::now_ms()/1000).to_string());
    for (index,arg) in parts.iter().skip(1).enumerate(){macros.insert(format!("$ARG{}$",index+1),arg.clone());}
    for (prefix,a) in [("HOST",&host.attributes),("SERVICE",&d.attributes)] {
        for (key,value) in a {
            if let Some(name)=key.strip_prefix('_'){macros.insert(format!("$_{prefix}{}$",name.to_ascii_uppercase()),value.clone());}
        }
    }
    let mut line=command.command_line.clone();let mut seen=BTreeSet::new();
    for _ in 0..32 {
        if !seen.insert(line.clone()){return Err("recursive command macros".into());}
        let next=substitute(&line,&macros)?;
        if next==line{return Ok(line.replace("$$","$"));}
        line=next;
    }
    Err("command macro expansion exceeds 32 levels".into())
}
struct ProcessGroup(Pid);
impl Drop for ProcessGroup {
    fn drop(&mut self){let _=killpg(self.0,Signal::SIGKILL);}
}
async fn drain(mut reader:impl AsyncRead+Unpin,limit:usize)->io::Result<(Vec<u8>,bool)> {
    let mut bytes=Vec::new();let mut buffer=[0;8192];let mut truncated=false;
    loop {
        let n=reader.read(&mut buffer).await?;if n==0{break;}
        let keep=n.min(limit.saturating_sub(bytes.len()));bytes.extend_from_slice(&buffer[..keep]);truncated|=keep<n;
    }
    Ok((bytes,truncated))
}
pub(crate) async fn run(config:&MonitoringConfig,d:&Definition)->PluginResult {
    let started=Instant::now();
    let line=match render(config,d){Ok(v)=>v,Err(e)=>return PluginResult::failure(e,0.0)};
    let mut process=std::process::Command::new("/bin/sh");
    process.arg("-c").arg(line).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped()).process_group(0);
    let mut command=Command::from(process);command.kill_on_drop(true);
    let mut child=match command.spawn(){Ok(v)=>v,Err(e)=>return PluginResult::failure(format!("cannot spawn check: {e}"),started.elapsed().as_secs_f64())};
    let Some(pid)=child.id().and_then(|id|i32::try_from(id).ok()) else {
        let _=child.kill().await;return PluginResult::failure("cannot obtain check process id".into(),0.0);
    };
    let group=ProcessGroup(Pid::from_raw(pid));
    let stdout=child.stdout.take().expect("piped stdout");let stderr=child.stderr.take().expect("piped stderr");
    let result=time::timeout(Duration::from_millis(d.check.timeout_ms),async {
        tokio::try_join!(child.wait(),drain(stdout,config.max_output_bytes),drain(stderr,config.max_output_bytes))
    }).await;
    drop(group);let elapsed=started.elapsed().as_secs_f64();
    match result {
        Err(_)=>{let _=child.kill().await;let _=child.wait().await;PluginResult::failure(format!("check timed out after {} ms",d.check.timeout_ms),elapsed)},
        Ok(Err(e))=>{let _=child.kill().await;let _=child.wait().await;PluginResult::failure(format!("check I/O: {e}"),elapsed)},
        Ok(Ok((status,(out,truncated),(err,err_truncated))))=>{
            let code=match status.code(){Some(0..=3)=>status.code().unwrap_or(3) as u8,_=>3};
            let mut result=PluginResult::from_text(code,&String::from_utf8_lossy(&out),elapsed);
            if !err.is_empty() {
                if !result.long_output.is_empty(){result.long_output.push('\n');}
                result.long_output.push_str("stderr: ");result.long_output.push_str(String::from_utf8_lossy(&err).trim_end());
            }
            if truncated||err_truncated{result.long_output.push_str("\n[plugin output truncated]");}
            if status.code().is_none_or(|c|!(0..=3).contains(&c)) {
                result.output=format!("UNKNOWN: invalid plugin exit status {status}: {}",result.output);
            }
            result
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn plugin_output_and_escaped_arguments() {
        let r=PluginResult::from_text(2,"CRITICAL | x=2\nmore information\nlast | y=3",0.1);
        assert_eq!(r.output,"CRITICAL");assert_eq!(r.long_output,"more information\nlast");
        assert_eq!(r.perf_data,"x=2 y=3");
        assert_eq!(arguments(r"cmd!a\!b!c"),vec!["cmd","a!b","c"]);
        assert!(substitute("$UNDEFINED$",&Attributes::new()).is_err());
    }
}
