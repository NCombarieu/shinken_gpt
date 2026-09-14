# Quick Start: InfluxDB + Grafana with Shinken

Get Shinken metrics graphing in 5 minutes.

## Prerequisites

- `podman` and `podman-compose`
- Git clone of `shinken_gpt`

## 1. Start Containers

```bash
cd shinken_gpt
podman-compose up -d influxdb grafana broker scheduler poller arbiter
```

Wait for healthchecks to pass:

```bash
# Check status
podman-compose ps

# Should show all as "healthy" or "running"
```

## 2. Access Grafana

Open browser: **http://localhost:3000**

Login: `admin` / `admin`

## 3. Add InfluxDB Data Source

1. Click "Configuration" (gear icon) → "Data Sources"
2. Click "Add data source"
3. Select **InfluxDB**
4. Configure:
   - **URL**: `http://influxdb:8086`
   - **Database**: `shinken`
   - **User**: `admin`
   - **Password**: `shinkenpass`
5. Click "Save & test" (should show "Success")

## 4. View Dashboard

1. Click "Dashboards" (home icon) → "Browse"
2. Select **"Shinken Monitoring Overview"**
3. Should show CPU graph with real data from checks

If no data yet:
- Wait 30 seconds (Grafana refresh interval)
- Check logs: `podman-compose logs broker | tail -20`

## 5. Create Your Own Dashboard

### Simple CPU Graph

1. Click "+" → "Dashboard" → "Add new panel"
2. In "Metrics browser", enter:
   ```
   from(bucket:"shinken")
     |> range(start: -24h)
     |> filter(fn: (r) => r._measurement == "check_cpu")
   ```
3. Click "Run query"
4. Switch to "Time series" visualization
5. Set title: "CPU Usage"
6. Click "Save"

### Memory + Disk

```
from(bucket:"shinken")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement =~ /check_memory|check_disk/)
  |> aggregateWindow(every: 5m, fn: mean)
```

### Alert When CPU > 85%

1. In a panel, click the bell icon (Alert)
2. Set condition: `value > 85`
3. For 5 minutes
4. Click "Create alert"

## Troubleshooting

### No data in Grafana

```bash
# Check broker is exporting metrics
podman-compose logs broker | grep -i influx

# Check InfluxDB has data
curl -s http://localhost:8086/query?db=shinken \
  --data-urlencode 'q=SELECT * FROM check_cpu LIMIT 5'
```

### Grafana can't connect to InfluxDB

```bash
# Verify InfluxDB is running
podman-compose ps influxdb

# Test connection
curl http://localhost:8086/api/v1/ping
# Should return 204 No Content
```

### Broker crashes with InfluxDB errors

1. Check Broker config includes InfluxDB settings (default: yes)
2. Verify `influxdb-client` is installed in container:
   ```bash
   podman-compose exec broker pip list | grep influxdb
   ```

## Next Steps

- See `doc/METRICS.md` for full configuration options
- See Grafana docs: https://grafana.com/docs/grafana/latest/
- Create dashboards for your custom checks

---

**Full stack**:
- Shinken (monitoring) → InfluxDB (metrics) → Grafana (visualization)
