from datetime import date
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

from frontend.streamlit.components.thermography import registration
from backend.tests.test_analysis_archive import example_views


def prepared_values():
    sources = example_views()
    views, items = {}, {}
    for view, source in sources.items():
        views[view] = {'image': source['image'], 'signature': view, 'name': 'teste.jpg'}
        items[f'{view}:{view}'] = {
            'minimum_temperature': source['minimum_temperature'],
            'maximum_temperature': source['maximum_temperature'],
            'part_settings_v4': source['part_settings'],
            'analysis': {'threshold': source['default_threshold'], 'boxes': source['boxes'],
                         'temperatures': source['temperatures'], 'masks': source['segmentation_masks']},
        }
    return dict(athlete_id=7, athlete_name='Teste', mass=75., pain_score=0,
                observations='', views=views, items=items, pair_signature='pair-test')


class FrontendCombinedRegistrationTests(unittest.TestCase):
    def test_confirmation_keeps_dialog_on_failure_then_registers_selected_date(self):
        script = '''
import streamlit as st
from frontend.tests.test_combined_registration import prepared_values
from frontend.streamlit.components.thermography.registration import confirm_analysis_registration
if st.button('Registrar Análise', key='open_registration'):
    st.session_state['dialog_open'] = True
if st.session_state.get('dialog_open') and not st.session_state.get('thermal_registered_analysis'):
    confirm_analysis_registration(**prepared_values())
'''
        result = {'analysis': {'athlete_id': 7, 'id': 'saved-id'}, 'inserted_measurements': 8}
        with patch.object(registration, 'register_analysis', side_effect=ValueError('Falha simulada')) as request:
            app = AppTest.from_string(script).run()
            app.button(key='open_registration').click().run()
            app.button(key='confirm_analysis_pair-test').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertTrue(any('Falha simulada' in error.value for error in app.error))
            request.side_effect = None
            request.return_value = result
            app.date_input(key='thermal_collection_date_pair-test').set_value(date(2026, 11, 9)).run()
            app.button(key='confirm_analysis_pair-test').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(app.session_state['thermal_registered_analysis']['date'], date(2026, 11, 9))
            self.assertEqual(request.call_args.args[2], date(2026, 11, 9))
            self.assertFalse(any(button.key == 'confirm_analysis_pair-test' for button in app.button))

    def test_one_request_updates_timeline_and_caches_after_success(self):
        state = {'thermography_timeline_date_7': date(2026, 1, 1)}
        result = {'analysis': {'athlete_id': 7, 'id': 'saved-id'}, 'inserted_measurements': 8}
        with patch.object(registration.st, 'session_state', state), \
             patch.object(registration, 'register_analysis', return_value=result) as request, \
             patch.object(registration.load_thermography_history, 'clear') as history, \
             patch.object(registration.load_player_dashboard_data, 'clear') as dashboard:
            registration.register_prepared_analysis(collected_at=date(2026, 11, 10), **prepared_values())
        request.assert_called_once()
        history.assert_called_once()
        dashboard.assert_called_once()
        self.assertEqual(state['thermography_timeline_ti'], 'saved-id')
        self.assertEqual(state['thermography_timeline_player'], 7)
        self.assertNotIn('thermography_timeline_date_7', state)
        self.assertEqual(state['thermal_registered_analysis']['signature'], 'pair-test')
        self.assertIn('banco local e adicionada à timeline', state['thermography_flash'])

    def test_failure_does_not_set_success_or_change_timeline(self):
        state = {'thermography_timeline_ti': 'old-id', 'date-key': date(2026, 11, 10)}
        with patch.object(registration.st, 'session_state', state), \
             patch.object(registration, 'register_analysis', side_effect=ValueError('Coleta duplicada')) as request:
            registration._submit('date-key', prepared_values())
        request.assert_called_once()
        self.assertEqual(state['thermography_timeline_ti'], 'old-id')
        self.assertNotIn('thermal_registered_analysis', state)
        self.assertNotIn('thermography_flash', state)
        self.assertEqual(state['thermal_registration_error'], 'Coleta duplicada')
