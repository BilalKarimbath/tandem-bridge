# Tandem details: ownership

Read this when this part of the workflow applies. These rules are retained from the pre-trim skill.

## File ownership for this workspace

Codex owns `bridge/` source, its skill, and the root bridge guidance. Claude owns
workspace `.claude/`. Both use helper-managed state and uniquely named outbox
files, one author per file. Assign project write ownership explicitly per task;
`upstream/` remains read-only. These conventions yield to explicit user assignments
and do not imply filesystem locking by the helper. Freeze files under active
review until the final reply is claimed, rather than acting on a draft reply.

`scope.allowed` lists permitted task writes; read-only tasks may inspect their
specified inputs with an empty list. `scope.protected` prohibits mutation. Bridge
bookkeeping stays in shared state and unique outbox artifacts. Access restrictions
and project permissions still apply. Disclose an actual denied operation; an
expressly permitted alternative method is not itself a bypass.
