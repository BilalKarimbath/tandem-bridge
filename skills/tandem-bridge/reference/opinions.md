# Tandem details: opinions

Read this when this part of the workflow applies. These rules are retained from the pre-trim skill.

## Ask a model for a second opinion

For an authorized design question or plan review, use
`opinion --model <exact-id> --agent codex --session <UUID> --question-file <path>
--context <explicit-input> --out <new-answer>` with the explicit shared state dir.
Read the README's opinion section first. A current passing `opinion probe` is
required; do not launch paid probes without user authorization or retry a refusal.
Codex's opinion backend is currently unavailable because its no-tools gate was not
established. Do not substitute read-only execution or route around that gate.

Review the record's observed model, runtime tool evidence, status and limitations.
Only completed validated outputs are answers; raw failed artifacts are evidence.
An opinion is advisory input, not truth or authorization. Never delegate project
edits through it or start opinion-of-opinion loops. Keep these records separate
from Tandem tasks and inspect them with `summary --opinions`.
