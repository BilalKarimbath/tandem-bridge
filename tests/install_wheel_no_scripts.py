"""Development check: install an inspected wheel without dependencies or scripts.

Disposable test environment only: invoke using its Python, then run wheel_smoke.py there.
This does not create a virtual environment or run any generated launcher.
"""
import configparser
from pathlib import Path
import subprocess
import sys
import sysconfig
import zipfile


def main():
    wheel = Path(sys.argv[1]).resolve(strict=True)
    with zipfile.ZipFile(wheel) as archive:
        for name in archive.namelist():
            assert not name.lower().endswith(('.exe', '.pyd', '.so', '.dll')), name
            assert '.data/scripts/' not in name, name
            if name.endswith('/entry_points.txt'):
                parser = configparser.ConfigParser()
                parser.read_string(archive.read(name).decode())
                assert not parser.has_section('console_scripts')
                assert not parser.has_section('gui_scripts')
    scripts = Path(sysconfig.get_path('scripts'))
    before = {p.name: p.read_bytes() for p in scripts.iterdir() if p.is_file()}
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', str(wheel)], check=True)
    after = {p.name: p.read_bytes() for p in scripts.iterdir() if p.is_file()}
    assert after == before, 'Installing Tandem changed the scripts directory'
    print('No native code or launcher entry points; Scripts/bin unchanged by installation.')


if __name__ == '__main__':
    main()
