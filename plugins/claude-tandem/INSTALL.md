# Run Tandem from source

Tandem connects two live peers on one shared task. They cycle build, review
and fix until the done criterion, a block, or a stated budget ends the work;
the user remains the only authority. Use a direct user question for one-off
inquiries. Task envelopes can record advisory `--budget` and repeatable
`--evidence-required` values; the helper does not enforce a timer. For a
project handoff, use `checkpoint` and `recap` as described in README. Add
`.tandem/handoff/` to that project's `.gitignore` so local snapshots are not
committed with source files. For concurrent sessions, pass `--agent` and
`--session` to `checkpoint`; it writes a separate pointer for each session.

Install Python 3.10 or newer yourself and use an existing authenticated Claude
Code or Codex CLI. Check the interpreter rather than assuming an OS ships the
required version. Tandem does not require Node.js or Next.js; each vendor CLI
has its own installation requirements.

Clone the repository, then select Python 3.10 or newer:

```text
git clone https://github.com/BilalKarimbath/tandem-bridge
cd tandem-bridge
```

```powershell
# Windows
py -3 --version
py -3 tandem.py --help
```

```sh
# Linux or macOS
python3 --version
python3 tandem.py --help
```

There is no runtime pip install step. Select a working Python interpreter on
your machine; an absolute interpreter path is also valid. A Store alias or
sandbox denial is a separate launch issue, not a reason to change permissions
automatically. Report the actual denial and follow the host's approval process.
The interpreter and checkout must be readable and executable from the *current
agent session's* workspace and sandbox. A Python path that works from another
workspace may be denied here. A trusted-project entry alone does not
provide shell access to Python outside that workspace. Start the agent in a
workspace with access to both, or obtain the host's normal runtime approval
for the exact paths; do not
change filesystem permissions or Codex configuration to work around a denial.
On macOS, Xcode's `python3` may be 3.9 even when a suitable `uv` managed
interpreter exists outside `PATH`. For example, list candidates with
`find "$HOME/.local/share/uv/python" -name python3.12 -print`, choose the
installed binary's absolute path, and run `"<absolute-python3.12>" --version`
before `"<absolute-python3.12>" install_codex_skill.py`. Use that same path
for `install_claude_skill.py`; no shell configuration change is needed.
In PowerShell, quote absolute paths even when they contain spaces or parentheses:

```powershell
& "<python>" "<absolute-path-to-tandem.py>" --state-dir "<absolute-ledger>" discover --whoami
```

If the helper cannot run during an identity question, the Codex skill gives a
fast metadata-based identity and prospective ledger, marked as unverified by
the helper. A hello still requires access to the helper and interpreter.

From another working directory, pass the absolute path to `tandem.py`.
Alternatively, from the checkout run `python -m tandem_bridge` (where `python`
means your chosen interpreter). Do not add `-I` to this checkout module form:
isolated mode removes the checkout from the import path.

Use the same explicit absolute `--state-dir` on both peers. For example, from
the checkout, after substituting your project's absolute path:

```text
python tandem.py --state-dir <project>/.tandem/state discover
```

`discover` reads registry metadata; it neither creates a ledger nor proves a peer
is live. Confirm the recipient UUID and user authorization before sending.
See [the workflow](docs/REFERENCE.md#workflow) for create, claim, reply and status commands.
Use a new body file for each task and reply; `make` records its source path
only in the local ledger, and `reply` refuses the task's own body or an exact
copy. `status <id> --brief` shows dispatch, claim and reply progress without
the full event JSON. The project's `state/` and `provenance/` are local
bookkeeping and must stay ignored by Git.

For routine use, start with `summary --open`, inspect an item with `show <id>`,
and use `receive <id>` to claim it. A completed reply can be checked and then
claimed with `receive <reply-id> --accept`; the reply file becomes review
evidence. Use `make --fyi` for a read-only notice that needs only a claim.
Evidence files passed to `reply --evidence` are fingerprinted and rechecked
on receipt. `reply --body-stdin` explicitly reads a UTF-8 reply body and
generates safe outbox filenames. No command silently retries delivery.

The `close` command is for user-directed backlog housekeeping, not normal
acceptance. Preview with `close --before <ISO-date> --reason <text> --agent
<kind> --session <UUID> --dry-run`; omitting `--dry-run` records a closure
event for each listed task without deleting any body or outbox file. Do not
run it against a project ledger until its user has chosen the cutoff and reason.

## Watching a Claude session

Use one foreground Monitor command for that exact Claude session:

```text
python tandem.py --state-dir <project>/.tandem/state watch --agent claude --session <full-UUID> --follow
```

It prints `TANDEM_NEW <id> <kind> <JSON-quoted tag> from <agent> <8-hex ID>`
once per unclaimed addressed envelope, including backlog on startup. It renews
its own two-minute heartbeat and removes it on normal exit. After a hard kill,
relay fallback can be suppressed for up to about two minutes; a claim is still
the only proof of receipt. Keep this command in the foreground of the active
session, and do not run a separate hand-written folder Monitor. On Windows,
stopping a Monitor may hard-kill the follower without cleanup; run
`watch --stop` first when stopping it deliberately, then check for unclaimed
messages addressed to that UUID. Git Bash `timeout -s INT` does not reliably
interrupt native Windows Python. A reply may
also appear in chat when a relay ran: claim that envelope only once by ID.
Read its outcome from `result.status`. Conversation grants reset on restart.
If the helper warns that one Claude UUID has two live PIDs, close one window
before coordinating.

## Starting Codex for Tandem

Start the Codex CLI with `codex` when it works. On this Windows PC after the
0.157.0 update, plain `codex` exits with "host Job Object prevents daemon
detachment" and directs the user to `--no-daemon`. The user confirmed this
verbatim from plain PowerShell; it matches [openai/codex#48016](https://github.com/openai/codex/issues/48016).
A laptop restart did not fix it. Use `codex --no-daemon` to start a session
while that startup error is diagnosed. A Tandem ping completed with that flag
on 2026-09-25. The user's Mac also updated to 0.157.0 without this startup
problem; the observation is Windows-only so far. Two empty
`~/.codex/app-server-daemon/` lock files do not establish a stale
process. Do not stop other clients or delete daemon files merely because they
exist.
In a Windows observation on 2026-09-25, `codex queue`
without `--remote` started a turn within a second, before that thread was later
opened with `--no-daemon`. The message was read and answered but its Tandem FYI
envelope stayed unclaimed, because a ledger claim is a separate helper action.
If a queue report has no claim, inspect the target thread's rollout and ledger
before treating it as a daemon delivery failure. `--no-daemon` bypasses the
shared background server for that CLI invocation. `--remote` selects an
explicit app-server endpoint and is unnecessary for the observed local queue
route. The Mac route has not yet had the same live test.

Codex 0.157.0 also accepts `codex --remote <endpoint>` and
`codex queue --remote <endpoint>` for a separately started app-server. Tandem's
helper does not pass `--remote`, so it would need an explicit endpoint option
to queue into such a server; this route has not been tested here. A Windows
scheduled task could keep `codex app-server --listen ws://127.0.0.1:<port>`
running without an open terminal, but the WebSocket transport is experimental.
Bind a local experiment to `127.0.0.1`; nonlocal access needs TLS and WebSocket
authentication. Prefer the working `--no-daemon` path before adding a scheduled
server. See the [app-server documentation](https://learn.chatgpt.com/docs/app-server).

## Optional package installation

For an environment where you prefer an installed module, install a reviewed
pure-Python wheel using the selected interpreter:

```text
python -m pip install --no-deps <wheel-path>
python -m tandem_bridge --state-dir <absolute-ledger> discover
```

No `tandem` console command is installed. Outside a marked project the module
requires `--state-dir` or `TANDEM_STATE_DIR`; it never creates state in
site-packages. The source `tandem.py` wrapper retains its historical `state/`
fallback with a warning. Existing ledgers are not migrated.

## What gets written

Cloning writes source files. Python may create `__pycache__` when importing;
`python -B` suppresses that. Bridge operations write only their requested
ledger, outbox and output paths. Installing the optional wheel writes Python
modules, schemas and package metadata, with no runtime dependencies, native
extensions or generated Tandem launcher. Python, pip and optional developer
build/test tooling have their own executables; they are not bundled by Tandem.

Development-only `requirements.txt` installs validation oracles and their
dependencies. It is not needed to use Tandem. Build/test installations belong
in disposable environments; do not run wheel installation checks in your main
Python environment. No claim is made about antivirus behaviour.

## Agent skill

`python install_codex_skill.py` installs the staged Codex `SKILL.md` and its
`reference/` files, binding the core file to this checkout and interpreter.
Run `python install_codex_skill.py --print` first: stdout is the rendered core
skill and stderr lists every file with its SHA256. The installer compares the
whole destination folder and refuses to overwrite any differing or extra file.
Review those differences manually before updating; moving the
checkout or interpreter requires updating the binding. This does not install
Claude's skill, enroll peers or change approval settings. The separate staged
Other personal skills and hooks are separate from bridge setup.

### Install the Claude skill

The Claude Code plugin route bundles the helper and skill. Run:

```text
claude plugin marketplace add BilalKarimbath/tandem-bridge
claude plugin install tandem-bridge@tandem-bridge
```

For a later release, update the marketplace first, then the plugin, and restart
Claude Code:

```text
claude plugin marketplace update tandem-bridge
claude plugin update tandem-bridge@tandem-bridge
```

See [CHANGELOG.md](CHANGELOG.md) for version changes. To remove the plugin,
run `claude plugin uninstall tandem-bridge@tandem-bridge`.
Restart Claude Code after installation or update. The plugin's canonical helper
is `${CLAUDE_PLUGIN_ROOT}/tandem.py`, as resolved by the loaded skill. For a
GitHub install this is the versioned plugin cache; its absolute path changes on
`plugin update`. A local-directory marketplace may resolve to its source tree.
Use `py -3` on Windows. On macOS/Linux, check `python3 --version` before the
first helper call; if it is below 3.10, give the agent an absolute Python 3.10+
interpreter path. The plugin helper refuses an unmarked project without an
explicit `--state-dir`; keep ledgers under each project's `.tandem/state`,
never in the plugin cache. Do not keep this plugin and a
personal `~/.claude/skills/tandem-bridge/SKILL.md` installed together: they
would expose two Tandem skills. Codex still uses the checkout and
`install_codex_skill.py`; no Codex plugin is packaged in this phase.

The standalone Claude skill installer remains an alternative to the plugin.
Run `python install_claude_skill.py --print` with the chosen Python 3.10+
interpreter to preview the staged Claude skill bound to this checkout and
interpreter, then run `python install_claude_skill.py` to install it. The
destination is `~/.claude/skills/tandem-bridge/SKILL.md`, or under
`CLAUDE_CONFIG_DIR` when set. The installer refuses to overwrite a differing
copy; review and back it up before replacing it. The Xcode Python 3.9 is too old.

## Tested combinations

CI passed on Windows, Ubuntu and macOS with Python 3.10 and 3.13.
All six combinations passed the source-only suite, the full schema-parity suite,
and isolated wheel installation/module checks with no generated Tandem launcher.
This verifies the helper and package, not live vendor-CLI communication on every OS.
Filesystems must support atomic hard links; see the
[filesystem contract](docs/filesystem-portability.md).

To review a skill upgrade, run the corresponding installer with `--print` and
compare the rendered text with the installed skill. Preserve local customizations.
After reviewing, rename the old skill file as a backup and rerun the installer,
or merge the reviewed changes manually. Preview writes nothing.
