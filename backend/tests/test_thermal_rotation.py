import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image
from backend.mac_api.modules.thermography.thermal_analysis import image_regions, temperature_matrix


class ThermalRotationTests(unittest.TestCase):
    def test_rotation_preserves_temperature_mapping_and_leg_identity(self):
        rgb = np.zeros((80, 100, 3), dtype=np.uint8)
        for y in range(80):
            rgb[y, :] = (255-y*3, y*3, 20)
        image = Image.fromarray(rgb)
        bar = dict(left=90, top=0, width=10, height=80)
        legs = [dict(left=10, top=10, width=40, height=20),
                dict(left=10, top=45, width=40, height=20)]
        baseline = temperature_matrix(image, 20, 40, bar)
        with patch('backend.mac_api.modules.thermography.thermal_analysis.detect_leg_boxes', return_value=legs), \
             patch('backend.mac_api.modules.thermography.thermal_analysis.detect_colorbar_box', return_value=(bar, 1.0)):
            for degrees in (0, 90, 180, 270):
                rotated = image.rotate(degrees, expand=True)
                regions = image_regions(rotated, 'front', degrees)
                actual = temperature_matrix(rotated, 20, 40, regions['colorbar_box'], image_rotation=degrees)
                expected = np.asarray(Image.fromarray(baseline).rotate(degrees, expand=True))
                np.testing.assert_allclose(actual, expected)
                self.assertEqual(set(regions['boxes']), {'right', 'left'})
                self.assertEqual(regions['boxes']['right']['width'] * regions['boxes']['right']['height'], 800)
