"""Build or check the Claude plugin from the staged skill and root helper."""
import argparse
import json
from pathlib import Path
import sys

from tandem_bridge import __version__


ROOT = Path(__file__).resolve().parent
PLUGIN = ROOT / "plugins/claude-tandem"
SKILL_SOURCE = ROOT / "skills/claude/tandem-bridge/SKILL.md"
SKILL_REFERENCES = ROOT / "skills/claude/tandem-bridge/reference"
PLACEHOLDER = ('On this machine: `<checkout>` = `<checkout>`, '
               '`<python>` = `<python>`. This binding')
PLUGIN_BINDING = (
    'On this machine: `<checkout>` = `${CLAUDE_PLUGIN_ROOT}` '
    '(helper `${CLAUDE_PLUGIN_ROOT}/tandem.py`); choose `<python>` as '
    '`py -3` on Windows; elsewhere check `python3 --version` first. If below 3.10, '
    'look for `python3.13` through `python3.10`, Homebrew, then `uv python find`; '
    'offer a found absolute path, and ask only if none exists. This binding'
)
SOURCE_LAUNCH = 'cli(legacy_helper_dir=Path(__file__).resolve().parent)'
PLUGIN_LAUNCH = 'cli()'
SOURCE_LAUNCH_DOC = "Compatibility launcher: preserves this checkout's legacy ledger fallback."
PLUGIN_LAUNCH_DOC = 'Plugin launcher: requires a project marker or explicit ledger.'
ROOT_FILES = (
    'tandem.py', 'SCHEMA.json', 'SCHEMA-authorizations.json',
    'README.md', 'INSTALL.md', 'CHANGELOG.md', 'LICENSE', 'NOTICE', 'docs/REFERENCE.md', 'docs/session-directory.md',
    'docs/relay-prompt-revised-draft.md', 'docs/tandem-bridge.png', 'docs/install-connect.png',
)


def expected_files():
    source = SKILL_SOURCE.read_bytes().decode('utf-8')
    if source.count(PLACEHOLDER) != 1:
        raise ValueError('Staged Claude skill needs exactly one installer placeholder')
    skill = source.replace(PLACEHOLDER, PLUGIN_BINDING)
    result = {name: (ROOT / name).read_bytes() for name in ROOT_FILES}
    launcher = result['tandem.py']
    if launcher.count(SOURCE_LAUNCH.encode()) != 1:
        raise ValueError('Source launcher needs exactly one legacy fallback call')
    if launcher.count(SOURCE_LAUNCH_DOC.encode()) != 1:
        raise ValueError('Source launcher needs its legacy fallback description')
    result['tandem.py'] = (launcher.replace(SOURCE_LAUNCH.encode(), PLUGIN_LAUNCH.encode())
                          .replace(SOURCE_LAUNCH_DOC.encode(), PLUGIN_LAUNCH_DOC.encode()))
    for path in (ROOT / 'tandem_bridge').rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            relative = path.relative_to(ROOT).as_posix()
            result[relative] = path.read_bytes()
    result['skills/tandem-bridge/SKILL.md'] = skill.encode('utf-8')
    if SKILL_REFERENCES.exists():
        for path in sorted(SKILL_REFERENCES.rglob('*')):
            if path.is_file():
                result['skills/tandem-bridge/reference/' + path.relative_to(SKILL_REFERENCES).as_posix()] = path.read_bytes()
    manifest = {
        'name': 'tandem-bridge',
        'version': __version__,
        'description': 'Coordinate existing Claude and Codex sessions through a local ledger.',
        'author': {'name': 'Bilal Karimbath'},
        'license': 'Apache-2.0',
    }
    newline = '\r\n' if '\r\n' in source else '\n'
    result['.claude-plugin/plugin.json'] = (json.dumps(manifest, indent=2) + '\n').replace('\n', newline).encode('utf-8')
    return result


def run(check):
    expected = expected_files()
    present = {p.relative_to(PLUGIN).as_posix(): p for p in PLUGIN.rglob('*') if p.is_file()
               and '__pycache__' not in p.parts and p.suffix != '.pyc'} if PLUGIN.exists() else {}
    if check:
        differences = [name for name, content in expected.items()
                       if name not in present or present[name].read_bytes() != content]
        differences += sorted(set(present) - set(expected))
        if differences:
            raise ValueError('Claude plugin differs from source: ' + ', '.join(sorted(differences)))
        print(f'Claude plugin matches {len(expected)} source files')
        return
    extras = sorted(set(present) - set(expected))
    if extras:
        raise ValueError('Unexpected plugin files; inspect before building: ' + ', '.join(extras))
    for name, content in expected.items():
        destination = PLUGIN / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    print(f'Built Claude plugin: {len(expected)} files, version {__version__}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Compare package with its source, without writing')
    args = parser.parse_args()
    try:
        run(args.check)
    except (OSError, ValueError) as exc:
        sys.exit(str(exc))
