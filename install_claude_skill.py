"""Explicitly install a checkout-bound Claude skill; never overwrite differences."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys

PLACEHOLDER = ('On this machine: `<checkout>` = `<checkout>`, '
               '`<python>` = `<python>`. This binding')


def render(root, interpreter):
    text = (root / 'skills/claude/tandem-bridge/SKILL.md').read_text(encoding='utf-8')
    if text.count(PLACEHOLDER) != 1:
        raise ValueError('Expected exactly one Claude installation binding line')
    binding = (f'On this machine: `<checkout>` = `{root.as_posix()}`, '
               f'`<python>` = `{Path(interpreter).as_posix()}`. This binding')
    return text.replace(PLACEHOLDER, binding)


def install(root, destination, interpreter):
    text = render(root, interpreter)
    if destination.exists():
        if destination.read_text(encoding='utf-8') != text:
            raise ValueError('Existing skill differs; refusing to overwrite it. Review it first.')
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
    return {'installed': str(destination), 'helper': str(root / 'tandem.py'), 'python': interpreter}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--print', dest='preview', action='store_true', help='Render to stdout without writing files')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    home = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude').expanduser()
    target = home / 'skills/tandem-bridge/SKILL.md'
    try:
        if args.preview:
            text = render(root, sys.executable)
            sys.stdout.reconfigure(encoding='utf-8', newline='\n')
            sys.stdout.write(text)
            digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
            print(f'Preview: {target} | {len(text.splitlines())} lines | sha256 {digest}', file=sys.stderr)
            return
        print(json.dumps(install(root, target, sys.executable)))
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))


if __name__ == '__main__':
    main()
