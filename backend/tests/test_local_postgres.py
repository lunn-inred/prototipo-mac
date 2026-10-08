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

    def test_athlete_jump_and_thermal_transaction_roundtrip(self):
        athlete = self.client.post('/api/v1/athletes', json={'name':'Atleta integração', 'position':'Meia'}, headers=self.headers)
        self.assertEqual(athlete.status_code, 201, athlete.text)
        athlete_id = athlete.json()['id_atleta']
        jump = {'athlete_id': athlete_id, 'collected_at':'2026-10-08', 'cmj1':30, 'maior_cmj':30}
        response = self.client.post('/api/v1/jumps/collections', json=jump, headers=self.headers)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.client.get('/api/v1/jumps', headers=self.headers).json()[-1]['maior_cmj'], 30)
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
        response = self.client.delete(f'/api/v1/athletes/{athlete_id}', headers=self.headers)
        self.assertEqual(response.status_code, 409, response.text)
