import errno
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend.mac_api.modules.backups.directory_publication import DirectoryPublication


class DirectoryPublicationTests(unittest.TestCase):
    def test_keeps_mount_root_and_renames_only_within_volume(self):
        with TemporaryDirectory() as temp:
            root, stage = Path(temp)/'volume', Path(temp)/'overlay'
            root.mkdir(); stage.mkdir()
            (root/'old').write_text('original')
            (stage/'new').write_text('novo')
            inode = root.stat().st_ino
            original_replace = os.replace
            def mounted_replace(source, destination):
                source, destination = Path(source), Path(destination)
                if source == root or destination == root:
                    raise OSError(errno.EBUSY, 'mount point')
                if not source.is_relative_to(root) or not destination.is_relative_to(root):
                    raise OSError(errno.EXDEV, 'outro filesystem')
                return original_replace(source, destination)
            publication = DirectoryPublication(root)
            with patch('os.replace', side_effect=mounted_replace):
                publication.publish(stage)
                self.assertEqual((root/'new').read_text(), 'novo')
                publication.rollback()
            self.assertEqual((root/'old').read_text(), 'original')
            self.assertFalse((root/'new').exists())
            self.assertEqual(root.stat().st_ino, inode)
            self.assertEqual(list(root.iterdir()), [root/'old'])

    def test_partial_publication_failure_restores_already_moved_children(self):
        with TemporaryDirectory() as temp:
            root, stage = Path(temp)/'volume', Path(temp)/'stage'
            root.mkdir(); stage.mkdir()
            (root/'old').write_text('original')
            (stage/'new').write_text('novo')
            publication = DirectoryPublication(root)
            original_replace = os.replace
            def fail(source, destination):
                if Path(source).parent == publication.incoming:
                    raise OSError('falha simulada')
                return original_replace(source, destination)
            with patch('os.replace', side_effect=fail), self.assertRaises(OSError):
                publication.publish(stage)
            publication.rollback()
            self.assertEqual(list(root.iterdir()), [root/'old'])
