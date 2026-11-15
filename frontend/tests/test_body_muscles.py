import hashlib
from pathlib import Path
import unittest
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from frontend.streamlit.components import body_muscles as body
from frontend.streamlit.components.body_muscles_groups import custom_groups

PAGE = Path(__file__).resolve().parents[1] / 'streamlit/pages/Mapa_Corporal_Lab.py'


class BodyMusclesTests(unittest.TestCase):
    def test_original_catalog_and_licensed_offline_bundle_are_available(self):
        catalog = body.region_catalog()
        self.assertEqual(len(catalog), 89)
        self.assertEqual({v['view'] for v in catalog.values()}, {'FRONT', 'BACK'})
        self.assertEqual(hashlib.sha256((body.VENDOR/'body-muscles.umd.min.js').read_bytes()).hexdigest(),
                         '4d0592e251bbcd060f14ba03776241866c7f9a69b8fe4a0e33786391632c287d')
        self.assertIn('Apache License', (body.VENDOR/'LICENSE').read_text())
        self.assertIn('Ivan Vulović', (body.VENDOR/'NOTICE').read_text())

    def test_state_rejects_unknown_regions_and_invalid_intensities(self):
        identifier = next(iter(body.region_catalog()))
        valid = dict(active=identifier, bodyState={identifier: dict(intensity=7, selected=True)})
        self.assertEqual(body.normalize_state(valid), valid)
        for intensity in (-1, 11, .5, True):
            with self.subTest(intensity=intensity), self.assertRaises(ValueError):
                body.normalize_state(dict(bodyState={identifier: dict(intensity=intensity, selected=True)}))
        with self.assertRaises(ValueError):
            body.normalize_state(dict(active='unknown', bodyState={}))
        for custom in (False, True):
            ids = list(custom_groups() if custom else body.region_catalog())[:2]
            previous = dict(active=ids[1], bodyState={
                ids[0]: dict(intensity=7, selected=True), ids[1]: dict(intensity=3, selected=True)})
            normalized = body.normalize_state(previous, custom_grouping=custom)
            self.assertFalse(normalized['bodyState'][ids[0]]['selected'])
            self.assertTrue(normalized['bodyState'][ids[1]]['selected'])
            self.assertEqual(normalized['bodyState'][ids[0]]['intensity'],7)

    def test_custom_groups_match_both_sides_and_views_without_overlap(self):
        groups, original = custom_groups(), body.region_catalog()
        self.assertEqual(len(groups), 16)
        members = []
        for group in groups.values():
            self.assertTrue(all(original[member]['view'] == group['view'] for member in group['members']))
            self.assertTrue(all(member.endswith('-'+group['side']) for member in group['members']))
            members.extend(group['members'])
        self.assertEqual(len(members), len(set(members)))
        self.assertEqual(groups['front-coxa-right']['members'], ['quads-right','adductors-right','hip-flexor-right'])
        self.assertEqual(groups['back-canela-left']['members'],
                         ['calves-gastroc-medial-left','calves-gastroc-lateral-left','calves-soleus-left'])
        value = dict(active='back-canela-left', bodyState={'back-canela-left': dict(intensity=8,selected=True)})
        self.assertEqual(body.normalize_state(value,custom_grouping=True), value)
        with self.assertRaises(ValueError):
            body.normalize_state(value)

    def test_exploration_receives_state_changes_view_and_resets_without_api(self):
        identifier = next(iter(body.region_catalog()))
        value = dict(active=identifier, bodyState={identifier: dict(intensity=6, selected=True)})
        def mount(**kwargs):
            return {'value': kwargs['data']['value']}
        with patch.object(body, '_component') as factory, \
             patch('frontend.streamlit.api_client.service_gateway._http_request', side_effect=AssertionError('Sem API')):
            factory.return_value.side_effect = mount
            app = AppTest.from_file(str(PAGE)).run()
            self.assertFalse(app.exception)
            app.session_state['body_lab_map_0'] = {'value': value}
            app.run()
            self.assertEqual(app.session_state['body_lab_state'], value)
            app.selectbox(key='body_lab_view').set_value('Costas').run()
            self.assertEqual(factory.return_value.call_args.kwargs['data']['view'], 'BACK')
            self.assertEqual(app.session_state['body_lab_state'], value)
            app.checkbox(key='body_lab_custom_grouping').check().run()
            self.assertEqual(app.session_state['body_lab_custom_state']['bodyState'], {})
            self.assertEqual(len(factory.return_value.call_args.kwargs['data']['groups']),16)
            grouped = dict(active='front-coxa-right',bodyState={'front-coxa-right':dict(intensity=4,selected=True)})
            app.session_state['body_lab_map_0_custom'] = {'value': grouped}
            app.run()
            app.checkbox(key='body_lab_custom_grouping').uncheck().run()
            self.assertEqual(app.session_state['body_lab_state'], value)
            app.checkbox(key='body_lab_custom_grouping').check().run()
            self.assertEqual(app.session_state['body_lab_custom_state'], grouped)
            app.button(key='body_lab_reset').click().run()
            self.assertFalse(app.exception)
            app.checkbox(key='body_lab_custom_grouping').check().run()
            self.assertTrue(factory.return_value.call_args.kwargs['data']['customGrouping'])
            self.assertEqual(app.session_state['body_lab_custom_state']['bodyState'], {})
            app.checkbox(key='body_lab_custom_grouping').uncheck().run()
            self.assertFalse(factory.return_value.call_args.kwargs['data']['customGrouping'])
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['body_lab_state']['bodyState'], {})
