from pathlib import Path
import tempfile
import unittest
import os
import re
import subprocess
import sys
import install_codex_skill as installer
import install_claude_skill as claude_installer


class SkillInstallTests(unittest.TestCase):
    def test_codex_core_reference_links_exist(self):
        root = Path(__file__).resolve().parents[1]
        folder = root / 'skills/tandem-bridge'
        core = (folder / 'SKILL.md').read_text(encoding='utf-8')
        refs = set(re.findall(r'`(reference/[^`]+\.md)`', core))
        self.assertGreaterEqual(len(refs), 7)
        for ref in refs:
            self.assertTrue((folder / ref).is_file(), ref)
        self.assertLessEqual(len(core.splitlines()), 220)

    def test_preview_writes_nothing(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as scratch:
            result = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'install_codex_skill.py'), '--print'],
                env={**os.environ, 'CODEX_HOME': scratch}, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('## Receive', result.stdout)
            self.assertEqual(result.stdout, installer.render(root, sys.executable))
            self.assertIn('sha256', result.stderr)
            for name in installer.rendered_files(root, sys.executable):
                self.assertIn(name, result.stderr)
            self.assertEqual(list(Path(scratch).iterdir()), [])
            raw = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'install_codex_skill.py'), '--print'],
                env={**os.environ, 'CODEX_HOME': scratch}, capture_output=True)
            self.assertEqual(raw.stdout, installer.render(root, sys.executable).encode('utf-8'))

    def test_binding_preserves_workflow_and_refuses_customized_skill(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as scratch:
            dest = Path(scratch) / 'skill/SKILL.md'
            installer.install(root, dest, '/selected/python')
            text = dest.read_text(encoding='utf-8')
            self.assertIn('/selected/python', text)
            self.assertIn(root.as_posix() + '/tandem.py', text)
            self.assertIn('--relay-model', text)
            self.assertIn('## Receive', text)
            expected = installer.rendered_files(root, '/selected/python')
            self.assertEqual({p.relative_to(dest.parent).as_posix(): p.read_bytes()
                              for p in dest.parent.rglob('*') if p.is_file()}, expected)
            installer.install(root, dest, '/selected/python')
            dest.write_text(text + '\nUser customization\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
                installer.install(root, dest, '/selected/python')
            self.assertTrue(dest.read_text(encoding='utf-8').endswith('User customization\n'))

    def test_cli_installs_full_folder_into_temp_codex_home(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as scratch:
            result = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'install_codex_skill.py')],
                env={**os.environ, 'CODEX_HOME': scratch}, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            folder = Path(scratch) / 'skills/tandem-bridge'
            expected = installer.rendered_files(root, sys.executable)
            self.assertEqual({p.relative_to(folder).as_posix(): p.read_bytes()
                              for p in folder.rglob('*') if p.is_file()}, expected)
            again = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'install_codex_skill.py')],
                env={**os.environ, 'CODEX_HOME': scratch}, capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(again.returncode, 0, again.stderr)

    def test_modified_reference_and_extra_file_refuse_whole_folder(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as scratch:
            dest = Path(scratch) / 'skills/tandem-bridge/SKILL.md'
            installer.install(root, dest, '/selected/python')
            reference = next((dest.parent / 'reference').glob('*.md'))
            original = reference.read_bytes()
            reference.write_bytes(original + b'changed')
            with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
                installer.install(root, dest, '/selected/python')
            self.assertEqual(reference.read_bytes(), original + b'changed')
            reference.write_bytes(original)
            (dest.parent / 'local-note.txt').write_text('keep', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
                installer.install(root, dest, '/selected/python')

    def test_claude_preview_and_install(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as scratch:
            result = subprocess.run([sys.executable, '-X', 'utf8', str(root / 'install_claude_skill.py'), '--print'],
                env={**os.environ, 'CLAUDE_CONFIG_DIR': scratch}, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
            self.assertEqual(result.stdout, claude_installer.render(root, sys.executable).encode('utf-8'))
            self.assertIn(b'sha256', result.stderr)
            self.assertEqual(list(Path(scratch).iterdir()), [])
            dest = Path(scratch) / 'skills/tandem-bridge/SKILL.md'
            claude_installer.install(root, dest, '/selected/python')
            text = dest.read_text(encoding='utf-8')
            self.assertIn('`/selected/python`', text)
            self.assertIn(f'`{root.as_posix()}`', text)
            claude_installer.install(root, dest, '/selected/python')
            dest.write_text(text + '\nUser customization\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'refusing to overwrite'):
                claude_installer.install(root, dest, '/selected/python')
