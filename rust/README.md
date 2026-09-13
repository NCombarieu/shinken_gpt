# shinken-rs

`shinken-rs` is a new Rust monitoring engine. It does not run the Python
Shinken daemons. It loads their `cfg_file`/`cfg_dir` configuration trees and
publishes a Livestatus endpoint that Thruk can use.

## First run

Build and verify a configuration:

```bash
cargo run --release --package shinken-rs -- config-check /etc/shinken/shinken.cfg
```

Execute every service check once:

```bash
cargo run --release --package shinken-rs -- run /etc/shinken/shinken.cfg --once
```

Start the engine with a Unix Livestatus socket and a TCP endpoint for Thruk:

```bash
cargo run --release --package shinken-rs -- run /etc/shinken/shinken.cfg \
  --livestatus-unix /var/run/shinken-rs/live.sock \
  --livestatus-tcp 127.0.0.1:6557
```

In Thruk, configure a `livestatus` peer pointed at that Unix socket or TCP
address. The implemented tables are currently `hosts`, `services` and
`status`; the engine supports `GET`, `Columns`, `Filter`, `Limit`, JSON/CSV
output and `ResponseHeader: fixed16`.

## Container

Build a standalone image with no Python runtime:

```bash
podman build -f Containerfile.rust -t shinken-rs:dev .
```

Mount the configuration tree and the plugin directory, then run the same
`shinken-rs run ...` command in the container.
