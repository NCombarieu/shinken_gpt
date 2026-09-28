# Metrics quick start: not yet available

Automatic Shinken-to-InfluxDB export is not implemented. The previous
instructions incorrectly presented the experimental adapter and Grafana
examples as an integrated deployment.

Use the [standard installation](installation.md) for Shinken and its
native status dashboard. A normal Compose startup runs the six Shinken
daemons; the experimental metrics services are excluded by default.

See [METRICS.md](METRICS.md) for the remaining integration work. Enabling
the `experimental-metrics` profile alone will not produce metrics.
