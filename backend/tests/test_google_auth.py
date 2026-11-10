"""OAuth handoff tests without Google calls or production data."""

import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.mac_api.main import create_app
from backend.mac_api.modules import google_auth


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = patch.dict(os.environ, {
            "MAC_GOOGLE_CLIENT_ID": "test-client",
            "MAC_GOOGLE_CLIENT_SECRET": "test-secret",
            "MAC_GOOGLE_ALLOWED_EMAIL": "mac@example.org",
            "MAC_GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
            "MAC_GOOGLE_FRONTEND_URL": "http://localhost:8501",
            "MAC_GOOGLE_TOKEN_FILE": f"{self.directory.name}/google.json",
            "MAC_API_KEY": "api-test-key",
        })
        self.config.start()
        self.addCleanup(self.config.stop)
        google_auth._pending.clear()
        google_auth._tickets.clear()
        google_auth._sessions.clear()
        self.client = TestClient(create_app(), follow_redirects=False)

    def test_api_requires_google_session_after_key(self):
        response = self.client.post('/api/v1/analytics/unknown', headers={'X-API-Key': 'api-test-key'}, json={})
        self.assertEqual(response.status_code, 401)
        self.assertIn('Google', response.json()['detail'])

    def test_callback_checks_state_and_account_and_redeems_once(self):
        start = self.client.get('/auth/google/start')
        self.assertEqual(start.status_code, 307)
        self.assertIn('access_type=offline', start.headers['location'])
        self.assertIn('drive.file', start.headers['location'])
        state = start.cookies['mac_oauth_state']
        invalid = self.client.get('/auth/google/callback', params={'code': 'code', 'state': 'wrong'})
        self.assertEqual(invalid.status_code, 400)

        class TokenResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'id_token': 'id', 'access_token': 'access', 'refresh_token': 'refresh'}

        with patch.object(google_auth.httpx, 'post', return_value=TokenResponse()), \
             patch.object(google_auth, '_google_identity', return_value={
                 'email': 'mac@example.org', 'email_verified': True,
             }), patch.object(google_auth, '_folder', return_value='folder-id') as folder:
            callback = self.client.get(
                '/auth/google/callback', params={'code': 'code', 'state': state},
                cookies={'mac_oauth_state': state},
            )
        self.assertEqual(callback.status_code, 307)
        folder.assert_called_once_with('access', None)
        self.assertEqual(google_auth._saved_credentials()['folder_id'], 'folder-id')
        ticket = callback.headers['location'].split('mac_login_ticket=')[1]
        headers = {'X-API-Key': 'api-test-key'}
        bad = self.client.post('/auth/google/redeem', params={'ticket': ticket})
        self.assertEqual(bad.status_code, 401)
        redeemed = self.client.post('/auth/google/redeem', params={'ticket': ticket}, headers=headers)
        self.assertEqual(redeemed.status_code, 200)
        again = self.client.post('/auth/google/redeem', params={'ticket': ticket}, headers=headers)
        self.assertEqual(again.status_code, 400)
        token = redeemed.json()['session_token']
        self.assertEqual(
            self.client.get('/auth/google/session', headers={**headers, 'Authorization': f'Bearer {token}'}).status_code,
            200,
        )
        self.assertEqual(self.client.get('/auth/google/session', headers=headers).status_code, 401)
        authenticated = self.client.post(
            '/api/v1/analytics/unknown',
            headers={**headers, 'Authorization': f'Bearer {token}'}, json={},
        )
        self.assertEqual(authenticated.status_code, 404)
        self.client.post('/auth/google/logout', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(
            self.client.get('/auth/google/session', headers={**headers, 'Authorization': f'Bearer {token}'}).status_code,
            401,
        )
        logged_out = self.client.post(
            '/api/v1/analytics/unknown',
            headers={**headers, 'Authorization': f'Bearer {token}'}, json={},
        )
        self.assertEqual(logged_out.status_code, 401)

    def test_other_google_account_is_rejected_without_storing_tokens(self):
        start = self.client.get('/auth/google/start')
        state = start.cookies['mac_oauth_state']

        class TokenResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'id_token': 'id', 'access_token': 'access', 'refresh_token': 'refresh'}

        with patch.object(google_auth.httpx, 'post', return_value=TokenResponse()), \
             patch.object(google_auth, '_google_identity', return_value={
                 'email': 'other@example.org', 'email_verified': True,
             }), patch.object(google_auth, '_folder') as folder:
            response = self.client.get(
                '/auth/google/callback', params={'code': 'code', 'state': state},
                cookies={'mac_oauth_state': state},
            )
        self.assertEqual(response.status_code, 403)
        folder.assert_not_called()
        self.assertEqual(google_auth._saved_credentials(), {})

    def test_drive_folder_is_created_or_reused(self):
        class FolderResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {'id': 'folder-id', 'trashed': False}

        with patch.object(google_auth.httpx, 'get', return_value=FolderResponse()) as get, \
             patch.object(google_auth.httpx, 'post', return_value=FolderResponse()) as post:
            self.assertEqual(google_auth._folder('access', None), 'folder-id')
            post.assert_called_once()
            self.assertEqual(post.call_args.kwargs['json']['mimeType'], 'application/vnd.google-apps.folder')
            self.assertEqual(google_auth._folder('access', 'folder-id'), 'folder-id')
            get.assert_called_once()
            post.assert_called_once()
