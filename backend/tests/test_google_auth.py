"""OAuth handoff tests without Google calls or production data."""

import os
import unittest
import httpx
from fastapi import HTTPException
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

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
            "MAC_GOOGLE_BACKUP_FOLDER_ID": "folder-id",
            "MAC_GOOGLE_REDIRECT_URI": "http://localhost:8000/auth/google/callback",
            "MAC_GOOGLE_FRONTEND_URL": "http://localhost:8501",
            "MAC_GOOGLE_TOKEN_FILE": f"{self.directory.name}/google.json",
            "MAC_GOOGLE_DESKTOP_TOKEN_FILE": f"{self.directory.name}/desktop.json",
            "MAC_GOOGLE_DESKTOP_REMEMBER_FILE": f"{self.directory.name}/desktop-remember.json",
            "MAC_API_KEY": "api-test-key",
        })
        self.config.start()
        self.addCleanup(self.config.stop)
        google_auth._pending.clear()
        google_auth._tickets.clear()
        google_auth._sessions.clear()
        google_auth._desktop_pending.clear()
        google_auth._desktop_results.clear()
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
        folder.assert_called_once_with('access')
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

    def test_drive_folder_uses_configured_id_and_never_creates_a_folder(self):
        class FolderResponse:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {'id': 'folder-id', 'trashed': False,
                        'mimeType': 'application/vnd.google-apps.folder',
                        'capabilities': {'canAddChildren': True}}

        with patch.object(google_auth.httpx, 'get', return_value=FolderResponse()) as get, \
             patch.object(google_auth.httpx, 'post', return_value=FolderResponse()) as post:
            google_auth._save_credentials({'folder_id': 'old-folder', 'refresh_token': 'private'})
            self.assertEqual(google_auth._folder('access'), 'folder-id')
            get.assert_called_once()
            self.assertEqual(get.call_args.args[0], 'https://www.googleapis.com/drive/v3/files/folder-id')
            self.assertIn('capabilities(canAddChildren)', get.call_args.kwargs['params']['fields'])
            post.assert_not_called()

    def test_desktop_handoff_uses_browser_then_returns_session_to_app(self):
        client = TestClient(create_app(), base_url="http://localhost:8000", follow_redirects=False)
        headers = {"X-API-Key": "api-test-key"}
        self.assertEqual(client.post('/auth/google/desktop/start').status_code, 401)
        started = client.post('/auth/google/desktop/start', headers=headers)
        self.assertEqual(started.status_code, 200)
        data = started.json()
        query = parse_qs(urlparse(data['authorization_url']).query)
        self.assertEqual(query['redirect_uri'], ['http://localhost:8000/auth/google/callback'])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        state = query['state'][0]
        self.assertEqual(client.post('/auth/google/desktop/poll', json={'poll_token': data['poll_token']}, headers=headers).status_code, 202)

        class TokenResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'id_token': 'id', 'access_token': 'access', 'refresh_token': 'refresh'}

        with patch.object(google_auth.httpx, 'post', return_value=TokenResponse()) as exchange, \
             patch.object(google_auth, '_google_identity', return_value={
                 'email': 'mac@example.org', 'email_verified': True,
             }), patch.object(google_auth, '_folder', return_value='folder-id'):
            callback = client.get('/auth/google/callback', params={'code': 'code', 'state': state})
        self.assertEqual(callback.status_code, 200)
        self.assertIn('Volte à janela do MAC', callback.text)
        self.assertIn('code_verifier', exchange.call_args.kwargs['data'])
        self.assertNotIn('mac_login_ticket', callback.text)
        completed = client.post('/auth/google/desktop/poll', json={'poll_token': data['poll_token']}, headers=headers)
        self.assertEqual(completed.status_code, 200)
        token = completed.json()['session_token']
        self.assertTrue(google_auth.valid_session(token))
        google_auth._sessions.clear()  # Simula reinício da API sem perder o arquivo privado.
        self.assertEqual(client.get('/auth/google/session', headers={**headers, 'Authorization': f'Bearer {token}'}).status_code, 200)
        self.assertNotIn(token, google_auth._remember_path().read_text(encoding='utf-8'))
        client.post('/auth/google/logout', headers={'Authorization': f'Bearer {token}'})
        google_auth._sessions.clear()
        self.assertFalse(google_auth.valid_session(token))
        self.assertFalse(google_auth._remember_path().exists())
        self.assertEqual(client.post('/auth/google/desktop/poll', json={'poll_token': data['poll_token']}, headers=headers).status_code, 410)

    def test_missing_or_invalid_folder_id_does_not_use_saved_id_or_call_google(self):
        google_auth._save_credentials({'folder_id': 'old-folder'})
        for folder_id in ('', '   ', 'https://drive.google.com/drive/folders/folder-id', '../folder', 'a' * 256):
            with self.subTest(folder_id=folder_id), patch.dict(os.environ, MAC_GOOGLE_BACKUP_FOLDER_ID=folder_id), \
                 patch.object(google_auth.httpx, 'get') as get, patch.object(google_auth.httpx, 'post') as post:
                with self.assertRaises(HTTPException) as raised:
                    google_auth._folder('access')
                self.assertEqual(raised.exception.status_code, 503)
                get.assert_not_called()
                post.assert_not_called()

    def test_drive_errors_never_fall_back_to_another_folder(self):
        for status, expected in ((401, 401), (403, 403), (404, 403), (429, 503), (500, 503), (400, 502)):
            with self.subTest(status=status), \
                 patch.object(google_auth.httpx, 'get', return_value=httpx.Response(status)), \
                 patch.object(google_auth.httpx, 'post') as post:
                with self.assertRaises(HTTPException) as raised:
                    google_auth._folder('access')
                self.assertEqual(raised.exception.status_code, expected)
                post.assert_not_called()
        with patch.object(google_auth.httpx, 'get', side_effect=httpx.ConnectTimeout('Timeout')), \
             patch.object(google_auth.httpx, 'post') as post:
            with self.assertRaises(HTTPException) as raised:
                google_auth._folder('access')
            self.assertEqual(raised.exception.status_code, 503)
            post.assert_not_called()

    def test_folder_must_be_a_writable_folder_outside_trash(self):
        valid = dict(id='folder-id', trashed=False, mimeType='application/vnd.google-apps.folder',
                     capabilities={'canAddChildren': True})
        cases = [
            ({**valid, 'trashed': True}, 409),
            ({**valid, 'trashed': None}, 409),
            ({**valid, 'mimeType': 'image/png'}, 422),
            ({**valid, 'mimeType': 'application/vnd.google-apps.shortcut'}, 422),
            ({**valid, 'capabilities': {'canAddChildren': False}}, 403),
            ({**valid, 'capabilities': {}}, 403),
            ({**valid, 'capabilities': 'invalid'}, 502),
            ({**valid, 'id': 'different-folder'}, 502),
            ([], 502),
        ]
        for metadata, expected in cases:
            with self.subTest(metadata=metadata), \
                 patch.object(google_auth.httpx, 'get', return_value=httpx.Response(200, json=metadata)), \
                 patch.object(google_auth.httpx, 'post') as post:
                with self.assertRaises(HTTPException) as raised:
                    google_auth._folder('access')
                self.assertEqual(raised.exception.status_code, expected)
                post.assert_not_called()
        with patch.object(google_auth.httpx, 'get', return_value=httpx.Response(200, text='invalid JSON')):
            with self.assertRaises(HTTPException) as raised:
                google_auth._folder('access')
            self.assertEqual(raised.exception.status_code, 502)

    def test_web_folder_denied_preserves_previous_credentials_and_issues_no_session(self):
        old = dict(email='mac@example.org', refresh_token='old-refresh', folder_id='old-folder')
        google_auth._save_credentials(old)
        started = self.client.get('/auth/google/start')
        state = started.cookies['mac_oauth_state']
        tokens = httpx.Response(200, json=dict(id_token='id', access_token='access', refresh_token='new-refresh'),
                                request=httpx.Request('POST', 'https://oauth2.googleapis.com/token'))
        with patch.object(google_auth.httpx, 'post', return_value=tokens) as post, \
             patch.object(google_auth.httpx, 'get', return_value=httpx.Response(404)), \
             patch.object(google_auth, '_google_identity', return_value=dict(email='mac@example.org', email_verified=True)):
            response = self.client.get('/auth/google/callback', params=dict(code='code', state=state),
                                       cookies={'mac_oauth_state': state})
        self.assertEqual(response.status_code, 403)
        self.assertIn('Google Picker', response.json()['detail'])
        self.assertEqual(google_auth._saved_credentials(), old)
        self.assertFalse(google_auth._sessions)
        self.assertFalse(google_auth._tickets)
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], 'https://oauth2.googleapis.com/token')

    def test_native_folder_denied_reports_error_without_saving_unvalidated_id(self):
        client = TestClient(create_app(), base_url='http://127.0.0.1:9123', follow_redirects=False)
        headers = {'X-API-Key': 'api-test-key'}
        with patch.dict(os.environ, MAC_GOOGLE_DESKTOP_CLIENT_ID='desktop-client', MAC_GOOGLE_DESKTOP_CLIENT_SECRET='desktop-secret'):
            started = client.post('/auth/google/desktop/start', headers=headers).json()
            state = parse_qs(urlparse(started['authorization_url']).query)['state'][0]
            tokens = httpx.Response(200, json=dict(id_token='id', access_token='access', refresh_token='refresh'),
                                    request=httpx.Request('POST', 'https://oauth2.googleapis.com/token'))
            with patch.object(google_auth.httpx, 'post', return_value=tokens) as post, \
                 patch.object(google_auth.httpx, 'get', return_value=httpx.Response(404)), \
                 patch.object(google_auth, '_google_identity', return_value=dict(email='mac@example.org', email_verified=True)):
                response = client.get('/auth/google/callback', params=dict(code='code', state=state))
            self.assertEqual(response.status_code, 400)
            poll = client.post('/auth/google/desktop/poll', json={'poll_token': started['poll_token']}, headers=headers)
            self.assertEqual(poll.status_code, 400)
            self.assertIn('Google Picker', poll.json()['detail'])
            self.assertFalse(google_auth._saved_credentials(desktop=True))
            self.assertFalse(google_auth._sessions)
            post.assert_called_once()

    def test_web_and_native_share_folder_but_keep_separate_authorizations(self):
        google_auth._save_credentials(dict(email='mac@example.org', refresh_token='previous-web', folder_id='old-folder'))
        desktop = TestClient(create_app(), base_url='http://127.0.0.1:9123', follow_redirects=False)
        metadata = dict(id='folder-id', trashed=False, mimeType='application/vnd.google-apps.folder',
                        capabilities={'canAddChildren': True})
        def exchange(url, **kwargs):
            self.assertEqual(url, 'https://oauth2.googleapis.com/token')
            native = kwargs['data']['client_id'] == 'desktop-client'
            return httpx.Response(200, json=dict(id_token='id', access_token='native-access' if native else 'web-access',
                refresh_token='native-refresh' if native else 'web-refresh'), request=httpx.Request('POST', url))
        with patch.dict(os.environ, MAC_GOOGLE_DESKTOP_CLIENT_ID='desktop-client', MAC_GOOGLE_DESKTOP_CLIENT_SECRET='desktop-secret'), \
             patch.object(google_auth.httpx, 'post', side_effect=exchange) as post, \
             patch.object(google_auth.httpx, 'get', return_value=httpx.Response(200, json=metadata)) as get, \
             patch.object(google_auth, '_google_identity', return_value=dict(email='mac@example.org', email_verified=True)):
            web_start = self.client.get('/auth/google/start')
            state = web_start.cookies['mac_oauth_state']
            web = self.client.get('/auth/google/callback', params=dict(code='web-code', state=state),
                                  cookies={'mac_oauth_state': state})
            self.assertEqual(web.status_code, 307, web.text)
            native_start = desktop.post('/auth/google/desktop/start', headers={'X-API-Key': 'api-test-key'}).json()
            native_state = parse_qs(urlparse(native_start['authorization_url']).query)['state'][0]
            native = desktop.get('/auth/google/callback', params=dict(code='native-code', state=native_state))
            self.assertEqual(native.status_code, 200, native.text)
        self.assertEqual(post.call_count, 2)  # Somente trocas OAuth, nunca criação no Drive.
        self.assertEqual([call.args[0] for call in get.call_args_list], ['https://www.googleapis.com/drive/v3/files/folder-id'] * 2)
        self.assertEqual([call.kwargs['headers']['Authorization'] for call in get.call_args_list], ['Bearer web-access', 'Bearer native-access'])
        web_credentials = google_auth._saved_credentials()
        native_credentials = google_auth._saved_credentials(desktop=True)
        self.assertEqual(web_credentials['folder_id'], native_credentials['folder_id'])
        self.assertEqual(web_credentials['refresh_token'], 'web-refresh')
        self.assertEqual(native_credentials['refresh_token'], 'native-refresh')

    def test_remembered_desktop_session_expires(self):
        with patch.object(google_auth.time, 'time', return_value=1000):
            google_auth._remember_session('temporary-token', 'mac@example.org', 1001)
        with patch.object(google_auth.time, 'time', return_value=1002):
            self.assertFalse(google_auth.valid_session('temporary-token'))

    def test_native_desktop_client_uses_dynamic_loopback_port(self):
        client = TestClient(create_app(), base_url="http://127.0.0.1:9123", follow_redirects=False)
        headers = {"X-API-Key": "api-test-key"}
        with patch.dict(os.environ, {
            'MAC_GOOGLE_DESKTOP_CLIENT_ID': 'desktop-client',
            'MAC_GOOGLE_DESKTOP_CLIENT_SECRET': 'desktop-secret',
            'MAC_GOOGLE_DESKTOP_TOKEN_FILE': f'{self.directory.name}/desktop.json',
        }):
            started = client.post('/auth/google/desktop/start', headers=headers)
            self.assertEqual(started.status_code, 200)
            query = parse_qs(urlparse(started.json()['authorization_url']).query)
            self.assertEqual(query['client_id'], ['desktop-client'])
            self.assertEqual(query['redirect_uri'], ['http://127.0.0.1:9123/auth/google/callback'])

            class TokenResponse:
                def raise_for_status(self):
                    pass

                def json(self):
                    return {'id_token': 'id', 'access_token': 'access', 'refresh_token': 'desktop-refresh'}

            with patch.object(google_auth.httpx, 'post', return_value=TokenResponse()), \
                 patch.object(google_auth, '_google_identity', return_value={
                     'email': 'mac@example.org', 'email_verified': True,
                 }), patch.object(google_auth, '_folder', return_value='folder-id') as folder:
                callback = client.get('/auth/google/callback', params={'code': 'code', 'state': query['state'][0]})
            self.assertEqual(callback.status_code, 200)
            folder.assert_called_once_with('access')
            self.assertEqual(google_auth._saved_credentials(desktop=True)['refresh_token'], 'desktop-refresh')
            self.assertEqual(google_auth._saved_credentials(desktop=True)['folder_id'], 'folder-id')
            self.assertEqual(client.post('/auth/google/desktop/poll', json={'poll_token': started.json()['poll_token']}, headers=headers).status_code, 200)

    def test_desktop_rejects_other_account_and_reports_failure_to_webview(self):
        client = TestClient(create_app(), base_url="http://localhost:8000", follow_redirects=False)
        headers = {"X-API-Key": "api-test-key"}
        started = client.post('/auth/google/desktop/start', headers=headers).json()
        state = parse_qs(urlparse(started['authorization_url']).query)['state'][0]

        class TokenResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {'id_token': 'id', 'access_token': 'access', 'refresh_token': 'refresh'}

        with patch.object(google_auth.httpx, 'post', return_value=TokenResponse()), \
             patch.object(google_auth, '_google_identity', return_value={
                 'email': 'other@example.org', 'email_verified': True,
             }):
            callback = client.get('/auth/google/callback', params={'code': 'code', 'state': state})
        self.assertEqual(callback.status_code, 400)
        self.assertEqual(client.post('/auth/google/desktop/poll', json={'poll_token': started['poll_token']}, headers=headers).status_code, 400)
        self.assertEqual(google_auth._saved_credentials(), {})
