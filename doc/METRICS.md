# Metrics & TimeSeries Data (InfluxDB + Grafana)

Shinken can export performance metrics to **InfluxDB** for graphing, trending, and alerting via **Grafana**.

## What Gets Stored?

Every Nagios check produces **perfdata** (performance data) — metric values with thresholds:

```
CPU check output:
  cpu=87.5%;80;95;0;100 temp=62C;70;80;0;100
  ↓ perfdata ↓
  Stored in InfluxDB as:
    - check_cpu{host=web-01, service=CPU}: 87.5
    - check_temp{host=web-01, service=CPU}: 62
```

These are stored **separately** from events (which go to Livestatus/SQL):

| Data | Storage | Use |
|------|---------|-----|
| **Events** (state changes, alerts) | Livestatus (SQL) | SLA reports, compliance |
| **Metrics** (CPU, disk, latency) | InfluxDB (TimeSeries) | Graphs, trending, thresholds |

## Architecture

```
Shinken Broker
    ├─→ Livestatus Module (SQL: SQLite/MySQL/Oracle)
    │   └─ Events: state changes, alerts, downtime
    │   └─ API: Livestatus socket for Thruk
    │
    └─→ TimeSeries Module (InfluxDB)
        └─ Metrics: perfdata from checks
        └─ API: InfluxDB query engine
        └─ Consumers: Grafana, alerting
```

## Installation

### 1. Install InfluxDB

**Docker (recommended):**
```bash
podman run -d \
  --name influxdb \
  -p 8086:8086 \
  -e INFLUXDB_DB=shinken \
  -e INFLUXDB_ADMIN_USER=admin \
  -e INFLUXDB_ADMIN_PASSWORD=password \
  influxdb:2.7
```

**Or native (Linux):**
```bash
# Fedora
sudo dnf install influxdb

# Ubuntu
curl https://repos.influxdata.com/influxdata-archive_compat.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg > /dev/null
echo 'deb [signed-by=/etc/apt/trusted.gpg.d/influxdata-archive_compat.gpg] https://repos.influxdata.com/debian stable main' | sudo tee /etc/apt/sources.list.d/influxdata.list
sudo apt-get update && sudo apt-get install influxdb

# Start
sudo systemctl start influxdb
sudo systemctl enable influxdb
```

**Verify:**
```bash
curl http://localhost:8086/api/v1/ping
```

### 2. Install Grafana

**Docker:**
```bash
podman run -d \
  --name grafana \
  -p 3000:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=admin \
  grafana/grafana:latest
```

**Or native:**
```bash
# Fedora
sudo dnf install grafana-enterprise

# Ubuntu
sudo apt-get install grafana

# Start
sudo systemctl start grafana-server
sudo systemctl enable grafana-server
```

**Access:** http://localhost:3000 (login: admin/admin)

### 3. Install Python InfluxDB Client

```bash
pip install influxdb-client>=1.36
```

## Configuration

### Configure Shinken Broker

Update `etc/brokers/broker-master.cfg`:

```ini
modules = broker_livestatus,broker_timeseries

# Existing Livestatus config
[broker_livestatus]
module_type = broker
broker_log_file = /var/log/shinken/livestatus.log
logstore_type = logstore_sqlite
logstore_sqlite_database_path = /var/lib/shinken/livestatus.db

# NEW: InfluxDB metrics export
[broker_timeseries]
module_type = broker_timeseries
influx_host = localhost
influx_port = 8086
influx_database = shinken
influx_username = admin
influx_password = password
influx_ssl = 0
influx_timeout = 10
# Batch writes for efficiency
influx_batch_size = 100
influx_batch_timeout = 5
```

### Configure InfluxDB Data Retention

Keep metrics for 30 days by default:

```bash
# Via InfluxDB CLI
influx bucket create \
  --name shinken \
  --org default \
  --retention 30d \
  --token <YOUR_TOKEN>
```

## Connect Grafana to InfluxDB

### 1. Add InfluxDB Data Source

In Grafana:
1. Menu → Configuration → Data Sources
2. Click "Add data source"
3. Select "InfluxDB"
4. Configure:
   - **URL**: `http://localhost:8086`
   - **Database**: `shinken`
   - **Username**: `admin`
   - **Password**: `password`
5. Click "Save & test"

### 2. Create Your First Dashboard

**Basic CPU Usage Graph:**

1. Menu → Dashboards → New → New Dashboard
2. Click "Add panel"
3. In Query editor:
   ```sql
   from(bucket:"shinken")
     |> range(start: -24h)
     |> filter(fn: (r) => r._measurement == "check_cpu" and r.host == "web-01")
     |> aggregateWindow(every: 5m, fn: mean)
   ```
4. In Visualization, choose "Time series"
5. Set title: "Web-01 CPU Usage"
6. Click "Save"

**Available Metrics (from perfdata):**
- `check_cpu` — CPU usage percentage
- `check_disk` — Disk usage
- `check_memory` — Memory usage
- `check_latency` — Network latency
- `check_http_time` — HTTP response time
- (Any custom perfdata from your checks)

## Sample Dashboards

### 1. Host Overview
Shows CPU, memory, disk for a host:

```json
{
  "dashboard": {
    "title": "Host Overview: $host",
    "panels": [
      {
        "title": "CPU Usage",
        "targets": [{
          "query": "from(bucket:\"shinken\") |> range(start: -24h) |> filter(fn: (r) => r._measurement == \"check_cpu\" and r.host == \"$host\")"
        }]
      },
      {
        "title": "Memory Usage",
        "targets": [{
          "query": "from(bucket:\"shinken\") |> range(start: -24h) |> filter(fn: (r) => r._measurement == \"check_memory\" and r.host == \"$host\")"
        }]
      },
      {
        "title": "Disk Usage",
        "targets": [{
          "query": "from(bucket:\"shinken\") |> range(start: -24h) |> filter(fn: (r) => r._measurement == \"check_disk\" and r.host == \"$host\")"
        }]
      }
    ]
  }
}
```

### 2. Service Quality (All Hosts)

Aggregate performance across all hosts:

```
Average latency across all web servers:
from(bucket:"shinken")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "check_latency" and r.service == "ping")
  |> aggregateWindow(every: 1h, fn: mean)
  |> group(columns: ["host"])
```

### 3. Threshold Violations

Alert when metrics exceed thresholds:

```
CPU over 90% warning threshold:
from(bucket:"shinken")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "check_cpu" and r.value > 90)
  |> group(columns: ["host"])
```

## Alerting

### Grafana Alerts from InfluxDB Metrics

1. In a dashboard panel, click the alert bell icon
2. Set condition: "CPU > 85%"
3. Set notification channel (Email, Slack, PagerDuty)
4. Example:
   ```
   Alert: Web CPU High
   When: CPU average > 85% for 5 minutes
   Then: Send to #alerts Slack channel
   ```

### Multi-Host Alert

```
Alert if ANY host CPU > 90%:
from(bucket:"shinken")
  |> range(start: -5m)
  |> filter(fn: (r) => r._measurement == "check_cpu" and r.value > 90)
  |> count()
```

## Adding Custom Metrics

Your own checks can export perfdata:

```bash
# Example check script
#!/bin/bash
USAGE=$(df /home | awk 'NR==2 {print $5}' | cut -d% -f1)
echo "OK - Disk usage is ${USAGE}% | disk_usage=${USAGE}%;80;95;0;100"
exit 0
```

Output format:
```
message | metric1=value1[UOM];warn;crit;min;max metric2=value2...
```

Examples:
- `load=4.5;5;10;0;32` — 5-minute load average
- `requests/s=1523;1000;2000;0` — HTTP requests per second
- `cache_hit_ratio=92.5%;80;50;0;100` — Cache hit percentage
- `queue_depth=250;1000;5000;0` — Message queue depth

All are automatically exported to InfluxDB!

## Troubleshooting

### Metrics not appearing in InfluxDB

1. Check Broker is running:
   ```bash
   systemctl status shinken-broker
   # Or in container
   podman logs shinken-broker
   ```

2. Verify InfluxDB connectivity:
   ```bash
   curl http://localhost:8086/api/v1/ping
   # Should return 204 No Content
   ```

3. Check Broker logs for errors:
   ```bash
   tail -50 /var/log/shinken/broker.log | grep -i influx
   ```

4. Test InfluxDB write:
   ```bash
   curl -X POST 'http://localhost:8086/write?db=shinken' \
     --data-binary 'check_cpu,host=web-01 value=87.5'
   ```

5. Query InfluxDB:
   ```bash
   curl 'http://localhost:8086/query?db=shinken' \
     --data-urlencode 'q=SELECT * FROM check_cpu LIMIT 10'
   ```

### Grafana can't connect to InfluxDB

1. Check InfluxDB is accessible:
   ```bash
   curl http://influx-host:8086/api/v1/ping
   ```

2. In Grafana data source, try "Skip TLS Verify" if using self-signed certs

3. Check Grafana logs:
   ```bash
   journalctl -u grafana-server -f
   ```

### High disk usage

1. Reduce retention period:
   ```bash
   influx bucket update --name shinken --retention 14d
   ```

2. Lower precision (aggregate to 1m instead of 1s):
   ```ini
   # In broker config
   influx_precision = m  # or s, ms, us, ns
   ```

3. Archive old data:
   ```bash
   influx export --bucket shinken --start 2025-01-01 --end 2025-08-01 > archive.json
   influx delete --bucket shinken --start 2025-01-01 --end 2025-08-01
   ```

## Performance Tips

1. **Batch writes**: Set `influx_batch_size=100` to reduce network round-trips
2. **Retention**: Keep only data you need; old metrics can be archived
3. **Downsampling**: Use 5m or 10m aggregations for long-range views
4. **Index on tags**: InfluxDB auto-indexes tags (host, service) — no manual action needed

## Integration with Alerting

### Alert Escalation Path

```
Check returns perfdata
    ↓
Broker stores in InfluxDB
    ↓
Grafana alert rule evaluates metric
    ↓
Condition met (e.g., CPU > 90%)
    ↓
Alert notification → Email/Slack/PagerDuty
    ↓
(Meanwhile) Shinken also sends notification via Reactionner
```

Both systems can send alerts — coordination depends on your config!

---

**Related:**
- See `doc/ARCHITECTURE.md` for Broker daemon
- See `doc/DATABASE.md` for event logs (Livestatus/SQL)
- See `doc/LOGGING.md` for structured logging
- Grafana docs: https://grafana.com/docs/grafana/latest/
- InfluxDB docs: https://docs.influxdata.com/influxdb/latest/
