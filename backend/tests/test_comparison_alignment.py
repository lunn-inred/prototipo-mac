import copy
import os
import unittest
from unittest.mock import patch

import numpy as np

from backend.mac_api.modules.thermography.comparison_alignment import align_leg_to_baseline
from backend.mac_api.modules.thermography.thermal_analysis import compare_temperature_maps


def leg(height, width, cuts, spans, temperatures):
    boundaries = [0, *(round(height * cut / 100) for cut in cuts), height]
    field = np.zeros((height, width), dtype=float)
    mask = np.zeros_like(field, dtype=bool)
    for index, (start, end) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        field[start:end] = temperatures[index]
        left, right = spans[index]
        mask[start:end, left:right] = True
    box = dict(left=0, top=0, width=width, height=height)
    return dict(temperatures=field, segmentation_masks={side: mask.copy() for side in ('left', 'right')},
                boxes={side: box.copy() for side in ('left', 'right')}, default_threshold=33,
                part_settings={side: dict(cuts=cuts, axis='vertical', foot_at_end=True)
                               for side in ('left', 'right')})


class AnatomicalAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.baseline = leg(40, 10, [25, 50, 75], [(2, 8), (3, 7), (2, 8), (1, 9)], [30, 31, 32, 33])
        self.current = leg(60, 18, [50, 60, 80], [(5, 15), (6, 12), (4, 16), (2, 17)], [31, 33, 35, 37])

    def test_different_sizes_cuts_and_widths_align_each_anatomical_region(self):
        original = copy.deepcopy(self.current)
        base, aligned, mask = align_leg_to_baseline(self.baseline, self.current, 'right')
        np.testing.assert_array_equal(mask, self.baseline['segmentation_masks']['right'])
        for index in range(4):
            region = np.zeros(mask.shape, dtype=bool)
            region[index * 10:(index + 1) * 10] = True
            valid = region & mask
            np.testing.assert_allclose((aligned - base)[valid], index + 1)
        self.assertFalse(np.isfinite(aligned[~mask]).any())
        np.testing.assert_array_equal(original['temperatures'], self.current['temperatures'])
        for side in ('left', 'right'):
            np.testing.assert_array_equal(original['segmentation_masks'][side], self.current['segmentation_masks'][side])

    def test_baseline_shape_and_holes_are_preserved_for_different_current_shapes(self):
        self.baseline['segmentation_masks']['right'][5, 4] = False
        result = compare_temperature_maps(self.baseline, self.current, (10, 40))
        expected = self.baseline['segmentation_masks']['right']
        np.testing.assert_array_equal(result['baseline_masks']['right'], expected)
        np.testing.assert_array_equal(result['valid_masks']['right'], expected)
        pixels = np.asarray(result['images']['right'])
        self.assertTrue(np.all(pixels[~expected] == 0))
        self.assertTrue(np.any(pixels[expected] != 0, axis=1).all())

    def test_missing_current_part_is_not_invented_and_does_not_hide_other_parts(self):
        self.current['segmentation_masks']['right'][48:] = False
        result = compare_temperature_maps(self.baseline, self.current, (10, 40))
        expected = self.baseline['segmentation_masks']['right'].copy()
        expected[30:] = False
        np.testing.assert_array_equal(result['valid_masks']['right'], expected)
        np.testing.assert_array_equal(result['baseline_masks']['right'], self.baseline['segmentation_masks']['right'])

    def test_internal_current_hole_stays_unavailable(self):
        self.current['segmentation_masks']['right'][5:15, 8:11] = False
        _, aligned, mask = align_leg_to_baseline(self.baseline, self.current, 'right')
        self.assertTrue(np.any(mask & ~np.isfinite(aligned)))

    def test_scale_uses_only_the_pair_even_with_old_fixed_setting(self):
        with patch.dict(os.environ, MAC_THERMOGRAPHY_DELTA_LIMIT_C='3'):
            a = compare_temperature_maps(self.baseline, self.current, (10, 40))
            extreme = copy.deepcopy(self.current)
            extreme['temperatures'] += 50
            b = compare_temperature_maps(self.baseline, extreme, (10, 40))
            self.assertEqual(a['limit'], 4)
            self.assertEqual(b['limit'], 54)
            self.assertGreaterEqual(a['limit'], a['max_difference'])
            self.assertGreaterEqual(b['limit'], b['max_difference'])

    def test_invalid_anatomical_cuts_and_explicit_limit_are_rejected(self):
        self.current['part_settings']['right']['cuts'] = [60, 20, 80]
        with self.assertRaisesRegex(ValueError, 'Divisões'):
            compare_temperature_maps(self.baseline, self.current)
        for value in ('0', 'nan', 'wrong'):
            with self.assertRaisesRegex(ValueError, 'limite'):
                compare_temperature_maps(self.baseline, self.baseline, limit=value)

    def test_legacy_horizontal_orientation_is_restored_to_baseline(self):
        base = copy.deepcopy(self.baseline)
        current = copy.deepcopy(self.current)
        for source in (base, current):
            source['temperatures'] = source['temperatures'].T
            for side in ('right', 'left'):
                source['segmentation_masks'][side] = source['segmentation_masks'][side].T
                h, w = source['temperatures'].shape
                source['boxes'][side] = dict(left=0, top=0, width=w, height=h)
                source['part_settings'][side]['axis'] = 'horizontal'
        _, aligned, mask = align_leg_to_baseline(base, current, 'right')
        self.assertEqual(aligned.shape, base['temperatures'].shape)
        np.testing.assert_array_equal(mask, base['segmentation_masks']['right'])
        self.assertTrue(np.isfinite(aligned[mask]).all())
