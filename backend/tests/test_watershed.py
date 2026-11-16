import io
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient

from backend.mac_api.main import create_app
from backend.mac_api.core.wire import encode, decode
from backend.mac_api.modules.thermography import thermal_analysis as thermal
from backend.mac_api.modules.thermography.watershed import segment_pair, segment_region


def thermogram(box_lines=False, background=(170, 0, 210)):
    image = Image.new('RGB', (240, 320), background)
    draw = ImageDraw.Draw(image)
    draw.rectangle((65, 30, 170, 90), fill=(40, 185, 80))
    red = tuple(int(v) for v in cv2.cvtColor(np.array([[[178, 200, 230]]], 'uint8'), cv2.COLOR_HSV2RGB)[0, 0])
    draw.polygon([(68, 75), (115, 75), (102, 170), (75, 290), (45, 290)], fill=red)
    draw.polygon([(125, 75), (169, 75), (195, 290), (165, 290), (137, 170)], fill=(235, 60, 30))
    if box_lines:
        draw.rectangle((30, 70, 116, 298), outline='white')
        draw.rectangle((124, 70, 210, 298), outline='white')
    for y in range(30, 280):
        draw.line((226, y, 234, y), fill=(255-y//2, y//2, 30))
    return image


class WatershedTests(unittest.TestCase):
    def test_background_colors_preserve_legs_and_isolated_white_hot_regions(self):
        for color in ((40, 40, 40), (0, 0, 0), (230, 230, 230),
                      (255, 255, 255), (30, 30, 150), (170, 0, 210)):
            with self.subTest(background=color):
                image = thermogram(True, background=color)
                ImageDraw.Draw(image).ellipse((70, 135, 90, 160), fill='white')
                original = np.array(image).copy()
                left, right = segment_pair(image)
                self.assertTrue(left[148, 80])
                self.assertTrue(right[150, 155])
                self.assertFalse(left[220, 120] or right[220, 120])
                self.assertFalse(left[200, 35] or right[200, 207])
                self.assertFalse(np.any(left & right))
                np.testing.assert_array_equal(np.array(image), original)

    def test_neutral_gradient_background_does_not_become_foreground(self):
        image = thermogram()
        pixels = np.array(image)
        background = np.all(pixels == (170, 0, 210), axis=2)
        gray = np.repeat(np.linspace(25, 230, image.height, dtype='uint8')[:, None], image.width, axis=1)
        pixels[background] = np.repeat(gray[..., None], 3, axis=2)[background]
        left, right = segment_pair(Image.fromarray(pixels))
        self.assertTrue(left[150, 80] and right[150, 155])
        self.assertFalse(left[250, 120] or right[250, 120])

    def test_dark_patch_in_clothing_does_not_define_the_start_of_the_gap(self):
        image = thermogram(background=(40, 40, 40))
        draw = ImageDraw.Draw(image)
        draw.rectangle((100, 60, 140, 120), fill=(40, 185, 80))
        draw.rectangle((116, 65, 124, 105), fill=(30, 30, 30))
        left, right = segment_pair(image)
        self.assertFalse(left[:100].any() or right[:100].any())
        self.assertTrue(left[150, 80] and right[150, 155])

    def test_red_wrap_and_camera_lines_do_not_fill_background(self):
        for lines in (False, True):
            image = thermogram(lines)
            before = np.array(image).copy()
            left, right = segment_pair(image)
            self.assertTrue(left[150, 80])  # HSV red 178 must be retained.
            self.assertTrue(right[150, 155])
            self.assertFalse(left[200, 35])  # Inside camera box, outside leg.
            self.assertFalse(right[200, 207])
            self.assertFalse(np.any(left & right))
            np.testing.assert_array_equal(np.array(image), before)

    def test_laterality_uses_upright_image_and_view_not_camera_boxes(self):
        image = thermogram()
        front = thermal.image_regions(image, 'front')
        back = thermal.image_regions(image, 'back')
        self.assertIsNone(front['segmentation_warning'])
        np.testing.assert_array_equal(front['masks']['right'], back['masks']['left'])
        self.assertLess(front['boxes']['right']['left'], front['boxes']['left']['left'])
        # Metadata describes an earlier rotation, not a second image rotation.
        for degrees in (90, 180, 270):
            regions = thermal.image_regions(image, 'front', degrees)
            np.testing.assert_array_equal(regions['masks']['right'], front['masks']['right'])

    def test_brush_exclusions_keep_anatomical_reference_and_temperatures(self):
        image = thermogram()
        original = thermal.segmented_image(image, 'front', 20, 40, 30)
        mask = original['masks']['right']
        seed = np.zeros(mask.shape, 'int8')
        seed[mask & (np.indices(mask.shape)[0] < 170)] = -1
        corrected = thermal.segmented_image(image, 'front', 20, 40, 30, seeds={'right': seed})
        self.assertEqual(corrected['boxes'], original['boxes'])
        self.assertFalse(corrected['masks']['right'][seed < 0].any())
        self.assertLess(corrected['metrics']['right']['total_pixels'], original['metrics']['right']['total_pixels'])
        np.testing.assert_array_equal(corrected['temperatures'], original['temperatures'])

    def test_manual_region_recovery_does_not_require_central_gap(self):
        image = Image.new('RGB', (150, 100), '#181818')
        ImageDraw.Draw(image).ellipse((20, 25, 130, 75), fill=(240, 60, 30))
        box = dict(left=10, top=15, width=130, height=70)
        seeds = np.zeros((100, 150), 'int8')
        seeds[50, 35] = -1
        seeds[20, 15] = 1
        mask = segment_region(image, box, seeds)
        self.assertFalse(mask[50, 35])
        self.assertTrue(mask[20, 15])
        self.assertFalse(mask[:15].any())

    def test_failure_provides_editable_regions_but_no_fake_segmentation(self):
        image = Image.new('RGB', (240, 320), '#181818')
        regions = thermal.image_regions(image, 'front')
        self.assertIsNone(regions['masks'])
        self.assertTrue(regions['segmentation_warning'])
        with self.assertRaisesRegex(ValueError, 'duas pernas'):
            thermal.segmented_image(image, 'front', 20, 40, 30)

    def test_invalid_or_conflicting_seeds_are_rejected(self):
        image = thermogram()
        for seed in (np.zeros((2, 3), 'int8'), np.full((320, 240), 2, 'int8')):
            with self.assertRaisesRegex(ValueError, 'correção'):
                thermal.segmented_image(image, 'front', 20, 40, 30, seeds={'right': seed})
        seed = np.zeros((320, 240), 'int8'); seed[150, 80] = 1
        with self.assertRaisesRegex(ValueError, 'duas pernas'):
            thermal.segmented_image(image, 'front', 20, 40, 30, seeds={'right': seed, 'left': seed})

    def test_typed_api_runs_automatic_watershed_without_manual_boxes(self):
        image = thermogram(True)
        client = TestClient(create_app())
        with patch('backend.mac_api.main.api_key', return_value='test-key'):
            response = client.post('/api/v1/thermography/segment', headers={'X-API-Key': 'test-key'},
                                   json=encode(dict(image=image, view='front', minimum_temperature=20,
                                                    maximum_temperature=40, threshold=30)))
        self.assertEqual(response.status_code, 200, response.text)
        result = decode(response.json())
        self.assertIsNone(result['segmentation_warning'])
        for side in ('right', 'left'):
            self.assertEqual(result['metrics'][side]['total_pixels'], int(result['masks'][side].sum()))

    def test_legacy_service_uses_same_watershed_metrics(self):
        from backend.mac_api.modules.thermography.thermography_analysis_service import analyze_thermography_view
        image = thermogram()
        stream = io.BytesIO(); image.save(stream, 'PNG')
        legacy = analyze_thermography_view(stream.getvalue(), view='front', minimum_temperature=20,
                                          maximum_temperature=40, threshold=30)
        result = thermal.segmented_image(image, 'front', 20, 40, 30)
        self.assertEqual(legacy['metrics'], result['metrics'])
