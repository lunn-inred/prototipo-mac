import io
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import numpy as np
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from streamlit.testing.v1 import AppTest

from backend.mac_api.main import create_app
from frontend.streamlit.components.thermography.wizard import cuts_from_objects, rotated_view, segmented_preview_image


class ThermalWizardTests(unittest.TestCase):
    def test_full_segmentation_preview_keeps_only_mask_pixels(self):
        image = Image.new('RGB', (3, 2), (200, 100, 50))
        right = np.array([[True, False, False], [False, False, False]])
        left = np.array([[False, False, False], [False, False, True]])
        preview = np.asarray(segmented_preview_image(image, {'right': right, 'left': left}))
        np.testing.assert_array_equal(preview[0, 0], [200, 100, 50])
        np.testing.assert_array_equal(preview[1, 2], [200, 100, 50])
        np.testing.assert_array_equal(preview[0, 1], [0, 0, 0])

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
                headers = [header.value for header in app.subheader]
                self.assertLess(headers.index('Nova análise térmica'), headers.index('Timeline térmica'))
                self.assertLess(headers.index('Timeline térmica'), headers.index('Envio de Formulário'))
                self.assertFalse(any(expander.label == 'Formulários' for expander in app.expander))
                self.assertFalse(any('Timeline' in expander.label for expander in app.expander))
                self.assertEqual(len(app.get('tab')), 0)
                temperature_inputs = [widget for widget in app.number_input
                                      if widget.key and widget.key.startswith('wizard_tmin_')]
                self.assertEqual(len(temperature_inputs), 2 if step == 5 else 0)
                if step in (3, 4):
                    from frontend.streamlit.components.thermography.wizard import centered_preview
                    with patch('frontend.streamlit.components.thermography.wizard.centered_preview', wraps=centered_preview) as preview:
                        app.run()
                    captions = [call.kwargs.get('caption', '') for call in preview.call_args_list]
                    self.assertEqual(captions.count('Pernas segmentadas — área completa'), 0 if step == 3 else 2)
                    if step == 3:
                        self.assertEqual(captions.count('Coxa · Joelho · Canela · Pé (de cima para baixo)'), 2)
                    self.assertFalse(any('Pixels quentes' in caption for caption in captions))
                if step == 1:
                    key = next(button.key for button in app.button if button.key and button.key.startswith('thermal_rotation_front_'))
                    app.button(key=key).click().run()
                    self.assertEqual(app.session_state['thermal_uploads']['front']['rotation'], 270)
                    for _ in range(3):
                        app.button(key=key).click().run()
                    self.assertEqual(app.session_state['thermal_uploads']['front']['rotation'], 0)
                if step == 3:
                    key = next(button.key for button in app.button if button.key and button.key.startswith('wizard_parts_front:'))
                    with patch('frontend.streamlit.components.thermography.wizard.st_canvas', return_value=SimpleNamespace(json_data=None)) as canvas:
                        app.button(key=key).click().run()
                        self.assertEqual(len(app.exception), 0, list(app.exception))
                        scene = canvas.call_args.kwargs['initial_drawing']
                        self.assertEqual(len(scene['objects']), 3)
                        self.assertEqual(scene['objects'][0]['dragConstraint']['axis'], {'x': 0, 'y': 1})
                        self.assertFalse(any(widget.label in ('Orientação', 'Onde está a coxa?') for widget in app.radio))
                        next(button for button in app.button if button.label == 'Concluir').click().run()
                    def moved_canvas(**kwargs):
                        scene = kwargs['initial_drawing']
                        objects = [dict(obj, y=kwargs['height'] * cut / 100)
                                   for obj, cut in zip(scene['objects'], [40, 60, 85])]
                        return SimpleNamespace(json_data={'objects': objects})
                    with patch('frontend.streamlit.components.thermography.wizard.st_canvas', side_effect=moved_canvas):
                        app.button(key=key).click().run()
                        self.assertEqual(len(app.exception), 0, list(app.exception))
                        item_key = key.removeprefix('wizard_parts_')
                        item = app.session_state['thermography_items'][item_key]
                        self.assertEqual(item['part_settings_v4']['right']['cuts'], [40, 60, 85])
                        self.assertIn('right', item['part_scenes'])
                        next(button for button in app.button if button.label == 'Concluir').click().run()
            self.assertIn('Resumo da coleta', [h.value for h in app.subheader])
            threshold_key = next(widget.key for widget in app.slider
                                 if widget.key and widget.key.startswith('wizard_threshold_front:'))
            app.slider(key=threshold_key).set_value(50.0).run()
            item_key = threshold_key.removeprefix('wizard_threshold_')
            self.assertEqual(app.session_state['thermography_items'][item_key]['threshold_percentage'], 50.0)
            self.assertFalse(app.button(key='save_image_thermography').disabled)
            for _ in range(5):
                app.button(key='thermal_previous').click().run()
            self.assertEqual(app.number_input(key='thermography_mass').value, 75.0)
            self.assertEqual(app.number_input(key='thermography_pain_score').value, 0)
            self.assertEqual(app.selectbox(key='thermography_player').value, 1)
