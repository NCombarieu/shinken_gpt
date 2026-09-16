# Metrics integration: experimental, not connected

The repository contains an experimental `shinken/timeseries_adapter.py`
helper and Grafana provisioning examples. It does **not** contain a
`broker_timeseries` module that consumes broker events. Starting InfluxDB
and Grafana therefore does not export Shinken check results.

The default configuration intentionally enables no timeseries broker.
`etc/brokers/broker-timeseries.cfg` is a comment-only placeholder. Do not
add INI sections to Shinken object configuration files: they require
`define <object> { ... }` syntax.

InfluxDB and Grafana services are isolated behind the Compose profile
`experimental-metrics`. They are development scaffolding, not a working
metrics deployment. Their current initialization and datasource settings
still need to be aligned with InfluxDB 2 authentication, organization and
bucket configuration before use. The bundled credentials are examples.

## Work needed before enabling metrics

- Implement and register a broker module that consumes check-result broks.
- Configure InfluxDB 2 organization, bucket and token consistently in the
  adapter, container initialization and Grafana datasource.
- Validate perfdata parsing, line-protocol escaping, batch flushing,
  connection failures and shutdown behavior.
- Test real check results through the broker into InfluxDB and Grafana.

For the supported monitoring deployment and native status dashboard, see
[installation.md](installation.md). The distributed CI validates those
components; it does not validate InfluxDB or Grafana.
