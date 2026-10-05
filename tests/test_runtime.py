import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tandem_bridge import runtime as r, tandem as t
from tandem_bridge import opinions as o
from tandem_bridge.limits import MAX_INPUT_UTF16_UNITS, utf16_units
from test_tandem import message


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.exe = self.root / 'vendor.exe'
        self.exe.write_text('test fixture, never executed')
        self.exe.chmod(0o700)

    def test_override_beats_path_and_invalid_override_never_falls_back(self):
        with patch.object(r.shutil, 'which') as which:
            result = r.executable('codex', str(self.exe))
            self.assertEqual(result.source, 'override')
            self.assertEqual(result, str(self.exe.resolve()))
            with self.assertRaises(ValueError):
                r.executable('codex', str(self.root / 'absent'))
            with self.assertRaises(ValueError):
                r.executable('codex', '')
            which.assert_not_called()

    def test_path_beats_known_location_and_fallback_is_reported(self):
        with patch.object(r.shutil, 'which', return_value=str(self.exe)), patch.object(r, 'known_locations') as known:
            self.assertEqual(r.executable('claude').source, 'PATH')
            known.assert_not_called()
        with patch.object(r.shutil, 'which', return_value=None), patch.object(r, 'known_locations', return_value=[self.exe]):
            self.assertEqual(r.executable('claude').source, 'known-location')

    def test_windows_shell_shim_rejected_without_launch(self):
        for suffix in ('.cmd', '.bat', '.ps1'):
            shim = self.root / ('codex' + suffix)
            shim.write_text('never execute')
            with self.assertRaisesRegex(ValueError, 'shell shims'):
                r.executable('codex', str(shim), platform='win32')

    def test_platform_fallbacks(self):
        self.assertIn(self.root / '.local/bin/claude.exe', r.known_locations('claude', 'win32', self.root, {}))
        self.assertIn(Path('/opt/homebrew/bin/codex'), r.known_locations('codex', 'darwin', self.root, {}))
        self.assertIn(self.root / '.local/bin/codex', r.known_locations('codex', 'linux', self.root, {}))

    def test_rejected_path_shim_allows_native_known_location(self):
        shim = self.root / 'claude.cmd'
        shim.write_text('never execute')
        with patch.object(r.shutil, 'which', side_effect=[None, str(shim)]), patch.object(r, 'known_locations', return_value=[self.exe]):
            self.assertEqual(r.executable('claude', platform='win32').source, 'known-location')
        with patch.object(r.shutil, 'which', side_effect=[None, str(shim)]), patch.object(r, 'known_locations', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'PATH candidate .*claude.cmd rejected'):
                r.executable('claude', platform='win32')

    @unittest.skipIf(os.name == 'nt', 'POSIX execute bit')
    def test_posix_non_executable_rejected(self):
        self.exe.chmod(0o600)
        with self.assertRaisesRegex(ValueError, 'not executable'):
            r.executable('codex', str(self.exe))

    def test_resolution_recorded_in_both_send_events(self):
        ledger = t.Ledger(self.root / 'ledger')
        exe = r.Executable(self.exe, 'override')
        msg = message()
        with patch.object(t.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'queued', '')):
            result = t.send(msg, ledger, exe, self.root, 1)
        self.assertEqual(result['executable_source'], 'override')
        for event in ledger.events(msg['id']):
            self.assertEqual(event['executable_source'], 'override')
            self.assertEqual(event['executable_path'], str(self.exe))

    def test_missing_executable_fails_before_ledger_mutation(self):
        ledger = t.Ledger(self.root / 'absent-ledger')
        source = self.root / 'message.json'
        t.immutable_write(source, message())
        from types import SimpleNamespace
        args = SimpleNamespace(command='send', message=str(source), timeout=None,
            executable=str(self.root / 'missing'), claude_home=str(self.root), dry_run=False)
        with self.assertRaises(ValueError):
            t.execute(args, ledger)
        self.assertFalse(ledger.root.exists())

    def test_shared_product_limit_counts_utf16(self):
        self.assertEqual(o.LIMIT, MAX_INPUT_UTF16_UNITS)
        self.assertEqual(utf16_units('a🙂'), 3)
        msg = message()
        msg['body'] = '🙂' * 11500  # Below body character cap, above transport unit cap.
        with self.assertRaisesRegex(ValueError, 'product limit'):
            t.validate(msg)
