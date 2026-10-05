# Session directory

Use the chosen Python interpreter from the checkout:

```text
python tandem.py --state-dir <ledger> discover --whoami
python tandem.py --state-dir <ledger> discover --whoami --agent claude --session <full-UUID>
python tandem.py --state-dir <ledger> connect <peer-full-UUID>
python tandem.py --state-dir <ledger> discover --format table
python tandem.py --state-dir <ledger> discover --format markdown
python tandem.py --state-dir <ledger> discover --rows
python tandem.py --state-dir <ledger> discover --card <full-session-UUID>
```

Installed-module users substitute `python -m tandem_bridge`. Bare `discover`
retains its original JSON shape and scope; `--rows` opts into versioned normalized
JSON. The table abbreviates long fields with `~`; use rows/card for full values.

`discover --whoami` prints exactly two plain lines: this session's recorded name,
full UUID, project basename and selected ledger, then a line to paste into another
session. Codex uses `CODEX_THREAD_ID`; Claude passes `--agent claude --session`
after reading its own registry entry. An unresolved self identity or project fails
with one error line. This command sends nothing and does not create state.

`connect <full-UUID>` resolves both endpoints through the directory and sends one
fixed read-only hello. `--to-agent` can disambiguate the target kind; Claude can
pass `--agent claude --session <full-UUID>` for itself. Missing or ambiguous targets
are refused with candidates. The command prints its envelope ID and transport
state on one line. A queue report is not a receiver claim; inspect the ledger if
delivery is uncertain, and never retry the hello automatically. Pasting the
whoami line authorizes that hello only. The receiver surfaces the request and
waits for the user's "I approve" before claiming it or beginning peer work.

The grouped table shows vendor, name, project, UUID, last-observed model/effort,
status and **Linked To**. Each section is one direct pair, newest completed reply
first, with exchange count and latest-reply timestamp. A session in several pairs
appears in each section, marked with its other-pair count. Rows JSON keeps unique
sessions plus a link list with stable sorted-endpoint `pair_id` values; it does
not merge indirect contacts into a team. Linked To lists direct peers only. Both task
and completed correlated reply require finalized claims naming their expected
receivers. Partial claims, blocked results and one-way messages do not establish
a link. Links record history: one incidental completed review also counts. Group
membership neither grants permission nor means everyone is currently working
together. A missing registry entry can still appear as a historical endpoint.

No age cutoff is applied. When a self hint resolves unambiguously to a recorded
absolute project cwd, that cwd is the default filter. Optional
`--project-root <path>` overrides it, never using the ledger location.
No resolved self cwd means no automatic filter. Cards retain their explicit
lookup scope (no automatic self-project filter). `--all-projects` clears filtering;
it does not inspect other ledgers. Direct links to peers outside a filter may
remain visible, identified by endpoint. No declared-pair file is created.

Claude registry status is reported metadata, not reachability. Process state is
currently unknown; no process probes or socket calls are made. Claude model and
effort are unobserved. Codex inventory combines saved rollout IDs and its name
index. Its model/effort is the last usable turn context in a bounded tail, not
necessarily the current model. Saved threads may accept queued messages with no
consumer attached. Refresh before sending; sending remains a separate command.

The self marker uses `CODEX_THREAD_ID` when available, or explicit
`--agent <kind> --session <UUID>`. Both are hints, not authentication. No parent-PID
inference is attempted. `--card` without a UUID uses that hint if available; an
ambiguous or unknown target fails rather than choosing a same-folder session.
Cards print full identity, invocation argv, ledger, and scoped authorization and
receive/reply templates. They neither send nor enroll anyone. Review and complete
placeholders. There is no Tandem URL or persistent server.
Cards render as text even with `--format json`; use `--rows` without `--card`
for machine-readable session fields.

## Source and privacy bounds

The ASCII table uses short UUIDs and relative ages, with one line per session.
The first three pairs are expanded; subsequent pair headers remain visible, with
one-off pairs sharing an endpoint within 24 hours folded into a counted receipt.
`--history` expands all pairs. Under No known link, Claude entries and recent
non-auto-review Codex threads remain visible. Other Codex threads are folded into
disjoint counted categories. Unlinked internal roles (worker, relay heuristic,
auto-review) require `--internal` to expand; `--all` does not expand those roles.
Other older/unknown-age threads expand with `--all`. These are display folds,
not inventory cutoffs. `--all-projects` separately clears a project filter.
Markdown uses the same folds and adds a legend; use it for chat, while ASCII is
for a terminal. Labels use code spans, pipes are escaped, controls become spaces,
and literal backticks become typographic apostrophes in Markdown only; `--rows`
retains the original fields. Full normalized rows add `role` and `sources.role`, retaining
existing status fields and source bounds. `codex_exec` in rollout originator
identifies a worker; model prefix `codex-auto-review` takes precedence. A Claude
derived name matching `bridge-[0-9a-z]+` with cwd equal to the helper checkout is
only a relay heuristic, not proof. Unknown cases remain peers; roles never select
recipients or change links. No paid probe is used to infer registry kinds.
Long labels and paths use `~` truncation to keep lines within 100 columns; use
`--rows` for complete fields and warnings. Model/effort means last observed turn.
`--color=auto` uses ANSI only on a TTY when `NO_COLOR` is unset. `always` forces it
even in a pipe or with `NO_COLOR`; `never` disables it. `--no-color` wins over all
color settings. Markdown never emits ANSI.
Color assumes a VT-capable terminal. The ledger has its own line; if it exceeds
the available width, a leading `~` marks omitted parent directories while keeping
the distinguishing tail. Use `--rows` or a card to copy an unabridged long path.

Sources are version-dependent adapters. Missing, inaccessible or malformed input
is reported rather than equated with no peers. Only whitelisted metadata is
retained. JSON lines can contain private text; the parser discards unrelated
fields and never returns transcript bodies. It does not open `.key` credentials
or `history.jsonl`. Local paths/names in output still need review before sharing.

Limits: 10,000 files per source traversal, 128 KiB per JSON record/first rollout
line, 4 MiB for the name index, at most the last 2 MiB/2,048 lines per rollout,
64 MiB aggregate rollout-tail budget. A capped or malformed tail can leave model
information unknown. Blank tail lines are skipped. The budget is assigned to
recently indexed threads first, then descending IDs for entries without index
timestamps; this ordering is not evidence of liveness. Multiple rollouts for one UUID are reported as ambiguous;
none is guessed from modification time. Bounds can make an inventory incomplete.
The helper never starts a model, installs dependencies, writes state, pings a
peer, scans other project ledgers, or changes permissions for discovery.
