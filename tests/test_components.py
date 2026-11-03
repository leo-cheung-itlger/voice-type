import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from common import components


class ComponentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'portable.json').write_text('{"version":"1.0.0"}', encoding='utf-8')
        self.spec = {'name': 'cuda.zip', 'bytes': 4, 'sha256': 'a' * 64}
        self.manifest = {'version': '1.0.0', 'cuda': self.spec}
        self.base = patch.object(components, 'BASE_DIR', self.root)
        self.base.start()
        self.addCleanup(self.base.stop)
        components.job.update(status='idle')

    def get_plan(self, manifest):
        with patch.object(components, 'urlopen', return_value=io.BytesIO(json.dumps(manifest).encode())), patch.object(components, '_download') as download:
            result = components.plan()
            download.assert_not_called()
            return result

    def test_plan_reads_size_without_downloading_payload(self):
        self.assertEqual(self.get_plan(self.manifest)['bytes'], 4)

    def test_manifest_rejects_wrong_version_paths_hash_and_size(self):
        for field, value in [('name', '../cuda.zip'), ('name', 'C:cuda.zip'), ('sha256', 'bad'), ('bytes', -1)]:
            manifest = copy.deepcopy(self.manifest)
            manifest['cuda'][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.get_plan(manifest)
        manifest = copy.deepcopy(self.manifest)
        manifest['version'] = '0.9.0'
        with self.assertRaises(ValueError):
            self.get_plan(manifest)

    def test_manifest_rejects_inconsistent_parts(self):
        self.spec['parts'] = [{'name': 'cuda.part01', 'bytes': 3, 'sha256': 'b' * 64}]
        with self.assertRaises(ValueError):
            self.get_plan(self.manifest)

    def test_changed_manifest_requires_new_confirmation(self):
        with patch.object(components, 'plan', return_value={'sha256': 'b' * 64}), patch.object(components.threading, 'Thread') as thread:
            with self.assertRaises(ValueError):
                components.start('a' * 64)
            thread.assert_not_called()

    def test_corrupt_assembly_never_installs_or_changes_cpu(self):
        data = self.root / 'data'
        cache = data / 'components'
        cache.mkdir(parents=True)
        (cache / 'cuda.zip').write_bytes(b'bad!')
        with patch.object(components, 'DATA_DIR', data), patch.object(components, '_download'):
            components._run({'version': '1.0.0', 'base': 'https://example.invalid/', 'spec': self.spec})
        self.assertEqual(components.job['status'], 'error')
        self.assertFalse((self.root / 'runtime-cuda').exists())
