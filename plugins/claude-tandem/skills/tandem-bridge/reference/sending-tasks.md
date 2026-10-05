# Sending tasks: details (read when addressing a new thread, crossing projects, or sending large material)

## Ask only what the ledger cannot tell

Every question in a body costs the receiver shell commands, and on Windows each Codex command can
flash a console window while Codex's managed daemon runs. A connection ping asks for the thread ID,
CLI version and read time, nothing about processes or start mode unless that is being diagnosed. Do
not tell Codex to check your watch heartbeat; its `send --relay auto` does that.

## Finding the Codex thread

Codex thread UUIDs are not discoverable non-interactively (`codex agents` needs a TTY; `discover`
shows `codex_current_session` only inside a Codex process). Ask the user (the app shows the thread), or
read the most recent Codex-origin envelope in the ledger (`from.session_id` with `agent` = `codex`).
Delivery is a queue: a message to a thread not open in the app waits until it is.

## One ledger per collaboration

The ledger belongs to the project BOTH peers are authorized in. A Codex thread started in project X
files X's tasks in `X/.tandem/state`. When the only Codex peer is authorized in a different project (a
cross-project review), use that peer's ledger and treat the subject project's material as disclosed
evidence; never create a ledger the peer cannot reach. Say in the body which project the task is about
and which ledger it is filed in. Long-running work deserves its own Codex thread started in that project.

## Can the peer read the files?

- **Same project:** documents go BY PATH: each file's project-relative path plus sha256, the review
  questions and the reply format. The peer confirms the hash first ("hash matches" / "hash differs").
  Never shrink a document the peer can open; a review of a summary reviews your summary.
- **Different project:** make the body self-contained (facts, excerpts, question, acceptance criteria)
  and say no file reads are needed. The peer should refuse reads outside its own project.

## Large material across projects

Caps: body 12,000 characters, envelope 22,000 UTF-16 units; the helper refuses oversize bodies. In order:
1. Shrink: the question plus a summary and the sha256 of the full text; say it is a summary.
2. Split: `<tag>-part-1-of-3` …, each under the cap, each claimed; say in part 1 how many follow.
3. File: a path inside the peer's authorized project, named with its sha256, only with the user's
   explicit authorization to disclose that material there.
Never hand-encode, compress or split a single JSON envelope.

## Templates and output

```
<python> <checkout>/tandem.py --state-dir <ledger> validate <outbox>/<unique>.json
<python> <checkout>/tandem.py --state-dir <ledger> send --dry-run <outbox>/<unique>.json
```
`validate` prints `"valid": true`, the id and `body_sha256`; `send` prints `"state":
"transport_returned"` and the queue's line. Silence is not success: read unfiltered output if a grep
hid it. Put input hashes in the body of any mutating task. Add `--budget "<≤200 chars>"` and
repeatable `--evidence-required "<what to return>"` for loop work. `--relay-model` / `--relay-prompt`
apply only to sends that reach Claude.

## Sub-agents

There is no separate command. If the receiver may split the work, say so in the body: how many
sub-agents at most, whether they may edit (otherwise read-only), and that the receiver combines their
findings into ONE reply with file:line evidence. The receiver stays responsible for the task and its
reply; the task's scope and protected paths still apply to every sub-agent.

## Visual work

For anything a person will look at (UI, mockups, diagrams, images), the body requires the receiver to
render the result at the stated sizes or widths, look at the rendered output itself, and attach the
screenshot paths as `--evidence` (fingerprinted, so the reviewer can check them). Name the render
command that works on that platform. Most visual defects come from a builder that never saw its own output.

## Honest framing

A Codex reply is produced with Codex's own tools; it is an independent opinion, not a no-tools one.
Report what its evidence shows.
