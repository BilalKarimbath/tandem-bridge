"""Resolve existing vendor CLIs without a shell, installation or privilege changes."""
import os
from pathlib import Path
import shutil
import sys


class Executable(str):
    """A subprocess-compatible path with discovery provenance for event records."""
    def __new__(cls, path, source):
        value = super().__new__(cls, str(path))
        value.source = source
        return value


def known_locations(agent, platform, home, environ):
    if platform == 'win32':
        if agent == 'claude':
            return [home / '.local/bin/claude.exe']
        local = Path(environ.get('LOCALAPPDATA', str(home / 'AppData/Local')))
        return [local / 'Programs/OpenAI/Codex/bin/codex.exe']
    paths = [home / '.local/bin' / agent, Path('/usr/local/bin') / agent, Path('/usr/bin') / agent]
    if platform == 'darwin':
        paths.insert(1, Path('/opt/homebrew/bin') / agent)
    return paths


def executable(agent, override=None, *, platform=None):
    if agent not in ('claude', 'codex'):
        raise ValueError('Unknown CLI agent')
    platform = sys.platform if platform is None else platform

    def check(value, source):
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f'Executable not found: {path}; supply --executable')
        if platform == 'win32' and path.suffix.lower() in ('.cmd', '.bat', '.ps1'):
            raise ValueError('Windows shell shims are unsupported; supply the native vendor executable via --executable')
        if platform != 'win32' and not os.access(path, os.X_OK):
            raise ValueError(f'CLI file is not executable: {path}')
        return Executable(path, source)

    if override is not None:
        if not str(override).strip():
            raise ValueError('--executable must not be empty')
        return check(override, 'override')
    # Prefer a native Windows program over a similarly named npm shell shim.
    path = shutil.which(agent + '.exe') if platform == 'win32' else None
    path = path or shutil.which(agent)
    rejected = None
    if path:
        try:
            return check(path, 'PATH')
        except ValueError as exc:
            rejected = f'PATH candidate {path} rejected: {exc}'
    for path in known_locations(agent, platform, Path.home(), os.environ):
        if path.is_file():
            return check(path, 'known-location')
    detail = f'{rejected}; ' if rejected else ''
    raise ValueError(f'{detail}{agent} executable not found on PATH or known install locations; supply --executable')


def evidence(exe):
    return {'executable_path': str(exe) if exe is not None else None,
            'executable_source': getattr(exe, 'source', 'caller') if exe is not None else None}
