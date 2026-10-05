# Ask a model for a second opinion (read when the user wants an independent view on a design or plan)

An opinion is advisory input to your judgment: never permission, never verified truth, never a way to
delegate edits; no opinion-of-opinion loops.
```
<python> <checkout>/tandem.py --state-dir <ledger> opinion probe --model <model> --agent claude --session <this UUID> --out <new file>
<python> <checkout>/tandem.py --state-dir <ledger> opinion --model <model> --agent claude --session <this UUID> --question-file <q.txt> [--context <file> ...] --out <new answer file>
<python> <checkout>/tandem.py --state-dir <ledger> summary --opinions
```
- **Ask a model that is not you.** Your own model id is in the system prompt (a `[1m]` suffix is the
  same model). Most independent: a different vendor, through a read-only task to the Codex peer (its
  answer comes with its own tools). Next: a different Claude family via `opinion`. Your own model only
  if the user asks. Say which model answered and why.
- A passing `opinion probe` for the exact model, CLI version and tool policy is required first; probes
  cost a model call, so get the user's word. Codex models are recorded `not_probed` (no supported way
  to disable all tools per call); do not route around that with a read-only sandbox.
- Question and context are UTF-8 files; context is quoted as untrusted data; combined input is capped
  at 22,000 UTF-16 units. `--out` must not exist. Exit 2 means failed or unknown: read the record's
  reason, never retry blindly.
- Before trusting an answer, read `<ledger>/opinions/<id>.json`: `model_observed`, `tool_evidence` with
  `tools: []` and `mcp_servers: []`, status completed. A refusal can still arrive as an "answer".
