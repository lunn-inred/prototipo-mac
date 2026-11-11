import os
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
from unittest.mock import patch
import unittest
import numpy as np
import streamlit as st
from streamlit.testing.v1 import AppTest
from fastapi.testclient import TestClient
from urllib.parse import urlsplit

from backend.mac_api.main import create_app
from backend.mac_api.modules.thermography import analysis_archive as archive
from backend.tests.test_analysis_archive import example_views
from frontend.streamlit.components.thermography import history


class AnalysisHistoryTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)
        self.directory = TemporaryDirectory(prefix='mac-history-')
        self.addCleanup(self.directory.cleanup)
        env = patch.dict(os.environ, MAC_ANALYSES_DIR=self.directory.name)
        env.start(); self.addCleanup(env.stop)
        views = example_views()
        for value in views.values():
            value['colorbar_box'] = dict(left=7, top=0, width=1, height=12)
        self.saved = archive.save_analysis(athlete_id=1, athlete_name='Teste', collected_at=date(2026, 11, 1),
            mass=75., pain_score=0, observations='Anterior', views=views)
        self.loaded = archive.load_analysis(1, date(2026, 11, 1), self.saved['id'])

    def test_restore_preserves_rotation_masks_temperatures_and_widgets(self):
        state = {'thermal_draft': {'notes': 'Rascunho'}, 'thermography_mass': 90.,
                 'thermography_front_upload_0': 'upload anterior'}
        with patch.object(history.st, 'session_state', state):
            history.load_into_wizard(self.loaded)
        self.assertEqual(state['thermal_step'], 0)
        self.assertEqual(state['thermal_draft']['pain'], 0)
        self.assertEqual(state['thermal_draft']['notes'], 'Anterior')
        self.assertEqual(state['thermal_edit_source']['id'], self.saved['id'])
        self.assertNotIn('thermography_mass', state)
        self.assertNotIn('thermography_front_upload_0', state)
        self.assertEqual(state['thermal_upload_generation'], 1)
        for key, item in state['thermography_items'].items():
            source = self.loaded['views'][key.split(':')[0]]
            np.testing.assert_array_equal(item['saved_analysis']['temperatures'], source['temperatures'])
            np.testing.assert_array_equal(item['saved_analysis']['masks']['left'], source['segmentation_masks']['left'])

    def test_browser_selects_player_then_analysis_without_database_writes(self):
        script = '''
import streamlit as st
from frontend.streamlit.components.thermography.history import show_history
if not st.session_state.get('thermal_edit_source'):
    show_history({1:{'id_atleta':1,'nome':'Teste','posicao':'Meia'}})
'''
        with patch.object(history, 'list_local_analyses', return_value=[self.saved]), \
             patch.object(history, 'load_local_analysis', return_value=self.loaded) as load, \
             patch('psycopg2.connect', side_effect=AssertionError('Sem banco')):
            app = AppTest.from_string(script).run()
            cards = [item.proto.body for item in app.get('html') if 'class="player-card compact"' in item.proto.body]
            self.assertEqual(len(cards), 1)
            self.assertIn('class="player-name">Teste</div>', cards[0])
            self.assertFalse(any('class="player-card compact"' in item.value for item in app.markdown))
            self.assertEqual(len(app.code), 0)
            app.button(key='analysis_player_1').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            app.button(key=f'analysis_select_{self.saved["id"]}').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(app.session_state['thermal_edit_source']['id'], self.saved['id'])
            load.assert_called_once()

    def test_loading_failure_keeps_current_draft(self):
        state = {'thermal_draft': {'player': 5, 'notes': 'Não perder'}}
        with patch.object(history.st, 'session_state', state), patch.object(history, 'load_local_analysis', side_effect=ValueError('indisponível')):
            history._select_analysis(self.saved)
        self.assertEqual(state['thermal_draft']['notes'], 'Não perder')
        self.assertNotIn('thermal_edit_source', state)

    def test_reopened_wizard_keeps_saved_masks_without_automatic_resegmentation(self):
        state = {}
        with patch.object(history.st, 'session_state', state):
            history.load_into_wizard(self.loaded)
        app = AppTest.from_string(
            'from frontend.streamlit.components.thermography.wizard import render_wizard\n'
            'render_wizard({1:{"id_atleta":1,"nome":"Teste"}})', default_timeout=30)
        for key, value in state.items():
            app.session_state[key] = value
        client = TestClient(create_app())
        def http(method, url, **kwargs):
            kwargs.pop('timeout', None)
            return client.request(method, urlsplit(url).path, **kwargs)
        with patch('frontend.streamlit.api_client.service_gateway._http_request', side_effect=http), \
             patch('backend.mac_api.modules.thermography.thermal_analysis.segment_leg_mask', side_effect=AssertionError('Não refazer máscara salva')), \
             patch('backend.mac_api.modules.thermography.thermal_analysis.temperature_matrix', side_effect=AssertionError('Não refazer matriz salva')):
            app.run()
            for _ in range(5):
                app.button(key='thermal_next').click().run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertFalse(app.button(key='thermal_next').disabled)
            self.assertEqual(len(app.error), 0, list(app.error))
            for key, item in app.session_state['thermography_items'].items():
                source = self.loaded['views'][key.split(':')[0]]
                np.testing.assert_array_equal(item['analysis']['masks']['left'], source['segmentation_masks']['left'])
                np.testing.assert_array_equal(item['analysis']['temperatures'], source['temperatures'])
