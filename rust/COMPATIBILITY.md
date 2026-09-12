# Compatibility contract

Compatibility is deliberately narrow. The Rust stack must preserve:

- accepted Nagios and Shinken object syntax, includes, templates, inheritance,
  additive fields, macros, defaults, and validation diagnostics;
- enough object semantics to load existing `cfg_file` and recursive `cfg_dir`
  configuration trees without rewriting them;
- the standard plugin contract: exit status, output, timeout and performance
  data;
- the Livestatus tables, columns, filters and commands used by Thruk.

Shinken's daemon topology, Python module API, pickle transport, internal object
layout, timing quirks and implementation-specific broker events are explicitly
not compatibility targets.

## Proof strategy

Every legacy fixture must load in Rust and produce a normalized configuration
snapshot. Captured Thruk Livestatus queries must succeed against both an
established backend and the Rust engine with schema-compatible responses.

The parser already preserves object order, directive order, duplicate
directives, raw values, and source line numbers. Semantic expansion follows in
the next milestones; parsing success alone is not considered compatibility.
