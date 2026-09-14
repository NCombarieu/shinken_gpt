# Development Guide

This guide covers setting up a development environment and contributing to Shinken.

## Prerequisites

- Python 3.11, 3.12, or 3.13
- Linux (Fedora, Ubuntu, or similar)
- `podman` and `podman-compose` (for container testing)
- `git`

## Setup

### 1. Clone and Install in Development Mode

```bash
git clone https://github.com/NCombarieu/shinken_gpt.git
cd shinken_gpt
git checkout modernize/podman-python3  # if not already on this branch

# Install Shinken and dev dependencies
pip install --upgrade pip
pip install -e ".[dev]"  # includes pytest, ruff, pytest-cov, etc.
```

### 2. Verify Installation

```bash
# Should print the Shinken module path
python -c "import shinken; print(shinken.__file__)"

# Should show version and available daemons
shinken-arbiter --version
shinken-scheduler --version
shinken-poller --version
shinken-broker --version
shinken-receiver --version
shinken-reactionner --version
```

## Running Tests Locally

### Quick Tests (compatibility only, ~10s)
```bash
pytest -v test/test_macroresolver.py test/test_complex_hostgroups.py
```

### Full Test Suite (~2-3 minutes)
```bash
pytest -v --timeout=60 --cov=shinken --cov-report=html test/
```

The HTML coverage report will be in `htmlcov/index.html`.

## Code Quality

### Linting with Ruff

```bash
# Check for errors and style issues
ruff check shinken bin cli modules libexec integration test

# Auto-fix fixable issues
ruff check --fix shinken bin cli modules libexec integration test

# Format with Ruff formatter
ruff format shinken bin cli modules libexec integration test
```

### Before Committing

Run the CI checks locally:

```bash
# 1. Compile check (catches syntax errors early)
python -m compileall -q shinken bin cli modules libexec integration test

# 2. Lint check
ruff check --select E9,F7,F82 shinken bin cli modules libexec integration test

# 3. Run tests
pytest --timeout=60 -x test/
```

## Container Testing

Build and test the container image locally:

```bash
# Build the container
podman build --tag shinken:dev --file Containerfile .

# Run a smoke test
podman run --rm shinken:dev shinken-arbiter --version

# Run the full integration lab
bash integration/podman-lab.sh
```

The integration lab:
- Starts all 6 daemons in containers
- Loads a real configuration with sample hosts/services
- Executes actual checks (ping, SSH, HTTP)
- Verifies Livestatus is responding

## Project Structure

```
shinken/
  ├── daemons/                  # One subdir per daemon
  │   ├── arbiter/
  │   │   ├── pyproject.toml    # Independent daemon package metadata
  │   │   └── ...
  │   ├── scheduler/
  │   ├── poller/
  │   ├── broker/
  │   ├── receiver/
  │   └── reactionner/
  ├── objects/                  # Nagios config objects (Host, Service, etc.)
  ├── modules/                  # Loadable modules (Livestatus, DB backends)
  ├── __init__.py
  ├── db*.py                    # Database abstraction
  ├── check.py                  # Check execution
  ├── scheduler.py              # Scheduling logic
  └── ...
test/                           # Test suite (~150 tests)
doc/                            # Documentation
├── ARCHITECTURE.md             # This file (daemon roles, comm, storage)
├── configuration.md            # Configuration format and examples
├── exploitation.md             # Operational runbooks
├── installation.md             # Build and run instructions
├── livestatus-thruk.md         # Integrating Thruk web UI
└── presentation.md             # What Shinken is, fork changes
etc/                            # Default configuration
containers/                     # Dockerfile and entrypoint
compose.yaml                    # Podman Compose file for local testing
```

## Database Support

Shinken's **Broker** daemon can store monitoring logs in a database (via Livestatus):

### SQLite (default, no extra dependencies)
Already available; used by default in containers.

### MySQL
```bash
pip install -e ".[mysql]"  # installs PyMySQL>=1.1
```

### Oracle
```bash
pip install -e ".[oracle]"  # installs cx_Oracle>=8.3
```

Then configure in `etc/brokers/broker-master.cfg`:
```
modules = broker_livestatus
module_type = broker

[broker_livestatus]
broker_log_file = /var/log/shinken/livestatus.log
logstore_type = logstore_mysql  # or logstore_oracle, logstore_sqlite (default)
database = shinken_logs
db_host = localhost
db_user = shinken
db_password = ...
```

## Logging

Shinken currently uses Python's built-in `logging` module. Logs are written to:
- **Console** (stderr) for the running daemon
- **Files** in `/var/log/shinken/` for persistence
- **Database** (optional, via Livestatus) for query-able history

For local development, logs appear on stdout/stderr.

Future work: Migrate to structured logging (JSON) for better parsing and aggregation.

## Making Changes

### 1. Create a feature branch
```bash
git checkout -b feature/my-improvement
```

### 2. Make your changes and test
```bash
# Edit code
vim shinken/...

# Run tests to catch regressions
pytest test/

# Lint and format
ruff check --fix shinken/...
ruff format shinken/...
```

### 3. Commit with a clear message
```bash
git add shinken/...
git commit -m "subsystem: brief description

Longer explanation of why this change is needed, what it fixes, etc.
Keep lines under 100 chars. Reference issue #123 if applicable."
```

### 4. Push and open a pull request
```bash
git push origin feature/my-improvement
```

Then open a PR on GitHub. The CI will automatically:
- Compile check all Python files
- Run the linter
- Run the test suite on Python 3.11, 3.12, 3.13
- Build the container image
- Run the integration lab

## Common Tasks

### Add a new check plugin
Plugins are standard Nagios plugins (executable scripts). Place them in:
- Built-in: `etc/nagios-plugins/` (in container image)
- Custom: `etc/plugins/` (mounted from host)

Reference in config:
```
define command {
  command_name check_my_service
  command_line /etc/nagios-plugins/check_my_service -H $HOSTADDRESS$ -p $ARG1$
}

define service {
  service_description My Service
  host_name my_host
  check_command check_my_service!8080
}
```

### Add a configuration object type
1. Create the object class in `shinken/objects/`
2. Add it to `shinken/objects/__init__.py`
3. Add parsing rules to `shinken/configurationmanager.py`
4. Add tests in `test/`

### Fix a daemon bug
1. Identify which daemon(s) are affected (run with `--verbose` or `--debug`)
2. Check `doc/depannage.md` for known issues
3. Add a test case to `test/` that reproduces the bug
4. Fix the bug in `shinken/daemons/*.py`
5. Verify the test passes

## Troubleshooting

### Tests fail locally but pass in CI
- Check Python version: `python --version` (must be 3.11+)
- Check dependencies: `pip install -e ".[dev]"` again
- Try clean install: `pip uninstall shinken && pip install -e ".[dev]"`

### Container build fails
- Check disk space: `df -h`
- Check `podman` is installed: `podman --version`
- Try building with verbose output: `podman build --file Containerfile . 2>&1 | tail -50`

### Daemon won't start
- Check logs: `tail -50 /var/log/shinken/arbiter.log` (or scheduler/poller/etc.)
- Try verbose mode: `shinken-arbiter --verbose --debug`
- Verify config: `shinken-arbiter --verify-config`

---

**Questions?** Open an issue on GitHub or check `doc/depannage.md` for known issues.
