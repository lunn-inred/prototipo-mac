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
             patch.object(backups, 'job_status', return_value=job):
            app = AppTest.from_file(str(PAGE)).run()
            app.button(key='sync_start').click().run()
            self.assertFalse(app.exception)
            start.assert_called_once_with()
            self.assertTrue(app.button(key='sync_start').disabled)

    def test_completion_preserves_unsaved_analysis_and_failure_allows_retry(self):
        app = AppTest.from_file(str(PAGE))
        app.session_state['thermal_draft'] = dict(player=1, notes='Não perder')
        app.session_state['sync_job'] = dict(id='sync', kind='sync', status='running', message='Comparando')
        completed = dict(id='sync', kind='sync', status='completed', message='Concluída', result={})
        with patch.object(backups, 'job_status', return_value=completed):
            app.run()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['thermal_draft']['notes'], 'Não perder')
        self.assertTrue(app.success)
        app.session_state['sync_job'] = dict(id='other', kind='sync', status='failed', message='Conflito')
        app.run()
        self.assertFalse(app.exception)
        self.assertFalse(app.button(key='sync_start').disabled)
        self.assertEqual(app.error[0].value, 'Conflito')
