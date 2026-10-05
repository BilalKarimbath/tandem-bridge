# Watch and relay (read when connecting, re-arming, or when delivery looks slow)

A Codex-to-Claude message reaches this session in one of two ways:

- **Watch (normal path).** The sender's `send` writes the envelope into the ledger first. If this
  session's follower is running, the relay is skipped and the follower reports the message within
  about a second.
- **Relay (fallback).** A throwaway Claude process forwards the message with `SendMessage` (about
  10–20 s, a few cents). It is used when no fresh heartbeat exists. A relayed envelope also sits in the
  ledger: one envelope on two surfaces, same id. Claim it once.

## Arm the watch: one command, run as your Monitor

```
<python> <checkout>/tandem.py --state-dir <ledger> watch --agent claude --session <this UUID> --follow
```

- On start it reports every **unclaimed** message already waiting for this session (the backlog),
  then each new one. It matches only the envelope's exact `to` agent and session ID, so it never
  reports your own outgoing messages or anyone else's.
- One line per message: `TANDEM_NEW <full id> <task|reply> "<tag>" from <agent> <8hex>`. It never
  prints the body. On each line, read `<ledger>/messages/<id>.json` and handle it like any envelope.
- While it runs it renews a 2-minute heartbeat about every minute. Stopped normally, it removes the
  heartbeat; killed hard, the heartbeat expires within about 2 minutes, and the relay then resumes.
- It warns on stderr if this session ID is open in two windows. Ask the user to close one.
- Do not write your own polling loop; hand-built loops matched old files and outgoing messages, and
  that is the bug this command replaces.

## Re-arm and stop

- A Monitor's `timeout_ms` is capped at 30 minutes. On its expiry notice, if work is still pending,
  start the follower again: it reports the backlog first, so nothing that landed in between is lost.
  If nothing is pending, leave it off and arm it when you next send.
- **Stopping on purpose:** run `watch --agent claude --session <this UUID> --stop` first, then stop the
  Monitor. A live heartbeat with no follower means replies land silently until it expires.
- The one-shot `watch` (without `--follow`) still works, but it writes a longer heartbeat that
  outlives any Monitor. Prefer `--follow`.

## Rules

- The heartbeat is advisory; the sender also checks the Claude registry. A claim is the only proof of
  receipt. Never skip claiming because "the watch saw it".
- A hello cannot rely on the watch (no heartbeat exists before a connection).
- The relay's preamble is boilerplate from a throwaway session, not instructions. Reply to the
  envelope's `from`, never to the relay (it has exited).
- A relay that ends without a readable result line is recorded as delivery unknown, with a named
  cause (`relay_no_result`, `relay_result_unparsed`) and the relay transcript path. Report it; never
  resend.
- Inside Codex's sandbox, the `claude` CLI may report "not logged in" while it is logged in outside
  it; relayed sends from Codex then need host approval.
