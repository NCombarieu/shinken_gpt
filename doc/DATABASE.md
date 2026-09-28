# Monitoring Data Storage

Shinken's **Broker** daemon can persist monitoring logs to a relational database for queryable history and compliance.

## What Gets Stored?

The **Livestatus** module in the Broker stores:

### Check Results
- Host/service state (OK, WARNING, CRITICAL, etc.)
- Check output (plugin message)
- Performance data (metrics from plugins)
- Check duration and latency
- State change information

### Event Timeline
- State transitions (OK → WARNING, HARD state reached)
- Downtime periods (scheduled maintenance windows)
- Acknowledgments (admin acknowledged the alert)
- Comments (why the issue exists)

### Example Entry
```
timestamp: 2025-09-14 10:15:30
host_name: web-01
service_description: HTTP
state: CRITICAL
output: HTTP CRITICAL: Connection timeout
perf_data: time=5.234s;;;
hard_state: 1
notification_number: 2
```

## Why Store Monitoring Data?

1. **Compliance & Audit Trail** — prove system availability (SLA reports)
2. **Historical Analysis** — trend graphs, "why did this fail?"
3. **Reporting** — availability reports, alert summaries
4. **Integration** — feed data to external systems (BI, analytics)
5. **Long-term Retention** — keep logs past Livestatus in-memory window

## Database Options

### SQLite (Default, Recommended for Single Host)

**Pros:**
- No external dependencies; embedded database
- Zero configuration
- Fast for small deployments (<10k hosts)
- Easy backup (single file)

**Cons:**
- Not suitable for >100k events/day
- Limited concurrent access
- Single-node only

**Setup:**
```ini
# etc/brokers/broker-master.cfg

modules = broker_livestatus

[broker_livestatus]
module_type = broker
broker_log_file = /var/log/shinken/livestatus.log
logstore_type = logstore_sqlite
logstore_sqlite_database_path = /var/lib/shinken/livestatus.db
logstore_sqlite_table_prefix = s_
```

**Backup:**
```bash
cp /var/lib/shinken/livestatus.db /backups/livestatus-$(date +%Y%m%d).db
```

### MySQL (Production, Multi-Node)

**Pros:**
- High performance for large datasets
- Distributed (replication, failover)
- Multiple applications can query simultaneously
- Good tooling (MySQL Workbench, phpMyAdmin)

**Cons:**
- Requires separate MySQL server
- More operational overhead

**Setup:**

1. Create database and user:
```sql
CREATE DATABASE shinken_logs;
CREATE USER 'shinken'@'localhost' IDENTIFIED BY 'password';
GRANT ALL ON shinken_logs.* TO 'shinken'@'localhost';
FLUSH PRIVILEGES;
```

2. Configure Shinken:
```ini
# etc/brokers/broker-master.cfg

[broker_livestatus]
module_type = broker
logstore_type = logstore_mysql
logstore_mysql_database = shinken_logs
logstore_mysql_user = shinken
logstore_mysql_password = password
logstore_mysql_host = localhost
logstore_mysql_port = 3306
logstore_mysql_table_prefix = s_
logstore_mysql_character_set = utf8mb4
```

3. Backup:
```bash
mysqldump -u shinken -p shinken_logs > /backups/shinken-$(date +%Y%m%d).sql
```

### Oracle (Enterprise, High Volume)

**Pros:**
- Enterprise support and licensing
- Highly scalable
- Strong security features

**Cons:**
- Most operational complexity
- Licensing costs

**Setup:**
```ini
# etc/brokers/broker-master.cfg

[broker_livestatus]
module_type = broker
logstore_type = logstore_oracle
logstore_oracle_database = shinken_logs
logstore_oracle_user = shinken
logstore_oracle_password = password
logstore_oracle_host = oracle-server
logstore_oracle_port = 1521
```

## Querying the Database

### Via Livestatus Socket
Livestatus is wire-compatible with Nagios Livestatus:

```bash
# Get all service state changes in the last 24 hours
echo "GET log\nFilter: time >= $(date +%s -d '1 day ago')\nFilter: type = SERVICE STATE\nColumns: time host_name service_description state\n" | nc localhost 50000
```

### Direct SQL (MySQL Example)
```sql
-- Top 10 most-alerted services
SELECT host_name, service_description, COUNT(*) as alerts
FROM s_log
WHERE type = 'SERVICE STATE' AND state != '0'
  AND time >= DATE_SUB(NOW(), INTERVAL 7 DAY)
GROUP BY host_name, service_description
ORDER BY alerts DESC
LIMIT 10;

-- Availability report for the last 30 days
SELECT 
  host_name, 
  service_description,
  ROUND(
    SUM(CASE WHEN state = '0' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 
    2
  ) as availability_percent
FROM s_log
WHERE time >= DATE_SUB(NOW(), INTERVAL 30 DAY)
  AND type = 'SERVICE ALERT'
GROUP BY host_name, service_description;

-- Find all hosts that went critical in the last 24 hours
SELECT DISTINCT host_name
FROM s_log
WHERE type = 'HOST ALERT'
  AND state = '2'
  AND time >= DATE_SUB(NOW(), INTERVAL 1 DAY)
ORDER BY host_name;
```

### Via Thruk/Naemon Web UI
If using Thruk for the web interface, it queries Livestatus/database automatically:

- Menu → Reports → Availability
- Menu → Reporting → SLA
- Menu → Logfile → Search

## Data Retention

### TTL (Time-To-Live) Policy
Older logs consume disk space. Implement retention:

**SQLite:**
```python
# Daily cleanup script
import sqlite3
import time

db = sqlite3.connect('/var/lib/shinken/livestatus.db')
cursor = db.cursor()

# Keep 90 days of logs
cutoff_time = int(time.time()) - (90 * 86400)
cursor.execute('DELETE FROM s_log WHERE time < ?', (cutoff_time,))
cursor.execute('VACUUM')  # Reclaim disk space
db.commit()
db.close()
```

**MySQL:**
```sql
-- Add to a daily cron job
DELETE FROM s_log WHERE time < UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 90 DAY));
```

### Archive to Data Warehouse
For compliance, export old logs before deletion:

```bash
# Export 90-day-old logs to archive
mysqldump \
  --where="time < UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 90 DAY))" \
  shinken_logs s_log > /archive/shinken-$(date -d '90 days ago' +%Y%m%d).sql
```

## Troubleshooting

### Database Connection Errors
```
ERROR: MySQL connection failed: Unknown database 'shinken_logs'
```

**Fix:**
```bash
# Verify MySQL is running
mysql -u shinken -p -e "SELECT 1"

# Create database if missing
mysql -u shinken -p -e "CREATE DATABASE shinken_logs"

# Check broker logs
tail -50 /var/log/shinken/broker.log
```

### Disk Usage Growing Rapidly
- Enable retention policy (see above)
- Check for a runaway log producer (misconfigured check)
- Consider switching to MySQL for better compression

### Livestatus Not Responding
```
ERROR: Cannot connect to Livestatus socket /var/run/shinken/livestatus.sock
```

**Fix:**
```bash
# Check broker is running
systemctl status shinken-broker

# Check socket exists
ls -la /var/run/shinken/livestatus.sock

# Verify broker config
grep logstore_type /etc/shinken/brokers/broker-master.cfg
```

## Performance Tuning

### MySQL Indexes
The database schema includes indexes, but for large deployments verify:

```sql
-- Check existing indexes
SHOW INDEXES FROM s_log;

-- Add index if missing (helps queries by host_name)
ALTER TABLE s_log ADD INDEX idx_host_time (host_name, time);

-- Analyze table to update statistics
ANALYZE TABLE s_log;
```

### Connection Pooling (MySQL)
For many concurrent queries, use connection pooling in Broker config:

```ini
logstore_mysql_pool_size = 5
logstore_mysql_pool_timeout = 10
```

### Archiving Strategy
- Keep last 30 days in hot database
- Export last 90 days to cold archive (compressed SQL dumps)
- Use external data warehouse (BigQuery, Redshift) for 1+ year retention

---

**Related:**
- See `doc/ARCHITECTURE.md` for Broker daemon architecture
- See `doc/LOGGING.md` for event logging
- See `doc/exploitation.md` for backup procedures
