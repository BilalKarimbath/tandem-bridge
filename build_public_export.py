"""Create a reviewed, source-only public copy from an explicit file allowlist."""

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import sys


ROOT = Path(__file__).resolve().parent
ALLOWLIST = ROOT / 'PUBLIC-ALLOWLIST.txt'
MANIFEST = 'PUBLIC-MANIFEST.sha256'
PRIVATE_WORDS = ROOT / '.public-export-private-words'


def allowed_paths():
    names = [line.strip() for line in ALLOWLIST.read_text(encoding='utf-8').splitlines()
             if line.strip() and not line.startswith('#')]
    if len(names) != len(set(names)) or MANIFEST in names:
        raise ValueError('Invalid or duplicate public allowlist entry')
    for name in names:
        path = PurePosixPath(name)
        denied = {'state', 'outbox', 'hooks', '__pycache__', '.git', 'build', 'dist'}
        if (path.is_absolute() or not path.parts or any(part in ('', '.', '..') for part in path.parts)
                or '\\' in name or path.as_posix() != name):
            raise ValueError(f'Invalid public allowlist path: {name}')
        if any(part in denied or part.endswith('.egg-info') for part in path.parts) or path.suffix in ('.pyc', '.exe', '.whl'):
            raise ValueError(f'Forbidden public source path: {name}')
        source = ROOT.joinpath(*path.parts)
        if not source.is_file() or any(item.is_symlink() for item in (source, *source.parents) if item != ROOT):
            raise ValueError(f'Missing or linked public source: {name}')
        if not source.resolve().is_relative_to(ROOT):
            raise ValueError(f'Public source escapes checkout: {name}')
    return names


def privacy_patterns(private_words_file=None):
    """Use portable checks plus optional local words that never ship."""
    patterns = [
        ('home path', re.compile(r'(?:[A-Za-z]:)?[\\/](?:Users|home)[\\/][^\\/\s]+', re.IGNORECASE)),
        ('email address', re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.IGNORECASE)),
        ('full UUID', re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b', re.IGNORECASE)),
        ('dated report filename', re.compile(r'\b[A-Za-z0-9_.-]+-2026-[0-9]{2}-[0-9]{2}[A-Za-z0-9_.-]*\.(?:md|txt|json)\b', re.IGNORECASE)),
    ]
    private_words_file = Path(private_words_file) if private_words_file is not None else PRIVATE_WORDS
    if private_words_file.is_file():
        for word in private_words_file.read_text(encoding='utf-8').splitlines():
            word = word.strip()
            if word and not word.startswith('#'):
                patterns.append(('local private word', re.compile(re.escape(word), re.IGNORECASE)))
    return patterns


def scan_export(folder, private_words_file=None):
    """Return privacy findings for filenames and UTF-8 contents in an export."""
    findings = []
    patterns = privacy_patterns(private_words_file)
    for path in sorted(folder.rglob('*')):
        if not path.is_file():
            continue
        name = path.relative_to(folder).as_posix()
        try:
            body = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            findings.append(f'{name}: non-UTF-8 file')
            continue
        for label, pattern in patterns:
            if pattern.search(name) or pattern.search(body):
                findings.append(f'{name}: {label}')
    return findings


def export(target):
    target = Path(target).expanduser()
    if target.is_symlink():
        raise ValueError('Public export target must not be a symlink')
    destination = target.resolve()
    if destination == ROOT or destination.is_relative_to(ROOT):
        raise ValueError('Public export target must be outside this repository')
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError('Public export target must be an empty directory')
    names = allowed_paths()
    target.mkdir(parents=True, exist_ok=True)
    hashes = []
    for name in names:
        source = ROOT.joinpath(*PurePosixPath(name).parts)
        output = target.joinpath(*PurePosixPath(name).parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
        hashes.append(f'{hashlib.sha256(output.read_bytes()).hexdigest()}  {name}')
    findings = scan_export(target)
    if findings:
        raise ValueError('Privacy scan failed:\n' + '\n'.join(findings))
    (target / MANIFEST).write_text('\n'.join(hashes) + '\n', encoding='utf-8', newline='\n')
    print(f'Public export: {len(names)} files; privacy scan clean; manifest {MANIFEST}')
    return len(names)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('target', help='New or empty folder outside the checkout')
    args = parser.parse_args()
    try:
        export(args.target)
    except (OSError, ValueError) as exc:
        sys.exit(str(exc))
