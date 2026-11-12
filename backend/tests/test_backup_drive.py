import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import httpx
from backend.mac_api.modules.backups import drive


class BackupDriveTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory(prefix='mac-drive-mock-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        environment = patch.dict(os.environ, MAC_GOOGLE_ALLOWED_EMAIL='mac@example.org', MAC_GOOGLE_CLIENT_ID='web-id',
            MAC_GOOGLE_CLIENT_SECRET='web-secret', MAC_GOOGLE_DESKTOP_CLIENT_ID='desktop-id',
            MAC_GOOGLE_DESKTOP_CLIENT_SECRET='desktop-secret', MAC_BACKUP_MAX_BYTES=str(20 * 1024**2))
        environment.start(); self.addCleanup(environment.stop)
        saved = patch.object(drive.google_auth, '_saved_credentials', side_effect=lambda desktop=False:
            dict(email='mac@example.org', refresh_token='desktop-refresh' if desktop else 'web-refresh'))
        saved.start(); self.addCleanup(saved.stop)
        folder = patch.object(drive.google_auth, '_folder', return_value='folder-id')
        folder.start(); self.addCleanup(folder.stop)
        self.original_client = httpx.Client
        self.requests = []

    def install(self, handler):
        def transport(request):
            self.requests.append(request)
            if request.url.host == 'oauth2.googleapis.com':
                return httpx.Response(200, json={'access_token': 'access'})
            return handler(request)
        client = patch.object(drive.httpx, 'Client', side_effect=lambda **kwargs:
            self.original_client(transport=httpx.MockTransport(transport), **kwargs))
        client.start(); self.addCleanup(client.stop)

    def test_upload_uses_resumable_chunks_and_unique_file_metadata(self):
        content = b'x' * (8 * 1024**2 + 123)
        source = self.root / 'backup.zip'
        source.write_bytes(content)
        def handler(request):
            if request.method == 'POST':
                metadata = json.loads(request.content)
                self.assertEqual(metadata['parents'], ['folder-id'])
                self.assertEqual(metadata['properties']['sha256'], hashlib.sha256(content).hexdigest())
                self.assertNotIn('refresh', request.content.decode())
                return httpx.Response(200, headers={'Location': 'https://www.googleapis.com/upload/drive/v3/files?upload_id=test'})
            if request.headers['Content-Range'].startswith('bytes 0-'):
                self.assertEqual(len(request.content), 8 * 1024**2)
                return httpx.Response(308, headers={'Range': f'bytes=0-{8 * 1024**2 - 1}'})
            self.assertEqual(request.content, b'x' * 123)
            return httpx.Response(201, json={'id': 'uploaded'})
        self.install(handler)
        with drive.Drive() as client:
            self.assertEqual(client.upload(source, 'mac-backup-unique.zip', 'installation')['id'], 'uploaded')
        self.assertEqual([request.method for request in self.requests], ['POST', 'POST', 'PUT', 'PUT'])

    def test_download_verifies_folder_size_and_checksum(self):
        content = b'fake zip bytes'
        def handler(request):
            if request.url.params.get('alt') == 'media':
                return httpx.Response(200, content=content)
            return httpx.Response(200, json=dict(id='backup-id', parents=['folder-id'], trashed=False,
                mimeType='application/zip', size=str(len(content)), properties=dict(macBackupFormat='1', sha256=hashlib.sha256(content).hexdigest())))
        self.install(handler)
        with drive.Drive(desktop=True) as client:
            client.download('backup-id', self.root / 'download.zip')
        self.assertEqual((self.root / 'download.zip').read_bytes(), content)
        self.assertIn(b'client_id=desktop-id', self.requests[0].content)

    def test_foreign_folder_and_invalid_upload_host_are_rejected(self):
        self.install(lambda request: httpx.Response(200, json=dict(parents=['another-folder'], mimeType='application/zip',
            properties={'macBackupFormat': '1'})) if request.method == 'GET' else httpx.Response(200, headers={'Location': 'https://attacker.invalid/upload'}))
        source = self.root / 'backup.zip'
        source.write_bytes(b'zip')
        with drive.Drive() as client:
            with self.assertRaises(ValueError):
                client.download('backup-id', self.root / 'forbidden.zip')
            with self.assertRaises(ValueError):
                client.upload(source, 'backup.zip', 'installation')
        self.assertFalse((self.root / 'forbidden.zip').exists())
        self.assertFalse(any(request.method == 'PUT' for request in self.requests))

    def test_listing_follows_pages_inside_only_configured_folder(self):
        def handler(request):
            self.assertIn("'folder-id' in parents", request.url.params['q'])
            self.assertIn('macBackupFormat', request.url.params['q'])
            return httpx.Response(200, json={'files': [{'id': 'two'}]}) if request.url.params.get('pageToken') else httpx.Response(200, json={'nextPageToken': 'next', 'files': [{'id': 'one'}]})
        self.install(handler)
        with drive.Drive() as client:
            self.assertEqual([entry['id'] for entry in client.list()], ['one', 'two'])

    def test_checksum_mismatch_does_not_silently_accept_download(self):
        def handler(request):
            return httpx.Response(200, content=b'bad') if request.url.params.get('alt') else httpx.Response(200, json=dict(
                parents=['folder-id'], mimeType='application/zip', size='3', properties=dict(macBackupFormat='1', sha256='0'*64)))
        self.install(handler)
        with drive.Drive() as client:
            with self.assertRaisesRegex(ValueError, 'corrompido'):
                client.download('backup-id', self.root / 'bad.zip')
