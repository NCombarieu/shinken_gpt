# Shinken Rust rewrite

Development branch: `rewrite/rust-core`, based on the Python modernization branch. The Python product remains in the repository while the independent Rust engine is developed.

This is an experimental native monitoring engine, not a feature-complete Shinken replacement. Its runtime does not import Python or load Python modules. Existing executable monitoring plugins remain usable.

The implementation now includes recursive configuration loading, template inheritance, host and service execution, bounded concurrency, plugin timeouts, SOFT/HARD states, passive results, atomic retention, weekly time periods with timezone handling, native notification commands, a Livestatus backend and external commands.

Read [rust/README.md](rust/README.md) for installation and [rust/COMPATIBILITY.md](rust/COMPATIBILITY.md) before importing a production configuration. CI runs a standalone daemon against a real configuration tree and the upstream Thruk Livestatus client. Client interoperability does not certify every Thruk page or action.

The Rust work neither merges the Python modernization PR nor replaces an existing deployment.
