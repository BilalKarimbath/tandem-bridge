"""Create a reviewed, source-only public copy from an explicit file allowlist."""

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import zlib


ROOT = Path(__file__).resolve().parent
ALLOWLIST = ROOT / 'PUBLIC-ALLOWLIST.txt'
MANIFEST = 'PUBLIC-MANIFEST.sha256'
PRIVATE_WORDS = ROOT / '.public-export-private-words'
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'
PNG_PRIVATE_CHUNKS = {b'tEXt', b'iTXt', b'zTXt', b'eXIf'}


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


def scan_png(path):
    """Accept a complete PNG only when it has no text or EXIF chunks."""
    data = path.read_bytes()
    if not data.startswith(PNG_SIGNATURE):
        return ['invalid PNG signature']
    offset = len(PNG_SIGNATURE)
    chunk_number = 0
    findings = []
    while offset < len(data):
        if offset + 12 > len(data):
            return findings + ['truncated PNG chunk']
        length = int.from_bytes(data[offset:offset + 4], 'big')
        kind = data[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(data):
            return findings + ['truncated PNG chunk']
        payload = data[offset + 8:offset + 8 + length]
        checksum = int.from_bytes(data[end - 4:end], 'big')
        if zlib.crc32(kind + payload) != checksum:
            return findings + ['invalid PNG chunk checksum']
        if chunk_number == 0 and (kind != b'IHDR' or length != 13):
            return findings + ['invalid PNG header']
        if kind in PNG_PRIVATE_CHUNKS:
            findings.append(f'PNG text metadata {kind.decode("ascii")}')
        offset = end
        chunk_number += 1
        if kind == b'IEND':
            if length or offset != len(data):
                return findings + ['invalid PNG ending']
            return findings
    return findings + ['missing PNG ending']


def scan_export(folder, private_words_file=None):
    """Return privacy findings for filenames, UTF-8 contents and explicit PNGs."""
    findings = []
    patterns = privacy_patterns(private_words_file)
    for path in sorted(folder.rglob('*')):
        if not path.is_file():
            continue
        name = path.relative_to(folder).as_posix()
        for label, pattern in patterns:
            if pattern.search(name):
                findings.append(f'{name}: {label}')
        if path.suffix.lower() == '.png':
            findings.extend(f'{name}: {finding}' for finding in scan_png(path))
            continue
        try:
            body = path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            findings.append(f'{name}: non-UTF-8 file')
            continue
        for label, pattern in patterns:
            if pattern.search(body):
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
