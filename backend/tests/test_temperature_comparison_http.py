import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

from backend.mac_api.main import create_app
from backend.tests.test_temperature_comparison import source
from frontend.streamlit.api_client import thermal_client


class TemperatureComparisonHttpTests(unittest.TestCase):
    def test_client_transports_scale_contours_summary_and_legend(self):
        client = TestClient(create_app())

        def bridge(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        with patch('backend.mac_api.main.api_key', return_value=None), \
             patch.object(thermal_client, '_request', side_effect=bridge):
            result = thermal_client.compare_temperature_maps(source(35), source(34, threshold=36), limit=5)
        self.assertEqual(result['limit'], 5)
        self.assertEqual(result['threshold'], 33)
        self.assertEqual(result['max_difference'], 1)
        self.assertEqual(result['summaries']['right']['current']['total']['hot_percentage'], 100)
        self.assertTrue(result['contours']['right']['current'].any())
        self.assertEqual(result['legend'].size, (420, 58))
        pixel = np.asarray(result['images']['right'])[160, 90]
        self.assertGreater(pixel[2], pixel[0])
