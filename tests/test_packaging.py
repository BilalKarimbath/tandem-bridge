import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from importlib.resources import files

from tandem_bridge import tandem as t
from test_tandem import message


class PackagingTests(unittest.TestCase):
    def test_relay_instructions_do_not_depend_on_checkout_or_install_path(self):
        msg = message()
        msg['to']['agent'] = 'claude'
        with patch.object(t, 'recipient_name', return_value='peer'):
            _, prompt, _ = t.transport(msg, 'claude', Path.home(), relay_prompt='legacy')
        preamble = prompt.split('Routing header and envelope follow:', 1)[0]
        self.assertNotIn(t.HERE.as_posix(), preamble)
        self.assertNotRegex(preamble, r'(?:[A-Za-z]:[/\\]|/(?:home|Users|usr|opt)/)')
        self.assertIn("receiver's tandem-bridge skill", preamble)

    def test_both_schemas_are_package_resources_and_match_legacy(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('SCHEMA.json', 'SCHEMA-authorizations.json'):
            packaged = json.loads(files('tandem_bridge').joinpath(name).read_text(encoding='utf-8'))
            self.assertEqual(packaged, json.loads((root / name).read_text(encoding='utf-8')))

    def test_installed_resolution_has_no_package_ledger_fallback(self):
        bare = Path(Path.cwd().anchor)
        with self.assertRaisesRegex(ValueError, 'supply --state-dir'):
            t.resolve_state_dir(cwd=bare, environ={})

    def test_legacy_resolution_retains_original_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path, source = t.resolve_state_dir(cwd=Path(root.anchor), environ={}, helper_dir=root)
            self.assertEqual((path, source), ((root / 'state').resolve(), 'fallback'))
            self.assertFalse(path.exists())

    def test_legacy_launcher_from_another_directory(self):
        wrapper = Path(__file__).resolve().parents[1] / 'tandem.py'
        with tempfile.TemporaryDirectory() as temp:
            ledger = Path(temp) / 'ledger'
            env = dict(os.environ, TANDEM_STATE_DIR='')
            result = subprocess.run([sys.executable, str(wrapper), '--state-dir', str(ledger),
                'summary', '--format', 'json'], cwd=temp, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['state_dir'], str(ledger.resolve()))
            self.assertFalse(ledger.exists())
