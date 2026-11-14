import unittest
from unittest.mock import patch
from PIL import Image

from frontend.streamlit.api_client import thermal_client
from frontend.streamlit.api_client.service_gateway import ApiClientError
from frontend.streamlit.api_client.wire import encode
from frontend.streamlit.components.thermography.editor import segmented_analysis
from frontend.streamlit.presentation.thermal_zones import normalize_zone_selection, zone_caption


class ThermalZoneCompatibilityTests(unittest.TestCase):
    def test_incomplete_drafts_are_upgraded_without_discarding_manual_work(self):
        for previous in (None, '', 'Zona fria', 'unknown'):
            with self.subTest(previous=previous):
                item = {'thermal_zone': previous, 'analysis_config': ('legacy',),
                        'notes': 'Rascunho', 'mask_seeds': {'right': 'traços'},
                        'manual_boxes': {'right': 'área'}}
                self.assertEqual(normalize_zone_selection(item), 'hot')
                self.assertEqual(item['thermal_zone'], 'hot')
                self.assertNotIn('analysis_config', item)
                self.assertEqual(item['mask_seeds'], {'right': 'traços'})
                self.assertEqual(item['manual_boxes'], {'right': 'área'})
                self.assertEqual(item['notes'], 'Rascunho')
        item = {'thermal_zone': 'cold', 'analysis_config': ('current',)}
        self.assertEqual(normalize_zone_selection(item), 'cold')
        self.assertEqual(item['analysis_config'], ('current',))

    def test_zone_caption_handles_missing_none_and_empty_metadata(self):
        for response in ({}, {'zone_label': None}, {'zone_label': ''}):
            self.assertEqual(zone_caption(response, 'cold'), 'Zona fria')
            self.assertEqual(zone_caption(response, None), 'Zona quente')
        self.assertEqual(zone_caption({'zone_label': 'Zona neutra'}, 'neutral'), 'Zona neutra')

    def test_old_api_does_not_silently_return_threshold_counts_as_zone_counts(self):
        with patch.object(thermal_client, '_request', return_value=encode({'threshold': 36})):
            with self.assertRaisesRegex(ApiClientError, 'inicie-a novamente'):
                thermal_client.segmented_image(Image.new('RGB', (20, 30)), 'front', 20, 40, 36,
                                               thermal_zone='cold')

    def test_mismatched_zone_is_rejected(self):
        with patch.object(thermal_client, '_request', return_value=encode({'thermal_zone': 'hot'})):
            with self.assertRaisesRegex(ApiClientError, 'não confirmou'):
                thermal_client.segmented_image(Image.new('RGB', (20, 30)), 'front', 20, 40, 36,
                                               thermal_zone='neutral')

    def test_legacy_client_can_still_use_threshold_api(self):
        with patch.object(thermal_client, '_request', return_value=encode({'threshold': 36})):
            result = thermal_client.segmented_image(Image.new('RGB', (20, 30)), 'front', 20, 40, 36)
        self.assertEqual(result['threshold'], 36)

    def test_cached_analysis_without_zone_is_refetched_without_losing_draft(self):
        item = {'thermal_zone': 'cold', 'notes': 'Preservar rascunho'}
        image = Image.new('RGB', (20, 30))
        with patch.object(thermal_client, 'segmented_image', side_effect=[{'thermal_zone': 'cold'}, {'thermal_zone': 'cold'}]) as request:
            segmented_analysis(image, 'front', 20, 40, 36, item)
            item['analysis'] = {'threshold': 36}  # Stale result from an older API.
            result = segmented_analysis(image, 'front', 20, 40, 36, item)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(result['thermal_zone'], 'cold')
        self.assertEqual(item['notes'], 'Preservar rascunho')
