"""CI-only wheel build/install check; no model calls or generated Tandem launchers."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import venv


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='tandem-ci-') as temp:
        scratch = Path(temp)
        dist = scratch / 'dist'
        subprocess.run([sys.executable, '-m', 'build', '--wheel', '--outdir', str(dist), str(root)], check=True)
        wheels = list(dist.glob('*.whl'))
        if len(wheels) != 1:
            raise RuntimeError('Expected exactly one freshly built wheel')
        environment = scratch / 'env'
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        for script, args in (
            ('install_wheel_no_scripts.py', [str(wheels[0])]),
            ('wheel_smoke.py', []),
        ):
            subprocess.run([str(python), '-I', str(root / 'tests' / script), *args],
                           cwd=scratch, check=True)


if __name__ == '__main__':
    main()
