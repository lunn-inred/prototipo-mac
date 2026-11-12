import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.mac_api.main import create_app
from backend.mac_api.modules.backups import jobs, service
from backend.mac_api.core.maintenance import exclusive_operation


class BackupRoutesTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='mac-backup-api-')
        self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, MAC_API_KEY='backup-test', MAC_GOOGLE_CLIENT_ID='fake-google',
                         MAC_BACKUPS_DIR=self.directory.name, MAC_ANALYSES_DIR=str(Path(self.directory.name).parent / (Path(self.directory.name).name+'-analyses')))
        env.start(); self.addCleanup(env.stop)
        session = patch('backend.mac_api.modules.google_auth.valid_session', return_value=True)
        session.start(); self.addCleanup(session.stop)
        self.client = TestClient(create_app())
        self.headers = {'X-API-Key': 'backup-test', 'Authorization': 'Bearer fake-session'}

    def test_authentication_and_explicit_confirmation_are_required(self):
        self.assertEqual(self.client.get('/api/v1/backups').status_code, 401)
        with patch.object(jobs, 'start', return_value=dict(id='job', status='queued')) as start:
            payload = dict(file_id='backup-id', expected_sha256='a'*64)
            self.assertEqual(self.client.post('/api/v1/backups/restore', headers=self.headers, json=payload).status_code, 422)
            start.assert_not_called()
            response = self.client.post('/api/v1/backups/restore', headers=self.headers, json={**payload, 'confirm': True})
            self.assertEqual(response.status_code, 202)
            start.assert_called_once_with('restore', desktop=False, file_id='backup-id', expected_sha256='a'*64)

    def test_maintenance_blocks_normal_endpoints_but_not_job_polling(self):
        with exclusive_operation(), patch.object(jobs, 'status', return_value=dict(id='job', status='running')):
            response = self.client.get('/api/v1/athletes', headers=self.headers)
            self.assertEqual(response.status_code, 423)
            self.assertEqual(self.client.get('/api/v1/backups/jobs/job', headers=self.headers).status_code, 200)

    def test_interrupted_restore_blocks_data_access_after_restart(self):
        (Path(self.directory.name) / 'restore-pending.json').write_text('{}')
        response = self.client.get('/api/v1/athletes', headers=self.headers)
        self.assertEqual(response.status_code, 423)
        self.assertIn('interrompida', response.json()['detail'])

    def test_remote_target_is_never_used_for_backup(self):
        with patch.dict(os.environ, MAC_DB_TARGET='supabase'), patch.object(service, 'Drive') as drive:
            with self.assertRaisesRegex(ValueError, 'exclusivamente'):
                service.create_backup()
            drive.assert_not_called()
