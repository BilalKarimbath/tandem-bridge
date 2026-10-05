import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import build_claude_plugin as package
from tandem_bridge import __version__, PROTOCOL_VERSION


class ClaudePluginTests(unittest.TestCase):
    def test_generated_plugin_matches_root_sources(self):
        package.run(check=True)
        expected = package.expected_files()
        for name, content in expected.items():
            with self.subTest(name=name):
                self.assertEqual((package.PLUGIN / name).read_bytes(), content)

    def test_manifests_and_version_agree(self):
        root = package.ROOT
        pyproject = (root / 'pyproject.toml').read_text(encoding='utf-8')
        self.assertEqual(re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1), __version__)
        manifest = json.loads((package.PLUGIN / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
        market = json.loads((root / '.claude-plugin/marketplace.json').read_text(encoding='utf-8'))
        self.assertEqual((manifest['name'], manifest['version']), ('tandem-bridge', __version__))
        self.assertEqual(market['name'], 'tandem-bridge')
        self.assertEqual(market['plugins'], [{'name': 'tandem-bridge', 'source': './plugins/claude-tandem'}])
        self.assertEqual((root / market['plugins'][0]['source']).resolve(), package.PLUGIN.resolve())

    def test_plugin_skill_binding_and_single_skill(self):
        skill = (package.PLUGIN / 'skills/tandem-bridge/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('${CLAUDE_PLUGIN_ROOT}/tandem.py', skill)
        self.assertNotIn('C:/GitHub/', skill)
        self.assertNotIn(package.PLACEHOLDER, skill)
        self.assertEqual([p.relative_to(package.PLUGIN).as_posix()
                          for p in (package.PLUGIN / 'skills').rglob('SKILL.md')],
                         ['skills/tandem-bridge/SKILL.md'])

    def test_plugin_reference_files_match_staged_source(self):
        staged = package.SKILL_REFERENCES
        expected = {p.relative_to(staged).as_posix(): p.read_bytes()
                    for p in staged.rglob('*') if p.is_file()} if staged.exists() else {}
        bundled = package.PLUGIN / 'skills/tandem-bridge/reference'
        actual = {p.relative_to(bundled).as_posix(): p.read_bytes()
                  for p in bundled.rglob('*') if p.is_file()} if bundled.exists() else {}
        self.assertEqual(actual, expected)

    def test_builder_copies_staged_reference_tree(self):
        with tempfile.TemporaryDirectory() as scratch:
            source = Path(scratch) / 'reference'
            source.mkdir()
            (source / 'directory.md').write_bytes(b'read on demand\n')
            with patch.object(package, 'SKILL_REFERENCES', source):
                files = package.expected_files()
            self.assertEqual(files['skills/tandem-bridge/reference/directory.md'], b'read on demand\n')

    def test_generated_text_follows_checkout_line_endings(self):
        source = package.SKILL_SOURCE.read_text(encoding='utf-8').replace('\r\n', '\n')
        with tempfile.TemporaryDirectory() as scratch:
            staged = Path(scratch) / 'SKILL.md'
            for newline in ('\n', '\r\n'):
                with self.subTest(newline=repr(newline)):
                    staged.write_bytes(source.replace('\n', newline).encode('utf-8'))
                    with patch.object(package, 'SKILL_SOURCE', staged):
                        files = package.expected_files()
                    self.assertIn(newline.encode(), files['skills/tandem-bridge/SKILL.md'])
                    self.assertIn(newline.encode(), files['.claude-plugin/plugin.json'])
                    if newline == '\n':
                        self.assertNotIn(b'\r\n', files['skills/tandem-bridge/SKILL.md'])
                        self.assertNotIn(b'\r\n', files['.claude-plugin/plugin.json'])

    def test_source_and_bundled_helper_report_versions_without_ledger(self):
        for root in (package.ROOT, package.PLUGIN):
            with self.subTest(root=root):
                result = subprocess.run([sys.executable, '-B', str(root / 'tandem.py'), 'version'],
                                        capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout),
                                 {'version': __version__, 'protocol': PROTOCOL_VERSION})
                self.assertNotIn('state_dir', result.stdout)

    def test_launchers_reject_older_python_before_import(self):
        for root in (package.ROOT, package.PLUGIN):
            with self.subTest(root=root), patch.object(sys, 'version_info', (3, 9)):
                with self.assertRaisesRegex(SystemExit, 'Python 3.10 or newer.*absolute'):
                    runpy.run_path(str(root / 'tandem.py'), run_name='__main__')
        with patch.object(sys, 'version_info', (3, 9)):
            with self.assertRaisesRegex(SystemExit, 'Python 3.10 or newer.*absolute'):
                runpy.run_module('tandem_bridge.__main__', run_name='__main__')

    def test_plugin_refuses_unmarked_project_instead_of_cache_fallback(self):
        with tempfile.TemporaryDirectory() as scratch:
            env = {**os.environ, 'TANDEM_STATE_DIR': ''}
            run = subprocess.run([sys.executable, '-B', str(package.PLUGIN / 'tandem.py'),
                                  'discover', '--format', 'json'], cwd=scratch, env=env,
                                 capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(run.returncode, 1)
            self.assertIn('No project marker', run.stderr)
            self.assertFalse((package.PLUGIN / 'state').exists())


if __name__ == '__main__':
    unittest.main()
