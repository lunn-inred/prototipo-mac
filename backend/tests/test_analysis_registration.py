from contextlib import contextmanager
from datetime import date
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from backend.mac_api.main import create_app
from backend.mac_api.core.wire import encode, decode
from backend.mac_api.modules.thermography import analysis_archive as archive
from backend.mac_api.modules.thermography import analysis_registration as registration
from backend.mac_api.modules.thermography.thermography_service import DuplicateThermographyError
from backend.tests.test_analysis_archive import example_views


class CombinedRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='mac-combined-analysis-test-')
        self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, MAC_ANALYSES_DIR=self.directory.name, MAC_DB_TARGET='local', MAC_API_KEY='combined-test')
        env.start(); self.addCleanup(env.stop)
        self.values = dict(athlete_id=123, athlete_name='Nome vindo da interface',
                           collected_at=date(2026, 11, 10), mass=75., pain_score=2,
                           observations='Teste', views=example_views())
        self.database = MagicMock()
        self.database.cursor.return_value.__enter__.return_value.fetchone.return_value = ('Nome do banco',)
        self.committed = False
        self.rolled_back = False

    @contextmanager
    def factory(self, *, fail_commit=False):
        try:
            yield self.database
            if fail_commit:
                raise RuntimeError('Falha simulada no commit')
            self.committed = True
        except Exception:
            self.rolled_back = True
            raise

    def test_success_stores_files_and_measures_with_identical_pixel_counts(self):
        with patch.object(registration, '_insert_collection', return_value=9) as insert:
            result = registration.register_analysis(**self.values, connection_factory=self.factory)
        self.assertTrue(self.committed)
        self.assertEqual(result['inserted_measurements'], 9)
        saved = archive.load_analysis(123, self.values['collected_at'], result['analysis']['id'])
        self.assertEqual(saved['athlete_name'], 'Nome do banco')
        measurements = insert.call_args.kwargs['measurements']
        for view, suffix in [('front', 'FRENTE'), ('back', 'VERSO')]:
            for side, label in [('left', 'ESQUERDA'), ('right', 'DIREITA')]:
                expected = saved['metadata']['views'][view]['metrics'][side]['hot_pixels']
                self.assertEqual(measurements[f'PERNA_{label}_{suffix}'], expected)
            self.assertEqual(measurements[f'SOMA_{suffix}'], sum(saved['metadata']['views'][view]['metrics'][side]['hot_pixels'] for side in ('left', 'right')))

    def test_file_failure_rolls_back_database_and_keeps_existing_analyses(self):
        old = archive.save_analysis(**{**self.values, 'collected_at': date(2026, 11, 9)})
        with patch.object(registration, '_insert_collection', return_value=9), \
             patch('numpy.save', side_effect=OSError('Falha simulada')):
            with self.assertRaises(OSError):
                registration.register_analysis(**self.values, connection_factory=self.factory)
        self.assertTrue(self.rolled_back)
        self.assertFalse(self.committed)
        self.assertEqual([entry['id'] for entry in archive.list_analyses(123)], [old['id']])
        self.assertFalse(list(Path(self.directory.name).rglob('.pending_*')))

    def test_commit_failure_removes_only_the_new_analysis(self):
        old = archive.save_analysis(**{**self.values, 'collected_at': date(2026, 11, 9)})
        with patch.object(registration, '_insert_collection', return_value=9), self.assertRaises(RuntimeError):
            registration.register_analysis(**self.values, connection_factory=lambda: self.factory(fail_commit=True))
        self.assertTrue(self.rolled_back)
        self.assertEqual([entry['id'] for entry in archive.list_analyses(123)], [old['id']])

    def test_duplicate_does_not_create_files(self):
        with patch.object(registration, '_insert_collection', side_effect=DuplicateThermographyError('duplicada')):
            with self.assertRaises(DuplicateThermographyError):
                registration.register_analysis(**self.values, connection_factory=self.factory)
        self.assertTrue(self.rolled_back)
        self.assertEqual(archive.list_analyses(123), [])

    def test_archive_only_duplicate_requires_confirmation_without_inserting_measures(self):
        old = archive.save_analysis(**self.values)
        with patch.object(registration, '_insert_collection') as insert:
            with self.assertRaises(registration.AnalysisConflictError):
                registration.register_analysis(**self.values, connection_factory=self.factory)
        insert.assert_not_called()
        self.assertEqual([entry['id'] for entry in archive.list_analyses(123)], [old['id']])

    def test_invalid_images_do_not_open_database(self):
        values = {**self.values, 'views': {'front': example_views()['front']}}
        factory = MagicMock()
        with self.assertRaises(ValueError):
            registration.register_analysis(**values, connection_factory=factory)
        factory.assert_not_called()

    def test_endpoint_saves_both_and_rejects_missing_required_fields(self):
        client = TestClient(create_app())
        headers = {'X-API-Key': 'combined-test'}
        payload = {**self.values, 'collected_at': self.values['collected_at'].isoformat(), 'views': encode(self.values['views'])}
        with patch.object(registration, 'database_write_connection', self.factory), \
             patch.object(registration, '_insert_collection', return_value=9):
            response = client.post('/api/v1/thermography/analyses/register', json=payload, headers=headers)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(decode(response.json())['inserted_measurements'], 9)
        for field in ('mass', 'pain_score'):
            invalid = {**payload}; invalid.pop(field)
            self.assertEqual(client.post('/api/v1/thermography/analyses/register', json=invalid, headers=headers).status_code, 422)

    def test_endpoint_never_uses_remote_target(self):
        with patch.dict(os.environ, MAC_DB_TARGET='supabase'), patch.object(registration, 'database_write_connection') as factory:
            with self.assertRaisesRegex(ValueError, 'banco local'):
                registration.register_analysis(**self.values)
            factory.assert_not_called()
