import errno
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tandem_bridge import authorization as a, opinions as o, storage as s, tandem as t


class StoragePathsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_both_publishers_preserve_existing_complete_content(self):
        for publish, value in ((t.immutable_write, {'body': 'café 漢字'}), (o.publish_text, 'café 漢字\n')):
            dest = self.root / 'record'
            publish(dest, value)
            original = dest.read_bytes()
            with self.assertRaises(FileExistsError):
                publish(dest, value)
            self.assertEqual(dest.read_bytes(), original)
            self.assertEqual(list(self.root.glob('.pending-*')), [])
            dest.unlink()

    def test_no_fallback_when_links_are_unavailable(self):
        for publish, value in ((t.immutable_write, {'body': 'private'}), (o.publish_text, 'private')):
            dest = self.root / 'record'
            with patch.object(s.os, 'link', side_effect=OSError(errno.ENOTSUP, 'unsupported')):
                with self.assertRaisesRegex(OSError, 'no fallback'):
                    publish(dest, value)
            self.assertFalse(dest.exists())
            self.assertEqual(list(self.root.iterdir()), [])

    def test_flush_failure_never_publishes(self):
        dest = self.root / 'record'
        with patch.object(s.os, 'fsync', side_effect=OSError(errno.EIO, 'disk error')), patch.object(s.os, 'link') as link:
            with self.assertRaises(OSError):
                s.publish_text(dest, 'private')
            link.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_permission_failure_is_not_misreported_as_unsupported(self):
        original = PermissionError(errno.EACCES, 'denied', 'destination')
        with patch.object(s.os, 'link', side_effect=original):
            with self.assertRaises(PermissionError) as caught:
                s.publish_text(self.root / 'record', 'private')
        self.assertIs(caught.exception, original)
        self.assertEqual(original.errno, errno.EACCES)
        self.assertEqual(original.filename, 'destination')
        self.assertIn('no fallback', str(original))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_invalid_function_error_also_explains_no_fallback(self):
        original = OSError(errno.EINVAL, 'invalid function')
        with patch.object(s.os, 'link', side_effect=original):
            with self.assertRaisesRegex(OSError, 'no fallback') as caught:
                s.publish_text(self.root / 'record', 'private')
        self.assertIs(caught.exception, original)
        self.assertEqual(original.errno, errno.EINVAL)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_canonical_containment_is_not_string_prefix(self):
        project = self.root / 'alpha'
        other = self.root / 'alpha-other'
        project.mkdir()
        other.mkdir()
        self.assertFalse(a.within(a.local_path(other), a.local_path(project)))
        self.assertTrue(a.within(a.local_path(project), a.local_path(self.root)))
        for bad in ('relative', '//server/share', r'\\server\share', r'\\?\C:\file'):
            with self.assertRaises(ValueError):
                a.local_path(bad)

    def test_symlink_escape_resolves_before_containment(self):
        project = self.root / 'project'
        outside = self.root / 'outside'
        project.mkdir()
        outside.mkdir()
        alias = project / 'alias'
        try:
            alias.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            if os.name == 'nt':
                self.skipTest(f'Windows symlink creation unavailable: {exc.winerror}')
            raise
        self.assertEqual(a.local_path(alias), a.local_path(outside))
        self.assertFalse(a.within(a.local_path(alias), a.local_path(project)))

    @unittest.skipIf(os.name == 'nt', 'POSIX path semantics')
    def test_posix_colons_and_case_preservation(self):
        path = self.root / 'MiXeD:name'
        path.mkdir()
        self.assertEqual(a.local_path(path), str(path))
        self.assertFalse(a.within(str(path), str(self.root / 'mixed:name')))

    @unittest.skipUnless(os.name == 'nt', 'Windows path semantics')
    def test_windows_case_normalization(self):
        path = self.root / 'MiXeD'
        path.mkdir()
        self.assertEqual(a.local_path(path), a.local_path(str(path).swapcase()))
