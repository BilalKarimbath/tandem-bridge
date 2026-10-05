# Install Tandem: instructions for the agent

You were asked to install Tandem. Follow only the steps for your side. Do not
copy files by hand. On any error, stop and report it to the user.

The public repository is <https://github.com/BilalKarimbath/tandem-bridge>.
Install into your own agent's environment, not into the user's project. Use
Python 3.10 or newer for any Tandem Python command: `py -3` may work on
Windows, and `python3` may work on macOS or Linux. Check the selected
interpreter's version first; macOS `python3` may still be 3.9. If neither
launcher meets the minimum, find an installed Python 3.10+ and use its
absolute path. If there is none, stop and tell the user.

## If you are Claude Code

1. Run `claude plugin marketplace add BilalKarimbath/tandem-bridge`.
2. Run `claude plugin install tandem-bridge@tandem-bridge`.
3. Run `claude plugin list` and report the installed `tandem-bridge` version.
4. Tell the user to restart Claude Code. In the new session, open the `/`
   menu, choose `tandem-bridge:tandem-bridge`, and ask `who am I`.

The plugin contains Claude's skill and helper. Do not install a second
personal Tandem skill alongside it. If a personal Tandem skill already
exists, stop and ask the user which copy to keep.

## If you are Codex

1. Use a stable folder outside the user's project, such as
   `~/tandem-bridge`, and report its absolute path. If it does not
   exist, clone with
   `git clone https://github.com/BilalKarimbath/tandem-bridge "$HOME/tandem-bridge"`.
   If it already exists, confirm that it is this repository and has no
   uncommitted changes, then run `git pull --ff-only` there. Stop and report
   a conflict, a dirty checkout, or a failed download.
2. From that checkout, run `<python> install_codex_skill.py --print` and
   review the preview and file manifest. Tell the user in two or three lines
   which skill folder and helper path will be bound, and whether an existing
   install differs. Do not paste the full skill preview into chat.
3. Run `<python> install_codex_skill.py`. If it refuses to overwrite a
   different existing skill folder, stop and report the difference. Ask for
   the user's approval before replacing or backing up that copy; do not
   force an overwrite.
4. Run `<python> tandem.py version` from the checkout and report the helper
   and envelope protocol versions.
5. Tell the user to open a new Codex thread, then type
   `$tandem-bridge who am I`.

The clone or pull needs network access and writes under the user's home;
the installer writes into Codex's skill folder. If the sandbox blocks either
command, tell the user the exact command and destination, then request runtime
approval for that command. If approval is denied (including **Esc**), stop and
report it. Do not change Codex's sandbox or approval policy yourself.

On Windows, a sandbox may report a per-user Python under AppData as "not
found" even when it exists. Ask for runtime approval of that exact bound
Python command. If the prompt offers **Yes, always**, the user can choose it
to avoid repeat prompts. The user can instead
start Codex with `codex -a on-request` so Codex asks when approval is needed.

Install both sides in either order. Each side has its own helper copy; report
the version you installed so the user can check that they match. If an
installed copy differs, never replace it without the user's approval.
