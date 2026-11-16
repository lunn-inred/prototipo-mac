from datetime import date
import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from backend.mac_api.main import create_app
from backend.mac_api.modules.thermography import thermal_analysis as thermal, analysis_archive as archive
from backend.mac_api.modules.thermography.thermal_zones import selected_pixels
from backend.tests.test_watershed import thermogram
from backend.tests.test_analysis_archive import example_views
from frontend.streamlit.api_client import thermal_client


class ThermalZoneTests(unittest.TestCase):
    def test_boundaries_partition_finite_temperatures_without_overlap(self):
        values = np.array([-5, 30.99, 31, 32.99, 33, 45, np.nan, np.inf, -np.inf])
        masks = [selected_pixels(values, 36, zone) for zone in ('cold', 'neutral', 'hot')]
        for mask, indices in zip(masks, ([0, 1], [2, 3], [4, 5])):
            np.testing.assert_array_equal(np.flatnonzero(mask), indices)
        np.testing.assert_array_equal(sum(mask.astype('int8') for mask in masks), np.isfinite(values).astype('int8'))
        with self.assertRaisesRegex(ValueError, 'Zona térmica'):
            selected_pixels(values, 33, 'unknown')

    def test_counts_parts_and_overlay_use_same_zone_and_denominator(self):
        values = np.array([[30, 31, 32, 33], [29, 31, 33, 35], [25, 30, 32, 34], [20, 31, 32, 40]], dtype='float32')
        mask = np.ones(values.shape, bool); mask[0, 0] = False
        image = Image.new('RGB', (4, 4), (220, 70, 30))
        box = dict(left=0, top=0, width=4, height=4)
        for zone in ('cold', 'neutral', 'hot'):
            expected = mask & selected_pixels(values, 36, zone)
            pixels, area = thermal.count_hot_pixels(values, box, 36, mask, thermal_zone=zone)
            self.assertEqual((pixels, area), (int(expected.sum()), 15))
            parts, _ = thermal.leg_part_metrics(values, mask, 36, (25, 50, 75),
                                               axis='vertical', region_box=box, thermal_zone=zone)
            self.assertEqual(sum(p['hot_pixels'] for p in parts.values()), pixels)
            self.assertEqual(sum(p['total_pixels'] for p in parts.values()), area)
            overlay = np.array(thermal.hot_pixels_overlay(image, values, {'right': mask}, 36, thermal_zone=zone))
            np.testing.assert_array_equal(np.any(overlay != 0, axis=2), expected)
        # Legacy callers still select everything at/above the supplied threshold.
        self.assertEqual(thermal.count_hot_pixels(values, box, 34, mask), (3, 15))

    def test_zone_outside_scale_is_empty_not_clamped_into_another_zone(self):
        values = np.full((4, 4), 35.)
        mask = np.ones(values.shape, bool)
        box = dict(left=0, top=0, width=4, height=4)
        self.assertEqual(thermal.count_hot_pixels(values, box, 35, mask, thermal_zone='cold'), (0, 16))
        self.assertEqual(thermal.count_hot_pixels(values, box, 35, mask, thermal_zone='neutral'), (0, 16))

    def test_zone_crosses_typed_http_and_uses_actual_segmented_pixels(self):
        image = thermogram()
        values = np.resize(np.array([29, 31, 32.99, 33, 36], dtype='float32'), (image.height, image.width))
        client = TestClient(create_app())
        def bridge(method, path, **kwargs):
            response = client.request(method, path, headers={'X-API-Key': 'zone-test'}, **kwargs)
            response.raise_for_status()
            return response.json()
        with patch('backend.mac_api.main.api_key', return_value='zone-test'), \
             patch.object(thermal_client, '_request', side_effect=bridge), \
             patch.object(thermal, 'temperature_matrix', return_value=values):
            for zone in ('cold', 'neutral', 'hot'):
                result = thermal_client.segmented_image(image, 'front', 20, 40, 36, thermal_zone=zone)
                self.assertEqual(result['thermal_zone'], zone)
                for side, mask in result['masks'].items():
                    self.assertEqual(result['metrics'][side]['hot_pixels'], int((mask & selected_pixels(values, 36, zone)).sum()))
                    self.assertEqual(result['metrics'][side]['total_pixels'], int(mask.sum()))

    def test_archive_reload_and_timeline_preserve_zone_and_recompute_counts(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, MAC_ANALYSES_DIR=directory):
            views = {view: {**source, 'thermal_zone': zone} for (view, source), zone in
                     zip(example_views().items(), ('cold', 'neutral'))}
            saved = archive.save_analysis(athlete_id=123, athlete_name='Teste', collected_at=date(2026, 11, 14), views=views)
            entry = archive.load_analysis(123, date(2026, 11, 14), saved['id'])
            for view, zone in (('front', 'cold'), ('back', 'neutral')):
                source = entry['views'][view]
                self.assertEqual(source['thermal_zone'], zone)
                derived = thermal.timeline_view_at_threshold(source, source['default_threshold'])
                for side, mask in source['segmentation_masks'].items():
                    expected = mask & selected_pixels(source['temperatures'], 36, zone)
                    self.assertEqual(source['metrics'][side]['hot_pixels'], int(expected.sum()))
                    np.testing.assert_array_equal(derived['hot_masks'][side], expected)

    def test_comparison_uses_baseline_zone_and_keeps_temperature_deltas(self):
        from backend.tests.test_temperature_comparison import source
        basal = {**source(32), 'thermal_zone': 'neutral'}
        actual = {**source(34), 'thermal_zone': 'hot'}
        result = thermal.compare_temperature_maps(basal, actual)
        self.assertEqual(result['zone_label'], 'Zona neutra')
        for side in ('right', 'left'):
            self.assertEqual(result['summaries'][side]['baseline']['total']['hot_percentage'], 100)
            self.assertEqual(result['summaries'][side]['current']['total']['hot_percentage'], 0)
        self.assertEqual(result['max_difference'], 2)
