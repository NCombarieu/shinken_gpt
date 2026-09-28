# Shinken Architecture

Shinken is a distributed, modular monitoring framework based on the Nagios configuration format. This document describes the core architecture and key daemon components.

## System Overview

Shinken uses a **hub-and-spoke** distributed architecture with six independent daemons, each responsible for a specific aspect of monitoring:

```
                    ┌─ Scheduler ─┐
                    │             │
         Arbiter ───┼─ Poller ────┤─── Broker (Central Hub)
                    │             │
                    ├─ Receiver ──┤
                    │             │
                    └─ Reactionner┘
```

Each daemon runs as a separate process and communicates via:
- **Pyro5 (RPC)** — for daemon-to-daemon communication
- **HTTP/REST** — for external tool integration (Thruk, Livestatus)
- **Protocol buffers** — for internal message serialization

## Core Daemons

### Arbiter
**Package**: `shinken-arbiter`  
**Role**: Configuration and orchestration

- Reads Shinken configuration files (Nagios-compatible format)
- Distributes configuration to other daemons
- Manages daemon lifecycle and health
- Triggers reconfiguration and reloads
- Single point of entry for the monitoring system

**Key files**:
- `shinken/daemons/arbiterdaemon.py` — main daemon loop
- `shinken/objects/` — configuration object definitions
- `shinken/configurationmanager.py` — configuration parsing

### Scheduler
**Package**: `shinken-scheduler`  
**Role**: Check scheduling and state management

- Maintains the state of all monitored hosts and services
- Schedules checks according to configured intervals
- Handles dependencies, timeperiods, and escalations
- Tracks host/service state transitions and soft/hard states
- Communicates check work to pollers

**Key files**:
- `shinken/daemons/schedulerdaemon.py` — main daemon loop
- `shinken/scheduler.py` — scheduling logic
- `shinken/objects/host.py`, `shinken/objects/service.py` — state objects

### Poller
**Package**: `shinken-poller`  
**Role**: Check execution

- Receives check requests from the scheduler
- Executes Nagios plugins (sh, perl, python, etc.)
- Collects check output and performance data
- Returns results to scheduler via Pyro5 RPC
- Runs with elevated capabilities for network checks (ICMP ping)

**Key files**:
- `shinken/daemons/pollerdaemon.py` — main daemon loop
- `shinken/check.py` — check execution wrapper
- `shinken/worker.py` — multiprocessing worker pool

### Broker
**Package**: `shinken-broker` (with optional database support)  
**Role**: Status/log aggregation and Livestatus interface

- Central hub for all status and log events from other daemons
- Provides HTTP REST API for status queries
- Implements Livestatus protocol (wire-compatible with Nagios Livestatus)
- Manages database connections for log storage (SQLite, MySQL, Oracle)
- Serves as the backend for web UI tools (Thruk, Naemon)

**Key files**:
- `shinken/daemons/brokerdaemon.py` — main daemon loop
- `modules/livestatus/module.py` — Livestatus implementation
- `shinken/db*.py` — database abstraction (SQLite, MySQL, Oracle)

**Health check**: Available at `http://localhost:8080/healthz`

### Receiver
**Package**: `shinken-receiver`  
**Role**: External check result ingestion

- Listens for NSCA-compatible external check submissions
- Accepts passive check results from external systems
- Submits results to scheduler for processing
- Used for integrating external monitoring data

**Key files**:
- `shinken/daemons/receiverdaemon.py` — main daemon loop
- `shinken/message.py` — message parsing

### Reactionner
**Package**: `shinken-reactionner`  
**Role**: Notifications and event handlers

- Executes notification scripts when alerts are triggered
- Runs custom event handlers on state transitions
- Manages notification escalations and host/service dependencies
- Sends alerts via email, SMS, PagerDuty, etc.

**Key files**:
- `shinken/daemons/reactionnerdaemon.py` — main daemon loop
- `shinken/action.py` — notification/handler execution

## Communication Flow

### Check Execution Pipeline
```
1. Arbiter reads config
2. Scheduler receives config, schedules checks
3. Scheduler sends check work to Poller
4. Poller executes check, returns result
5. Scheduler updates state, sends events to Broker
6. Broker stores logs, triggers Livestatus updates
7. If state change: Broker notifies Reactionner
8. Reactionner executes notifications
```

### Data Storage

The **Broker** manages optional database storage for monitoring logs via the Livestatus module:

- **SQLite** (default in containers): `modules/livestatus/logstore_sqlite.py`
- **MySQL**: requires `PyMySQL>=1.1`
- **Oracle**: requires `cx_Oracle>=8.3`

Logs contain:
- Check results (output, perfdata, timing)
- State transitions and events
- Downtime and acknowledgment history
- Notification records

Query the database via:
- Livestatus socket: `unixsock:///var/run/shinken/livestatus.sock`
- HTTP API: `curl http://localhost:8080/api/livestatus`
- Direct database access (if not using Livestatus)

## Configuration

Shinken uses **Nagios-compatible configuration** organized as:

```
/etc/shinken/
├── nagios.cfg              # Main config (loads resources and cfg_dir)
├── resource.cfg            # Macro definitions
├── commands/               # Command definitions
├── contacts/               # Contact/contact group definitions
├── hosts/                  # Host/hostgroup definitions
├── services/               # Service definitions and templates
└── realms/                 # Shinken-specific realm (distributed) config
```

The Arbiter parses this on startup and distributes it to all daemons.

## Multi-Realm Distributed Monitoring

Shinken supports **distributed monitoring** via realms:

- Each realm represents an independent monitoring "site" or data center
- Arbiter in each realm manages its own daemons
- Realms can federate via upstream arbiters
- Useful for:
  - Multi-site deployments
  - High availability
  - Network segmentation

See `etc/realms/` for example configurations.

## Dependencies

### Core
- **Bottle** — lightweight HTTP framework
- **Pyro5** — Python RPC (daemon-to-daemon communication)
- **pycurl** — HTTP client (module downloads, notifications)
- **cheroot** — pure-Python WSGI server
- **six** — Python 2/3 compatibility (legacy, being phased out)

### Optional
- **Database drivers**: `pysqlite3`, `PyMySQL`, `cx_Oracle`
- **setproctitle** — improves process listing in `ps` output

## Testing

The project includes two test suites:

1. **Compatibility tests** (CI): `pytest test/test_macroresolver.py test/test_complex_hostgroups.py`
   - Fast, modernized tests with Python 3.11+

2. **Legacy test suite** (CI): `pytest test/`
   - ~150 tests covering all subsystems
   - Slower, uses old test patterns but comprehensive

Run locally:
```bash
pip install -e ".[dev]"
pytest -v --cov=shinken test/
```

## Container Deployment

The project builds a single multi-daemon container image:

- **Builder stage**: compiles Python wheel
- **Runtime stage**: installs wheel + Nagios plugins + SSH/NRPE utilities
- **Entrypoint**: `containers/entrypoint.sh` — selects which daemon(s) to run

Compose file (`compose.yaml`) runs all 6 daemons as separate containers sharing volumes.

Health checks are configured on the Broker container only (most stateful).

---

**Next steps**:
- See `doc/configuration.md` for Nagios config syntax
- See `doc/exploitation.md` for operational runbooks
- See `doc/depannage.md` for known issues and fixes
