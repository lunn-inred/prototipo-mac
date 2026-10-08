import io
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from streamlit.testing.v1 import AppTest

from backend.mac_api.main import create_app
from frontend.streamlit.components.thermography.wizard import cuts_from_objects, rotated_view


class ThermalWizardTests(unittest.TestCase):
    def test_dragged_boundaries_convert_both_directions(self):
        objects = [{'x': x} for x in (45, 57, 88)]
        self.assertEqual(cuts_from_objects(objects, 100, True), [45, 57, 88])
        self.assertEqual(cuts_from_objects(objects, 100, False), [12, 43, 55])
        with self.assertRaises(ValueError):
            cuts_from_objects([{'x': 0}, {'x': 40}, {'x': 40}], 100, True)

    def test_rotation_expands_and_preserves_original(self):
        image = Image.new('RGB', (120, 60))
        buffer = io.BytesIO(); image.save(buffer, format='PNG')
        result, _, _ = rotated_view(buffer.getvalue(), 90)
        self.assertEqual(result.size, (60, 120))

    def test_six_steps_preserve_data_and_reach_review_via_http(self):
        from backend.mac_api.repositories import data_repository
        client = TestClient(create_app())
        def http(method, url, **kwargs):
            kwargs.pop('timeout', None)
            return client.request(method, urlsplit(url).path, **kwargs)
        image = Image.new('RGB', (320, 200), (15, 15, 15))
        draw = ImageDraw.Draw(image)
        draw.ellipse((45, 62, 215, 102), fill=(230, 55, 25))
        draw.ellipse((45, 125, 215, 162), fill=(240, 70, 25))
        for y in range(20, 180):
            draw.line((280, y, 294, y), fill=(255-y, y, 40))
        buffer = io.BytesIO(); image.save(buffer, format='PNG')
        def upload(label, **kwargs):
            if kwargs.get('accept_multiple_files'): return []
            result = io.BytesIO(buffer.getvalue()); result.name = 'teste.png'
            return result
        root = Path(__file__).resolve().parents[2]
        with patch.object(data_repository, 'list_athletes', return_value=[dict(id_atleta=1, nome='Teste', apelido=None)]), \
             patch('frontend.streamlit.api_client.service_gateway.httpx.request', side_effect=http), \
             patch('streamlit.file_uploader', side_effect=upload), \
             patch('frontend.streamlit.components.thermography.wizard.cached_temperature_scale', return_value=dict(minimum_temperature=20.0, maximum_temperature=40.0)):
            app = AppTest.from_file(str(root/'frontend/streamlit/pages/Termografia.py'), default_timeout=30).run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(app.button(key='thermal_next').disabled)
            app.selectbox(key='thermography_player').set_value(1)
            app.number_input(key='thermography_mass').set_value(75.0)
            app.number_input(key='thermography_pain_score').set_value(0)
            app.run()
            for step in range(1, 6):
                app.button(key='thermal_next').click().run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertEqual(app.session_state['thermal_step'], step)
                if step == 4:
                    key = next(button.key for button in app.button if button.key and button.key.startswith('wizard_parts_front:'))
                    with patch('frontend.streamlit.components.thermography.wizard.st_canvas', return_value=SimpleNamespace(json_data=None)) as canvas:
                        app.button(key=key).click().run()
                        self.assertEqual(len(app.exception), 0, list(app.exception))
                        scene = canvas.call_args.kwargs['initial_drawing']
                        self.assertEqual(len(scene['objects']), 3)
                        self.assertEqual(scene['objects'][0]['dragConstraint']['axis'], {'x': 0, 'y': 1})
                        next(button for button in app.button if button.label == 'Concluir').click().run()
            self.assertIn('Resumo da coleta', [h.value for h in app.subheader])
            self.assertFalse(app.button(key='save_image_thermography').disabled)
            for _ in range(5):
                app.button(key='thermal_previous').click().run()
            self.assertEqual(app.number_input(key='thermography_mass').value, 75.0)
            self.assertEqual(app.number_input(key='thermography_pain_score').value, 0)
            self.assertEqual(app.selectbox(key='thermography_player').value, 1)
