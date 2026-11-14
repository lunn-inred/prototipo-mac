import os
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
from unittest.mock import Mock, patch
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
        self.assertEqual(state['thermography_mass'], 75.)
        self.assertEqual(state['thermography_player'], 1)
        self.assertEqual(state['thermography_pain_score'], 0)
        self.assertEqual(state['thermography_observations'], 'Anterior')
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
            card = app.button(key='analysis_player_1')
            self.assertEqual(card.label, '**Teste**\n\nMeia\n\nCadastro: ativo')
            self.assertEqual(card.proto.icon, '👤')
            self.assertFalse(any(button.label == 'Selecionar atleta' for button in app.button))
            self.assertEqual(len(app.code), 0)
            app.button(key='analysis_player_1').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            card = app.button(key=f'analysis_select_{self.saved["id"]}')
            self.assertIn('**Frente**\n![Frente](data:image/png;base64,', card.label)
            self.assertIn('**Costas**\n![Costas](data:image/png;base64,', card.label)
            self.assertIn('**01/11/2026**', card.label)
            self.assertIn('Massa: 75.0 kg · EVA: 0', card.label)
            self.assertFalse(any(button.label == 'Selecionar análise' for button in app.button))
            app.button(key=f'analysis_select_{self.saved["id"]}').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(app.session_state['thermal_edit_source']['id'], self.saved['id'])
            load.assert_called_once()

    def test_browser_clears_previous_cards_before_requesting_analyses(self):
        script = '''
from frontend.streamlit.components.thermography.history import show_history
show_history({1: {'id_atleta': 1, 'nome': 'Teste'}})
'''
        original_empty = st.empty
        slots = []

        def empty():
            slot = original_empty()
            slot.empty = Mock(wraps=slot.empty)
            slot.container = Mock(wraps=slot.container)
            slots.append(slot)
            return slot

        def load(*args, **kwargs):
            # A limpeza deve ser enviada antes da consulta, não só ao concluir.
            slots[0].empty.assert_called_once_with()
            slots[0].container.assert_called_once_with(key='analysis_browser_loading')
            return [self.saved]

        app = AppTest.from_string(script).run()
        with patch.object(history.st, 'empty', side_effect=empty), \
             patch.object(history, 'list_local_analyses', side_effect=load) as request:
            app.button(key='analysis_player_1').click().run()
        self.assertFalse(app.exception)
        request.assert_called_once_with(1, include_drafts=True)
        self.assertFalse(any(button.key.startswith('analysis_player_') for button in app.button))
        self.assertIsNotNone(app.button(key=f'analysis_select_{self.saved["id"]}'))

    def test_loading_failure_keeps_current_draft(self):
        state = {'thermal_draft': {'player': 5, 'notes': 'Não perder'}}
        with patch.object(history.st, 'session_state', state), patch.object(history, 'load_local_analysis', side_effect=ValueError('indisponível')):
            history._select_analysis(self.saved)
        self.assertEqual(state['thermal_draft']['notes'], 'Não perder')
        self.assertNotIn('thermal_edit_source', state)

    def test_all_players_and_analyses_are_available_without_pagination_or_close_button(self):
        script = '''
from frontend.streamlit.components.thermography.history import show_history
show_history({i: {'id_atleta': i, 'nome': f'Atleta {i}'} for i in range(1, 9)})
'''
        entries = [{**self.saved, 'id': f'analysis-{i}'} for i in range(7)]
        with patch.object(history, 'list_local_analyses', return_value=entries), \
             patch.object(history.st, 'html', wraps=history.st.html) as html:
            app = AppTest.from_string(script).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            styles = '\n'.join(call.args[0] for call in html.call_args_list)
            self.assertIn('[data-testid="stDialog"]:has(.st-key-analysis_browser_results)', styles)
            self.assertIn('height: calc(100dvh - 2rem) !important;', styles)
            self.assertIn('flex: 1 1 0% !important;', styles)
            self.assertIn('min-height: 0 !important;', styles)
            self.assertIn('max-height: none !important;', styles)
            self.assertNotIn('calc(100dvh - 300px)', styles)
            self.assertEqual([button.key for button in app.button], [f'analysis_player_{i}' for i in range(1, 9)] + ['analysis_player_0'])
            self.assertFalse(any(button.label == 'Selecionar atleta' for button in app.button))
            self.assertTrue(any('analysis_browser_results' in block.proto.id for block in app.get('flex_container')))
            app.button(key='analysis_player_8').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual([button.key for button in app.button], [f'analysis_select_analysis-{i}' for i in range(7)] + ['analysis_browser_back'])
            app.button(key='analysis_browser_back').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(len(app.button), 9)
            app.text_input(key='analysis_browser_query').set_value('Atleta 8').run()
            self.assertEqual([button.key for button in app.button], ['analysis_player_8'])

    def test_new_opening_resets_browser_navigation_but_keeps_current_draft(self):
        script = '''
from frontend.streamlit.components.thermography.history import render_history_button
render_history_button({1: {'id_atleta': 1, 'nome': 'Teste'}})
'''
        app = AppTest.from_string(script)
        app.session_state['analysis_browser_player'] = 1
        app.session_state['analysis_browser_query'] = 'Busca anterior'
        app.session_state['analysis_browser_error'] = 'Erro anterior'
        app.session_state['thermal_draft'] = {'player': 7, 'notes': 'Preservar'}
        with patch.object(history, 'show_history') as dialog:
            app.run()
            app.button(key='thermal_history_open').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            dialog.assert_called_once()
            self.assertNotIn('analysis_browser_player', app.session_state)
            self.assertNotIn('analysis_browser_query', app.session_state)
            self.assertNotIn('analysis_browser_error', app.session_state)
            self.assertEqual(app.session_state['thermal_draft']['notes'], 'Preservar')
            self.assertFalse(app.error)
            # AppTest não simula o X: representar o estado deixado ao fechar.
            app.session_state['analysis_browser_player'] = 1
            app.session_state['analysis_browser_query'] = 'Teste'
            app.run()
            app.button(key='thermal_history_open').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertNotIn('analysis_browser_player', app.session_state)
            self.assertNotIn('analysis_browser_query', app.session_state)
            self.assertEqual(dialog.call_count, 2)

    def test_back_button_remains_available_when_analysis_listing_fails(self):
        script = '''
import streamlit as st
from frontend.streamlit.components.thermography.history import show_history
st.session_state.setdefault('analysis_browser_player', 1)
show_history({1: {'id_atleta': 1, 'nome': 'Teste'}})
'''
        with patch.object(history, 'list_local_analyses', side_effect=ValueError('Indisponível')):
            app = AppTest.from_string(script).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(app.button[-1].key, 'analysis_browser_back')
            app.button(key='analysis_browser_back').click().run()
            self.assertTrue(any(button.key == 'analysis_player_1' for button in app.button))

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
