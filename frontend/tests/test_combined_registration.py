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
    def script(self):
        return """
import streamlit as st
from datetime import date
from frontend.tests.test_combined_registration import prepared_values
from frontend.streamlit.components.thermography.save_flow import render_save_button, render_pending_save
from frontend.streamlit.components.thermography.draft_state import reset_after_saved_analysis
reset_after_saved_analysis()
if st.session_state.get('thermal_step') == 0:
    render_pending_save()
    st.stop()
st.session_state['thermal_prepared_record'] = {**prepared_values(), 'collected_at': date(2026, 11, 9)}
render_save_button(6)
render_pending_save()
"""

    def test_duplicate_prompts_and_only_overwrites_after_explicit_yes(self):
        from frontend.streamlit.api_client.service_gateway import ApiClientError
        conflict = ApiClientError('Conflito', status_code=409, detail={'code':'analysis_date_conflict'})
        result = {'analysis': {'athlete_id':7, 'id':'saved-id'}, 'inserted_measurements':8}
        with patch.object(registration, 'register_analysis', side_effect=conflict) as create, \
             patch.object(registration, 'save_analysis_changes', return_value=result) as replace:
            app = AppTest.from_string(self.script()).run()
            app.button(key='thermal_save_analysis').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any(w.value == 'Uma análise do atleta já foi realizada nessa data. Deseja sobrescrevê-la?' for w in app.warning))
            replace.assert_not_called()
            app.button(key='thermal_save_cancel').click().run()
            self.assertNotIn('thermal_registered_analysis', app.session_state)
            replace.assert_not_called()
            app.button(key='thermal_save_analysis').click().run()
            app.button(key='thermal_save_confirm').click().run()
            self.assertFalse(app.exception)
            replace.assert_called_once()
            self.assertTrue(replace.call_args.kwargs['overwrite'])
            self.assertEqual(create.call_count, 2)
            self.assertEqual(app.session_state['thermal_step'], 0)
            self.assertEqual(app.toast[0].value, 'Análise salva. Você poderá visualizá-la em Ver análises anteriores.')

    def test_save_uses_summary_date_without_a_date_popup_and_keeps_errors_retryable(self):
        result = {'analysis': {'athlete_id': 7, 'id': 'saved-id'}, 'inserted_measurements': 8}
        with patch.object(registration, 'register_analysis', side_effect=ValueError('Falha simulada')) as request:
            app = AppTest.from_string(self.script()).run()
            app.button(key='thermal_save_analysis').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any('Falha simulada' in error.value for error in app.error))
            self.assertFalse(app.date_input)
            request.side_effect = None
            request.return_value = result
            app.button(key='thermal_save_analysis').click().run()
            self.assertFalse(app.exception)
            self.assertNotIn('thermal_registered_analysis', app.session_state)
            self.assertNotIn('thermal_edit_source', app.session_state)
            self.assertNotIn('thermal_metadata_sync', app.session_state)
            self.assertEqual(app.session_state['thermal_step'], 0)
            self.assertEqual(app.toast[0].value, 'Análise salva. Você poderá visualizá-la em Ver análises anteriores.')
            self.assertEqual(request.call_args.args[2], date(2026, 11, 9))
            self.assertFalse(app.date_input)

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
        from frontend.streamlit.components.thermography import save_flow
        state = {'thermography_timeline_ti': 'old-id'}
        with patch.object(save_flow.st, 'session_state', state), \
             patch.object(registration, 'register_analysis', side_effect=ValueError('Coleta duplicada')) as request:
            result = save_flow._attempt(dict(kind='complete', values={**prepared_values(), 'collected_at':date(2026,11,10)}))
        self.assertFalse(result)
        request.assert_called_once()
        self.assertEqual(state['thermography_timeline_ti'], 'old-id')
        self.assertNotIn('thermal_registered_analysis', state)
        self.assertEqual(state['thermal_save_error'], 'Coleta duplicada')
        self.assertNotIn('thermal_reset_after_save', state)
        self.assertNotIn('thermography_saved_notice', state)
