# Filesystem contract

Ledger JSON and published opinion answers share one implementation: write a
temporary file beside the destination, flush and fsync it, then publish with
`os.link`. Existing destinations are never replaced. Temporary files are removed
after success or failure during normal execution. A process crash can leave a
temporary file or a reservation; neither authorizes an automatic retry.

This requires a filesystem with atomic same-filesystem hard-link creation.
Unsupported hard links fail closed; there is no direct-create or overwrite
fallback. Permission failures remain permission failures. Destination directories
may already have been created when publication fails. No claim is made about
power-loss durability of directory entries or unusual network filesystems.

Authorization paths must exist and be absolute and local. Canonicalization uses
the host's `Path.resolve(strict=True)` and `os.path.normcase`: links are resolved,
Windows comparisons normalize case, and POSIX comparisons preserve case. UNC
and Windows device-prefix spellings are rejected. Windows alternate data streams
are disallowed; colon characters remain valid POSIX filename characters.
Containment compares path components, not string prefixes. A symlink escaping
the project therefore does not acquire project scope through its alias.
On case-insensitive macOS volumes, differently cased spellings can still fail
policy matching because POSIX normalization preserves case; use consistent paths.

These are declaration checks, not an access sandbox: another process can change
paths after validation. Host permissions and runtime approval remain separate.
Tests exercise real local paths and links on each runner; Windows symlink tests
skip when the host does not permit creating them. Cross-platform support is
reported only for the OS/Python combinations actually exercised by CI.
