# Tandem details: send-relay-and-material

Read this when this part of the workflow applies. These rules are retained from the pre-trim skill.

Pass the same explicit absolute `--state-dir` on both sides. For Claude-bound
sends, use `send <envelope> --relay-model claude-sonnet-5` by default in this
skill; the user may choose another model or the CLI default. Do not pass
`--relay-model` for Codex-bound sends. The helper's own default is unchanged.
Executable discovery is override, PATH, known locations; do not run Windows
shell shims or change permissions to work around a denial.

For routine `make`, `send`, `receive`, `reply`, `status` and `connect` calls,
use the command templates here as written. Do not run `--help`, search the docs
or re-read README/INSTALL unless a command fails. Replace placeholders with
the verified paths and UUIDs:

```text
<python> <helper> --state-dir <ledger> make --from-agent <kind> --from-session <UUID> --to-agent <kind> --to-session <UUID> --body-file <body.txt> --out <outbox/task.json> --tag <tag> --done <criterion>
<python> <helper> --state-dir <ledger> send <outbox/task.json> --relay-model claude-sonnet-5
<python> <helper> --state-dir <ledger> receive <ledger>/messages/<id>.json --agent codex --session <own-UUID>
<python> <helper> --state-dir <ledger> reply <ledger>/messages/<id>.json --agent codex --session <own-UUID> --body-file <result.txt> --out <outbox/reply.json> --status completed
<python> <helper> --state-dir <ledger> send <outbox/reply.json> --relay-model claude-sonnet-5
<python> <helper> --state-dir <ledger> status <id>
<python> <helper> --state-dir <ledger> connect <peer-full-UUID>
<python> <helper> --state-dir <ledger> checkpoint --project-root <project> --body-file <snapshot.md>
<python> <helper> --state-dir <ledger> recap --project-root <project>
```

For an edit, add the scope explicitly (repeat `--allow`, `--protect` and
`--done` as needed):

```text
<python> <helper> --state-dir <ledger> make --from-agent <kind> --from-session <UUID> --to-agent <kind> --to-session <UUID> --body-file <body.txt> --out <outbox/task.json> --tag <tag> --mode edit-in-place --allow <project/path> --protect <project/source> --mutation-key <same-intended-edit> --done <criterion>
```

Modes are `read-only`, `additive-only`, `edit-in-place` and `render`. A directory
in `--allow` covers new and existing files beneath it. The helper records this
scope declaration; the receiver must check actual edit paths against it because
the helper does not enforce filesystem access.

Add optional `--budget "2h"` or `--budget "3 review rounds"` and repeatable
`--evidence-required "<what to return>"` to `make` when useful. The helper
records and displays them but cannot enforce time or judge evidence. Older
envelopes without them remain valid.

Use `--relay-model` only for Claude-bound sends; omit it for Codex-bound sends.
For a routine answer, claim with `receive`, do the authorized work, then use
the adjacent `reply` and `send` templates without looking them up elsewhere.
Let `send --relay auto` check Claude's watch heartbeat and registry; do not
read the heartbeat separately. When proposing a routine connection ping, ask
only for information the ledger cannot provide. Request process or CLI details
only when diagnosing them.
If a Claude Monitor is being stopped manually, run `watch --stop` before
stopping it, then scan unclaimed messages for that exact Claude UUID. Do not
assume the heartbeat proves the Monitor is alive.
When a helper process remains active, poll its output about every 5 seconds and
stop as soon as the JSON result appears. This is a tool polling interval, not
a helper flag.

After sending a task or frozen review request, end this turn and let the
queued reply wake the session. Never poll the ledger for a reply inside the
same turn. If a reply is overdue, tell the user; do not send a duplicate.

## Send

When reporting a bridge outcome to the user, start the final reply with a short
plain sentence prefixed `Tandem: `. Say queued, received, awaiting review or
verified as the evidence warrants. Keep this first line under 240 characters,
without paths, raw envelopes, URLs or secrets. An optional local speech hook
may read that line aloud; none is included.

Before choosing how to carry documents, first establish whether the exact peer can
read the files. Use the peer's recorded folder from its directory row or hello:
the peer must work in the same project, and every named file must sit inside it.
For a same-project review, send documents by project-relative path and SHA256,
never by pasted text or a summary. Put the review questions and required reply
format in the body, and instruct the peer to confirm each hash before reviewing.
If a hash differs, it reports the actual hash instead of reviewing another
version. A review of a summary is only a review of that summary.

For different projects, keep the transfer order: shrink with a SHA256, split
the material, or place a file inside the peer's authorized readable scope with
the user's disclosure authorization. State plainly when the peer will review
a summary.

- Confirm the user authorized this handoff. Discover the actual sender and target
  UUIDs; never guess a peer name or choose another conversation after a failure.
- Create a UTF-8 body file and use `make` to record scope and concrete done
  criteria. Include input hashes/live-state expectations for edits. Reuse a
  mutation key for the same intended mutation; it is not a retry token.
- Check `discover` for the selected ledger. Resolution is explicit `--state-dir`
  then `TANDEM_STATE_DIR`, nearest `.tandem`/`.git` project marker, then legacy
  helper/state with a warning for the source wrapper only; module invocation
  fails without a resolved ledger. Carry the same absolute path throughout the task.
- For routine read-only or single-file tasks, run `make` then `send` only:
  `make` validates before writing and `send` validates again. Reserve a separate
  `validate` and `send --dry-run` for mutations touching more than one file or
  a body near the size cap. Native routes: Codex queue; temporary Claude peer
  relay when no fresh Claude watch exists. For Claude sends use the default
  `--relay auto`; report the printed state verbatim. `written_for_watcher`
  means the message was recorded for a watching peer, never receipt. A
  `claimed` event proves the receiver's helper claimed it; it does not prove
  a human read it. Relay
  delivery reports are not execution results. If the Claude CLI reports
  `Not logged in; please run /login`, surface that cause while retaining
  delivery uncertainty and no automatic retry. Preserve denials.
- When several small changes target the same file or files, put them in one
  task with a `done_when` item for each outcome. Split only if a later change
  depends on reviewing the first result.
- Do not keep a relay alive for project work; the receiver replies to the
  original endpoint. Report uncertainty if delivery or completion is unknown.
