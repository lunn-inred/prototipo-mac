import unittest

import numpy as np
from PIL import Image

from backend.mac_api.core.wire import decode, encode
from backend.mac_api.modules.thermography.thermal_analysis import compare_temperature_maps, extract_colorbar


def source(temperature, threshold=33.):
    values = np.full((20, 20), temperature, dtype=float)
    mask = np.ones(values.shape, dtype=bool)
    box = dict(left=0, top=0, width=20, height=20)
    return dict(temperatures=values, segmentation_masks=dict(right=mask, left=mask),
                boxes=dict(right=box, left=box), default_threshold=threshold,
                part_settings={side: dict(cuts=[25, 50, 75], axis='vertical', foot_at_end=True)
                               for side in ('right', 'left')})


class TemperatureComparisonTests(unittest.TestCase):
    def compare(self, baseline, current, **kwargs):
        return compare_temperature_maps(baseline, current, (20, 20), **kwargs)

    def test_uses_original_colorbar_for_map_zero_and_legend(self):
        baseline, current = source(30, threshold=100), source(30, threshold=100)
        rgb = np.zeros((20, 20, 3), dtype=np.uint8)
        rgb[:, :, 0] = np.linspace(255, 0, 20).astype(np.uint8)[:, None]
        rgb[:, :, 1] = 120
        rgb[:, :, 2] = np.linspace(0, 255, 20).astype(np.uint8)[:, None]
        baseline['image'] = Image.fromarray(rgb)
        baseline['colorbar_box'] = dict(left=0, top=0, width=20, height=20)
        current['temperatures'][:, 2] = 28
        current['temperatures'][:, 17] = 32
        result = self.compare(baseline, current, limit=2)
        palette = extract_colorbar(baseline['image'], baseline['colorbar_box'])
        np.testing.assert_array_equal(result['palette'], palette)
        pixels = np.asarray(result['images']['right'])
        np.testing.assert_array_equal(pixels[10, 2], palette[-1])
        np.testing.assert_array_equal(pixels[10, 17], palette[0])
        midpoint = np.rint((palette[9].astype(float) + palette[10]) / 2).astype(np.uint8)
        np.testing.assert_array_equal(pixels[10, 10], midpoint)
        legend = np.asarray(result['legend'])
        np.testing.assert_array_equal(legend[8, 20], palette[-1])
        np.testing.assert_array_equal(legend[8, 399], palette[0])
        # A provided palette keeps the back view consistent with the front.
        shared = self.compare(source(30, threshold=100), current, limit=2, palette=palette)
        np.testing.assert_array_equal(np.asarray(shared['images']['right']), pixels)

    def test_cooling_can_remain_hot_and_uses_only_basal_threshold(self):
        result = self.compare(source(35), source(34, threshold=36), limit=3)
        pixel = np.asarray(result['images']['right'])[10, 10]
        self.assertGreater(pixel[2], pixel[0])
        self.assertTrue(result['contours']['right']['current'].any())
        summary = result['summaries']['right']
        self.assertEqual(summary['current']['total']['hot_percentage'], 100)
        self.assertEqual(summary['current']['total']['mean_temperature'], 34)
        self.assertEqual(result['threshold'], 33)

    def test_identical_temperatures_and_masks_ignore_current_threshold(self):
        baseline = source(34)
        result = self.compare(baseline, source(34, threshold=35))
        self.assertTrue(result['unchanged'])
        np.testing.assert_array_equal(result['contours']['right']['baseline'],
                                      result['contours']['right']['current'])
        np.testing.assert_array_equal(np.asarray(result['images']['right'])[10, 10], [255] * 3)

    def test_hot_regions_enter_and_leave_independently(self):
        baseline, current = source(30), source(30)
        baseline['temperatures'][2:8, 2:8] = 35
        current['temperatures'][12:18, 12:18] = 35
        result = self.compare(baseline, current)
        outlines = result['contours']['right']
        self.assertTrue(outlines['baseline'][2, 2])
        self.assertFalse(outlines['current'][2, 2])
        self.assertTrue(outlines['current'][12, 12])
        self.assertFalse(outlines['baseline'][12, 12])
        image = np.asarray(result['images']['right'])
        self.assertGreater(image[4, 4, 2], image[4, 4, 0])
        self.assertGreater(image[14, 14, 0], image[14, 14, 2])

    def test_shared_limit_preserves_colors_across_comparisons_and_sides(self):
        baseline = source(30)
        first = source(31)
        second = source(31)
        second['temperatures'][0, 0] = 34
        a = self.compare(baseline, first, limit=5)
        b = self.compare(baseline, second, limit=5)
        self.assertEqual(a['limit'], b['limit'])
        np.testing.assert_array_equal(np.asarray(a['images']['right'])[10, 10],
                                      np.asarray(b['images']['left'])[10, 10])
        np.testing.assert_array_equal(np.asarray(a['legend']), np.asarray(b['legend']))

    def test_native_regional_statistics_and_empty_regions(self):
        baseline, current = source(30), source(30)
        baseline['temperatures'][:] = np.repeat([30., 32., 34., 36.], 5)[:, None]
        current['temperatures'][:] = baseline['temperatures'] + 1
        # Current coxa uses its own saved cut: rows 0..3 rather than 0..4.
        current['part_settings']['right']['cuts'] = [20, 50, 75]
        current['segmentation_masks']['right'] = current['segmentation_masks']['right'].copy()
        current['segmentation_masks']['right'][15:] = False
        result = self.compare(baseline, current)
        summary = result['summaries']['right']
        self.assertEqual(summary['baseline']['coxa']['mean_temperature'], 30)
        self.assertEqual(summary['current']['coxa']['mean_temperature'], 31)
        self.assertEqual(summary['baseline']['total']['hot_percentage'], 50)
        self.assertAlmostEqual(summary['current']['total']['hot_percentage'], 100 * 10 / 15)
        self.assertIsNone(summary['current']['pe']['mean_temperature'])
        self.assertIsNone(summary['current']['pe']['hot_percentage'])

    def test_no_overlap_is_dark_and_is_not_unchanged(self):
        baseline, current = source(35), source(34)
        for side in ('right', 'left'):
            baseline['segmentation_masks'][side] = np.zeros((20, 20), dtype=bool)
            current['segmentation_masks'][side] = np.zeros((20, 20), dtype=bool)
            baseline['segmentation_masks'][side][:8] = True
            current['segmentation_masks'][side][12:] = True
        result = self.compare(baseline, current)
        self.assertFalse(result['has_overlap'])
        self.assertFalse(result['unchanged'])
        np.testing.assert_array_equal(np.asarray(result['images']['right']), np.full((20, 20, 3), 18))

    def test_invalid_limits_and_wire_roundtrip(self):
        for limit in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.compare(source(30), source(31), limit=limit)
        result = decode(encode(self.compare(source(30), source(31), limit=4)))
        self.assertEqual(result['limit'], 4)
        self.assertEqual(result['legend'].size, (420, 58))
        self.assertEqual(result['contours']['right']['current'].dtype, bool)
