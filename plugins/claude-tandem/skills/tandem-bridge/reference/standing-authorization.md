# Standing authorization (read when an envelope arrives and nothing the user said in this conversation covers it)

An opt-in policy file, `~/.tandem/authorizations.json`, that only the user edits. The helper's check
reads it; it never grants, writes or claims.
```
<python> <checkout>/tandem.py --state-dir <header path> authorization check <header path>/messages/<id>.json --agent claude --session <this UUID> --project-root <this project root> --sender-project <sender's project root> --purpose status|review [--read-path <file> ...] [--bookkeeping-path <outbox dir>]
```
- Exit 0, `covered`: post one line ("Tandem: read-only <purpose> task <tag> from enrolled peer;
  claiming under standing intent, grant <grant_id>") and claim. It is a declared-policy match only:
  still read the body for semantic scope; the runtime may still ask or deny. `--sender-project` and
  `--purpose` are your declarations, not facts.
- Exit 2, `needs_user_authorization`: surface the envelope as usual. No policy file is this state.
- Exit 1, `invalid_policy`: surface with the reason; do not claim; the user fixes the file. One stale
  path invalidates the whole file by design.
- Only read-only tasks with no declared writes can be covered. Grants are exact UUID pairs, exact
  ledger, exact projects, and an expiry with timezone.
- `authorization template --agent claude --session <this UUID> --project-root <root>` prints an empty
  policy with candidate values for the user to review; it installs nothing. `authorization status`
  lists grants and expiries.
