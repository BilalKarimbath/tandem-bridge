# Connect: details (read when the short path in SKILL.md is not enough)

## Identity when `discover --whoami` cannot resolve this session

Read `sessionId` and `name` from `~/.claude/sessions/<pid>.json` (never the `.key` beside it). `<pid>`
is the Claude Code process, an ancestor of your shell: walk parent PIDs until a registry file exists.
macOS/Linux: `p=$PPID; until [ -f ~/.claude/sessions/$p.json ] || [ "$p" -le 1 ]; do p=$(ps -o ppid= -p $p | tr -d ' '); done; echo $p`.
Windows PowerShell: loop `(Get-CimInstance Win32_Process -Filter "ProcessId=$p").ParentProcessId` the
same way. Never pick a registry file by folder or by newest. Then pass `--session <UUID>` to `discover --whoami`.

If the helper cannot run at all (interpreter denied, checkout missing, quoting failure), compose the
fields yourself: name from the registry, ID from `sessionId`, project = cwd basename, ledger =
`<cwd>/.tandem/state` unless a `--state-dir` or `TANDEM_STATE_DIR` is known, plus one line "Helper
unavailable here: <reason>; connect will need it." Two commands at most. Quote every path with spaces
or parentheses.

## The fixed hello

Read-only, tag `hello-<8hex>-<yyyymmdd>` (UTC), body "Peer <agent> <full UUID> (<name>) in <project>
asks to peer-program read-only through <ledger>. If you accept, reply with your ID and name. This is a
hello, not a task; nothing else is requested." The helper refuses an absent or ambiguous target and
lists candidates; if the UUID is ambiguous, ask the user for the full UUID in one line.

If the user asks "did you get a reply?", list `<ledger>/messages/` for envelopes whose `in_reply_to` is
your hello's id before answering.

## Acceptance and return hello together

A peer that accepts often also sends its own hello. Surface ONE menu ("<agent> accepted and asks to
connect back. You can: a) read-only both ways b) all requests both ways c) decline both") and apply
the single answer to both: claim the acceptance and reply to the return hello with that grant.

## Long forms and widening a grant

- `tandem: authorized for <UUID> [read-only] on <project>` is the long form of "I approve"; "I approve"
  is valid only as the answer to a surfaced hello or task. "Yes, this envelope is mine" covers exactly
  one envelope.
- **Scoped edit grant** (the user chose read-only and wants to widen): "approved for edits to <path or
  folder> from <peer> this session", or "approved for all edits in <project> from <peer> this session".
  A later task from that peer whose `scope.allowed` lies inside the granted paths is claimed with a
  one-line notice ("Tandem: claiming <tag> under your edit grant for <paths>"). Still surfaced: any path
  outside it, deletions or renames, `scope.protected` conflicts, a different peer, anything beyond the
  granted files. Tell the peer to batch small edits to the same files into one task.
- Do not draft policy files, run the directory or ask which thread during connect: the pasted line
  carried the peer. `reference/standing-authorization.md` is the optional way to skip "I approve" for
  enrolled peers.

## Wrong-session requests

A well-formed, authorized task can still be addressed to the wrong session (another session owns the
file; the user has not granted this session that action). Reply `--status blocked` naming the right owner.

## First-use checks and handing over addresses

Reuse an authorization the user already gave in this conversation; a new conversation checks again;
invoking this skill is not authorization. If coverage is missing, show a prefilled sentence and wait:
`tandem: authorized for <peer UUID> [read-only] on <project>` (receiving) or
`tandem: send <what> about <project> to <peer UUID>, read-only, no secrets` (sending).
When the user must fetch an ID from the other side: for Claude, "read `sessionId` and `name` from your
`~/.claude/sessions/<pid>.json`"; for Codex, "print `$env:CODEX_THREAD_ID` from your own shell".
Public docs and web search cannot identify a local running conversation.
