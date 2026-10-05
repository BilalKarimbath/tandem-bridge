"""Run with the wheel venv Python; never import the source checkout."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from importlib.metadata import distribution


def run():
    dist = distribution('tandem-bridge')
    assert not [e for e in dist.entry_points if e.group in ('console_scripts', 'gui_scripts')]
    assert not [f for f in dist.files if str(f).lower().endswith(('.exe', '.pyd', '.so', '.dll'))]
    command = [sys.executable, '-I', '-m', 'tandem_bridge']
    with tempfile.TemporaryDirectory(prefix='tandem-wheel-') as temp:
        cwd = Path(temp)
        env = dict(os.environ, TANDEM_STATE_DIR='', PYTHONPATH='')
        def call(*args):
            return subprocess.run([*command, *args], cwd=cwd, env=env,
                                  capture_output=True, text=True, encoding='utf-8')
        help_result = call('--help')
        assert help_result.returncode == 0, help_result.stderr
        # Home may itself contain ~/.tandem; use the drive root only for this read-only negative check.
        bare = Path(cwd.anchor)
        assert not (bare / '.git').exists() and not (bare / '.tandem').exists()
        missing = subprocess.run([*command, 'summary', '--format', 'json'], cwd=bare,
                                 env=env, capture_output=True, text=True, encoding='utf-8')
        assert missing.returncode == 1 and 'No project marker' in missing.stderr, missing
        ledger = cwd / 'ledger'
        result = call('--state-dir', str(ledger), 'summary', '--format', 'json')
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['state_dir'] == str(ledger.resolve())
        auth = call('--state-dir', str(ledger), 'authorization', 'status', '--policy-file', str(cwd / 'absent.json'))
        assert auth.returncode == 0, auth.stderr
        assert json.loads(auth.stdout)['policy_present'] is False
        assert not ledger.exists(), 'Read-only smoke must not create a ledger'
        resource = subprocess.run([sys.executable, '-I', '-c',
            "from importlib.resources import files; import json; "
            "print([json.loads(files('tandem_bridge').joinpath(n).read_text())['$schema'] "
            "for n in ('SCHEMA.json','SCHEMA-authorizations.json')])"],
            cwd=cwd, env=env, capture_output=True, text=True)
        assert resource.returncode == 0, resource.stderr
        print(json.dumps({'wheel_smoke': 'passed', 'python': sys.version.split()[0],
                          'module': 'tandem_bridge', 'outside_checkout': True}))


if __name__ == '__main__':
    run()
