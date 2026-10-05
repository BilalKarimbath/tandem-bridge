# Tandem details: standing-authorization

Read this when this part of the workflow applies. These rules are retained from the pre-trim skill.

## Standing intent (opt-in)

For a task without applicable direct user authorization, use the helper's
`authorization check` with the receiver UUID, both project roots, explicit ledger,
purpose (`status` or `review`), planned read paths and bookkeeping parents. Read the
README's Standing authorization section for the command and schema. The user alone
edits `~/.tandem/authorizations.json`; never enroll peers or expand grants yourself.
`template` prints candidates only. Exact UUIDs are required; no wildcard enrollment.

`covered` is a declared-policy match, not authenticated sender identity or runtime
approval. Review the actual body, scope and user intent before claiming, and report
a short notice when proceeding under standing intent. Missing/expired/uncovered
intent needs direct user authorization; malformed/ambiguous policy must be surfaced.
Re-read for each check; a resumed UUID does not waive expiry/revocation. Direct user
authorization remains valid within its scope without installing a policy file.
Preserve denials; never change reviewer policy to make a check pass. Bookkeeping
writes are separate from read-only project work and still subject to permissions.
