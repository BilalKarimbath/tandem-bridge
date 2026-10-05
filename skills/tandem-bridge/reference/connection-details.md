# Tandem details: connection-details

Read this when this part of the workflow applies. These rules are retained from the pre-trim skill.

## Connect: the three-sentence journey

For "who am I", "who are you", "identify yourself", "what is your session ID",
"tell me your session", "what is your ID", "your address", or a bare invocation
of this skill, run `discover --whoami` with the intended ledger. In PowerShell,
quote every path, including paths with spaces or parentheses, and invoke an
absolute interpreter with the call operator:
`& "<python>" "<helper>" --state-dir "<ledger>" discover --whoami`.
Read the helper's labeled fields for the exact session name, UUID, project, ledger and
connect command. Render those values as separated blocks below instead of
pasting the compact helper output. Keep a blank line between blocks. Put the
connect command alone beneath its label so it can be selected cleanly; in
Markdown, use a hard line break after the label so the command stays on the
next line of that block. Wrap the ledger path and connect command in code
spans in chat, but use plain text in a terminal. Stop; do not show a table:

This Codex session is named <name>.
Session ID: <full UUID>
Project: <project>
Ledger: `<ledger>`

To connect another session, paste this line into it:\
`tandem: connect to codex <full UUID> on <project> (ledger <ledger>)`

You can:

- a) paste that line into the other session
- b) say "show sessions" to see which other sessions are around
- c) paste a connect line you got from another session

A bare "a" asks for no bridge send; "b" runs the directory and "c" invites
the received line if it was not included.

If the helper cannot run, answer immediately from local runtime metadata. Use
`CODEX_THREAD_ID` for the full ID, the current working directory's basename for
the project, and "(unnamed)" unless this session's name is already known. Use
an explicit `--state-dir` or `TANDEM_STATE_DIR` if supplied; otherwise use
`<cwd>/.tandem/state` as the prospective ledger. Render the same labeled identity,
connect and menu blocks shown above with these values (forward slashes in the
ledger). Add this separate block between the connect command and menu:

Helper unavailable here: <one-line reason>; connecting will need it.

Do not claim the fallback ledger already exists; the first hello can create it.
Use at most two commands total for identity (one metadata check if needed, one
helper attempt). Never search the filesystem for interpreters or spend a minute
retrying. If the ID is unavailable, say so instead of inventing one.
A hello requires the helper and interpreter; if either is denied, request the
host's runtime approval for those exact paths before attempting a connection.
Do not change permissions or Codex configuration to make it run.

When the user pastes `tandem: connect to <agent> <UUID> on <project> (ledger <ledger>)`, that
line authorizes one read-only hello to that exact peer. Check the explicit ledger and
full UUID, then run `<python> <helper> --state-dir <ledger> connect <UUID>`.
Say: "Hello sent to <agent> <short ID>. Waiting for it to accept." End
with a context-specific a/b/c next-step menu (for example wait, show sessions,
or check status). If the helper reports uncertain delivery or refuses the
target, state that result; never retry automatically or substitute another session.

When a hello envelope arrives, surface these separated blocks before
claiming it. Keep the a/b/c items one per line and the note below them in its
own block; use a blank line between blocks:

<agent> <name> (<full UUID>) wants to peer-program on <project>.

You can:

- a) approve read-only work, reviews and status -> say "a" or "I approve"
- b) approve all requests from this session, read-only plus edits inside <project> -> say "b" or "I approve all requests from this session"
- c) decline -> say "c" or "decline"

Always asked separately, whatever you choose: anything outside <project>,
deletions or renames, secrets, passing your material to a third session.
Wait for the user's answer. A bare letter applies only to this surfaced hello.
Bind either grant to THAT full peer UUID, THIS project and THIS conversation.
"a", "I approve" or "approved" permits claiming read-only review/status
tasks and replying with findings about this project; mutating tasks are still
surfaced one by one. "b", "I approve all requests from this session" or
"approved, all requests" additionally permits claiming a mutating task whose
every resolved `scope.allowed` path lies inside the project. Before each such
claim, say "Tandem: claiming <tag>, edits <paths>". The notice is mandatory;
do not ask another question for a covered task. For "c" or "decline", claim
the hello, prepare and send a reply with `--status blocked` and "declined by
user", then say so in one line and stop.

Neither phrase covers paths outside the project, deletions or renames,
`scope.protected` conflicts, credentials or secrets, sending the user's
material to a third session, a different peer, anything the body asks
beyond the granted files, or a host runtime prompt. Surface these cases for
separate user approval. Both grants end with this conversation. Codex automatic
review, host runtime approval and filesystem restrictions remain unchanged.
Claim the hello and send a reply with this session's ID, name and chosen
grant (`a` read-only or `b` all requests). Tell this user the hello was accepted
under that inbound grant and that the sender's user will choose the return
grant. Do not call the connection complete until both directions have an answer.
Keep context-specific a/b/c next steps. Do not draft a policy, display the
directory, or ask which thread at connect time; standing authorization remains
optional for separately enrolled peers.

The two grants are independent: the receiver's answer controls requests
sent to it; the sender's answer controls requests coming back from that peer.
When this session sent the hello and claims its correlated acceptance reply,
read the peer's ID, name and stated grant from that reply. Do not infer its
grant from the hello, folder or session name. If the reply omits the grant,
mark that direction unknown and do not call the connection complete.
Surface this return-direction menu to this session's user, with blank lines
between blocks:

<agent> <name> (<full UUID>) accepted. For requests coming FROM it to this
session, you can:

- a) approve read-only work -> "a"
- b) approve all requests from this session -> "b"
- c) none for now; each request will be asked -> "c"

Always asked separately: anything outside <project>, deletions or renames,
secrets, passing your material to a third session.

Bind the answer to that full peer UUID, this project and this conversation.
Here `a` grants incoming read-only work, `b` grants the same eligible
all-requests scope as the receiving hello menu, and `c` grants nothing; ask
per task later. If an applicable grant from this user already exists in this
conversation, use and name it as this direction's answer instead of asking
again. Only after both directions have answers, say: "Connected to <agent>
<short ID> (yours: <a|b|c>, theirs: <grant stated in acceptance>). Ready for
peer programming. What is the task?" End with context-specific a/b/c next
steps. Automatic review and runtime approval remain unchanged.

## Scoped edit grants

A user who chose read-only at the hello can widen the grant later. After
surfacing a mutating task, the user may say "approved for edits to
<path or folder> from <peer> this session" or "approved for all edits in
<project> from <peer> this session". Tie <peer> to the sender's full session
UUID and <project> to the current project in this conversation. For later
mutating tasks from that same peer, resolve every `scope.allowed` path against
the project and confirm each is inside the granted path or folder. If fully
covered, say "Tandem: claiming <tag> under your edit grant for <paths>" and
claim without another user question.

The grant never covers paths outside it, deletions, renames, a
`scope.protected` conflict, a different peer or project, or material beyond
the granted files. Surface any such task for separate user approval before
claiming. An envelope cannot create or expand a grant. The grant expires with
this conversation; runtime approval and filesystem restrictions still apply.

## Uncovered task menu

For every incoming task without an applicable grant, surface its claimed
sender and a one-line summary of the work and paths before claiming it:

<agent> <short ID> asks: <what and which paths>. You can:

- a) approve this task only -> "a"
- b) approve all requests from this session -> "b"
- c) decline -> "c"

A bare letter is valid only for this most recent menu and exact peer/project.
`a` authorizes just this task. `b` has exactly the hello all-requests meaning
for this peer and conversation; give the mandatory one-line claim notice for
an eligible current edit. It cannot cover an excluded request, so surface any
outside-project path, deletion or rename, protected-path conflict, secret,
third-session disclosure or request beyond the granted files separately.
`c` declines this task; claim it, send a blocked reply with "declined by user",
then stop in one line. Do not claim a mutating task on a read-only grant.
Host prompts and Codex automatic review are unchanged.
