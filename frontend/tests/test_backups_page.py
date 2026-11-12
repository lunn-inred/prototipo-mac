from pathlib import Path
import unittest
from unittest.mock import patch
import streamlit as st
from streamlit.testing.v1 import AppTest
from frontend.streamlit.api_client import backups

PAGE = Path(__file__).resolve().parents[1] / 'streamlit/pages/Backups.py'


class BackupsPageTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)
        self.entry = dict(id='file-id', name='mac-backup-test.zip', size='1024', createdTime='2026-11-11T10:00:00Z',
                          properties={'sha256': 'a'*64})
        for mock in (
            patch.object(backups, 'list_backups', return_value=[self.entry]),
            patch('frontend.streamlit.api_client.service_gateway._http_request', side_effect=AssertionError('Sem rede real')),
            patch('psycopg2.connect', side_effect=AssertionError('Sem banco real')),
        ):
            mock.start(); self.addCleanup(mock.stop)
        self.app = AppTest.from_file(str(PAGE), default_timeout=20)

    def test_page_lists_backup_and_restore_requires_confirmation(self):
        queued = dict(id='job', kind='restore', status='queued', message='Aguardando')
        with patch.object(backups, 'restore_backup', return_value=queued) as restore, \
             patch.object(backups, 'job_status', return_value={**queued, 'status': 'running'}):
            self.app.run()
            self.assertFalse(self.app.exception)
            self.app.button(key='backup_restore_open').click().run()
            self.assertFalse(self.app.exception)
            self.assertTrue(self.app.button(key='backup_restore_confirm').disabled)
            restore.assert_not_called()
            self.app.checkbox(key='backup_confirm_replace').check().run()
            self.assertFalse(self.app.button(key='backup_restore_confirm').disabled)
            self.app.button(key='backup_restore_confirm').click().run()
            self.assertFalse(self.app.exception)
            restore.assert_called_once_with(self.entry)

    def test_create_backup_is_single_request_and_controls_are_disabled_while_running(self):
        job = dict(id='job', kind='backup', status='running', message='Enviando')
        with patch.object(backups, 'create_backup', return_value=job) as create, patch.object(backups, 'job_status', return_value=job):
            self.app.run()
            self.app.button(key='backup_create').click().run()
            self.assertFalse(self.app.exception)
            create.assert_called_once_with()
            self.assertTrue(self.app.button(key='backup_create').disabled)
            self.assertTrue(self.app.button(key='backup_restore_open').disabled)

    def test_completed_restore_clears_stale_draft_and_preserves_login(self):
        self.app.session_state['thermal_draft'] = {'player': 1}
        self.app.session_state['mac_google_session'] = 'local-session'
        self.app.session_state['backup_job'] = dict(id='job', kind='restore', status='running', message='Restaurando')
        completed = dict(id='job', kind='restore', status='completed', message='Restaurado',
                         result=dict(analyses=3, preserved_local=2, recovery_copy='/tmp/safe.zip'))
        with patch.object(backups, 'job_status', return_value=completed):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertNotIn('thermal_draft', self.app.session_state)
        self.assertEqual(self.app.session_state['mac_google_session'], 'local-session')
        self.assertTrue(any('Restaurado' in message.value for message in self.app.success))
        self.assertFalse(self.app.button(key='backup_create').disabled)

    def test_failed_job_does_not_leave_controls_permanently_disabled(self):
        self.app.session_state['backup_job'] = dict(id='job', kind='backup', status='running', message='Enviando')
        with patch.object(backups, 'job_status', return_value=dict(id='job', kind='backup', status='failed', message='Drive indisponível')):
            self.app.run()
        self.assertFalse(self.app.exception)
        self.assertFalse(self.app.button(key='backup_create').disabled)
        self.assertTrue(any('Drive indisponível' in message.value for message in self.app.error))
