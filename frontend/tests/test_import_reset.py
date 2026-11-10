from contextlib import ExitStack
from copy import deepcopy
from io import BytesIO
from textwrap import dedent
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from frontend.streamlit.api_client.contracts import EXTRACTION_VERSION
from frontend.streamlit.components import import_reset


CONFIG = {
    'gps': dict(module='frontend.streamlit.components.gps_import_ui',
                app='from frontend.streamlit.components.gps_import_ui import render_gps_import\nrender_gps_import()',
                documents='gps_extraction_documents', uploader='gps_pdf_uploads',
                extracted=[dict(arquivo='gps.pdf', versao_extrator=EXTRACTION_VERSION,
                                origem_metadados='cabecalho_pagina', tabelas=[], paginas_analisadas=[1])],
                extract='extract_uploaded_pdfs', extract_label='Extrair dados',
                validate='preview_gps_payload', send='import_gps_payload'),
    'jump': dict(module='frontend.streamlit.components.jump_crud_ui',
                 app='from frontend.streamlit.components.jump_crud_ui import _render_import\n_render_import([])',
                 documents='jump_import_documents', uploader='jump_xlsx_uploads',
                 extracted=[dict(arquivo='saltos.xlsx', linhas=[])],
                 extract='extract_jump_workbooks', extract_label='Extrair planilhas',
                 validate='preview_jump_payload', send='import_jump_payload'),
}


class ImportResetTests(unittest.TestCase):
    def test_opening_dialog_reruns_only_clear_fragment(self):
        # AppTest.button.run() normalmente recria o runner inteiro. Solicitar o
        # rerun no mesmo runner reproduz o clique fragmentado feito no navegador.
        for kind, config in CONFIG.items():
            with self.subTest(kind=kind), ExitStack() as stack:
                validate, send = self.mock_services(stack, kind)
                script = (
                    'import streamlit as st\n'
                    "st.session_state['page_runs'] = st.session_state.get('page_runs', 0) + 1\n"
                    + config['app'] + '\n'
                    + dedent(f'''
                        from streamlit.runtime.scriptrunner import get_script_run_ctx
                        from streamlit.runtime.scriptrunner_utils.script_requests import RerunData
                        from streamlit.proto.WidgetStates_pb2 import WidgetStates
                        ctx = get_script_run_ctx()
                        states = ctx.session_state.get_widget_states()
                        button = next(state for state in states if state.id.endswith('-{kind}_clear_extraction'))
                        metadata = ctx.session_state._state._new_widget_state.widget_metadata[button.id]
                        assert metadata.fragment_id is not None
                        button.trigger_value = True
                        ctx.script_requests.request_rerun(RerunData(
                            widget_states=WidgetStates(widgets=states),
                            fragment_id_queue=[metadata.fragment_id],
                            is_fragment_scoped_rerun=True,
                        ))
                        st.empty()
                    ''')
                )
                app = AppTest.from_string(script)
                app.session_state[config['documents']] = self.fixtures(kind)[config['documents']]
                app.run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertEqual(app.session_state['page_runs'], 1)
                self.assertIsNotNone(app.button(key=f'{kind}_clear_confirm'))
                validate.assert_not_called()
                send.assert_not_called()

    def fixtures(self, kind):
        config = CONFIG[kind]
        if kind == 'gps':
            return dict(gps_extraction_documents=[dict(arquivo='antigo.pdf', versao_extrator=0)],
                        gps_extraction_revision=7, gps_extraction_edited={0: [{'atleta': 'Editado'}]},
                        gps_import_validation={'signature': 'old'}, gps_import_results=['old'],
                        gps_editor_7_0={'edited_rows': {0: {'atleta': 'Editado'}}})
        return {config['documents']: [dict(arquivo='saltos.xlsx', linhas=[])],
                'jump_import_revision': 7, 'jump_import_validation': {'signature': 'old'},
                'jump_import_result': {'old': True}, 'jump_import_editor_7': {'edited_rows': {}}}

    def mock_services(self, stack, kind):
        config = CONFIG[kind]
        stack.enter_context(patch('psycopg2.connect', side_effect=AssertionError('Sem acesso ao banco')))
        stack.enter_context(patch(f"{config['module']}.load_athletes", return_value=[]))
        validate = stack.enter_context(patch(f"{config['module']}.{config['validate']}"))
        send = stack.enter_context(patch(f"{config['module']}.{config['send']}"))
        return validate, send

    def test_clear_button_appears_only_after_extraction(self):
        for kind, config in CONFIG.items():
            with self.subTest(kind=kind), ExitStack() as stack:
                self.mock_services(stack, kind)
                app = AppTest.from_string(config['app']).run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertFalse(any(button.label == 'Limpar dados extraídos' for button in app.button))
                # Também é possível descartar uma extração vazia.
                app.session_state[config['documents']] = []
                app.run()
                self.assertIsNotNone(app.button(key=f'{kind}_clear_extraction'))

    def test_clear_is_in_column_left_of_validation(self):
        for kind, config in CONFIG.items():
            with self.subTest(kind=kind), ExitStack() as stack:
                self.mock_services(stack, kind)
                app = AppTest.from_string(config['app'])
                if kind == 'gps':
                    document = deepcopy(config['extracted'][0])
                    document['tabelas'] = [{'linhas': [{'_arquivo': 'gps.pdf', 'dados': {'Nome': 'CAIO'}}]}]
                    stack.enter_context(patch(
                        f"{config['module']}.extracted_rows_to_gps_view",
                        return_value=[{'nome_reconhecido': 'CAIO', 'jogador': None,
                                       'athlete_id': None, 'distance_km': 5.2}],
                    ))
                else:
                    document = dict(arquivo='saltos.xlsx', linhas=[
                        dict(arquivo='saltos.xlsx', aba='Saltos', linha=2,
                             nome_reconhecido='CAIO', jogador=None, athlete_id=None)
                    ])
                app.session_state[config['documents']] = [document]
                app.run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                columns = app.get('column')
                clear_index = next(i for i, column in enumerate(columns)
                                   if any(button.label == 'Limpar dados extraídos'
                                          for button in column.get('button')))
                validate_index = next(i for i, column in enumerate(columns)
                                      if any(button.label == 'Validar para envio'
                                             for button in column.get('button')))
                self.assertEqual(validate_index, clear_index + 1)

    def test_cancel_keeps_extraction_edits_and_upload_widget(self):
        for kind, config in CONFIG.items():
            with self.subTest(kind=kind), ExitStack() as stack:
                validate, send = self.mock_services(stack, kind)
                app = AppTest.from_string(config['app'])
                state = self.fixtures(kind)
                for key, value in state.items():
                    app.session_state[key] = deepcopy(value)
                app.run()
                original_upload = app.get('file_uploader')[0].proto.id
                app.button(key=f'{kind}_clear_extraction').click().run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                for key, value in state.items():
                    self.assertEqual(app.session_state[key], value)
                app.button(key=f'{kind}_clear_cancel').click().run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                for key, value in state.items():
                    self.assertEqual(app.session_state[key], value)
                self.assertEqual(app.get('file_uploader')[0].proto.id, original_upload)
                self.assertFalse(any(button.key == f'{kind}_clear_confirm' for button in app.button))
                validate.assert_not_called()
                send.assert_not_called()

    def test_confirm_discards_draft_resets_upload_and_allows_new_extraction(self):
        for kind, config in CONFIG.items():
            with self.subTest(kind=kind), ExitStack() as stack:
                validate, send = self.mock_services(stack, kind)
                app = AppTest.from_string(config['app'])
                state = self.fixtures(kind)
                for key, value in state.items():
                    app.session_state[key] = deepcopy(value)
                app.session_state['thermal_draft'] = {'player': 42}
                app.run()
                original_upload = app.get('file_uploader')[0].proto.id
                app.button(key=f'{kind}_clear_extraction').click().run()
                app.button(key=f'{kind}_clear_confirm').click().run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                for key in state:
                    self.assertNotIn(key, app.session_state)
                self.assertEqual(app.session_state['thermal_draft'], {'player': 42})
                self.assertEqual(app.session_state[f'{kind}_upload_generation'], 1)
                self.assertNotEqual(app.get('file_uploader')[0].proto.id, original_upload)
                self.assertFalse(any(button.key == f'{kind}_clear_extraction' for button in app.button))
                self.assertTrue(next(button for button in app.button if button.label == config['extract_label']).disabled)
                upload = BytesIO(b'new-file')
                upload.name = 'gps.pdf' if kind == 'gps' else 'saltos.xlsx'
                with patch(f"{config['module']}.st.file_uploader", return_value=[upload]), \
                     patch(f"{config['module']}.{config['extract']}", return_value=config['extracted']) as extract:
                    app.run()
                    next(button for button in app.button if button.label == config['extract_label']).click().run()
                    self.assertEqual(len(app.exception), 0, list(app.exception))
                    extract.assert_called_once()
                    self.assertEqual(app.session_state[config['documents']], config['extracted'])
                validate.assert_not_called()
                send.assert_not_called()

    def test_cleanup_is_scoped_and_repeated_clear_uses_new_upload_key(self):
        for kind in CONFIG:
            with self.subTest(kind=kind):
                other = 'jump' if kind == 'gps' else 'gps'
                state = {**self.fixtures(kind), **self.fixtures(other),
                         'thermal_draft': {'player': 42}, 'jump_create_cmj1': 35.,
                         'player_filter': 7}
                preserved = {key: deepcopy(value) for key, value in state.items()
                             if key not in self.fixtures(kind)}
                with patch.object(import_reset.st, 'session_state', state):
                    import_reset.clear_import(kind)
                    self.assertEqual(import_reset.upload_key(kind, CONFIG[kind]['uploader']), CONFIG[kind]['uploader'] + '_1')
                    import_reset.clear_import(kind)
                    self.assertEqual(import_reset.upload_key(kind, CONFIG[kind]['uploader']), CONFIG[kind]['uploader'] + '_2')
                for key, value in preserved.items():
                    self.assertEqual(state[key], value)
