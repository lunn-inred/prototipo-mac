"""Opt-in transactional integration tests, restricted to the disposable test DB."""
import os
import unittest
from datetime import date
from fastapi.testclient import TestClient
from backend.mac_api.main import create_app
from backend.mac_api.core.database import database_config


@unittest.skipUnless(os.getenv('MAC_TEST_DB_ENABLED') == '1', 'PostgreSQL local não habilitado')
class LocalPostgresTests(unittest.TestCase):
    def setUp(self):
        config = database_config()
        self.assertIn(config['host'], ('127.0.0.1', 'localhost', 'postgres-test'))
        self.assertEqual(config['dbname'], 'mac_test')
        self.client = TestClient(create_app())
        self.headers = {'X-API-Key': os.environ.get('MAC_API_KEY', '')}

    def test_status_migration_preserves_existing_rows(self):
        from pathlib import Path
        from backend.mac_api.core.database import database_write_connection
        migration = Path(__file__).resolve().parents[1] / 'migrations/20261016_athlete_status.sql'
        with database_write_connection() as database, database.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM public.atleta')
            before = cursor.fetchone()[0]
            cursor.execute('ALTER TABLE public.atleta DROP COLUMN status')
            cursor.execute(migration.read_text())
            cursor.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE status = 'ativo') FROM public.atleta")
            self.assertEqual(cursor.fetchone(), (before, before))
            # O teste da migração não deve alterar o estado das outras integrações.
            database.rollback()

    def test_combined_analysis_registration_and_file_failure_rollback(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from uuid import uuid4
        from backend.tests.test_analysis_archive import example_views
        from backend.mac_api.core.wire import encode, decode
        with TemporaryDirectory(prefix='mac-combined-postgres-') as directory, patch.dict(os.environ, MAC_ANALYSES_DIR=directory):
            athlete = self.client.post('/api/v1/athletes', json={'name': 'Teste integrado '+uuid4().hex[:8]}, headers=self.headers)
            self.assertEqual(athlete.status_code, 201, athlete.text)
            athlete_id = athlete.json()['id_atleta']
            payload = dict(athlete_id=athlete_id, athlete_name='Nome da interface', collected_at='2026-11-10',
                           mass=75., pain_score=0, observations='Teste', views=encode(example_views()))
            saved = self.client.post('/api/v1/thermography/analyses/register', json=payload, headers=self.headers)
            self.assertEqual(saved.status_code, 201, saved.text)
            self.assertEqual(decode(saved.json())['inserted_measurements'], 9)
            history = self.client.get(f'/api/v1/thermography?athlete_id={athlete_id}', headers=self.headers).json()
            self.assertEqual(len(history), 1)
            entries = decode(self.client.get(f'/api/v1/thermography/analyses?athlete_id={athlete_id}', headers=self.headers).json())
            self.assertEqual(len(entries), 1)
            duplicate = self.client.post('/api/v1/thermography/analyses/register', json=payload, headers=self.headers)
            self.assertEqual(duplicate.status_code, 409)
            with patch('numpy.save', side_effect=OSError('Falha simulada')):
                failed = self.client.post('/api/v1/thermography/analyses/register', json={**payload, 'collected_at': '2026-11-11'}, headers=self.headers)
            self.assertEqual(failed.status_code, 503)
            history = self.client.get(f'/api/v1/thermography?athlete_id={athlete_id}', headers=self.headers).json()
            self.assertEqual(len(history), 1)
            self.assertEqual(len(list(Path(directory).rglob('metadados.json'))), 1)

    def test_analysis_edit_move_overwrite_and_recovery(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from uuid import uuid4
        from backend.tests.test_analysis_archive import example_views
        from backend.mac_api.core.wire import encode, decode
        with TemporaryDirectory(prefix='mac-edit-postgres-') as directory, patch.dict(os.environ, MAC_ANALYSES_DIR=directory):
            ids = []
            for _ in range(2):
                response = self.client.post('/api/v1/athletes', json={'name': 'Edição '+uuid4().hex[:8]}, headers=self.headers)
                self.assertEqual(response.status_code, 201, response.text)
                ids.append(response.json()['id_atleta'])
            jump = self.client.post('/api/v1/jumps/collections', headers=self.headers,
                json={'athlete_id': ids[0], 'collected_at': '2026-11-10', 'cmj1': 39, 'maior_cmj': 39})
            self.assertEqual(jump.status_code, 201, jump.text)
            payload = dict(athlete_id=ids[0], athlete_name='Interface', collected_at='2026-11-10',
                           mass=75., pain_score=0, observations='Teste', views=encode(example_views()))
            original_response = self.client.post('/api/v1/thermography/analyses/register', json=payload, headers=self.headers)
            self.assertEqual(original_response.status_code, 201, original_response.text)
            original = decode(original_response.json())['analysis']
            def endpoint(entry):
                return f"/api/v1/thermography/analyses/{entry['athlete_id']}/{entry['collected_at']}/{entry['id']}"
            changed = self.client.put(endpoint(original), json={**payload, 'mass': 76,
                'expected_revision': original['created_at']}, headers=self.headers)
            self.assertEqual(changed.status_code, 200, changed.text)
            updated = decode(changed.json())['analysis']
            self.assertEqual(updated['id'], original['id'])
            stale = self.client.put(endpoint(original), json={**payload,
                'expected_revision': original['created_at']}, headers=self.headers)
            self.assertEqual(stale.status_code, 409, stale.text)
            self.assertEqual(stale.json()['detail']['code'], 'analysis_changed')
            destination = {**payload, 'athlete_id': ids[1], 'collected_at': '2026-11-11', 'mass': 80}
            target = self.client.post('/api/v1/thermography/analyses/register', json=destination, headers=self.headers)
            self.assertEqual(target.status_code, 201, target.text)
            moving = {**destination, 'mass': 77, 'expected_revision': updated['created_at']}
            conflict = self.client.put(endpoint(updated), json=moving, headers=self.headers)
            self.assertEqual(conflict.status_code, 409, conflict.text)
            self.assertEqual(conflict.json()['detail']['code'], 'analysis_date_conflict')
            self.assertEqual(len(list(Path(directory).rglob('metadados.json'))), 2)
            moved_response = self.client.put(endpoint(updated), json={**moving, 'overwrite': True}, headers=self.headers)
            self.assertEqual(moved_response.status_code, 200, moved_response.text)
            moved = decode(moved_response.json())['analysis']
            self.assertEqual(moved['id'], original['id'])
            self.assertEqual(moved['mass'], 77)
            self.assertEqual(self.client.get(f'/api/v1/thermography?athlete_id={ids[0]}', headers=self.headers).json(), [])
            records = self.client.get(f'/api/v1/thermography?athlete_id={ids[1]}', headers=self.headers).json()
            self.assertEqual(len(records), 1)
            self.assertEqual(len(list(Path(directory).rglob('metadados.json'))), 1)
            self.assertEqual(self.client.get(endpoint(updated), headers=self.headers).status_code, 404)
            with patch('numpy.save', side_effect=OSError('Falha simulada')):
                failed = self.client.put(endpoint(moved), json={**destination, 'collected_at': '2026-11-12',
                    'expected_revision': moved['created_at']}, headers=self.headers)
            self.assertEqual(failed.status_code, 503, failed.text)
            self.assertEqual(self.client.get(endpoint(moved), headers=self.headers).status_code, 200)
            self.assertEqual(self.client.get(f'/api/v1/thermography?athlete_id={ids[1]}', headers=self.headers).json(), records)
            self.assertFalse(list(Path(directory).rglob('.replacing_*')))
            jumps = self.client.get('/api/v1/jumps/collections', headers=self.headers).json()
            self.assertEqual(next(row for row in jumps if row['id_atleta'] == ids[0])['maior_cmj'], 39)

    def test_athlete_jump_and_thermal_transaction_roundtrip(self):
        from uuid import uuid4
        athlete = self.client.post('/api/v1/athletes', json={'name':f'Atleta integração {uuid4().hex[:8]}', 'position':'Meia'}, headers=self.headers)
        self.assertEqual(athlete.status_code, 201, athlete.text)
        athlete_id = athlete.json()['id_atleta']
        jump = {'athlete_id': athlete_id, 'collected_at':'2026-10-08', 'cmj1':30, 'maior_cmj':30}
        response = self.client.post('/api/v1/jumps/collections', json=jump, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        collections = self.client.get('/api/v1/jumps/collections', headers=self.headers).json()
        self.assertEqual(next(row for row in collections if row['id_atleta'] == athlete_id)['maior_cmj'], 30)
        response = self.client.put(f'/api/v1/jumps/collections/{athlete_id}/2026-10-08', json={**jump, 'cmj1':31, 'maior_cmj':31}, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.delete(f'/api/v1/jumps/collections/{athlete_id}/2026-10-08', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.text)
        thermal = {'athlete_id': athlete_id, 'collected_at':'2026-10-08', 'mass':75, 'pain_score':2, 'front_right':10, 'front_left':20, 'back_right':30, 'back_left':40}
        response = self.client.post('/api/v1/thermography', json=thermal, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        records = self.client.get(f'/api/v1/thermography?athlete_id={athlete_id}', headers=self.headers).json()
        self.assertEqual((records[0]['frente'], records[0]['verso']), (30, 70))
        response = self.client.post('/api/v1/thermography', json=thermal, headers=self.headers)
        self.assertEqual(response.status_code, 409, response.text)
        record = self.client.get(f'/api/v1/athletes/{athlete_id}', headers=self.headers).json()
        self.assertEqual(record['status'], 'ativo')
        for _ in range(2):
            response = self.client.patch(f'/api/v1/athletes/{athlete_id}/deactivate', headers=self.headers)
            self.assertEqual(response.status_code, 204, response.text)
        record = self.client.get(f'/api/v1/athletes/{athlete_id}', headers=self.headers).json()
        self.assertEqual(record['status'], 'inativo')
        after = self.client.get(f'/api/v1/thermography?athlete_id={athlete_id}', headers=self.headers).json()
        self.assertEqual(after, records)
        for _ in range(2):
            response = self.client.patch(f'/api/v1/athletes/{athlete_id}/reactivate', headers=self.headers)
            self.assertEqual(response.status_code, 204, response.text)
        record = self.client.get(f'/api/v1/athletes/{athlete_id}', headers=self.headers).json()
        self.assertEqual(record['status'], 'ativo')
        self.assertEqual(self.client.get(f'/api/v1/thermography?athlete_id={athlete_id}', headers=self.headers).json(), records)
        self.assertEqual(self.client.delete(f'/api/v1/athletes/{athlete_id}', headers=self.headers).status_code, 405)
