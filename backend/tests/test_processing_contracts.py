import unittest
from datetime import date
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from backend.mac_api.main import create_app
from backend.mac_api.core.wire import encode, decode
from frontend.streamlit.api_client import thermal_client, analytics_client, service_gateway


class ProcessingContractsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def bridge(self, method, path, **kwargs):
        response = self.client.request(method, path, headers={'X-API-Key': 'test-key'}, **kwargs)
        response.raise_for_status()
        return response.json()

    def test_client_metrics_match_server_and_preserve_dates_and_integer_keys(self):
        with patch('backend.mac_api.main.api_key', return_value='test-key'), patch.object(service_gateway, '_request', side_effect=self.bridge), patch.object(analytics_client, '_request', side_effect=self.bridge):
            grouped = analytics_client.call('player_data.group_measurements', [
                {'id_atleta': 12, 'medida': 'maior_cmj', 'data': date(2026, 10, 8), 'valor': 30},
            ])
            self.assertEqual(grouped[12]['cmj'][0], [date(2026, 10, 8), 30.0])
            latest, deviation = analytics_client.call('player_data.metric_summary', grouped[12]['cmj'], date(2026, 1, 1), date(2026, 12, 31))
            self.assertEqual((latest, deviation), (30, 0))

    def test_segmentation_manual_regions_area_parts_and_timeline_cross_http(self):
        image = Image.new('RGB', (320, 200), (15, 15, 15))
        draw = ImageDraw.Draw(image)
        draw.ellipse((30, 40, 240, 75), fill=(230, 55, 25))
        draw.ellipse((30, 120, 240, 155), fill=(240, 70, 25))
        for y in range(20, 180):
            draw.line((280, y, 294, y), fill=(255-y, y, 40))
        boxes = {'right': {'left': 20, 'top': 25, 'width': 240, 'height': 65},
                 'left': {'left': 20, 'top': 105, 'width': 240, 'height': 65}}
        bar = {'left': 280, 'top': 20, 'width': 15, 'height': 160}
        with patch('backend.mac_api.main.api_key', return_value='test-key'), patch.object(thermal_client, '_request', side_effect=self.bridge):
            result = thermal_client.segmented_image(image, 'front', 20, 40, 30, boxes, bar)
            self.assertEqual(result['boxes'], boxes)
            metric = result['metrics']['right']
            self.assertGreater(metric['total_pixels'], 0)
            self.assertLess(metric['total_pixels'], 240*65)
            parts, lines = thermal_client.leg_part_metrics(result['temperatures'], result['masks']['right'], 30)
            self.assertEqual(sum(part['total_pixels'] for part in parts.values()), metric['total_pixels'])
            comparison = thermal_client.compare_hot_masks(result['masks']['right'], result['masks']['right'], boxes['right'], boxes['right'])
            self.assertEqual(comparison['new_pixels'], 0)
            self.assertEqual(comparison['resolved_pixels'], 0)
            source = {'temperatures': result['temperatures'], 'segmentation_masks': result['masks']}
            hotter = thermal_client.timeline_view_at_threshold(source, 40)
            colder = thermal_client.timeline_view_at_threshold(source, 20)
            self.assertLessEqual(hotter['metrics']['right']['hot_pixels'], colder['metrics']['right']['hot_pixels'])

    def test_wire_rejects_unsafe_dtypes_and_inconsistent_shapes(self):
        payload = encode(np.ones((2, 2), dtype=np.float32))
        with self.assertRaises(ValueError): decode({**payload, 'dtype': 'object'})
        with self.assertRaises(ValueError): decode({**payload, 'shape': [3, 3]})

    def test_operation_authentication_and_allowlist(self):
        with patch('backend.mac_api.main.api_key', return_value='test-key'):
            response = self.client.post('/api/v1/thermography/operations/segment_leg_mask', json={})
            self.assertEqual(response.status_code, 401)
            response = self.client.post('/api/v1/thermography/operations/__import__', json={}, headers={'X-API-Key': 'test-key'})
            self.assertEqual(response.status_code, 404)
