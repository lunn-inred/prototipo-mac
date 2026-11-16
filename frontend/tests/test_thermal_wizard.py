import io
from datetime import date
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
    def setUp(self):
        map_patch = patch('frontend.streamlit.components.thermography.wizard.body_muscles_map',
                          return_value={'active': None, 'bodyState': {}})
        self.eva_map = map_patch.start()
        self.addCleanup(map_patch.stop)
        import streamlit as st
        st.cache_data.clear()
        self.addCleanup(st.cache_data.clear)

    def test_first_step_uses_grouped_leg_map_without_recording_regional_eva(self):
        from frontend.streamlit.components.thermography.save_flow import snapshot_state
        app = AppTest.from_string('''
from frontend.streamlit.components.thermography.wizard import render_wizard
render_wizard({1: {'id_atleta': 1, 'nome': 'Teste'}})
''').run()
        self.assertFalse(app.exception)
        self.assertFalse(any(w.key == 'thermography_pain_score' for w in app.number_input))
        args = self.eva_map.call_args.kwargs
        self.assertTrue(args['custom_grouping'])
        self.assertTrue(args['legs_only'])
        self.assertTrue(args['compact'])
        self.assertEqual(args['view'], 'BOTH')
        app.selectbox(key='thermography_player').set_value(1)
        app.number_input(key='thermography_mass').set_value(75.)
        app.text_area(key='thermography_observations').set_value('Teste visual').run()
        self.assertFalse(app.button(key='thermal_next').disabled)
        regional = {'active': 'front-thigh-right', 'bodyState': {'front-thigh-right': {'intensity': 6, 'selected': True}}}
        app.session_state['thermal_eva_map_state'] = regional
        app.button(key='thermal_next').click().run()
        app.button(key='thermal_previous').click().run()
        self.assertEqual(app.session_state['thermal_eva_map_state'], regional)
        self.assertEqual(app.text_area(key='thermography_observations').value, 'Teste visual')
        self.assertIsNone(app.session_state['thermal_draft']['pain'])
        with patch('frontend.streamlit.components.thermography.save_flow.st.session_state',
                   {'thermal_draft': app.session_state['thermal_draft'], 'thermal_eva_map_state': regional}):
            payload = snapshot_state()
        self.assertNotIn('thermal_eva_map_state', payload)
        self.assertNotIn('bodyState', payload['draft'])

    def test_cropped_strokes_are_positioned_in_original_image(self):
        from frontend.streamlit.components.thermography.editor import _canvas_seeds
        strokes = np.zeros((4, 3, 4), dtype=np.uint8)
        strokes[1, 1] = [0, 255, 0, 255]
        strokes[2, 2] = [255, 0, 0, 255]
        box = dict(left=5, top=6, width=3, height=4)
        seeds, included, excluded = _canvas_seeds(strokes, Image.new('RGB', (20, 20)), box, cropped=True)
        self.assertEqual((included, excluded), (1, 1))
        self.assertEqual(seeds[7, 6], 1)
        self.assertEqual(seeds[8, 7], -1)
        self.assertEqual(np.count_nonzero(seeds), 2)

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

    def test_seven_steps_preserve_data_and_reach_registration_via_http(self):
        from backend.mac_api.repositories import data_repository
        client = TestClient(create_app())
        processing_requests = []
        def http(method, url, **kwargs):
            kwargs.pop('timeout', None)
            processing_requests.append(urlsplit(url).path)
            return client.request(method, urlsplit(url).path, **kwargs)
        image = Image.new('RGB', (240, 320), (170, 0, 210))
        draw = ImageDraw.Draw(image)
        draw.rectangle((65, 30, 170, 90), fill=(40, 185, 80))
        draw.polygon([(68, 75), (115, 75), (102, 170), (75, 290), (45, 290)], fill=(230, 55, 25))
        draw.polygon([(125, 75), (169, 75), (195, 290), (165, 290), (137, 170)], fill=(240, 70, 25))
        for y in range(30, 280):
            draw.line((226, y, 234, y), fill=(255-y//2, y//2, 30))
        buffer = io.BytesIO(); image.save(buffer, format='PNG')
        upload_labels = []
        def upload(label, **kwargs):
            upload_labels.append(label)
            if kwargs.get('accept_multiple_files'): return []
            result = io.BytesIO(buffer.getvalue()); result.name = 'teste.png'
            return result
        root = Path(__file__).resolve().parents[2]
        with patch.object(data_repository, 'list_athletes', return_value=[dict(id_atleta=1, nome='Teste', apelido=None)]), \
             patch('frontend.streamlit.api_client.service_gateway._http_request', side_effect=http), \
             patch('streamlit.file_uploader', side_effect=upload), \
             patch('frontend.streamlit.components.thermography.wizard.dialog_canvas_limits', return_value=(1200, 650)), \
             patch('frontend.streamlit.components.thermography.editor.dialog_canvas_limits', return_value=(720, 650)), \
             patch('frontend.streamlit.components.thermography.wizard.cached_temperature_scale', return_value=dict(minimum_temperature=20.0, maximum_temperature=40.0)):
            app = AppTest.from_file(str(root/'frontend/streamlit/pages/Termografia.py'), default_timeout=30).run()
            self.assertEqual(len(app.exception), 0)
            self.assertTrue(app.button(key='thermal_next').disabled)
            app.selectbox(key='thermography_player').set_value(1)
            app.number_input(key='thermography_mass').set_value(75.0)
            app.run()
            for step in range(1, 7):
                app.button(key='thermal_next').click().run()
                self.assertEqual(len(app.exception), 0, list(app.exception))
                self.assertEqual(app.session_state['thermal_step'], step)
                if step <= 3:
                    self.assertNotIn('/api/v1/thermography/segment', processing_requests)
                else:
                    self.assertIn('/api/v1/thermography/segment', processing_requests)
                headers = [header.value for header in app.subheader]
                self.assertIn('Termografia - Nova análise térmica', [title.value for title in app.title])
                self.assertNotIn('Nova análise térmica', headers)
                self.assertNotIn('Timeline térmica', headers)
                self.assertFalse(any(expander.label == 'Formulários' for expander in app.expander))
                self.assertFalse(any('Timeline' in expander.label for expander in app.expander))
                self.assertEqual(len(app.get('tab')), 2 if step == 6 else 0)
                temperature_inputs = [widget for widget in app.number_input
                                      if widget.key and widget.key.startswith('wizard_tmin_')]
                self.assertEqual(len(temperature_inputs), 2 if step == 5 else 0)
                if step in (2, 3, 4):
                    from frontend.streamlit.components.thermography.wizard import centered_preview
                    with patch('frontend.streamlit.components.thermography.wizard.centered_preview', wraps=centered_preview) as preview:
                        app.run()
                    captions = [call.kwargs.get('caption', '') for call in preview.call_args_list]
                    self.assertEqual(captions.count('Pernas segmentadas'), 2 if step == 4 else 0)
                    if step == 2:
                        self.assertEqual(captions.count('Área das pernas'), 2)
                    if step == 3:
                        self.assertEqual(captions.count('Divisão anatômica'), 2)
                    self.assertFalse(any('Pixels quentes' in caption for caption in captions))
                if step == 1:
                    labels = [button.label for button in app.button]
                    self.assertEqual(labels.count('Girar 90° para a direita'), 2)
                    self.assertEqual(labels[-4:], ['Voltar', 'Continuar', 'Ver análises anteriores', 'Salvar análise'])
                    self.assertIn('Imagem de costas', upload_labels)
                    self.assertNotIn('Imagem de verso', upload_labels)
                    key = next(button.key for button in app.button if button.key and button.key.startswith('thermal_rotation_front_'))
                    app.button(key=key).click().run()
                    self.assertEqual(app.session_state['thermal_uploads']['front']['rotation'], 270)
                    for _ in range(3):
                        app.button(key=key).click().run()
                    self.assertEqual(app.session_state['thermal_uploads']['front']['rotation'], 0)
                if step == 2:
                    labels = [button.label for button in app.button]
                    self.assertEqual(labels.count('Ajustar regiões'), 2)
                    self.assertNotIn('Corrigir Áreas', labels)
                    self.assertEqual(labels[-4:], ['Voltar', 'Continuar', 'Ver análises anteriores', 'Salvar análise'])
                    self.assertIn('#### Costas', [text.value for text in app.markdown])
                if step == 3:
                    self.assertEqual([button.label for button in app.button].count('Redefinir regiões'), 2)
                    key = next(button.key for button in app.button if button.key and button.key.startswith('wizard_parts_front:'))
                    with patch('frontend.streamlit.components.thermography.wizard.st_canvas', return_value=SimpleNamespace(json_data=None)) as canvas:
                        app.button(key=key).click().run()
                        self.assertEqual(len(app.exception), 0, list(app.exception))
                        self.assertEqual(app.radio(key=f'parts_side_{key.removeprefix("wizard_parts_")}').options[0], 'Perna esquerda')
                        scene = canvas.call_args.kwargs['initial_drawing']
                        self.assertEqual(len(scene['objects']), 3)
                        self.assertEqual(next(button for button in app.button if button.label == 'Concluir').proto.type, 'primary')
                        self.assertTrue(all(obj['height'] >= 12 for obj in scene['objects']))
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
                        self.assertEqual(item['part_settings_v4']['left']['cuts'], [40, 60, 85])
                        self.assertIn('left', item['part_scenes'])
                        next(button for button in app.button if button.label == 'Concluir').click().run()
                if step == 4:
                    self.assertEqual([button.label for button in app.button].count('Ajustar área perna'), 2)
                    key = next(button.key for button in app.button if button.key and button.key.startswith('wizard_mask_front:'))
                    with patch('frontend.streamlit.components.thermography.editor.st_canvas', return_value=SimpleNamespace(image_data=None, json_data=None)) as canvas:
                        app.button(key=key).click().run()
                        self.assertEqual(len(app.exception), 0, list(app.exception))
                        item_key = key.removeprefix('wizard_mask_')
                        box = app.session_state['thermography_items'][item_key]['analysis']['boxes']['left']
                        background = canvas.call_args.kwargs['background_image']
                        self.assertFalse(canvas.call_args.kwargs['display_toolbar'])
                        self.assertAlmostEqual(background.width/background.height, box['width']/box['height'], delta=.05)
                        self.assertIn('Área segmentada', [caption.value for caption in app.caption])
                        self.assertEqual(next(button for button in app.button if button.label == 'Concluir').proto.type, 'primary')
                        self.assertEqual(next(button for button in app.button if button.label == 'Aplicar traços e recalcular').proto.type, 'secondary')
                        next(button for button in app.button if button.label == 'Concluir').click().run()
                if step == 5:
                    texts = [text.value for text in app.markdown]
                    left_index = next(index for index, text in enumerate(texts) if text.startswith('**Perna esquerda:**'))
                    right_index = next(index for index, text in enumerate(texts) if text.startswith('**Perna direita:**'))
                    self.assertLess(left_index, right_index)
                    for index in (left_index, right_index):
                        lines = texts[index].splitlines()
                        self.assertEqual(len(lines), 6)
                        self.assertTrue(lines[1].startswith('Total: **') and 'px)' in lines[1])
                        self.assertTrue(lines[-1].startswith('Pé: **'))
                        self.assertFalse(any(line.startswith('- ') for line in lines))
                    self.assertFalse(any('Pixels quentes —' in metric.label for metric in app.metric))
                    self.assertNotIn('Resumo da coleta', [h.value for h in app.subheader])
                    self.assertFalse(any(button.key == 'register_thermography_analysis' for button in app.button))
                    from frontend.streamlit.components.thermography.wizard import centered_preview
                    with patch('frontend.streamlit.components.thermography.wizard.centered_preview', wraps=centered_preview) as preview:
                        app.run()
                    captions = [call.kwargs.get('caption', '') for call in preview.call_args_list]
                    self.assertEqual(captions.count('Divisão anatômica'), 2)
                    self.assertNotIn('Original com caixas', captions)
                    cold_key = next(button.key for button in app.button
                                    if button.key and button.key.startswith('wizard_zone_cold_front:'))
                    item_key = cold_key.removeprefix('wizard_zone_cold_')
                    self.assertFalse(any(widget.key and widget.key.startswith('wizard_threshold_') for widget in app.slider))
                    self.assertEqual(len([button for button in app.button if button.key and button.key.startswith('wizard_zone_')]), 6)
                    for zone, zone_name in (('cold', 'Zona fria'), ('neutral', 'Zona neutra'), ('hot', 'Zona quente')):
                        app.button(key=f'wizard_zone_{zone}_{item_key}').click().run()
                        item = app.session_state['thermography_items'][item_key]
                        self.assertEqual(item['thermal_zone'], zone)
                        self.assertEqual(item['analysis']['thermal_zone'], zone)
                        with patch('frontend.streamlit.components.thermography.wizard.centered_preview', wraps=centered_preview) as preview:
                            app.run()
                        self.assertIn(zone_name, [call.kwargs.get('caption') for call in preview.call_args_list])
                    app.button(key=cold_key).click().run()
                    app.number_input(key=f'wizard_tmin_{item_key}').set_value(35.).run()
                    item = app.session_state['thermography_items'][item_key]
                    self.assertEqual(item['thermal_zone'], 'cold')
                    self.assertTrue(all(metric['hot_pixels'] == 0 for metric in item['analysis']['metrics'].values()))
                    self.assertEqual(len(app.exception), 0, list(app.exception))
            # O mapa é apenas visual; o contrato legado ainda recebe EVA no resumo.
            app.number_input(key='thermal_summary_pain_score').set_value(0).run()
            self.assertIn('Resumo da coleta', [h.value for h in app.subheader])
            self.assertNotIn('Registro preparado', [h.value for h in app.subheader])
            self.assertEqual(app.get('progress')[0].proto.text, 'Etapa 7 de 7 — Resumo da coleta')
            labels = [button.label for button in app.button]
            self.assertNotIn('Adicionar à timeline', labels)
            self.assertNotIn('Registrar coleta no banco', labels)
            self.assertNotIn('Registrar Análise', labels)
            self.assertLess(labels.index('Voltar'), labels.index('Iniciar outra análise'))
            self.assertFalse(any(widget.key and widget.key.startswith('wizard_tmin_') for widget in app.number_input))
            self.assertFalse(app.button(key='thermal_save_analysis').disabled)
            self.assertEqual(len(app.date_input), 1)
            self.assertIsNotNone(app.date_input(key='thermal_summary_date').value)
            self.assertFalse(any('Jogador' in frame.value.columns for frame in app.dataframe))
            self.assertIn('Frente', [tab.label for tab in app.tabs])
            self.assertIn('Costas', [tab.label for tab in app.tabs])
            regional_tables = [table.value for table in app.dataframe
                               if list(table.value.columns) == ['Região', 'Fria', 'Neutra', 'Quente']]
            self.assertEqual(len(regional_tables), 4)
            total_tables = [table.value for table in app.dataframe
                            if list(table.value.columns) == ['Zona', 'Total (px)']]
            self.assertEqual(len(total_tables), 0)
            for table in regional_tables:
                for zone in ('Fria', 'Neutra', 'Quente'):
                    self.assertEqual(table[zone].iloc[-1], table[zone].iloc[:4].sum())
            self.assertEqual(len(app.metric), 0)
            signature = next(iter(app.session_state['thermography_metrics']))
            app.session_state['thermal_registered_analysis'] = {'signature': signature}
            app.run()
            self.assertFalse(app.button(key='thermal_save_analysis').disabled)
            for _ in range(6):
                app.button(key='thermal_previous').click().run()
            self.assertEqual(app.number_input(key='thermography_mass').value, 75.0)
            self.assertEqual(app.session_state['thermal_draft'].get('pain'), 0)
            self.assertEqual(app.selectbox(key='thermography_player').value, 1)
            for _ in range(6):
                app.button(key='thermal_next').click().run()
            # Os campos individuais atualizam os dados enviados, sem popup de data.
            app.number_input(key='thermography_mass').set_value(76.5).run()
            app.text_area(key='thermography_observations').set_value('Revisado no resumo').run()
            app.date_input(key='thermal_summary_date').set_value(date(2026, 11, 21)).run()
            with patch('frontend.streamlit.components.thermography.save_flow.register_prepared_analysis', return_value={}) as save:
                self.assertEqual(app.session_state['thermal_prepared_record']['collected_at'], date(2026, 11, 21))
                # Voltar à segmentação não torna incompletos os cálculos já válidos.
                app.button(key='thermal_previous').click().run()
                app.button(key='thermal_previous').click().run()
                self.assertEqual(app.session_state['thermal_step'], 4)
                app.button(key='thermal_save_analysis').click().run()
                self.assertFalse(app.exception)
                self.assertFalse(any(button.key == 'thermal_save_confirm' for button in app.button))
                self.assertEqual(save.call_args.kwargs['collected_at'], date(2026, 11, 21))
                self.assertEqual(save.call_args.kwargs['mass'], 76.5)
                self.assertEqual(save.call_args.kwargs['observations'], 'Revisado no resumo')
                self.assertFalse(app.date_input)
            self.assertEqual(app.session_state['thermal_step'], 0)
            self.assertEqual(app.title[0].value, 'Termografia - Nova análise térmica')
            self.assertIsNone(app.number_input(key='thermography_mass').value)
            self.assertIsNone(app.session_state['thermal_draft'].get('pain'))
            self.assertIsNone(app.selectbox(key='thermography_player').value)
            self.assertEqual(app.session_state['thermal_upload_generation'], 1)
            self.assertNotIn('thermal_prepared_record', app.session_state)
            self.assertNotIn('thermal_calculation', app.session_state)
            self.assertEqual(app.toast[0].value, 'Análise salva. Você poderá visualizá-la em Ver análises anteriores.')
