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
            with patch('frontend.streamlit.api_client.service_gateway.httpx.request', side_effect=http), \
                 patch.object(timeline.st, 'session_state', state), \
                 patch('psycopg2.connect', side_effect=AssertionError('Sem banco')):
                timeline.add_to_timeline(1,date(2026,10,14),views,items,athlete_name='João',mass=75,pain_score=0,observations='Teste')
            files = list(Path(directory).rglob('metadados.json'))
            self.assertEqual(len(files), 1)
            import json
            metadata = json.loads(files[0].read_text())
            self.assertEqual(metadata['athlete_name'], 'João')
            self.assertEqual(metadata['pain_score'], 0)
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
                 patch('frontend.streamlit.api_client.service_gateway.httpx.request', side_effect=http):
                app = AppTest.from_file(str(root/'frontend/streamlit/pages/Termografia.py'), default_timeout=30).run()
                app.selectbox(key='thermography_timeline_player').set_value(1).run()
                self.assertIsNone(app.selectbox(key='thermography_player').value)
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertEqual(len(app.session_state['thermography_timeline']), 2)
                app.button(key=f'timeline_entry_{first["id"]}_t0').click().run()
                app.radio(key='thermography_timeline_role_v2').set_value('Atual').run()
                app.button(key=f'timeline_entry_{second["id"]}_ti').click().run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertEqual(len(app.error), 0, list(app.error))
                self.assertTrue(any('Comparação Basal × Atual' in text.value for text in app.markdown))
                self.assertEqual(len(list(Path(directory).rglob('metadados.json'))), 2)
                # Limpar um rascunho não deve limpar o filtro próprio da timeline.
                app.session_state['thermal_draft'] = {}
                app.run()
                self.assertEqual(app.selectbox(key='thermography_timeline_player').value, 1)
                self.assertEqual(len(app.session_state['thermography_timeline']), 2)
