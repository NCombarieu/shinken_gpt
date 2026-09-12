# Shinken Rust rewrite

This branch starts a new monitoring engine written in Rust. It deliberately
starts from `modernize/podman-python3` to inherit its configuration corpus and
deployment knowledge, but it does not reproduce Shinken's process model.

## Non-negotiable decisions

- Existing `cfg_file` and `cfg_dir` trees are accepted without edits.
- Python modules are not part of the target architecture. A feature must be
  implemented as a Rust crate, an external process, or a documented protocol.
- The rewrite branch may be unusable between milestones. Deployability is a
  release gate for the final cut-over, not for every intermediate commit.
- Thruk connects directly through a native Livestatus endpoint over a Unix or
  TCP socket.
- Internal architecture and runtime behaviour may diverge from Shinken when it
  makes the new system simpler, safer, faster, or easier to operate.

## Workspace map

| Crate | Responsibility |
| --- | --- |
| `shinken-model` | Stable domain types shared by every daemon |
| `shinken-config` | Nagios/Shinken syntax and source-preserving objects |
| `shinken-core` | Pure scheduling and state-transition rules |
| `shinken-livestatus` | Thruk-compatible query and response boundary |
| `shinken-rs` | One operator CLI and one engine process |

## Migration order

1. Freeze the configuration corpus and Thruk query corpus.
2. Parse, validate, inherit, and expand `cfg_file`/`cfg_dir` trees.
3. Build a single async engine: scheduler, executor, retention, events.
4. Expose Livestatus tables and external commands required by Thruk.
5. Add optional horizontal workers only where measurements justify them.
6. Run failure, load, upgrade, and Podman acceptance tests with real Thruk.
7. Ship a standalone Rust image with no Python runtime.

The first commit implements the typed boundary, a real object parser, a
Livestatus query boundary, and the first check state machine. It is intentionally
small enough to review but is executable rather than placeholder-only.
