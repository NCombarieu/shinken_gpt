# Structured Logging

Shinken supports both human-readable and structured (JSON) logging for flexible output handling.

## Logging Modes

### Human-Readable (Default)
Logs are formatted for humans reading directly:

```
[INFO    ] shinken.daemons.arbiterdaemon    (arbiterdaemon:main:123) Arbiter started successfully
[WARNING ] shinken.scheduler                (scheduler:schedule_checks:456) No checks scheduled for host web-01
[ERROR   ] shinken.poller                   (pollerdaemon:execute_check:789) Check failed: timeout
```

Use this for:
- Local development
- Interactive terminal viewing
- Debugging

### Structured (JSON)
Logs are formatted as JSON for machine parsing and aggregation:

```json
{"timestamp": "2025-09-14 10:23:45,123", "daemon": "shinken-arbiter", "level": "INFO", "logger": "shinken.daemons.arbiterdaemon", "message": "Arbiter started successfully", "module": "arbiterdaemon", "function": "main", "line": 123}
```

Use this for:
- Production deployments
- Log aggregation (ELK stack, Splunk, Datadog, CloudWatch)
- Automated parsing and alerting
- Container environments

## Enabling Structured Logging

### Via Command-Line Flag
All daemons accept `--json-logs`:

```bash
shinken-arbiter --json-logs -c /etc/shinken/nagios.cfg
shinken-broker --json-logs
shinken-poller --json-logs
```

### Via Environment Variable (Container)
In containers, set `SHINKEN_JSON_LOGS=1`:

```yaml
# compose.yaml
services:
  arbiter:
    environment:
      SHINKEN_JSON_LOGS: "1"
    command: ["arbiter"]
```

### Via Log Configuration File
Update `etc/shinken/logging.cfg` (if present):

```ini
[handler_console]
class = StreamHandler
formatter = json
stream = ext://sys.stderr
```

## Log Levels

Each daemon supports log level control:

| Flag | Level | Use Case |
|------|-------|----------|
| (none) | WARNING | Production — only serious issues |
| `--verbose` | INFO | Standard operation — startup, state changes |
| `--debug` | DEBUG | Development — function calls, data dumps |

Example:

```bash
# Only show errors/warnings
shinken-scheduler

# Show info + warnings/errors
shinken-scheduler --verbose

# Show everything (very verbose)
shinken-scheduler --debug --json-logs
```

## Log File Output

By default, logs go to stderr (for container environments where logs are collected by the container runtime).

To also write to a file:

```bash
shinken-arbiter \
  --logfile /var/log/shinken/arbiter.log \
  --json-logs \
  -c /etc/shinken/nagios.cfg
```

## Log Aggregation Setup

### ELK Stack (Elasticsearch, Logstash, Kibana)

In Logstash pipeline:

```ruby
input {
  file {
    path => "/var/log/shinken/*.log"
    codec => json
  }
}

filter {
  # Logstash can parse JSON automatically
  mutate {
    add_field => { "[@metadata][index_name]" => "shinken" }
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "shinken-%{+YYYY.MM.dd}"
  }
}
```

### Splunk

Forward logs to Splunk:

```bash
# Install Splunk Forwarder on the Shinken host
# /etc/splunk-forwarder/etc/apps/Shinken/local/inputs.conf

[monitor:///var/log/shinken]
sourcetype = shinken
```

Create a Splunk index and search:

```spl
sourcetype="shinken" daemon=shinken-arbiter level=ERROR
```

### CloudWatch (AWS)

In EC2 container or ECS task:

```json
{
  "logDriver": "awslogs",
  "options": {
    "awslogs-group": "/ecs/shinken",
    "awslogs-region": "us-east-1",
    "awslogs-stream-prefix": "ecs"
  }
}
```

CloudWatch will parse JSON logs if configured:

```bash
aws logs put-metric-filter \
  --log-group-name /ecs/shinken \
  --filter-name ErrorCount \
  --filter-pattern '[... level = "ERROR" ...]' \
  --metric-transformations metricName=ShinkenErrors,metricValue=1
```

### Datadog

Add Datadog Agent and configure:

```yaml
# datadog.yaml
logs:
  - type: file
    path: /var/log/shinken/*.log
    service: shinken
    source: shinken
    parser: json
```

### Syslog

Forward to a central syslog server:

```bash
# Using rsyslog on the Shinken host
# /etc/rsyslog.d/shinken.conf

:programname, isequal, "shinken-arbiter" @@syslog-server:514
:programname, isequal, "shinken-scheduler" @@syslog-server:514
```

## Using Logs in Your Application

### From Python Code

```python
import logging
from shinken.structured_logging import LogContext

logger = logging.getLogger(__name__)

# Simple log
logger.info("Host check completed")

# Log with extra fields (will appear in JSON output)
with LogContext(host_id="web-01", check_id=123):
    logger.info("State changed from OK to WARNING")

# Error with traceback
try:
    perform_check()
except Exception:
    logger.exception("Check execution failed")
```

### Grep JSON Logs

```bash
# Find all errors
grep '"level": "ERROR"' /var/log/shinken/arbiter.log

# Find errors from specific host
grep '"level": "ERROR"' /var/log/shinken/*.log | grep '"host_id": "web-01"'

# Pretty-print a line
tail -1 /var/log/shinken/arbiter.log | python -m json.tool
```

### Query in ELK

```json
GET /shinken-*/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "daemon": "shinken-arbiter" } },
        { "match": { "level": "ERROR" } },
        { "range": { "timestamp": { "gte": "now-1d" } } }
      ]
    }
  }
}
```

## Migration from Legacy Logging

Older Shinken versions used:
- Direct `print()` statements (stderr)
- File-based logs with custom format
- `logger.print()` (now removed)

This version standardizes on Python's `logging` module with structured output.

**For existing deployments:**
1. Update monitoring rules to parse the new JSON format
2. Test log aggregation in dev/staging first
3. Deploy with `--json-logs` in production
4. Retire old log parsing rules

## Troubleshooting

### Logs not appearing
- Check log file permissions: `ls -la /var/log/shinken/`
- Ensure log directory exists: `mkdir -p /var/log/shinken`
- Check daemon is actually logging: `shinken-arbiter --verbose -c config.cfg 2>&1 | head -20`

### JSON logs not valid
- Run through `jq` to validate: `jq . < /var/log/shinken/arbiter.log | head -1`
- Check for stderr leakage from libraries
- Enable `--debug` to see what's happening

### Performance impact
- JSON formatting adds <1% CPU overhead
- Use `--json-logs` in production (lower verbosity = fewer logs)
- Aggregate logs off-box (don't fill local disk with large files)

---

See also: `DEVELOPMENT.md` for local testing, `doc/exploitation.md` for operations.
