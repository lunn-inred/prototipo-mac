"""Sinal persistente, disparo após gravação e consulta do Drive sem serviços externos."""
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.mac_api.main import _is_sync_write, create_app
from backend.mac_api.modules.backups import auto_sync


class AutoSyncTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='mac-auto-sync-test-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        backup_path = patch.object(auto_sync.service, 'backups_directory', return_value=self.root)
        backup_path.start(); self.addCleanup(backup_path.stop)
        enabled = patch.object(auto_sync, 'enabled', return_value=True)
        enabled.start(); self.addCleanup(enabled.stop)
        auto_sync._wake.clear()

    def test_successful_write_marks_persistent_pending_without_marking_failed_request(self):
        with patch.dict('os.environ', MAC_GOOGLE_CLIENT_ID='', MAC_API_KEY='auto-sync-test'), \
             patch('backend.mac_api.main.create_athlete', return_value=3), \
             patch.object(auto_sync, 'mark_dirty') as marked:
            client = TestClient(create_app())
            headers = {'X-API-Key': 'auto-sync-test'}
            self.assertEqual(client.post('/api/v1/athletes', headers=headers, json={'name': 'Teste'}).status_code, 201)
            self.assertEqual(client.post('/api/v1/athletes', headers=headers, json={'name': ''}).status_code, 422)
            self.assertEqual(client.get('/health').status_code, 200)
            marked.assert_called_once_with()

    def test_pending_survives_restart_and_success_clears_only_observed_generation(self):
        auto_sync.mark_dirty()
        self.assertTrue(auto_sync._read()['pending'])
        self.assertEqual(auto_sync._read()['generation'], 1)
        with patch.object(auto_sync, 'DEBOUNCE_SECONDS', 0), \
             patch.object(auto_sync.jobs, 'start', return_value={'id': 'job'}), \
             patch.object(auto_sync.jobs, 'status', return_value={'status': 'completed'}):
            auto_sync._cycle(Event())
        self.assertFalse(auto_sync._read()['pending'])
        self.assertIsNotNone(auto_sync._read()['last_success'])
        auto_sync.mark_dirty()
        self.assertEqual(auto_sync._read()['generation'], 2)
        self.assertTrue(auto_sync._read()['pending'])

    def test_remote_poll_starts_job_only_for_new_revision(self):
        with patch('backend.mac_api.modules.backups.synchronization.status',
                   return_value={'revision': 'remote'}), \
             patch.object(auto_sync, '_baseline_revision', return_value='local'), \
             patch.object(auto_sync.jobs, 'start', return_value={'id': 'job'}) as start, \
             patch.object(auto_sync.jobs, 'status', return_value={'status': 'completed'}):
            auto_sync._cycle(Event())
            start.assert_called_once_with('sync', desktop=True)
        with patch('backend.mac_api.modules.backups.synchronization.status',
                   return_value={'revision': 'same'}), \
             patch.object(auto_sync, '_baseline_revision', return_value='same'), \
             patch.object(auto_sync.jobs, 'start') as start:
            auto_sync._cycle(Event())
            start.assert_not_called()

    def test_first_start_initializes_sync_even_without_remote_index(self):
        with patch('backend.mac_api.modules.backups.synchronization.status',
                   return_value={'revision': None}), \
             patch.object(auto_sync, '_baseline_revision', return_value=None), \
             patch.object(auto_sync.jobs, 'start', return_value={'id': 'job'}) as start, \
             patch.object(auto_sync.jobs, 'status', return_value={'status': 'completed'}):
            auto_sync._cycle(Event())
            start.assert_called_once_with('sync', desktop=True)

    def test_failed_job_keeps_pending_for_retry(self):
        auto_sync.mark_dirty()
        with patch.object(auto_sync, 'DEBOUNCE_SECONDS', 0), \
             patch.object(auto_sync.jobs, 'start', return_value={'id': 'job'}), \
             patch.object(auto_sync.jobs, 'status', return_value={'status': 'failed', 'message': 'Falha simulada'}):
            auto_sync._cycle(Event())
        state = auto_sync._read()
        self.assertTrue(state['pending'])
        self.assertEqual(state['last_error'], 'Falha simulada')
        self.assertGreater(state['retry_at'], 0)

    def test_new_write_during_sync_remains_pending(self):
        auto_sync.mark_dirty()
        before = auto_sync.generation()
        auto_sync.mark_dirty()
        auto_sync.record_success(before)
        self.assertTrue(auto_sync._read()['pending'])
        auto_sync.record_success(auto_sync.generation())
        self.assertFalse(auto_sync._read()['pending'])

    def test_write_route_filter_excludes_previews_and_backups(self):
        self.assertTrue(_is_sync_write('POST', '/api/v1/gps/import'))
        self.assertTrue(_is_sync_write('PUT', '/api/v1/jumps/collections/2/2026-11-01'))
        self.assertTrue(_is_sync_write('POST', '/api/v1/thermography/drafts'))
        self.assertFalse(_is_sync_write('POST', '/api/v1/gps/preview'))
        self.assertFalse(_is_sync_write('POST', '/api/v1/backups/sync'))

    def test_api_lifespan_starts_and_stops_background_worker(self):
        handle = object()
        with patch.object(auto_sync, 'start_worker', return_value=handle) as start, \
             patch.object(auto_sync, 'stop_worker') as stop:
            with TestClient(create_app()) as client:
                self.assertEqual(client.get('/health').status_code, 200)
            start.assert_called_once_with()
            stop.assert_called_once_with(handle)
