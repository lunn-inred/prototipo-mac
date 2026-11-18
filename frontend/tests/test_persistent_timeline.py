import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest
from backend.mac_api.main import create_app
from backend.mac_api.repositories import data_repository
from backend.mac_api.modules.thermography.analysis_archive import save_analysis
from backend.tests.test_analysis_archive import example_views


class PersistentTimelineTests(unittest.TestCase):
    def setUp(self):
        import streamlit as st
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)
        self.baselines = {}
        read = patch('frontend.streamlit.components.thermography.timeline.get_baseline',
                     side_effect=lambda athlete: self.baselines.get(athlete))
        def save(athlete, analysis_id):
            self.baselines[athlete] = {'analysis_id': str(analysis_id)}
            return self.baselines[athlete]
        write = patch('frontend.streamlit.components.thermography.timeline.set_baseline', side_effect=save)
        read.start(); write.start()
        self.addCleanup(read.stop); self.addCleanup(write.stop)

    def test_starting_another_analysis_keeps_timeline_player_and_selection(self):
        from frontend.streamlit.components.thermography import wizard
        state = {'thermal_step': 6, 'thermal_draft': {'player': 1},
                 'thermography_timeline_player': 1, 'thermography_timeline_t0': 'basal',
                 'thermography_timeline_ti': 'current'}
        with patch.object(wizard.st, 'session_state', state), \
             patch.object(wizard.st, 'warning'), \
             patch.object(wizard.st, 'button', side_effect=lambda label, **kwargs: label == 'Confirmar nova análise'), \
             patch.object(wizard.st, 'rerun', side_effect=RuntimeError('rerun solicitado')):
            with self.assertRaisesRegex(RuntimeError, 'rerun solicitado'):
                wizard.restart_analysis.__wrapped__()
        self.assertNotIn('thermal_draft', state)
        self.assertEqual(state['thermography_timeline_player'], 1)
        self.assertEqual(state['thermography_timeline_t0'], 'basal')
        self.assertEqual(state['thermography_timeline_ti'], 'current')

    def test_add_to_timeline_saves_through_http_without_database(self):
        from frontend.streamlit.components.thermography import timeline
        with TemporaryDirectory(prefix='mac-timeline-save-') as directory, \
             patch.dict(os.environ, MAC_ANALYSES_DIR=directory):
            client = TestClient(create_app())
            def http(method, url, **kwargs):
                kwargs.pop('timeout', None)
                return client.request(method, urlsplit(url).path, **kwargs)
            sources = example_views()
            views = {view: dict(signature=view, image=source['image'], name=f'{view}.jpeg')
                     for view, source in sources.items()}
            items = {f'{view}:{view}': dict(minimum_temperature=20., maximum_temperature=40.,
                      image_rotation=90, part_settings_v4=source['part_settings'],
                      analysis=dict(threshold=34., boxes=source['boxes'], temperatures=source['temperatures'], masks=source['segmentation_masks']))
                     for view, source in sources.items()}
            state = {}
            with patch('frontend.streamlit.api_client.service_gateway._http_request', side_effect=http), \
                 patch.object(timeline.st, 'session_state', state), \
                 patch('psycopg2.connect', side_effect=AssertionError('Sem banco')):
                timeline.add_to_timeline(1,date(2026,10,14),views,items,athlete_name='João',mass=75,pain_score=0,observations='Teste')
            files = list(Path(directory).rglob('metadados.json'))
            self.assertEqual(len(files), 1)
            import json
            metadata = json.loads(files[0].read_text())
            self.assertEqual(metadata['athlete_name'], 'João')
            self.assertIsNone(metadata['pain_score'])
            self.assertIsNone(metadata['regional_eva'])
            self.assertEqual(metadata['analysis_id'], state['thermography_timeline_ti'])

    def test_fresh_session_loads_saved_images_and_compares_basal_current(self):
        with TemporaryDirectory(prefix='mac-timeline-ui-') as directory, \
             patch.dict(os.environ, MAC_ANALYSES_DIR=directory):
            first = save_analysis(athlete_id=1, athlete_name='Teste', collected_at=date(2026,10,1), views=example_views())
            second = save_analysis(athlete_id=1, athlete_name='Teste', collected_at=date(2026,10,14), views=example_views())
            client = TestClient(create_app())
            def http(method, url, **kwargs):
                kwargs.pop('timeout', None)
                parsed = urlsplit(url)
                return client.request(method, parsed.path, **kwargs)
            root = Path(__file__).resolve().parents[2]
            with patch.object(data_repository, 'list_athletes', return_value=[dict(id_atleta=1,nome='Teste',apelido=None)]), \
                 patch('frontend.streamlit.api_client.service_gateway._http_request', side_effect=http):
                app = AppTest.from_file(str(root/'frontend/streamlit/pages/Timeline_Termo.py'), default_timeout=30).run()
                app.selectbox(key='thermography_timeline_player').set_value(1).run()
                self.assertFalse(any(widget.key == 'thermography_player' for widget in app.selectbox))
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertEqual(len(app.session_state['thermography_timeline']), 2)
                self.assertEqual(app.session_state['thermography_timeline_t0'], first['id'])
                self.assertEqual(app.session_state['thermography_timeline_ti'], second['id'])
                self.assertEqual(app.slider(key='timeline_comparison_gamma_front').value, 0.5)
                self.assertEqual(app.slider(key='timeline_comparison_gamma_back').value, 0.5)
                self.assertFalse(any('Limiar' in slider.label for slider in app.slider))
                self.assertFalse(any('Novos:' in text.value for text in app.caption))
                self.assertFalse(any('Amarelo: persistentes' in text.value for text in app.caption))
                self.assertEqual(len([button for button in app.button if button.label == 'Mudar Basal']), 2)
                self.assertEqual(app.select_slider(key='thermography_timeline_date_1').value, date(2026, 10, 14))
                app.select_slider(key='thermography_timeline_date_1').set_value(date(2026, 10, 1)).run()
                self.assertEqual(app.session_state['thermography_timeline_ti'], first['id'])
                self.assertEqual(app.session_state['thermography_timeline_t0'], first['id'])
                app.button(key='timeline_change_basal').click().run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                card = app.button(key=f'timeline_basal_{second["id"]}')
                self.assertIn('![Frente](data:image/png;base64,', card.label)
                self.assertIn('![Costas](data:image/png;base64,', card.label)
                self.assertIn('**14/10/2026**', card.label)
                self.assertFalse(any(button.label == 'Selecionar' for button in app.button))
                app.button(key=f'timeline_basal_{second["id"]}').click().run()
                self.assertEqual(app.session_state['thermography_timeline_t0'], second['id'])
                self.assertEqual(app.session_state['thermography_timeline_ti'], first['id'])
                self.assertFalse(any(button.key == f'timeline_basal_{second["id"]}' for button in app.button))
                app.select_slider(key='thermography_timeline_date_1').set_value(date(2026, 10, 14)).run()
                self.assertEqual(app.session_state['thermography_timeline_ti'], second['id'])
                self.assertEqual(app.session_state['thermography_timeline_t0'], second['id'])
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertEqual(len(app.error), 0, list(app.error))
                self.assertTrue(any('Comparação Basal × Atual' in text.value for text in app.markdown))
                self.assertEqual(len(list(Path(directory).rglob('metadados.json'))), 2)
                # Limpar um rascunho não deve limpar o filtro próprio da timeline.
                app.session_state['thermal_draft'] = {}
                app.run()
                self.assertEqual(app.selectbox(key='thermography_timeline_player').value, 1)
                self.assertEqual(len(app.session_state['thermography_timeline']), 2)

    def test_same_day_uses_last_registered_analysis(self):
        from frontend.streamlit.components.thermography.timeline import _analyses_by_date
        entries = [
            dict(id='new', collected_at=date(2026, 10, 14), sequence=30),
            dict(id='first', collected_at=date(2026, 10, 1), sequence=10),
            dict(id='old', collected_at=date(2026, 10, 14), sequence=20),
        ]
        by_date = _analyses_by_date(entries)
        self.assertEqual(list(by_date), [date(2026, 10, 1), date(2026, 10, 14)])
        self.assertEqual(by_date[date(2026, 10, 14)]['id'], 'new')

    def test_single_date_empty_history_and_player_switch(self):
        from frontend.streamlit.components.thermography import timeline
        entries = [dict(id='first', athlete_id=1, collected_at=date(2026, 10, 1), sequence=10)]
        athletes = [dict(id_atleta=i, nome=f'Jogador {i}') for i in (1, 2, 3)]
        other_entries = [dict(id='other', athlete_id=2, collected_at=date(2026, 10, 5), sequence=20)]
        root = Path(__file__).resolve().parents[2]
        with patch('frontend.streamlit.presentation.thermography_data.load_thermography_athletes', return_value=athletes), \
             patch.object(timeline, 'list_local_analyses', side_effect=lambda player: {1: entries, 2: other_entries, 3: []}[player]), \
             patch.object(timeline, '_render_comparison') as comparison:
            app = AppTest.from_file(str(root/'frontend/streamlit/pages/Timeline_Termo.py')).run()
            app.selectbox(key='thermography_timeline_player').set_value(1).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(len(app.select_slider), 0)
            comparison.assert_called_with(entries[0], entries[0])
            app.selectbox(key='thermography_timeline_player').set_value(2).run()
            comparison.assert_called_with(other_entries[0], other_entries[0])
            self.assertEqual(app.session_state['thermography_timeline_t0'], 'other')
            app.selectbox(key='thermography_timeline_player').set_value(3).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertNotIn('thermography_timeline_t0', app.session_state)
            self.assertNotIn('thermography_timeline_ti', app.session_state)

    def test_new_session_restores_saved_baseline_for_each_player(self):
        from frontend.streamlit.components.thermography import timeline
        entries = [dict(id=name, athlete_id=1, collected_at=date(2026, 10, day), sequence=day)
                   for name, day in (('old', 1), ('chosen', 14))]
        athletes = [dict(id_atleta=1, nome='Jogador')]
        root = Path(__file__).resolve().parents[2]
        path = str(root/'frontend/streamlit/pages/Timeline_Termo.py')
        with patch('frontend.streamlit.presentation.thermography_data.load_thermography_athletes', return_value=athletes), \
             patch.object(timeline, 'list_local_analyses', return_value=entries), \
             patch.object(timeline, '_render_comparison') as compare:
            self.baselines[1] = {'analysis_id': 'chosen'}
            for _ in range(2):
                app = AppTest.from_file(path).run()
                app.selectbox(key='thermography_timeline_player').set_value(1).run()
                self.assertFalse(app.exception)
                compare.assert_called_with(entries[1], entries[1])

    def test_failed_baseline_save_keeps_previous_choice(self):
        from frontend.streamlit.components.thermography import timeline
        state = {'thermography_timeline': [dict(id='new', athlete_id=1)],
                 'thermography_timeline_basal_1': 'old', 'thermography_timeline_t0': 'old'}
        with patch.object(timeline.st, 'session_state', state), \
             patch.object(timeline, 'set_baseline', side_effect=ValueError('Falha simulada')):
            timeline._select_baseline('new', 1)
        self.assertEqual(state['thermography_timeline_basal_1'], 'old')
        self.assertEqual(state['thermography_timeline_t0'], 'old')
        self.assertIn('escolha anterior', state['thermography_baseline_error'])

    def test_missing_local_baseline_warns_without_overwriting_database(self):
        from frontend.streamlit.components.thermography import timeline
        entries = [dict(id='available', athlete_id=1, collected_at=date(2026, 10, 1), sequence=1)]
        self.baselines[1] = {'analysis_id': 'missing'}
        root = Path(__file__).resolve().parents[2]
        with patch('frontend.streamlit.presentation.thermography_data.load_thermography_athletes',
                   return_value=[dict(id_atleta=1, nome='Teste')]), \
             patch.object(timeline, 'list_local_analyses', return_value=entries), \
             patch.object(timeline, '_render_comparison') as comparison:
            app = AppTest.from_file(str(root/'frontend/streamlit/pages/Timeline_Termo.py')).run()
            app.selectbox(key='thermography_timeline_player').set_value(1).run()
        self.assertFalse(app.exception)
        comparison.assert_called_with(entries[0], entries[0])
        self.assertEqual(self.baselines[1]['analysis_id'], 'missing')
        self.assertTrue(any('referência temporária' in item.value for item in app.warning))
