# Native Rust monitoring engine

Experimental Linux implementation. A monitoring cycle runs without Python: load configuration, execute plugins, update host/service states and serve Livestatus. Thruk is the separate web frontend; the engine does not bundle a web server.

## Run with Podman

From a checkout of the rewrite branch:

```sh
git clone --branch rewrite/rust-core https://github.com/NCombarieu/shinken_gpt.git
cd shinken_gpt
podman build -f Containerfile.rust -t localhost/shinken-rs:dev .
podman run --rm localhost/shinken-rs:dev config-check /etc/shinken/shinken.cfg
podman run --rm localhost/shinken-rs:dev run /etc/shinken/shinken.cfg --once
podman compose -f compose.rust.yaml up -d --build
```

The bundled example uses real `check_dummy` plugins and includes an intentionally critical service and a passive-only service. The compose stack retains state in a named volume and publishes Livestatus at `127.0.0.1:6557`. It requires a Compose provider installed for Podman. On Windows, run this Linux stack through WSL2 or a Podman Linux VM.

To use your configuration, change the configuration bind mount in `compose.rust.yaml` to your directory, keep its main file at `/etc/shinken/shinken.cfg`, then validate it with the same mount before starting. Paths in `cfg_file`, `cfg_dir` and `resource_file` resolve relative to the containing file. The plugin paths in resource macros must exist inside the container. Custom executables can be mounted separately; Python Shinken modules are never loaded.

## Build and run directly on Linux

Install Rust 1.85 and your monitoring plugins, then:

```sh
cargo build --locked --release -p shinken-rs
target/release/shinken-rs config-check rust/examples/minimal/shinken.cfg
target/release/shinken-rs run rust/examples/minimal/shinken.cfg --once
mkdir -p ./rust-state
target/release/shinken-rs run rust/examples/minimal/shinken.cfg \
  --livestatus-unix ./rust-state/live.sock \
  --livestatus-tcp 127.0.0.1:6557 \
  --state-file ./rust-state/state.json \
  --max-concurrent-checks 16
```

`--once` prints a JSON snapshot including header rows. Its exit status indicates whether execution completed, while monitoring problems are encoded in the snapshot. Plugin states do not make a healthy monitoring engine exit.

The daemon restores matching objects from retention at startup and writes atomic snapshots every 30 seconds and on SIGINT/SIGTERM. Abrupt termination can lose changes since the last snapshot. An invalid retention file is a startup error. Configuration is loaded at startup; reload currently requires a restart.

Unix sockets use mode 0660. Startup refuses any existing socket path. On a normal shutdown, the engine removes only the socket it created. After a crash, verify that the previous process is gone before removing a stale socket yourself.

## Connect Thruk

Merge the peer in [thruk_local.conf](thruk_local.conf) into the backend configuration of an existing Thruk installation. Use a login matching a configured contact (the example has `admin`). If Thruk runs elsewhere, use a Unix socket shared with appropriate group permissions or a protected TCP network.

Livestatus is a trusted administrative protocol: it carries external commands and has no built-in TCP authentication or TLS. The example publishes its TCP port only on localhost. `AuthUser` filters query visibility, but is not a substitute for authentication; Thruk handles login and command authorization.

The contract tests use the actual upstream `Monitoring::Livestatus` client and the provider's default host, service, contact, status, comment, downtime and log columns. Full browser interaction with Thruk and all of its optional plugins remains unvalidated.

Supported actions include passive results, acknowledgements without sending an acknowledgement notification, enabling/disabling checks, scheduling checks, comments and fixed untriggered downtimes. Unsupported actions return an error. Read the compatibility matrix before using this branch.

## Verify

```sh
cargo fmt --all -- --check
cargo clippy --locked --workspace --all-targets -- -D warnings
cargo test --locked --workspace --all-targets
cargo build --locked -p shinken-rs
python3 rust/tests/smoke.py target/debug/shinken-rs
```

Python is used only by the black-box test harness. CI additionally installs the pinned upstream Thruk client for interoperability tests, builds the rootless container and executes its installed monitoring plugins.
