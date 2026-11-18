"""Persistência da referência basal; banco real somente mac_test optativo."""
import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from backend.mac_api.main import create_app
from backend.mac_api.modules.thermography import baseline, analysis_archive
from backend.tests.test_analysis_archive import example_views


class BaselineValidationTests(TestCase):
    def test_wrong_player_or_missing_analysis_never_opens_database(self):
        factory = MagicMock()
        with patch.object(analysis_archive, 'list_analyses', return_value=[]):
            with self.assertRaises(FileNotFoundError):
                baseline.set_baseline(2, uuid4(), connection_factory=factory)
        factory.assert_not_called()

    def test_remote_write_is_rejected(self):
        factory = MagicMock()
        with patch.dict(os.environ, MAC_DB_TARGET='supabase'):
            with self.assertRaises(ValueError):
                baseline.set_baseline(1, uuid4(), connection_factory=factory)
        factory.assert_not_called()


@skipUnless(os.getenv('MAC_TEST_DB_ENABLED') == '1', 'PostgreSQL descartável não habilitado')
class BaselinePostgresTests(TestCase):
    def test_http_change_and_reload_use_persistent_database_reference(self):
        from backend.mac_api.core.database import database_config, database_write_connection
        config = database_config()
        self.assertEqual(config['dbname'], 'mac_test')
        self.assertEqual(config['host'], '127.0.0.1')
        self.assertEqual(str(config['port']), '55432')
        migration = Path(__file__).resolve().parents[1]/'migrations/20261118_thermography_baseline.sql'
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute(migration.read_text(encoding='utf-8'))
            cursor.execute(migration.read_text(encoding='utf-8'))
            cursor.execute('INSERT INTO public.atleta(nome) VALUES(%s) RETURNING id_atleta', ('Teste basal '+uuid4().hex,))
            athlete = cursor.fetchone()[0]
        try:
            with TemporaryDirectory(prefix='mac-basal-') as directory, \
                 patch.dict(os.environ, MAC_ANALYSES_DIR=directory, MAC_API_KEY='baseline-test'):
                headers = {'X-API-Key': 'baseline-test'}
                entries = [analysis_archive.save_analysis(athlete_id=athlete, athlete_name='Teste',
                           collected_at=date(2026, 10, day), views=example_views()) for day in (1, 14)]
                path = f'/api/v1/thermography/baseline/{athlete}'
                for entry in entries:
                    response = TestClient(create_app()).put(path, headers=headers, json={'analysis_id': entry['id']})
                    self.assertEqual(response.status_code, 200, response.text)
                    fresh_client = TestClient(create_app())
                    self.assertEqual(fresh_client.get(path, headers=headers).json(), {'analysis_id': entry['id']})
                response = TestClient(create_app()).put(path, headers=headers, json={'analysis_id': str(uuid4())})
                self.assertEqual(response.status_code, 404)
                self.assertEqual(baseline.get_baseline(athlete)['analysis_id'], entries[-1]['id'])
        finally:
            with database_write_connection() as connection, connection.cursor() as cursor:
                cursor.execute('DELETE FROM public.termografia_basal WHERE id_atleta=%s', (athlete,))
                cursor.execute('DELETE FROM public.atleta WHERE id_atleta=%s', (athlete,))
