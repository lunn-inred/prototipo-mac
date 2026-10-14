import unittest
import numpy as np
from backend.mac_api.modules.thermography.thermal_analysis import leg_part_metrics


class AnatomicalBoxReferenceTests(unittest.TestCase):
    def test_divisions_keep_box_coordinates_after_segmentation(self):
        mask = np.zeros((100, 20), dtype=bool)
        mask[25:75, 5:15] = True
        temperatures = np.full(mask.shape, 35.0)
        box = dict(left=0, top=10, width=20, height=80)
        parts, boundaries = leg_part_metrics(temperatures, mask, 30,
                                            (25, 50, 75), axis='vertical', region_box=box)
        self.assertEqual(boundaries, (30, 50, 70))
        self.assertEqual(sum(part['total_pixels'] for part in parts.values()), int(mask.sum()))
        self.assertEqual(sum(part['hot_pixels'] for part in parts.values()), int(mask.sum()))
