import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from PIL import Image
import streamlit as st
from streamlit.testing.v1 import AppTest
from fastapi.testclient import TestClient
from backend.mac_api.main import create_app
from backend.mac_api.modules.thermography import drafts
from frontend.streamlit.components.thermography import history


class ThermalDraftFlowTests(unittest.TestCase):
    def setUp(self):
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)
        self.directory = TemporaryDirectory(prefix='mac-draft-ui-')
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        env = patch.dict(os.environ, MAC_ANALYSES_DIR=str(root / 'analyses'), MAC_BACKUPS_DIR=str(root / 'backups'), MAC_API_KEY='draft-ui')
        env.start(); self.addCleanup(env.stop)
        self.client = TestClient(create_app())
        def http(method, url, **kwargs):
            kwargs.pop('timeout', None)
            return self.client.request(method, urlsplit(url).path, **kwargs)
        for mock in (patch('frontend.streamlit.api_client.service_gateway._http_request', side_effect=http),
                     patch('psycopg2.connect', side_effect=AssertionError('Rascunho sem atleta não usa SQL'))):
            mock.start(); self.addCleanup(mock.stop)
        self.script = '''
from frontend.streamlit.components.thermography.wizard import render_wizard
from frontend.streamlit.components.thermography.save_flow import render_pending_save
render_wizard({})
render_pending_save()
'''

    def test_save_without_player_shows_once_only_toast_and_does_not_persist(self):
        app = AppTest.from_string(self.script).run()
        self.assertTrue(app.button(key='thermal_next').disabled)
        self.assertFalse(app.button(key='thermal_save_analysis').disabled)
        with patch('frontend.streamlit.components.thermography.save_flow.save_draft') as save, \
             patch('frontend.streamlit.components.thermography.save_flow.register_prepared_analysis') as register:
            app.button(key='thermal_save_analysis').click().run()
            save.assert_not_called()
            register.assert_not_called()
        self.assertFalse(app.exception)
        self.assertEqual([message.value for message in app.toast], ['Selecione um jogador antes de salvar a análise.'])
        self.assertFalse(app.warning)
        self.assertFalse(any(button.key == 'thermal_save_confirm' for button in app.button))
        self.assertEqual(drafts.list_saved(), [])
        app.run()
        self.assertFalse(app.toast)

    def test_legacy_unassigned_draft_can_still_be_opened_to_select_a_player(self):
        from backend.tests.test_thermal_drafts import empty_state
        legacy = empty_state(); legacy['draft']['notes'] = 'Continuar amanhã'
        entry = drafts.save(legacy)
        loaded = drafts.load(entry['id'])
        state = {}
        with patch.object(history.st, 'session_state', state):
            history.load_into_wizard(loaded)
        reopened = AppTest.from_string(self.script)
        for key, value in state.items():
            reopened.session_state[key] = value
        reopened.run()
        self.assertFalse(reopened.exception)
        self.assertEqual(reopened.text_area(key='thermography_observations').value, 'Continuar amanhã')
        self.assertEqual(reopened.session_state['thermal_saved_draft']['id'], entry['id'])
        browser = AppTest.from_string('from frontend.streamlit.components.thermography.history import show_history\nshow_history({})').run()
        browser.button(key='analysis_player_0').click().run()
        self.assertFalse(browser.exception)
        label = browser.button(key=f'analysis_select_{entry["id"]}').label
        self.assertIn(':red[Análise incompleta]', label)
        self.assertNotIn('Rascunho incompleto', label)

    def test_opening_partial_analysis_restores_widgets_in_same_session(self):
        script = '''
import streamlit as st
from frontend.streamlit.components.thermography.draft_state import reset_after_saved_analysis
from frontend.streamlit.components.thermography.history import load_into_wizard
from frontend.streamlit.components.thermography.wizard import render_wizard
from frontend.streamlit.components.thermography.save_flow import render_pending_save
reset_after_saved_analysis()
st.button('Abrir registro de teste', key='fixture_open', on_click=load_into_wizard,
          args=(st.session_state['fixture_entry'],))
render_wizard({1: dict(id_atleta=1, nome='Salvo'), 2: dict(id_atleta=2, nome='Anterior')})
render_pending_save()
'''
        for initial in ('empty_after_save', 'previous_player', 'saved_missing_fields'):
            with self.subTest(initial=initial):
                draft = dict(player=1, mass=72.5, pain=0, notes='Registro salvo', collected_at='2026-11-12')
                if initial == 'saved_missing_fields':
                    draft.update(mass=None, pain=None, notes='')
                entry = dict(id='partial-fixture', created_at='2026-11-12T00:00:00+00:00', is_draft=True,
                             state=dict(step=0, draft=draft, uploads={}, items={}, source=None))
                app = AppTest.from_string(script)
                app.session_state['fixture_entry'] = entry
                app.session_state['thermal_reset_after_save'] = True
                app.run()
                if initial != 'empty_after_save':
                    app.selectbox(key='thermography_player').set_value(2)
                    app.number_input(key='thermography_mass').set_value(80.)
                    app.number_input(key='thermography_pain_score').set_value(9)
                    app.text_area(key='thermography_observations').set_value('Não reutilizar').run()
                app.button(key='fixture_open').click().run()
                self.assertFalse(app.exception)
                self.assertFalse(app.warning)
                widgets = [app.selectbox(key='thermography_player'), app.number_input(key='thermography_mass'),
                           app.number_input(key='thermography_pain_score'), app.text_area(key='thermography_observations')]
                self.assertEqual([widget.value for widget in widgets], [draft[key] for key in ('player','mass','pain','notes')])
                self.assertTrue(all(widget.proto.set_value for widget in widgets))
                self.assertEqual(app.session_state['thermal_saved_draft']['id'], entry['id'])
                app.run()
                self.assertEqual(app.number_input(key='thermography_mass').value, draft['mass'])
                self.assertEqual(app.number_input(key='thermography_pain_score').value, draft['pain'])

    def test_single_image_is_saved_before_uploading_the_other_view(self):
        buffer = io.BytesIO(); Image.new('RGB', (8, 12), 'red').save(buffer, format='PNG')
        app = AppTest.from_string(self.script)
        app.session_state['thermal_step'] = 1
        app.session_state['thermal_draft'] = dict(player=1)
        app.session_state['thermal_uploads'] = dict(front=dict(name='frente.png', content=buffer.getvalue(), rotation=90))
        app.run()
        self.assertTrue(app.button(key='thermal_next').disabled)
        with patch('frontend.streamlit.components.thermography.save_flow.save_draft',
                   return_value=dict(id='partial-test', created_at='2026-11-12T00:00:00+00:00', athlete_id=1)) as save:
            app.button(key='thermal_save_analysis').click().run()
            app.button(key='thermal_save_confirm').click().run()
            state = save.call_args.args[0]
        self.assertFalse(app.exception)
        self.assertEqual(set(state['uploads']), {'front'})
        self.assertEqual(state['uploads']['front']['rotation'], 90)
        self.assertEqual(app.session_state['thermal_step'], 0)
        self.assertNotIn('thermal_uploads', app.session_state)
        self.assertNotIn('thermography_items', app.session_state)
        self.assertNotIn('thermal_saved_draft', app.session_state)
        self.assertEqual(app.session_state['thermal_upload_generation'], 1)
        self.assertIsNone(app.selectbox(key='thermography_player').value)
        self.assertIsNone(app.number_input(key='thermography_mass').value)
        self.assertIsNone(app.number_input(key='thermography_pain_score').value)
        self.assertEqual(app.text_area(key='thermography_observations').value, '')
        self.assertFalse(app.success)
        self.assertEqual(app.toast[0].value, 'Análise parcial salva. Você poderá visualizá-la em Ver análises anteriores.')
        app.run()
        self.assertFalse(app.toast)

    def test_failed_partial_save_preserves_the_analysis_and_allows_retry(self):
        from frontend.streamlit.api_client.service_gateway import ApiClientError
        script = self.script.replace('render_wizard({})', "render_wizard({1: dict(id_atleta=1, nome='Teste')})")
        app = AppTest.from_string(script).run()
        app.selectbox(key='thermography_player').set_value(1)
        app.text_area(key='thermography_observations').set_value('Preservar ao falhar').run()
        with patch('frontend.streamlit.components.thermography.save_flow.save_draft',
                   side_effect=ApiClientError('Falha simulada', status_code=503)) as save:
            app.button(key='thermal_save_analysis').click().run()
            app.button(key='thermal_save_confirm').click().run()
            self.assertFalse(app.exception)
            self.assertTrue(app.error)
            self.assertFalse(app.toast)
            self.assertEqual(app.session_state['thermal_draft']['notes'], 'Preservar ao falhar')
            self.assertEqual(app.session_state['thermal_draft']['player'], 1)
            self.assertNotIn('thermal_reset_after_save', app.session_state)
            save.side_effect = None
            save.return_value = dict(id='partial-test', created_at='2026-11-12T00:00:00+00:00', athlete_id=1)
            app.button(key='thermal_save_confirm').click().run()
            self.assertFalse(app.exception)
            self.assertEqual(save.call_count, 2)
            self.assertIsNone(app.selectbox(key='thermography_player').value)
            self.assertEqual(app.text_area(key='thermography_observations').value, '')
            self.assertEqual(app.toast[0].value, 'Análise parcial salva. Você poderá visualizá-la em Ver análises anteriores.')

    def test_partial_save_on_first_step_explicitly_clears_browser_widget_values(self):
        script = self.script.replace('render_wizard({})', "render_wizard({1: dict(id_atleta=1, nome='Teste')})")
        app = AppTest.from_string(script).run()
        app.selectbox(key='thermography_player').set_value(1)
        app.number_input(key='thermography_mass').set_value(75.)
        app.number_input(key='thermography_pain_score').set_value(3)
        app.text_area(key='thermography_observations').set_value('Análise de teste').run()
        with patch('frontend.streamlit.components.thermography.save_flow.save_draft',
                   return_value=dict(id='partial-test', created_at='2026-11-12T00:00:00+00:00', athlete_id=1)) as save:
            app.button(key='thermal_save_analysis').click().run()
            app.button(key='thermal_save_confirm').click().run()
            self.assertEqual(save.call_args.args[0]['draft']['mass'], 75.)
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['thermal_step'], 0)
        widgets = [app.selectbox(key='thermography_player'), app.number_input(key='thermography_mass'),
                   app.number_input(key='thermography_pain_score'), app.text_area(key='thermography_observations')]
        for widget in widgets:
            with self.subTest(widget=widget.key):
                # Não basta o Python estar vazio: o navegador deve receber a ordem de limpar.
                self.assertTrue(widget.proto.set_value)
        self.assertEqual([widget.value for widget in widgets], [None, None, None, ''])
        self.assertEqual(app.toast[0].value, 'Análise parcial salva. Você poderá visualizá-la em Ver análises anteriores.')

    def test_return_to_first_step_preserves_images_and_filled_metadata(self):
        buffer = io.BytesIO(); Image.new('RGB', (8, 12), 'red').save(buffer, format='PNG')
        app = AppTest.from_string(self.script)
        app.session_state['thermal_step'] = 1
        app.session_state['thermal_draft'] = dict(player=None, mass=75., pain=2, notes='Não perder')
        upload = dict(name='frente.png', content=buffer.getvalue(), rotation=90)
        app.session_state['thermal_uploads'] = dict(front=upload)
        app.run()
        with patch('frontend.streamlit.components.thermography.save_flow.save_draft') as save:
            app.button(key='thermal_save_analysis').click().run()
            save.assert_not_called()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['thermal_step'], 0)
        self.assertEqual(app.session_state['thermal_uploads']['front'], upload)
        self.assertEqual(app.number_input(key='thermography_mass').value, 75.)
        self.assertEqual(app.number_input(key='thermography_pain_score').value, 2)
        self.assertEqual(app.text_area(key='thermography_observations').value, 'Não perder')
        self.assertEqual(app.toast[0].value, 'Selecione um jogador antes de salvar a análise.')

    def test_selected_player_with_pending_fields_still_gets_confirmation(self):
        script = self.script.replace('render_wizard({})', "render_wizard({1: dict(id_atleta=1, nome='Teste')})")
        app = AppTest.from_string(script).run()
        app.selectbox(key='thermography_player').set_value(1).run()
        with patch('frontend.streamlit.components.thermography.save_flow.save_draft') as save:
            app.button(key='thermal_save_analysis').click().run()
            self.assertFalse(app.exception)
            self.assertFalse(app.toast)
            self.assertEqual(app.warning[0].value, 'A análise atual possui etapas pendentes. Deseja salvar mesmo assim?')
            self.assertEqual([button.label for button in app.button[-2:]], ['Não, voltar', 'Salvar mesmo assim'])
            app.button(key='thermal_save_cancel').click().run()
            save.assert_not_called()

    def test_player_removed_in_summary_does_not_use_stale_first_step_selection(self):
        from frontend.tests.test_combined_registration import prepared_values
        app = AppTest.from_string('''
from frontend.streamlit.components.thermography.save_flow import render_save_button, render_pending_save
render_save_button(6)
render_pending_save()
''')
        app.session_state['thermal_step'] = 6
        app.session_state['thermal_draft'] = dict(player=1)
        app.session_state['thermal_prepared_record'] = {**prepared_values(), 'athlete_id': None}
        app.run()
        with patch('frontend.streamlit.components.thermography.save_flow.save_draft') as save, \
             patch('frontend.streamlit.components.thermography.save_flow.register_prepared_analysis') as register:
            app.button(key='thermal_save_analysis').click().run()
            save.assert_not_called()
            register.assert_not_called()
        self.assertFalse(app.exception)
        self.assertEqual(app.session_state['thermal_step'], 0)
        self.assertEqual(app.toast[0].value, 'Selecione um jogador antes de salvar a análise.')
        self.assertFalse(any(button.key == 'thermal_save_confirm' for button in app.button))
