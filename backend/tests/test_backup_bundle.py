from datetime import date
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile, ZipInfo

from backend.mac_api.modules.backups import bundle, database_snapshot
from backend.mac_api.modules.thermography import analysis_archive
from backend.tests.test_analysis_archive import example_views


class BackupBundleTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='mac-bundle-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def analysis(self, root, identity=None, saved_at='2026-11-11T10:00:00+00:00', athlete=1, day=date(2026, 11, 1)):
        with patch.dict(os.environ, MAC_ANALYSES_DIR=str(root)):
            entry = analysis_archive.save_analysis(athlete_id=athlete, athlete_name='Teste', collected_at=day,
                mass=75., pain_score=0, views=example_views(), analysis_id=identity)
        path = root / f'atleta_{athlete}' / day.isoformat() / f'analise_{entry["id"]}' / 'metadados.json'
        metadata = json.loads(path.read_text())
        metadata['created_at'] = saved_at
        path.write_text(json.dumps(metadata), encoding='utf-8')
        return entry['id']

    def test_roundtrip_package_preserves_all_analysis_bytes(self):
        content = self.root / 'content'
        identity = self.analysis(content / 'analyses')
        (content / 'database').mkdir()
        (content / 'database/database.json').write_text('{"format": 1}')
        (content / 'database/0.csv').write_text('1,"Nome com vírgula, e acento"\n')
        target = self.root / 'backup.zip'
        original = bundle.package(content, target, str(uuid4()))
        output = self.root / 'output'
        recovered = bundle.unpack(target, output)
        self.assertEqual(original, recovered)
        self.assertEqual(bundle.index_analyses(content / 'analyses')[identity]['hashes'],
                         bundle.index_analyses(output / 'analyses')[identity]['hashes'])
        self.assertFalse(any('credentials' in name or '.env' in name for name in recovered['files']))

    def test_reconcile_keeps_equal_newer_and_local_only_and_accepts_newer_remote(self):
        local, remote = self.root / 'local', self.root / 'remote'
        identity = self.analysis(local)
        self.analysis(remote, identity)
        equal, kept = bundle.reconcile(bundle.index_analyses(local), bundle.index_analyses(remote))
        self.assertEqual(len(kept), 1)
        self.assertEqual(equal[identity]['path'].parent.parent.parent, local)
        self.analysis(local, day=date(2026, 11, 2))
        newer_root = self.root / 'newer'
        self.analysis(newer_root, identity, saved_at='2026-11-12T10:00:00+00:00')
        winners, kept = bundle.reconcile(bundle.index_analyses(local), bundle.index_analyses(newer_root))
        self.assertEqual(len(winners), 2)
        self.assertEqual(len(kept), 1)
        self.assertEqual(winners[identity]['revision'].day, 12)
        _, kept = bundle.reconcile(bundle.index_analyses(newer_root), bundle.index_analyses(remote))
        self.assertEqual(len(kept), 1)

    def test_equal_revision_with_different_content_and_duplicate_day_are_refused(self):
        local, remote = self.root / 'local', self.root / 'remote'
        identity = self.analysis(local)
        self.analysis(remote, identity, athlete=2)
        with self.assertRaisesRegex(ValueError, 'mesma revisão'):
            bundle.reconcile(bundle.index_analyses(local), bundle.index_analyses(remote))
        remote2 = self.root / 'remote2'
        self.analysis(remote2)
        with self.assertRaisesRegex(ValueError, 'mesmo atleta/data'):
            bundle.reconcile(bundle.index_analyses(local), bundle.index_analyses(remote2))

    def test_unfinished_files_are_not_silently_omitted(self):
        root = self.root / 'analyses'
        self.analysis(root)
        (root / '.pending-file').write_text('incompleto')
        with self.assertRaisesRegex(ValueError, 'incompletos'):
            bundle.index_analyses(root)

    def test_system_metadata_from_finder_or_explorer_does_not_break_analysis_index(self):
        root = self.root / 'analyses'
        identity = self.analysis(root)
        original = bundle.index_analyses(root)
        (root / '.DS_Store').write_bytes(b'Finder metadata')
        (original[identity]['path'] / 'Thumbs.db').write_bytes(b'Explorer metadata')
        (original[identity]['path'] / '._original.png').write_bytes(b'AppleDouble')
        self.assertEqual(bundle.index_analyses(root)[identity]['hashes'], original[identity]['hashes'])

    def test_unsafe_archive_paths_duplicates_and_symlinks_are_refused(self):
        for index, name in enumerate(('../outside.txt', '/absolute.txt', 'analyses/../outside', 'analyses\\evil', 'credentials/token.json')):
            with self.subTest(name=name):
                source = self.root / f'unsafe-{index}.zip'
                with ZipFile(source, 'w') as zipped:
                    zipped.writestr('manifest.json', '{}')
                    zipped.writestr(name, 'evil')
                with self.assertRaises(ValueError):
                    bundle.unpack(source, self.root / f'output-{index}')
        source = self.root / 'link.zip'
        info = ZipInfo('analyses/link')
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        with ZipFile(source, 'w') as zipped:
            zipped.writestr('manifest.json', '{}')
            zipped.writestr(info, '/etc/passwd')
        with self.assertRaises(ValueError):
            bundle.unpack(source, self.root / 'links')

    def test_corrupt_checksum_and_size_limit_are_refused(self):
        source = self.root / 'corrupt.zip'
        manifest = dict(format='mac-backup-v1', scope='public', id=str(uuid4()), created_at='2026-11-11T10:00:00Z',
            files={'database/database.json': dict(size=2, sha256='0'*64)})
        with ZipFile(source, 'w') as zipped:
            zipped.writestr('manifest.json', json.dumps(manifest))
            zipped.writestr('database/database.json', '{}')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            bundle.unpack(source, self.root / 'corrupt')
        with patch.dict(os.environ, MAC_BACKUP_MAX_EXTRACTED_BYTES='1'):
            with self.assertRaisesRegex(ValueError, 'tamanho'):
                bundle.unpack(source, self.root / 'large')

    def test_table_order_respects_references_and_refuses_cycles(self):
        state = dict(tables={'child': [], 'parent': []}, foreign_keys=[dict(child='child', parent='parent')])
        self.assertEqual(database_snapshot.ordered_tables(state), ['parent', 'child'])
        state['foreign_keys'].append(dict(child='parent', parent='child'))
        with self.assertRaises(ValueError):
            database_snapshot.ordered_tables(state)
