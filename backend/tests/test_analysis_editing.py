from contextlib import contextmanager
from datetime import date
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from backend.mac_api.main import create_app
from backend.mac_api.core.wire import encode
from backend.mac_api.modules.thermography import analysis_archive as archive
from backend.mac_api.modules.thermography import analysis_registration as service
from backend.tests.test_analysis_archive import example_views


class AnalysisEditingTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='mac-editing-')
        self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, MAC_ANALYSES_DIR=self.directory.name, MAC_DB_TARGET='local', MAC_API_KEY='edit-test')
        env.start(); self.addCleanup(env.stop)
        self.values = dict(athlete_id=1, athlete_name='Original', collected_at=date(2026, 11, 1),
                           mass=75., pain_score=2, observations='Original', views=example_views())
        self.original = archive.save_analysis(**self.values)
        self.source = dict(athlete_id=1, collected_at=self.values['collected_at'], analysis_id=self.original['id'])
        self.database = MagicMock()
        self.cursor = self.database.cursor.return_value.__enter__.return_value
        self.committed = self.rolled_back = False

    @contextmanager
    def factory(self, fail=False):
        try:
            yield self.database
            if fail:
                raise RuntimeError('Falha no commit')
            self.committed = True
        except Exception:
            self.rolled_back = True
            raise

    def update(self, **overrides):
        values = {**self.values, **overrides}
        return service.replace_analysis(source=self.source, expected_revision=self.original['created_at'],
                                        connection_factory=self.factory, **values)

    def test_edit_preserves_id_and_replaces_without_history(self):
        self.cursor.fetchone.side_effect = [(1,), (1,), ('Nome atual',)]
        with patch.object(service, '_insert_collection', return_value=9):
            result = self.update(mass=80., observations='Editada')
        self.assertTrue(self.committed)
        self.assertEqual(result['analysis']['id'], self.original['id'])
        loaded = archive.load_analysis(**self.source)
        self.assertEqual(loaded['mass'], 80.)
        self.assertEqual(loaded['observations'], 'Editada')
        self.assertNotEqual(loaded['created_at'], self.original['created_at'])
        self.assertEqual(len(list(Path(self.directory.name).rglob('metadados.json'))), 1)
        self.assertFalse(list(Path(self.directory.name).rglob('.replacing_*')))

    def test_move_to_new_athlete_and_date(self):
        self.cursor.fetchone.side_effect = [(1,), (2,), (0,), ('Destino',)]
        with patch.object(service, '_insert_collection', return_value=9):
            result = self.update(athlete_id=2, collected_at=date(2026, 11, 2))
        self.assertEqual(archive.list_analyses(1), [])
        self.assertEqual(archive.list_analyses(2)[0]['id'], self.original['id'])
        self.assertEqual(result['analysis']['collected_at'], date(2026, 11, 2))
        deletions = [call for call in self.cursor.execute.call_args_list if call.args[0].startswith('DELETE')]
        self.assertEqual({call.args[1] for call in deletions}, {(1, date(2026, 11, 1)), (2, date(2026, 11, 2))})
        self.assertTrue(all("'termografia'" in call.args[0] for call in deletions))

    def test_conflict_preserves_both_analyses_until_confirmed(self):
        target = archive.save_analysis(**{**self.values, 'athlete_id': 2})
        self.cursor.fetchone.side_effect = [(1,), (2,), (1,)]
        with patch.object(service, '_insert_collection') as insert, self.assertRaises(service.AnalysisConflictError):
            self.update(athlete_id=2)
        insert.assert_not_called()
        self.assertEqual(archive.list_analyses(1)[0]['id'], self.original['id'])
        self.assertEqual(archive.list_analyses(2)[0]['id'], target['id'])
        self.assertFalse(any(call.args[0].startswith('DELETE') for call in self.cursor.execute.call_args_list))
        self.cursor.fetchone.side_effect = [(1,), (2,), (1,), ('Destino',)]
        with patch.object(service, '_insert_collection', return_value=9):
            self.update(athlete_id=2, overwrite=True)
        self.assertEqual(archive.list_analyses(1), [])
        self.assertEqual([entry['id'] for entry in archive.list_analyses(2)], [self.original['id']])

    def test_file_error_restores_original_and_destination(self):
        target = archive.save_analysis(**{**self.values, 'athlete_id': 2})
        self.cursor.fetchone.side_effect = [(1,), (2,), (1,), ('Destino',)]
        with patch.object(service, '_insert_collection', return_value=9), patch('numpy.save', side_effect=OSError('Falha')), self.assertRaises(OSError):
            self.update(athlete_id=2, overwrite=True)
        self.assertTrue(self.rolled_back)
        self.assertEqual(archive.list_analyses(1)[0]['created_at'], self.original['created_at'])
        self.assertEqual(archive.list_analyses(2)[0]['id'], target['id'])
        self.assertFalse(list(Path(self.directory.name).rglob('.replacing_*')))

    def test_commit_error_restores_the_original_files(self):
        self.cursor.fetchone.side_effect = [(1,), (1,), ('Original',)]
        with patch.object(service, '_insert_collection', return_value=9), self.assertRaises(RuntimeError):
            service.replace_analysis(source=self.source, expected_revision=self.original['created_at'],
                connection_factory=lambda: self.factory(fail=True), **self.values)
        self.assertTrue(self.rolled_back)
        self.assertEqual(archive.load_analysis(**self.source)['created_at'], self.original['created_at'])

    def test_stale_revision_never_overwrites(self):
        self.cursor.fetchone.return_value = (1,)
        with self.assertRaises(service.AnalysisChangedError):
            service.replace_analysis(source=self.source, expected_revision='outdated', overwrite=True,
                                     connection_factory=self.factory, **self.values)
        self.assertFalse(any(call.args[0].startswith('DELETE') for call in self.cursor.execute.call_args_list))

    def test_http_conflict_has_machine_readable_code(self):
        client = TestClient(create_app())
        headers = {'X-API-Key': 'edit-test'}
        payload = {**self.values, 'collected_at': self.values['collected_at'].isoformat(),
                   'views': encode(self.values['views']), 'expected_revision': self.original['created_at']}
        path = f'/api/v1/thermography/analyses/1/2026-11-01/{self.original["id"]}'
        with patch('backend.mac_api.modules.thermography.archive_routes.replace_analysis', side_effect=service.AnalysisConflictError('Uma análise do atleta já foi realizada nessa data. Deseja sobrescrevê-la?')):
            response = client.put(path, json=payload, headers=headers)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()['detail']['code'], 'analysis_date_conflict')
