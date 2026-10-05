"""Public export stays explicit and rejects private content."""

import json
from pathlib import Path
import tempfile
import unittest

import build_public_export as public
import build_claude_plugin as plugin


class PublicExportTests(unittest.TestCase):
    def test_clean_export_contains_exact_allowlist_and_manifest(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / 'export'
            names = set(public.allowed_paths())
            self.assertEqual(public.export(target), len(names))
            actual = {p.relative_to(target).as_posix() for p in target.rglob('*') if p.is_file()}
            self.assertEqual(actual, names | {public.MANIFEST})
            self.assertEqual(public.scan_export(target), [])
            manifest = (target / public.MANIFEST).read_text(encoding='utf-8').splitlines()
            self.assertEqual(len(manifest), len(names))
            self.assertNotIn('state/messages', '\n'.join(manifest))
            self.assertNotIn('outbox/', '\n'.join(manifest))
            self.assertNotIn('hooks/', '\n'.join(manifest))
            self.assertNotIn('.public-export-private-words', actual)

    def test_nonempty_target_is_refused(self):
        with tempfile.TemporaryDirectory() as scratch:
            target = Path(scratch) / 'export'
            target.mkdir()
            (target / 'keep.txt').write_text('do not replace', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'empty directory'):
                public.export(target)
            self.assertEqual((target / 'keep.txt').read_text(encoding='utf-8'), 'do not replace')

    def test_privacy_scan_rejects_planted_identity_and_history(self):
        with tempfile.TemporaryDirectory() as scratch:
            folder = Path(scratch) / 'export'
            folder.mkdir()
            planted = folder / 'planted.txt'
            private_words = Path(scratch) / 'local-words'
            private_words.write_text('project-secret\n', encoding='utf-8')
            cases = (
                'project-secret',
                'C:/' + 'Users/sample/project',
                '/U' + 'sers/sample/project',
                '/ho' + 'me/sample/project',
                'person' + '@example.test',
                '12345678-1234-' + '4234-8234-123456789abc',
                'report-2026-' + '09-22.md',
            )
            for value in cases:
                with self.subTest(value=value[:8]):
                    planted.write_text(value, encoding='utf-8')
                    self.assertTrue(public.scan_export(folder, private_words))

    def test_license_metadata_agrees(self):
        pyproject = (public.ROOT / 'pyproject.toml').read_text(encoding='utf-8')
        self.assertRegex(pyproject, r'(?m)^license = "Apache-2\.0"$')
        manifest = json.loads((plugin.PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['license'], 'Apache-2.0')
        self.assertRegex((public.ROOT / 'LICENSE').read_text(encoding='utf-8')[:100],
                         r'^\s+Apache License\s+Version 2\.0')
        self.assertIn('Copyright 2026 Bilal Karimbath', (public.ROOT / 'NOTICE').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
