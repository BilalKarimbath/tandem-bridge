# Tandem bridge changes

## 0.6.1

Added the Apache-2.0 license and a reviewed public export path. Runtime
behavior and the TANDEM/1 envelope protocol are unchanged.

## 0.6.0

Added compact open-work summary, reply acceptance on receive, FYI closure,
UTF-8 show, evidence fingerprints, per-session checkpoints and explicit
administrative close with a dry run. Generated reply body/envelope names and
Codex skill guidance for visual reviews and task closure.

## 0.5.2

The optional `connect --capability image-analysis|image-generation` flags add
sender-reported, current-session image hints to the existing read-only hello.
The hello remains a hello and grants no work or file access. Without flags,
the hello text and TANDEM/1 envelope format are unchanged.

## 0.5.1

Task creation records the local body source path and hash in the ledger, never
in the envelope. A reused task body file is refused; replies also refuse the
task's own source path or a copy with the same body hash. `status <id> --brief`
shows dispatch, claim and reply progress in one line, including whether a reply
is only prepared. The full JSON status remains the default.

## 0.5.0

Added `watch --follow` for exact-recipient backlog and new-message notices,
with heartbeat renewal tied to the foreground follower and a two-minute
expiry after a hard stop. Duplicate live Claude windows now trigger a PID
warning during identity discovery and follower startup. Reply preparation
names the file and the required send step. Skills and docs clarify duplicate
surfaces, `result.status`, and conversation-bound grants.

## 0.4.1

The revised Claude relay prompt is the default after 12 of 12 T3 messages reached the peer on one PC and one day (two per model/prompt cell). The result parser now accepts a valid final result line after prose, rejects result-marker text when a relay will launch, and names an unparseable result line while keeping delivery unknown. Watched sends can carry that text without a relay. This small sample is not a delivery guarantee; unknown delivery still has no automatic retry.

## 0.4.0

The Codex skill uses on-demand references; its installer copies and checks the full folder. The Claude plugin build bundles reference files. Relays name an end-turn/no-result cause; a revised prompt was added for testing.

## 0.3.2

Plugin launch refuses a checkout-cache ledger fallback. Python 3.9 gets a clear startup error, and whoami labels the session name and fields.

## 0.3.1

Project checkpoints accept symlinked ancestor aliases while refusing symlinked handoff paths.

## 0.3.0

Added the shared work-loop budget and evidence fields, project checkpoint and recap commands.

## 0.2.0

Packaged the Claude Code plugin and marketplace with one helper/protocol version.
