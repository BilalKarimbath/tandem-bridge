# Session directory (read when the user asks "show the sessions", "who is around", "who am I paired with")

You are the renderer. Never paste the terminal table (`--format table`) into chat. Prefer:
```
<python> <checkout>/tandem.py --state-dir <ledger> discover --format markdown
```
and fall back to `discover --rows`, rendering it yourself. Read-only: it opens no `.key`, no
transcripts, no other ledgers, sends and creates nothing.

When rendering from `--rows`: a markdown table, pairs first (latest exchange first), then unlinked
sessions, then one row per folded group naming its count and the flag that expands it. Columns: Pair ·
Session (`agent`, first 8 hex in code, name) · Project (folder basename) · Status · Last seen (now, N
min, N h, N d) · Model / effort (Codex only) · Exchanges (count and age of the latest completed reply,
on the pair's first row). A session in several pairs gets "also in pair N" on later appearances. Mark
this session with ★. Never pre-select a peer; never call any row live.

Always print this legend under the table:

| Word | Meaning |
|---|---|
| busy / idle | Claude registry-reported state; Last seen is the report's age. Process presence is not checked |
| saved | Codex thread on disk; consumer unknown. A queued message may wait until a consumer runs |
| gone | seen only in this ledger; no registry or index row now. Process exit is not established |
| hint | caller-supplied identity; no registry or index row confirms it |
| relay | heuristic: a short-lived session carrying an envelope; not a peer-selection rule |
| worker | Codex thread created by `codex exec`; a disposable helper, not a conversation |
| auto-review | Codex's internal review thread |
| pair | completed, claimed round trip in this ledger; history, not authorization or liveness |

Flags: `--history` expands pairs, `--all` other unlinked sessions, `--internal` worker, relay and
auto-review rows. For a fresh session that needs addressing details, `discover --card <full UUID>`
prints both endpoints, the ledger, the helper command and the authorization sentence. There is no URL:
the address is ledger path + peer UUID + helper.

Then offer the next step in one sentence: which pair or session to brief, and that you will draft the
envelope for the user's approval.
