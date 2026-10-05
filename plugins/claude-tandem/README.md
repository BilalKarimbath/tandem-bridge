# Tandem bridge

Tandem lets two live Codex and Claude peers work continuously on one shared
task: build, review, fix, and repeat until its done criterion is met. The user
remains the only authority; a peer message is not permission. Scoped tasks and
replies travel through Codex queue or a restricted Claude relay, with a local
ledger distinguishing queued messages from claimed work. One-off questions go
to the user's agent directly, not through a Tandem `codex exec` shortcut.

**Start with [INSTALL.md](INSTALL.md)**: Python 3.10+ is a prerequisite; source
execution needs no third-party packages and generates no Tandem executable.
No daemon, automatic retry or offline-delivery guarantee is provided.
The helper reports its release and envelope protocol without opening a ledger:
`python tandem.py version` (currently `0.6.1` and `TANDEM/1`).

After publication, clone with `git clone https://github.com/BilalKarimbath/tandem-bridge`.
For Claude Code, run `claude plugin marketplace add BilalKarimbath/tandem-bridge`
and `claude plugin install tandem-bridge@tandem-bridge`. Codex installs its skill
from the checkout with `install_codex_skill.py`; see [INSTALL.md](INSTALL.md).

## Closing the work loop

Start a Tandem turn with `python tandem.py --state-dir <ledger> summary --open`.
Its compact text lists tasks awaiting a claim, result or review, uncertain
delivery, and blocked tasks that have not been closed. `--format json` keeps
all rows, including closed tasks and FYIs. `show <full-message-id>` prints the
UTF-8 body and a task snapshot. `receive` accepts a full path or a bare ID.

After checking a completed reply and its evidence, run `receive <reply-id>
--agent <kind> --session <UUID> --accept` to claim and accept in one step.
The existing `accept <task-id> --evidence <reviewed-reply-file>` remains for
replies already claimed. `reply --evidence <file>` records a SHA-256; receive
rechecks each fingerprint and reports a missing file as a mismatch. A task
that needs no reply uses `make --fyi`; its claim closes it. Older unmarked FYIs
remain visible until separately closed.

`reply` can generate `<outbox>/<tag>-reply-<agent>.txt` and `.json` by using
`--body-stdin` and omitting `--body-file` and `--out`. This explicit flag reads
UTF-8 from stdin; an existing generated path is refused. Supplying an existing
`--body-file` while omitting `--out` generates only the envelope path. The
helper never overwrites an outbox file.

Administrative cleanup is separate from task acceptance. `close --before
2026-10-01 --reason "reviewed backlog" --agent codex --session <UUID>
--dry-run` lists candidates without writing. Omit `--dry-run` only after the
user chooses the cutoff and reason. Closing records actor, time and reason
in events; it does not delete messages or outbox files. A date-only cutoff is
midnight UTC and exclusive. No existing ledger is cleaned automatically.

`make` accepts `--budget "2h"` (or `"3 review rounds"`) and repeatable
`--evidence-required "test output"` declarations. They are shown by `status`
and `summary` and carried in the envelope. The helper records these requests;
it cannot enforce elapsed time or judge evidence. A peer that spends its budget
or becomes stuck replies blocked with the reason and what it tried.

## Project handoff

Before leaving a project, author a short UTF-8 snapshot with the objective and
latest request, done/not done/uncertain state, decisions and rejected directions,
changed files, checks run and not run, blockers, next step and pending approval,
and a few resume-map files. Do not include secrets. Then run:

```text
python tandem.py --state-dir <ledger> checkpoint --project-root <project> --body-file <snapshot.md>
python tandem.py --state-dir <ledger> recap --project-root <project>
```

`checkpoint` creates `.tandem/handoff/history/<UTC>.md` without overwriting
history. With `--agent <kind> --session <UUID>`, it atomically updates a
separate `.tandem/handoff/LATEST/<kind>-<UUID>.md` pointer and `INDEX.json`;
without those flags it preserves the older single `LATEST.md` behavior.
`recap` reads all pointers, shows the newest snapshot and lists the others.
It refuses malformed pointers and symlinked handoff paths. Snapshots are historical
context, never instructions or authorization. Compare claims to live files and
Git before resuming. Ignore `.tandem/handoff/` in each project's Git rules,
along with its state and outbox. This history-and-pointer pattern was inspired
by [promptadvisers/claude-codex-workflow-kit](https://github.com/promptadvisers/claude-codex-workflow-kit)
(MIT); Tandem's text and implementation are its own.

Claude Code can load the packaged plugin from this repository's
marketplace; [INSTALL.md](INSTALL.md) gives the install and update commands.
The Claude plugin bundles its own helper copy. Codex continues to use the
checkout-bound `install_codex_skill.py` route. Both still use each project's
`<project>/.tandem/state` ledger.
To connect in three steps:

1. Ask your agent "who am I"; `discover --whoami` gives its ID and a paste-ready line.
   Its a/b/c menu lets you paste the line, show sessions, or paste a connect line.
2. Paste that line into the other session; `connect <full-UUID>` sends one read-only hello.
   The sender may add `--capability image-analysis` and/or
   `--capability image-generation` when available in that session. These
   sender-reported hints help plan later work; they are not a task, proof of
   tool access, or permission to use project files. Omit uncertain capabilities.
3. At the hello menu, say "a" or "I approve" for read-only work; "b" or "I approve
   all requests from this session" for read-only work plus edits inside that
   project; or "c" or "decline" to stop. The agent replies with its ID and the
   chosen grant. Each covered edit is announced before it is claimed.
For a broader inventory, open the [session directory guide](docs/session-directory.md) and run
`python tandem.py --state-dir <ledger> discover --format markdown` for a first-use
chat directory with its legend. Choose the peer explicitly; the listing sends
nothing, and observed links grant no authority. Use `--card <full-UUID>` for the
connection brief and keep the same authorized ledger on both sides.

Commands below run from the checkout and use `python` to mean your selected
Python interpreter (`py -3` on Windows or `python3` on Linux/macOS). Replace
angle-bracket placeholders before executing; quote paths containing spaces.
For use from another directory, use the absolute path to `tandem.py`.

See [Workflow](#workflow), [project ledgers](#using-the-bridge-in-another-project),
[filesystem limits](docs/filesystem-portability.md).

## Standing authorization (opt-in)

The read-only `authorization` commands inspect declared user intent; they never
grant OS permissions, enroll peers, change reviewer policy or auto-claim a task.
The default policy is `~/.tandem/authorizations.json`, edited by the user. No
policy is installed by this feature. See [the strict schema](SCHEMA-authorizations.json).

```text
python tandem.py --state-dir <ledger> authorization template --agent codex --session <UUID> --project-root <project>
python tandem.py --state-dir <ledger> authorization status
python tandem.py --state-dir <ledger> authorization check <envelope.json> --agent codex --session <receiver-UUID> --project-root <receiver-project> --sender-project <sender-project> --purpose review --read-path <input-path> --bookkeeping-path <outbox>
```

`template` prints an empty policy plus candidate values, not an active grant.
To enroll, the user adds a reviewed grant object to the policy's `grants` array:

```json
{
  "grant_id": "project-review",
  "sender": {"agent": "claude", "session_id": "<canonical sender UUID>"},
  "receiver": {"agent": "codex", "session_id": "<canonical receiver UUID>"},
  "sender_project": "<project>",
  "receiver_project": "<project>",
  "ledger": "<project>/.tandem/state",
  "bookkeeping": ["<project>/.tandem/state", "<project>/.tandem/outbox"],
  "modes": ["read-only"],
  "purposes": ["status", "review"],
  "readable_scope": ["<project>/src"],
  "exclusions": [],
  "expires": "2026-10-22T00:00:00+04:00"
}
```

This is a structural example with placeholders, not a grant to copy unchanged.
All policy paths must already exist, be absolute local paths, and resolve without
UNC/device paths. Windows canonicalization resolves junctions/symlinks and compares
case-insensitively. Ledger identity is exact, not a parent-prefix match. A future
bookkeeping artifact is covered by declaring its existing authorized parent. Reads
and bookkeeping are separate; include every planned read via repeatable `--read-path`
and every bookkeeping parent via `--bookkeeping-path`. Empty read paths cover no
declared reads, not unrestricted inspection. The body still needs semantic review.

`check` exits 0 for **covered**, 2 for **needs_user_authorization**, 1 for invalid
policy or operational errors. Multiple matching grants are ambiguous. Unknown fields,
duplicate JSON keys, noncanonical UUIDs, wildcard receivers and expired grants cannot
silently authorize work. Revocation is a user edit/removal, observed on the next check.
One invalid/missing path in any grant currently invalidates the whole policy; repair
or remove the stale entry rather than treating other entries as partially validated.
An absent policy is informational for `status` (zero entries, exit 0), but `check`
still exits 2. Template candidates include an existing sibling outbox when available.
Replacement conversation UUIDs require enrollment; resuming the same UUID still
requires an unexpired, unrevoked grant. Cross-project exchanges require an explicit
directed grant naming both projects and endpoints. Sender project and purpose are
caller declarations, not authenticated facts; UUID comparison is also not authentication.

`covered` always includes `semantic_scope_review_required` and
`runtime_approval_separate`. It is not proof the request is safe, the file was written
by a human, or a classifier will accept the command. Scope checking is not a file
access sandbox. Policy location, hash and owner do not prove protection. `status`
reports effective writability as unknown and ACL owner as null: no write/ACL probe
is performed. Same-user host processes may have access that a sandboxed agent lacks.
Use `--format text` for a readable field listing; JSON is default.

Existing `receive` behavior is unchanged. A skill may explicitly check standing
intent before claiming; direct local user authorization remains another route.
The fresh-session live acceptance test is pending a user-installed minimal grant;
helper coverage and actual runtime approval must be measured separately.

## Ask a model for a second opinion

Opinion probes are advisory and depend on the locally available vendor models
and permissions. They do not establish answer quality.

An opinion is advisory input, never permission, verified truth or project-work
delegation. This is a
separate record lifecycle: no task, mutation key, claim or reply is created.

```text
python tandem.py --state-dir <ledger> opinion probe --model claude-sonnet-5 --agent codex --session <asker-UUID> --out <new-probe-answer.txt>
python tandem.py --state-dir <ledger> opinion --model claude-sonnet-5 --agent codex --session <asker-UUID> --question-file <question.txt> --context <explicit-input.txt> --out <new-answer.txt>
python tandem.py --state-dir <ledger> summary --opinions --format json
```

Exact supported IDs are listed by `opinion --help`. Codex model requests currently
produce an explicit unavailable/not-probed record without a model launch: an
enforceable complete no-tools CLI configuration was not established. Read-only
sandbox is not equivalent. Claude calls use an empty built-in tool list, explicit
empty strict MCP configuration and MCP deny pattern, safe mode, no Chrome,
dontAsk/permission-prompts none, isolated scratch cwd, and stream-json/verbose.
Successful parsing requires runtime init `tools: []`, `mcp_servers: []`, exact model
in init and result modelUsage, matching session IDs, no tool-use events, and explicit
empty permission denials. This is runtime evidence plus documented configuration,
not an independent security audit of the CLI or an OS sandbox around inference.

Normal calls require a successful latest explicit probe for the exact model, CLI
version and tool policy. A newer failed/incomplete probe invalidates the older pass.
The tool-policy key includes a hash of the fixed CLI flag list and a parser-contract
version, so a flag change invalidates earlier probes automatically.
The fixed probe expects `OPINION_PROBE_OK`; mismatches fail, without fallback or retry.
A pass demonstrates that sample only. Caller approval is still required for probes;
the helper never launches one implicitly. Effort overrides are rejected in v1 until
supported model-specific semantics and runtime evidence are established.

Question/context must be regular UTF-8 text files. Each context is hashed and labeled;
the complete framed prompt has a 22,000 UTF-16-unit product limit. Only explicitly
passed files are included. `--context` is repeatable; context is labeled untrusted
data, which is a prompt boundary rather than a guarantee of model behavior. Input
goes over stdin with shell-free argv arrays. `--dry-run` may query CLI version but
does not call a model or write files; it cannot verify the runtime gate.

Under `<ledger>/opinions`, immutable `<id>.started.json` precedes launch; `<id>.json`
records final status, hashes, requested/observed model, null unobserved effort,
claimed asker identity, tool evidence, CLI version, usage and duration. Raw responses
are retained under `artifacts/<id>` on failure. A started-only record is unknown.
Answer publication uses exclusive creation; existing outputs and ledger-internal
answer paths are refused. Exit 2 means failed/unknown, not permission to retry.
Failures and machine-readable refusals are retained, not published as answers;
natural-language refusals without a refusal signal still require caller review.
No opinion-of-opinion loops.

`--timeout` defaults to 180 seconds. A timeout terminates the child and records
unknown, retaining available partial output. Per-call `--max-budget-usd` defaults
to 0.50 (maximum 2); this is passed to the Claude CLI, not a guaranteed hard billing
ceiling. Reported usage/cost is CLI list-price evidence, not subscription allowance.
Aggregate experiment budgets are monitored by the operator, not by this command.

On-demand local helper for the supported routing mechanisms:
Codex queue into an existing thread, and Claude SendMessage through a restricted
temporary Claude process. No server, raw named-pipe client, automatic retry,
or promise of delivery
while either application is closed. A Claude session may optionally advertise
an advisory, short-lived folder watch.

Vendor executable discovery uses explicit `--executable` first, then PATH,
then known per-OS locations. Invalid explicit overrides fail without fallback.
Windows shell shims are not executed; a rejected PATH shim allows discovery
of a native installation, otherwise provide a native executable path. POSIX
executables need execute permission. Symlinks/junctions resolve to their target:
that target is executed and recorded as `executable_path` with discovery source.
Vendor updates can change that recorded path. The Claude relay uses the user's
CLI default model unless `--relay-model <exact-id>` is supplied. Existing CLI
logins are used; the helper does not read peer `.key` credentials.

## Workflow

For a first-use session screen with **Linked To** groups, run
`python tandem.py --state-dir <ledger> discover --format table`.
For chat, use `--format markdown` and include its legend. `--history` expands
pairs, `--all` expands other unlinked sessions, and `--internal` separately
expands workers, relay hints and auto-review threads. The resolved self project's
cwd filters the view by default; `--all-projects` shows other projects too.
Use `discover --card <full-UUID>` for a copyable connection brief and `discover
--rows` for full metadata. See [session directory](docs/session-directory.md)
for source limits and the distinction between observed exchanges and live peers.

Choose the project ledger using "Using the bridge in another project" below. `--state-dir` is a global
option and must appear **before** the subcommand.

Run `tandem.py --help` and the relevant subcommand's `--help`. Examples below use
`python` as shorthand for the actual interpreter. Start at the checkout root.

1. `python tandem.py --state-dir <ledger> discover`: inspect Claude registry entries and the
   current Codex thread environment variable. Registry entries are not guaranteed
   live. Read this session’s exact `CODEX_THREAD_ID` environment variable first;
   `codex agents` may require a TTY and is not a non-interactive fallback. Select the intended
   UUID, not the first session. UUIDs must be canonical lowercase.
2. Write the task body to a UTF-8 file, then create a message:

```text
python tandem.py --state-dir <ledger> make --from-agent codex --from-session <UUID> --to-agent claude --to-session <UUID> --tag review-1 --body-file <project>/.tandem/outbox/review.txt --done "Return findings with evidence, no edits" --out <project>/.tandem/outbox/review.json
python tandem.py --state-dir <ledger> send <project>/.tandem/outbox/review.json --relay-model claude-sonnet-5
```

`make` validates before writing the envelope, and `send` validates it again.
`make` also records the resolved task body source path and SHA256 in the local
ledger's `provenance/<id>.json`; this path is never part of the envelope. It
refuses a body file already used by another locally made task. Use a new body
file for each task.
For a mutation touching more than one file or a body near the size cap, also
run `validate <envelope>` and `send <envelope> --dry-run` before the real send.
For edits, set `--mode`, `--allow`, `--protect` and `--mutation-key`. Put input
paths, hashes and live-state expectations in the body. Scope and acceptance
criteria are instructions to the receiving agent, not an OS sandbox. Batch
small edits to the same files into one task with a `--done` criterion for each
outcome; split only when a later edit depends on reviewing the first.

The hello's "all requests" choice grants edits inside the named project from
that full peer UUID for this conversation. The agent announces each claimed
edit with its tag and paths. A user who chose read-only can later grant edits
to named paths after a mutating task is surfaced. Neither grant covers paths
outside the grant, deletion or rename, protected-path conflicts, credentials
or secrets, disclosure to a third session, or another peer. Codex automatic
review and host runtime approval still apply; an envelope grants nothing.

Connection approval has two directions. The receiver chooses what requests it
will accept from the sender; after the acceptance reply, the sender chooses what
requests it will accept back. The ready line shows both choices as `yours` and
`theirs`. A missing choice is unknown, never inferred from a hello or a task.
The return choice is not currently an envelope field; agents must not create an
acknowledgement-only message to announce it. A future protocol field needs a
separate design review.

3. Receiver saves the exact JSON following `TANDEM/1` to a new UTF-8 file if it
   cannot use the shared `<ledger>/messages/<id>.json`, then claims it:

```text
python tandem.py --state-dir <ledger> receive <ledger>/messages/<id>.json --agent claude --session <its-own-UUID>
```

Do not act if claiming fails. Check the target matches the receiver's actual
session, user authorization, scope and current project guidance before work.
This local convention does not authenticate an agent or authorize arbitrary tasks.

4. Receiver writes findings to a **new** body file named
   `<tag>-reply-<agent>.txt`, then prepares and sends a reply. Never overwrite
   the task body file or another file you did not create:

```text
python tandem.py --state-dir <ledger> reply <ledger>/messages/<id>.json --agent claude --session <its-own-UUID> --body-file <project>/.tandem/outbox/result.txt --status completed --evidence <path> --out <project>/.tandem/outbox/result.json
python tandem.py --state-dir <ledger> send <project>/.tandem/outbox/result.json
```

Use `--status blocked` and `--limitation` for blockers. The reply automatically
targets the original sender; no relay must remain alive. The initiating agent
claims the reply with `receive`, reviews evidence, and reports to the user.
Never send an acknowledgment merely to acknowledge another reply.
`reply` refuses the task's recorded body source path and a copied file whose
body has the same SHA256. For older tasks without local provenance, it still
refuses a body matching the task envelope. After claiming, finish with `reply`
and `send`; if work must stop early, send a blocked reply with the reason.

5. `python tandem.py --state-dir <ledger> status <id>` shows immutable event records. These
distinguish dispatch, transport output, claim, prepared reply, and receiver-reported
completion. A zero transport exit is not a read receipt. A prepared reply has
not been sent. An agent's completion claim is not independent verification.
Claude delivery reports must include a validated machine-readable result and
message UUID; they are recorded as `relay_reported_queued`, not observed receipt.
Missing/failed reports produce `delivery_unknown` and helper exit code 2.
`status` also reports dispatch/claim reservations and the finalized claim marker.
Add `--brief` for one line: `<id8> <tag> sent <UTC time|none> · claimed
<UTC time by agent|none> · reply <none|id8 prepared/sent/claimed UTC time,
result.status>`. `sent` is the start of dispatch, not a receipt. A prepared
reply is still only a local file; `claimed` records the peer helper's receipt,
not a person's reading. Full JSON remains the default.

## Task summary and coordinator handoff

Use the existing ledger explicitly (creating a project `.tandem/` or a bridge Git
repository changes automatic discovery; existing records are not migrated):

```text
python tandem.py --state-dir <ledger> summary
python tandem.py --state-dir <ledger> summary --format json
python tandem.py --state-dir <ledger> coordinator --project-root <project> --session <Codex UUID>
python tandem.py --state-dir <ledger> accept <task UUID> --agent codex --session <original sender UUID> --evidence "What was reviewed and where"
```

`summary` is read-only and joins received results to their original tasks. It
includes review-accepted history, unknown delivery, incomplete reservations,
blocked work and completion reports awaiting review. A prepared reply alone is
not a received result. Envelopes only created in an outbox and never dispatched
or claimed are not yet ledger tasks and cannot appear here. No automatic retries
or historical acceptance is inferred. `accept` records a coordinator assertion
after a completed reply is claimed; it does not itself verify the work.

`coordinator` atomically refreshes the marked generated block in
`<project>/.tandem/COORDINATOR.md`, preserving authored sections: Decisions + why,
Pitfalls, Learnings, Open items. Missing/ambiguous markers are refused. Keep one
writer per note; replacement is atomic but is not a multi-writer lock. Review
the snapshot and rediscover peers before sending after a handoff. Existing
claims are never transferred to a replacement conversation by these commands.

Independent handoff and review workflows may read the note for their own
briefings. Their writes require separate authorization; these commands do not
invoke those workflows automatically.

## Watching instead of relaying

A Claude session can run one foreground follower as its Monitor. It scans
unclaimed backlog first, then watches new files addressed to its exact agent
kind and session UUID. It emits one flushed line per envelope:
`TANDEM_NEW <id> <kind> <JSON-quoted tag> from <agent> <8-hex sender ID>`.
Use the full ID to claim. When relay runs, one envelope can appear both in chat
and on disk; claim it once by ID.

```text
python tandem.py --state-dir <ledger> watch --agent claude --session <Claude UUID> --follow
python tandem.py --state-dir <ledger> watch --agent claude --session <Claude UUID> --minutes 10
python tandem.py --state-dir <ledger> watch --agent claude --session <Claude UUID> --stop
python tandem.py --state-dir <ledger> send <outbox/message.json> --relay auto
```

`watch --follow` renews a two-minute heartbeat about every minute while its
scan loop is healthy. It removes the heartbeat on a catchable Ctrl-C or
SIGTERM. A hard kill can leave the file until expiry, creating up to about two
minutes of silence before relay resumes. On Windows the follower checks its
captured parent PID each scan so an orphan cannot keep renewing, but a Monitor
stop may kill parent and child before cleanup runs. Git Bash `timeout -s INT`
does not reliably interrupt native Windows Python. Keep the follower in the
foreground.
One-shot `watch` and `--minutes` remain for compatibility, but their heartbeat
is not tied to a live scanner. Before stopping an old Monitor, run
`watch --stop`, then scan unclaimed messages for the exact session UUID.

`watch` writes or refreshes `<ledger>/watch/<UUID>.json` atomically with agent,
session ID, UTC expiry and write time. This mutable file is bookkeeping, never
a ledger message, event or proof of receipt.

`send --relay auto` is the default. A heartbeat counts only while that Claude
session is also registered. When its heartbeat expires more than 15 seconds
from now, send records the message and a
`watch_delivery_expected` event without launching a relay, returning
`written_for_watcher`. This means the message was written for a watcher, not received.
A `claimed` event proves the receiver's helper claimed it, not that a human read it.
A stale, missing
or malformed heartbeat uses the usual relay. `--relay always` forces that relay;
`--relay never` records the message without one and returns
`written_without_relay`. Codex recipients still use their queue. Watch delivery
is best effort; restarting the follower repeats the unclaimed backlog scan.
Do not retry an uncertain envelope automatically. A reply's task outcome is
`result.status` (`completed` or `blocked`), not a top-level `status` field.
A conversation restart resets its grants; obtain them again. If
`discover --whoami` or `watch --follow` warns that one Claude UUID has multiple
live PIDs, close one window before coordinating. The helper never kills either.

## Ledger resolution and failures

### Opt-in relay measurements

`summary --usage --format json` includes `relay_usage` rows with reported model
names, uncached input, cached input, cache creation, output, duration and
`cost_usd_list`. Missing counters remain null, not zero. Historical raw reports
are parsed read-only; no old event is rewritten. These are CLI-reported
list-price estimates, not subscription allowance measurements or invoices.

Claude-bound `send` accepts `--relay-model <exact-model-id>` and
`--relay-cwd <existing-authorized-directory>`. The Codex skill uses
`claude-sonnet-5` for Claude relays by default; users can override
or omit it, and the helper default is unchanged. Both flags are refused for
Codex-bound messages. `--dry-run`
shows the requested arguments and cwd without starting a model or writing state;
it cannot prove model availability. The same safe-mode, strict MCP,
SendMessage-only and dontAsk flags remain in force. No settings-source override
or custom replacement system prompt is introduced.

`send --relay-prompt revised` is the default Claude relay fallback. It is a
truthful forwarding request: the relay may decline and does not claim that the
envelope proves authorization. `plain` and `legacy` remain selectable. Plain
uses data markers around the unchanged wire message; the markers are not
message content. When a relay is about to launch, the helper refuses message
text containing the literal `TANDEM_RELAY_RESULT` for every prompt variant,
so message text cannot forge a result line. A fresh watch can carry that text
because no relay result is parsed. Relay options are refused for Codex-bound messages. Dispatch and
result events, plus usage rows, record `relay_prompt_variant`; old events
without that field report null.

T3 on one PC on 2026-09-27 sent two messages per model and prompt cell:

| Relay model | Plain | Revised |
|---|---:|---:|
| Claude Sonnet 5 | 2/2 arrived | 2/2 arrived |
| Claude Opus 5.5 | 2/2 arrived | 2/2 arrived |
| Claude Haiku 4.5 | 2/2 arrived | 2/2 arrived |

Both Opus/revised outputs included prose before a valid final result line; the
old parser recorded them as uncertain although the peer observed both arrivals.
The parser now accepts a valid result line only as the last non-empty line.
Two runs per cell on one PC and one day support changing the default, not a
general reliability guarantee. An exit-zero relay ending without a result line
records `cause: relay_no_result`; an unparseable result line records
`cause: relay_result_unparsed`. Both point to the local transcript and keep
`delivery_unknown`; do not retry automatically. See [relay prompt details](docs/relay-prompt-revised-draft.md).

New relay events record the requested model, launch cwd and seconds since the
previous recorded relay launch **in this ledger**. This gap is not a cache-hit
guarantee and does not include relays outside this ledger. Concurrent launches
can observe the same previous event. Inspect actual cache counters instead.
Reported permission denials force `delivery_unknown` even if a success result
line is present. Never auto-retry that message.

Compare payload length, actual model and all input categories when evaluating
context changes; a warm cache alone does not mean fewer context tokens. Small
model experiments must verify independently received content against its stored
hash, not hash the sender's ledger twice. Test artifacts belong in ignored
`outbox/`; a successful experiment does not automatically change the default.

Every command prints its resolved absolute `state_dir` and `state_dir_source`.
New events include `state_dir`; old events are kept unchanged. `status` lists
`state_dir_mismatches` and counts `legacy_events_without_state_dir`. A claim is
refused if its existing events name another ledger, or if its input is the
canonical `messages/<id>.json` from another ledger. There is no global ledger
index: an arbitrary copied bare envelope with no events cannot prove where it
belongs. Always use the sender's routing header, not a guess from receiver cwd.

Each message ID can be dispatched and claimed once per shared state directory.
An ID cannot be reused with different content. A mutation key is reserved at
claim time for its recipient; another message with the same key is blocked,
including after a crash. All agents must use this same state directory for these
checks to work. Duplicate protection does not provide exactly-once side effects.
Controlled duplicate-mutation rejection releases its own empty claim folder;
unexpected crashes keep reservations. A receiver may prepare at most one reply
per task/status, allowing blocked then completed after an explicitly authorized
resolution. A result is accepted only from the recorded claimant and at most
once per task/status. Claimed sender identity is not cryptographic authentication.

Crashes/timeouts leave reservations intact and mean outcome unknown. Inspect
the recipient, evidence and status before any manual recovery; do not remove
reservations or create another ID to retry an uncertain mutation automatically.
There is no automatic lease expiry or task cancellation.
Do not fabricate `claimed.json` or completion events to recover a half-finished
claim. Inspect the task and worker first and make a deliberate recovery decision.
Transport waits default to 300 seconds for Claude and 60 for Codex. At timeout
the subprocess is terminated, but an already-delivered request may still run;
the relay UUID is retained for investigation. A longer timeout is configurable.

JSON files are published via same-directory temporary files plus an exclusive
hard link, then the temporary is removed. Use a local filesystem supporting hard
links (tested on NTFS), not a network share or sync folder. Each event has its
own file to avoid concurrent JSONL append corruption. Folders are session-scoped
through envelope checks; messages are globally keyed by UUID.

Processes use argument arrays with `shell=False`. Claude relay prompts go through
stdin; Codex queue currently takes message text as one argument. UTF-16 command
size is conservatively capped; large artifacts belong in local files. No nested
PowerShell quoting is needed. The relay keeps the proven default model and has
only SendMessage, with safe mode and no MCP configuration. Its report is retained
as a report, not relabeled as observed delivery.

Permissions still apply. A launch denial is surfaced; there is no fallback that
changes privilege, model, session or tool to evade it. The helper may require
host approval for named-pipe delivery. It never approves a project action for
the receiver. Logs contain task text and results; protect them as project data.

## Skills and validation

The staged Codex skill is `skills/tandem-bridge/SKILL.md`. The explicit
installer binds it to this checkout and selected interpreter under
`~/.codex/skills/tandem-bridge/` (or `$CODEX_HOME/skills`). It refuses conflicting
existing content. No global skill is updated by editing the staged source.
Claude's user-level skill is maintained separately under its own skill directory;
this installer does not write it. Plugin packaging is deferred.

Agree file ownership between peers before starting work; keep each agent’s
configuration under its own control.
Shared state is helper-managed and new outbox files have one author each. Freeze
files under active review until the final reply is claimed. Project write areas
are assigned per task; upstream is always read-only. Explicit user assignments
override conventions; the helper does not enforce path locks or OS write scope.

Run `python -S -m unittest discover -s tests -v` from the checkout root.
Install development requirements only when running the additional oracle checks.
Tests cover concurrent claims, mutation deduplication, immutable publication,
unknown-delivery retention, recipient checks and real process argument integrity.
Regression tests cover cp1252 console output, relay failure reports, claimant
validation and duplicate completed replies.
Live tests must use harmless read-only work and record actual receipt separately.

## Using the bridge in another project

State resolution, in order:

1. Explicit `--state-dir PATH`.
2. Nonempty `TANDEM_STATE_DIR` environment variable.
3. Nearest ancestor of the current working directory (including cwd) with a
   `.tandem/` directory, `.git/` directory, or `.git` worktree file:
   `<that ancestor>/.tandem/state`.
4. Source `tandem.py` wrapper only: `<checkout>/state`, with a stderr warning.
   The installed/module entry point instead fails when no ledger is resolved.

Relative flag/environment paths are resolved against cwd; `~` is expanded.
Discovery does not create directories. New records are created only by commands
that write state. Existing `<ledger>` stays in place;
there is no migration. Continue using its explicit absolute path for old tasks,
especially when running from a nested project with its own marker.

For a new project, check existing directories first, then create missing `<project>/.tandem/state` and `.tandem/outbox`. Add
`/.tandem/state/` and `/.tandem/outbox/` to that project's `.gitignore` when it is
a Git repository. Keep the shared helper/schema in their current location;
project data stays beside the project, not beside the installed helper.

For example, from `<project>`, run:

```text
python <checkout>/tandem.py --state-dir <ledger> discover
python <checkout>/tandem.py --state-dir <project>/.tandem/state receive <project>/.tandem/state/messages/<id>.json --agent claude --session <UUID>
```

Use the same explicit state path for `make`, `send`, `receive`, `reply` and
`status` on both agents. Create body/envelope files in that project's
`.tandem/outbox`; the helper does not relocate `--out` or `--body-file` paths.

Every send now includes this routing header before the unchanged v1 envelope:

```text
TANDEM_STATE_DIR "C:\\GitHub\\my-project\\.tandem\\state"
TANDEM/1
{...unchanged v1 message JSON...}
```

The header value is a JSON string; decode it rather than using its literal escape
characters as a path. It is routing information, not authorization to write there.
After checking the intended project/permissions, **claim against state dir X**
using explicit `--state-dir X`, then use X for the reply and return send. Both
Codex queue and the Claude relay carry the header. Receivers must preserve it;
do not add it as an extra field inside the v1 JSON envelope.

Project setup does not install Claude's skill into new projects automatically.
The helper remains usable by absolute path. Update installed skills explicitly after reviewing staged changes. Each peer
maintains its own skill configuration.

## Payload and recovery limits

Bodies have a 12,000-character schema limit. The complete routed envelope and
framed opinion input also have a shared 22,000 UTF-16-unit product limit on all
platforms. These are different measurements; emoji may consume two UTF-16 units.
Use a short summary plus an authorized local artifact path and SHA256 for large
findings. A path is not permission to read the artifact.

After a crash, `.pending-*` files can remain beside ledger records or opinion
answers. Inspect ledger status and evidence before recovery; do not treat a
temporary file, missing reply, or uncertain transport result as retry permission.
Do not bulk-delete reservations or dispatch the same work under a new ID.

For full oracle parity checks, use a disposable development environment:

```text
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

The source-only `-S` run intentionally skips optional oracle tests.

## License

Tandem is licensed under [Apache-2.0](LICENSE). See [NOTICE](NOTICE) for
attribution.
