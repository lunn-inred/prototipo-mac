"""End-to-end Streamlit/API tests against only the disposable local database."""
import io
import hashlib
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from streamlit.testing.v1 import AppTest

from backend.mac_api.main import create_app
from backend.mac_api.core.database import database_config, database_write_connection


@unittest.skipUnless(os.getenv('MAC_TEST_DB_ENABLED') == '1', 'PostgreSQL local não habilitado')
class WebUiIntegrationTests(unittest.TestCase):
    def setUp(self):
        config = database_config()
        self.assertIn(config['host'], ('127.0.0.1', 'localhost'))
        self.assertEqual(config['dbname'], 'mac_test')
        # Seed every chart metric so tests exercise populated pages, not only
        # their empty-state messages. This runs solely in the guarded test DB.
        from backend.mac_api.modules.gps.gps_import_service import GPS_METRIC_VIEW_COLUMNS
        with database_write_connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT id_atleta FROM public.atleta ORDER BY id_atleta LIMIT 1")
            row = cursor.fetchone()
            if row is None:
                cursor.execute("INSERT INTO public.atleta(nome,posicao) VALUES ('Atleta UI','Meia') RETURNING id_atleta")
                row = cursor.fetchone()
            athlete_id = row[0]
            cursor.execute("SELECT id_medida FROM public.medida WHERE nome='MAIOR_CMJ'")
            metric_id = cursor.fetchone()[0]
            cursor.execute("SELECT 1 FROM public.medida_valor WHERE id_atleta=%s AND id_medida=%s", (athlete_id,metric_id))
            if cursor.fetchone() is None:
                cursor.execute("INSERT INTO public.medida_valor(id_atleta,id_medida,valor,data) VALUES (%s,%s,31,%s)", (athlete_id,metric_id,date.today()))
            for name in GPS_METRIC_VIEW_COLUMNS:
                cursor.execute("SELECT id_medida FROM public.medida WHERE nome=%s AND id_grupo_medida=3", (name,))
                metric = cursor.fetchone()
                if metric is None:
                    cursor.execute("INSERT INTO public.medida(nome,id_grupo_medida) VALUES (%s,3) RETURNING id_medida", (name,))
                    metric = cursor.fetchone()
                    cursor.execute("INSERT INTO public.medida_valor(id_atleta,id_medida,valor,data) VALUES (%s,%s,2.4,%s)", (athlete_id,metric[0],date.today()))
        self.client = TestClient(create_app())
        self.root = Path(__file__).resolve().parents[2]

    def http(self, method, url, **kwargs):
        kwargs.pop('timeout', None)
        parsed = urlsplit(url)
        return self.client.request(method, parsed.path + ('?' + parsed.query if parsed.query else ''), **kwargs)

    def test_all_pages_render_via_http_without_direct_database_access(self):
        for filename in ('Jogadores.py','Metricas_de_Salto.py','Monitoramento_GPS.py','Termografia.py'):
            with self.subTest(filename=filename), patch('frontend.streamlit.api_client.service_gateway.httpx.request', side_effect=self.http):
                app = AppTest.from_file(str(self.root/'frontend/streamlit/pages'/filename), default_timeout=30).run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertFalse(any('Não foi possível carregar' in error.value for error in app.error))

    def test_thermal_uploads_render_masks_parts_and_pair_summary(self):
        image = Image.new('RGB', (320, 200), (15, 15, 15))
        draw = ImageDraw.Draw(image)
        draw.ellipse((45, 62, 215, 102), fill=(230, 55, 25))
        draw.ellipse((45, 125, 215, 162), fill=(240, 70, 25))
        for y in range(20, 180):
            draw.line((280, y, 294, y), fill=(255-y, y, 40))
        buffer = io.BytesIO(); image.save(buffer, format='PNG')
        def uploads(label, **kwargs):
            if kwargs.get('accept_multiple_files'): return []
            upload = io.BytesIO(buffer.getvalue()); upload.name = 'teste.png'
            return upload
        with patch('frontend.streamlit.api_client.service_gateway.httpx.request', side_effect=self.http), patch('streamlit.file_uploader', side_effect=uploads):
            app = AppTest.from_file(str(self.root/'frontend/streamlit/pages/Termografia.py'), default_timeout=60).run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            athletes = self.client.get('/api/v1/athletes', headers={'X-API-Key': os.environ['MAC_API_KEY']}).json()
            app.selectbox(key='thermography_player').set_value(athletes[0]['id_atleta'])
            app.number_input(key='thermography_mass').set_value(75.0)
            app.number_input(key='thermography_pain_score').set_value(0)
            app.run()
            for _ in range(5):
                app.button(key='thermal_next').click().run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertFalse(any('Não foi possível analisar' in error.value for error in app.error), list(app.error))
            self.assertIn('Resumo da coleta', [header.value for header in app.subheader])
            # AppTest does not reliably execute dialog fragments; exercise the
            # state callback directly, then render its comparison through HTTP.
            from backend.mac_api.modules.thermography.thermography_service import current_sao_paulo_date
            from frontend.streamlit.components.thermography import timeline
            signature = hashlib.sha256(buffer.getvalue()).hexdigest()
            views = {view: {'signature': signature, 'image': image} for view in ('front', 'back')}
            state = {}
            items = app.session_state['thermography_items']
            with patch.object(timeline.st, 'session_state', state):
                timeline.add_to_timeline(athletes[0]['id_atleta'], current_sao_paulo_date(), views,
                                         items)
            for key, value in state.items():
                app.session_state[key] = value
            app.run()
            self.assertEqual(len(app.exception), 0, list(app.exception))
            self.assertEqual(len(app.session_state['thermography_timeline']), 1)
