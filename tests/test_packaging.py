import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from scripts.build_portable import archive_tree


class PackagingTests(unittest.TestCase):
    def test_old_license_timestamp_preserves_file_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'runtime'
            root.mkdir()
            notice = root / 'LICENSE.txt'
            notice.write_bytes(b'upstream notice')
            os.utime(notice, (0, 0))
            archive = Path(directory) / 'runtime.zip'
            archive_tree(root, archive)
            with zipfile.ZipFile(archive) as bundle:
                self.assertEqual(bundle.read('runtime/LICENSE.txt'), b'upstream notice')
