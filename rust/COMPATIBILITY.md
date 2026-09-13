# Compatibility and boundaries

This branch is an alpha. Reusing configuration files does not imply exact Nagios/Shinken behavior. Configuration checking prints runtime limitations, and unsupported calendar exceptions in referenced periods are rejected instead of silently executing outside their window.

| Area | Implemented | Remaining boundaries |
| --- | --- | --- |
| Configuration tree | Recursive cfg_dir, cfg_file, resource_file, deterministic discovery, symlink-cycle protection | Files are read at startup; no hot reload |
| Object syntax | Inline semicolon comments, escaped semicolons, continuations, source locations | Arbitrary Shinken macro generators and business rules are absent |
| Templates | Multiple parents, first-parent precedence, additive lists, null clearing, cycle errors, object-local register | Not every historical inheritance edge case is certified |
| Object expansion | Hosts, explicit/wildcard service host selectors and exclusions, nested hostgroups, servicegroups, contacts and notificationways | Nested servicegroups/contactgroups are not supported |
| Validation | Required names, duplicate primary objects, check command references, host/group references, interval ranges | Full Nagios semantic equivalence remains a goal |
| Scheduling | Host and service checks, configured normal/retry intervals, bounded concurrency, one-shot checks, force scheduling | Active host reachability through parent topology, dependencies and distributed execution are absent |
| Check periods | Weekly ranges, exclusions, empty periods, IANA timezones and DST | Calendar/date exceptions are rejected when referenced |
| Plugin execution | Standard exit codes, resource/ARG/host/service/custom macros, bounded output, separate long output and performance data | On-demand macros are incomplete; no Python modules |
| Process lifecycle | Process groups, kill/reap on timeout, cancellation cleanup | Plugins that deliberately create a new session can escape their group |
| States | Independent hosts, service SOFT/HARD retries, recovery, passive hard states | Obsessive checks, freshness and flapping detection are absent |
| Retention | Versioned atomic snapshots, matching objects restored, checks/acks/comments/downtimes and notification history retained | No exactly-once delivery, multi-node database, historical SLA store or event replay |
| Livestatus | Unix/TCP, JSON/CSV/wrapped JSON, fixed16, keepalive, numeric/regex/boolean filters, grouped statistics, AuthUser visibility | Wait queries, custom separators, Python output and optimized Naemon/LMD extensions are absent |
| Tables | Status, hosts, services, groups, contacts, commands, comments, downtimes, state-transition log and columns | Log is bounded to 10,000 transitions, not a full Nagios archive |
| Thruk | Standard provider columns and upstream Perl client exercised by CI | Full UI and every optional page/action are not certified |
| External commands | Active/passive and notification toggles, passive results, forced/normal scheduling, acknowledgements, comments, fixed downtime | Notify=1 acknowledgements, flexible/triggered downtime, process restart and config-tool actions are rejected |
| Notifications | Native host/service commands, contact groups, notificationways, state/period filters, first delay, intervals, acknowledgements/downtime suppression, recovery and retained delivery history | Escalations, acknowledgement/flapping/downtime messages, event handlers and durable delivery queues are absent |
| Packaging | Native binary, container with monitoring plugins, persistent Compose example | Linux only; no published release or production deployment |

The engine can display configured metadata for a feature that is not executed. Runtime flags for event handlers and flapping remain disabled. Notification flags and timestamps reflect native execution. Unknown Livestatus columns, tables, query headers and external commands return errors.

Do not use this alpha as the sole production alerting system while dependencies, calendar exceptions, escalation logic and full compatibility remain incomplete.
