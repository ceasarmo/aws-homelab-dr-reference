"""Synthetic validation tests for S3 upload-set selection; no AWS access."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('upload', Path(__file__).resolve().parents[1] / 'scripts/lib/upload.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def complete_set(self):
        folder = self.root / 'npm/biweekly/20260925T030000Z-example'
        folder.mkdir(parents=True)
        payload = folder / 'config.tar.gz'
        payload.write_bytes(b'synthetic')
        digest = hashlib.sha256(payload.read_bytes()).hexdigest()
        manifest = {'service': 'npm', 'cadence': 'biweekly',
                    'files': [{'name': payload.name, 'bytes': payload.stat().st_size, 'sha256': digest}]}
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        manifest_digest = hashlib.sha256((folder / 'manifest.json').read_bytes()).hexdigest()
        (folder / 'SHA256SUMS').write_text(digest + '  config.tar.gz\n' + manifest_digest + '  manifest.json\n')
        (folder / 'COMPLETE').write_text('synthetic\n')
        return folder

    def test_completed_set_has_only_expected_files(self):
        folder = self.complete_set()
        with patch.object(u, 'ROOT', self.root):
            cadence, files = u.verify_set('npm', folder)
        self.assertEqual(cadence, 'biweekly')
        self.assertEqual([item.name for item in files],
                         ['config.tar.gz', 'manifest.json', 'SHA256SUMS', 'COMPLETE'])

    def test_tampered_payload_is_rejected(self):
        folder = self.complete_set()
        (folder / 'config.tar.gz').write_bytes(b'changed')
        with patch.object(u, 'ROOT', self.root):
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                u.verify_set('npm', folder)

    def test_backup_symlink_is_rejected(self):
        folder = self.complete_set()
        link = self.root / 'npm/biweekly/link'
        link.symlink_to(folder)
        with patch.object(u, 'ROOT', self.root):
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                u.verify_set('npm', link)


if __name__ == '__main__':
    unittest.main()
