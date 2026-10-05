"""Explicitly install a checkout-bound skill; never overwrite differences."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import sys

START = '<!-- tandem-install-binding:start -->'
END = '<!-- tandem-install-binding:end -->'


def render(root, interpreter):
    text = (root / 'skills/tandem-bridge/SKILL.md').read_text(encoding='utf-8')
    if text.count(START) != 1 or text.count(END) != 1:
        raise ValueError('Expected exactly one installation binding block')
    start, end = text.index(START), text.index(END) + len(END)
    binding = (
        f'{START}\nUse interpreter `{Path(interpreter).as_posix()}` with helper '
        f'`{root.as_posix()}/tandem.py`.\nRead [{root.name}/INSTALL.md]({root.as_posix()}/INSTALL.md) for setup and\n'
        f'[{root.name}/README.md]({root.as_posix()}/README.md) for commands.\n'
        'Update this source binding after moving the checkout or interpreter.\n'
        f'No Tandem console executable is installed.\n{END}'
    )
    return text[:start] + binding + text[end:]


def rendered_files(root, interpreter):
    skill_dir = root / 'skills/tandem-bridge'
    files = {'SKILL.md': render(root, interpreter).encode('utf-8')}
    for path in sorted((skill_dir / 'reference').rglob('*')):
        if path.is_file():
            files[path.relative_to(skill_dir).as_posix()] = path.read_bytes()
    if len(files) == 1:
        raise ValueError('Skill references missing; install the complete checkout')
    return files


def install(root, destination, interpreter):
    files = rendered_files(root, interpreter)
    folder = destination.parent
    if folder.is_symlink() or (folder.exists() and any(path.is_symlink() for path in folder.rglob('*'))):
        raise ValueError('Existing skill folder contains a symlink; refusing to overwrite it.')
    present = {path.relative_to(folder).as_posix(): path for path in folder.rglob('*') if path.is_file()} if folder.exists() else {}
    if set(present) - set(files) or any(present[name].read_bytes() != content for name, content in files.items() if name in present):
        raise ValueError('Existing skill folder differs; refusing to overwrite it. Review it first.')
    for name, content in files.items():
        target = folder / name
        if name not in present:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(content)
    return {'installed': str(destination), 'files': sorted(files),
            'helper': str(root / 'tandem.py'), 'python': interpreter}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--print', dest='preview', action='store_true', help='Render to stdout without writing files')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    home = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser()
    try:
        if args.preview:
            files = rendered_files(root, sys.executable)
            text = files['SKILL.md'].decode('utf-8')
            sys.stdout.reconfigure(encoding='utf-8', newline='\n')
            sys.stdout.write(text)
            target = home / 'skills/tandem-bridge/SKILL.md'
            print(f'Preview: {target} | {len(text.splitlines())} lines | {len(files)} files | sha256 manifest:', file=sys.stderr)
            for name, content in files.items():
                print(f'{hashlib.sha256(content).hexdigest()}  {name}', file=sys.stderr)
            return
        print(json.dumps(install(root, home / 'skills/tandem-bridge/SKILL.md', sys.executable)))
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))


if __name__ == '__main__':
    main()
