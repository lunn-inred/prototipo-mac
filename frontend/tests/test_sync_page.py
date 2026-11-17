from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from frontend.streamlit.api_client import backups

PAGE = Path(__file__).resolve().parents[1]/'streamlit/pages/Sincronizacao.py'


class SyncPageTests(unittest.TestCase):
    def test_start_is_single_request_and_disabled_while_running(self):
        job = dict(id='sync', kind='sync', status='running', message='Comparando')
        with patch.object(backups, 'synchronize', return_value=job) as start, \
             patch.object(backups, 'job_status', return_value=job), \
             patch.object(backups, 'auto_sync_status', return_value={'state': 'idle', 'revision': None}):
            app = AppTest.from_file(str(PAGE)).run()
            app.button(key='sync_start').click().run()
            self.assertFalse(app.exception)
            start.assert_called_once_with()
            self.assertTrue(app.button(key='sync_start').disabled)

    def test_automatic_progress_disables_manual_and_hides_previous_error(self):
        job = dict(id='automatic', kind='sync', status='running', message='Baixando análises')
        with patch.object(backups, 'job_status', return_value=job), \
             patch.object(backups, 'auto_sync_status', return_value={
                 'state': 'syncing', 'job_id': 'automatic', 'last_error': 'Erro antigo', 'revision': None}), \
             patch.object(backups, 'synchronize') as start:
            app = AppTest.from_file(str(PAGE)).run()
        self.assertFalse(app.exception)
        self.assertTrue(app.button(key='sync_start').disabled)
        self.assertEqual(app.info[0].value, 'Baixando análises')
        self.assertFalse(any(w.value == 'Erro antigo' for w in app.warning))
        start.assert_not_called()

    def test_completion_preserves_unsaved_analysis_and_failure_allows_retry(self):
        app = AppTest.from_file(str(PAGE))
        app.session_state['thermal_draft'] = dict(player=1, notes='Não perder')
        app.session_state['sync_job'] = dict(id='sync', kind='sync', status='running', message='Comparando')
        completed = dict(id='sync', kind='sync', status='completed', message='Concluída', result={})
        with patch.object(backups, 'job_status', return_value=completed), \
             patch.object(backups, 'auto_sync_status', return_value={'state': 'idle', 'revision': 'one'}):
            app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['thermal_draft']['notes'], 'Não perder')
        self.assertTrue(app.success)
        app.session_state['sync_job'] = dict(id='other', kind='sync', status='failed', message='Conflito')
        with patch.object(backups, 'auto_sync_status', return_value={'state': 'error', 'revision': 'one',
                                                                    'last_error': 'Falha automática'}):
            app.run()
        self.assertFalse(app.exception)
        self.assertFalse(app.button(key='sync_start').disabled)
        self.assertEqual(app.error[0].value, 'Conflito')
