"""Completude depende dos dados atuais, não da etapa nem de caches antigos."""
from copy import deepcopy
from datetime import date
import io
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
import streamlit as st
from streamlit.testing.v1 import AppTest
from backend.mac_api.modules.thermography import analysis_archive as archive
from backend.tests.test_analysis_archive import example_views
from frontend.streamlit.components.thermography import history, save_flow
from frontend.streamlit.components.thermography.editor import analysis_configuration


class ThermalSaveReadinessTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear(); self.addCleanup(st.cache_data.clear)
        temporary = TemporaryDirectory(prefix='mac-readiness-')
        self.addCleanup(temporary.cleanup)
        env = patch.dict(os.environ, MAC_ANALYSES_DIR=temporary.name)
        env.start(); self.addCleanup(env.stop)
        entry = archive.save_analysis(athlete_id=1, athlete_name='Teste', collected_at=date(2026,11,1),
                                      mass=75., pain_score=0, observations='', views=example_views())
        loaded = archive.load_analysis(1, date(2026,11,1), entry['id'])
        self.state = {}
        with patch.object(history.st, 'session_state', self.state):
            history.load_into_wizard(loaded)
        self.state['thermal_available_players'] = {1: dict(id_atleta=1, nome='Teste')}
        self.key = next(key for key in self.state['thermography_items'] if key.startswith('front:'))

    def values(self, step=0):
        with patch.object(save_flow.st, 'session_state', self.state):
            return save_flow._complete_values(step)

    def test_complete_saved_analysis_is_ready_at_every_earlier_step(self):
        for step in range(6):
            with self.subTest(step=step):
                values = self.values(step)
                self.assertIsNotNone(values)
                self.assertEqual(values['athlete_id'], 1)
                self.assertEqual(values['pain_score'], 0)
                self.assertEqual(set(values['views']), {'front','back'})

    def test_current_metadata_is_used_instead_of_old_calculation(self):
        self.state['thermal_calculation'] = ('stale',)
        self.state['thermal_draft'].update(mass=82., pain=0, notes='Atual', collected_at=date(2026,11,2))
        values = self.values(1)
        self.assertEqual((values['mass'], values['pain_score'], values['observations'], values['collected_at']),
                         (82., 0, 'Atual', date(2026,11,2)))

    def test_reused_saved_views_still_satisfy_backend_storage_contract(self):
        from frontend.streamlit.components.thermography.timeline import views_for_storage
        values = self.values(0)
        stored = views_for_storage(values['views'], values['items'])
        for view in ('front', 'back'):
            archive._validate_view(stored[view])

    def test_changed_image_or_rotation_cannot_reuse_old_matrices(self):
        original = deepcopy(self.state['thermal_uploads']['front'])
        self.state['thermal_uploads']['front']['rotation'] = (original['rotation'] + 90) % 360
        self.assertIsNone(self.values())
        buffer = io.BytesIO(); Image.new('RGB', (8,12), 'blue').save(buffer, format='PNG')
        self.state['thermal_uploads']['front'] = {**original, 'content': buffer.getvalue()}
        self.assertIsNone(self.values())

    def test_changed_boxes_palette_or_scale_require_current_calculations(self):
        original = deepcopy(self.state['thermography_items'][self.key])
        for change in ('box', 'colorbar', 'scale'):
            with self.subTest(change=change):
                item = deepcopy(original)
                if change == 'box':
                    item['manual_boxes']['left']['width'] -= 1
                elif change == 'colorbar':
                    item['manual_colorbar_box'] = dict(left=0,top=0,width=1,height=1)
                else:
                    item['minimum_temperature'] += 1
                self.state['thermography_items'][self.key] = item
                self.assertIsNone(self.values(2))

    def test_current_analysis_cache_is_ready_but_stale_mask_corrections_are_not(self):
        item = self.state['thermography_items'][self.key]
        item['analysis'] = save_flow._ready_analysis(item, item['image_rotation'])
        item['analysis_config'] = analysis_configuration(item['minimum_temperature'], item['maximum_temperature'],
                                                       item['threshold_temperature'], item)
        self.assertIsNotNone(self.values(4))
        item['mask_seeds'] = {'left': np.ones_like(item['saved_analysis']['temperatures'], dtype=np.int8)}
        self.assertIsNone(self.values(4))

    def test_reopened_complete_analysis_saves_from_first_step_without_incomplete_popup(self):
        script = '''
from frontend.streamlit.components.thermography.wizard import render_wizard
from frontend.streamlit.components.thermography.save_flow import render_pending_save
render_wizard({1: dict(id_atleta=1, nome='Teste')})
render_pending_save()
'''
        app = AppTest.from_string(script)
        for key, value in self.state.items():
            app.session_state[key] = value
        with patch.object(save_flow, 'register_prepared_analysis', return_value={}) as register, \
             patch.object(save_flow, 'save_draft') as partial:
            app.run()
            app.button(key='thermal_save_analysis').click().run()
            self.assertFalse(app.exception)
            register.assert_called_once()
            partial.assert_not_called()
            self.assertEqual(register.call_args.kwargs['pain_score'], 0)
            self.assertFalse(app.warning)
            self.assertFalse(any(button.key == 'thermal_save_confirm' for button in app.button))
            self.assertEqual(app.toast[0].value, 'Análise salva. Você poderá visualizá-la em Ver análises anteriores.')
            self.assertIsNone(app.selectbox(key='thermography_player').value)
            for widget in (app.selectbox(key='thermography_player'), app.number_input(key='thermography_mass'),
                           app.number_input(key='thermography_pain_score'), app.text_area(key='thermography_observations')):
                self.assertTrue(widget.proto.set_value, widget.key)

    def test_missing_required_metadata_still_requests_partial_confirmation(self):
        self.state['thermal_draft']['mass'] = None
        self.state['thermography_mass'] = None
        app = AppTest.from_string('''
from frontend.streamlit.components.thermography.wizard import render_wizard
from frontend.streamlit.components.thermography.save_flow import render_pending_save
render_wizard({1: dict(id_atleta=1, nome='Teste')})
render_pending_save()
''')
        for key, value in self.state.items():
            app.session_state[key] = value
        with patch.object(save_flow, 'register_prepared_analysis') as register, patch.object(save_flow, 'save_draft') as partial:
            app.run()
            app.button(key='thermal_save_analysis').click().run()
            self.assertFalse(app.exception)
            register.assert_not_called()
            partial.assert_not_called()
            self.assertEqual(app.warning[0].value, 'A análise atual possui etapas pendentes. Deseja salvar mesmo assim?')
            self.assertTrue(any(button.key == 'thermal_save_confirm' for button in app.button))
