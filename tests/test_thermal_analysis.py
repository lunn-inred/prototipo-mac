import unittest

import numpy as np
from PIL import Image

from thermal_analysis import (
    count_hot_pixels,
    reference_palette,
    temperature_matrix,
)


class ThermalAnalysisTests(unittest.TestCase):
    def test_maps_palette_extremes_to_temperature_limits(self) -> None:
        palette = reference_palette().astype(np.uint8)
        image = Image.fromarray(np.asarray([[palette[0], palette[-1]]], dtype=np.uint8))

        temperatures = temperature_matrix(image, 20.0, 40.0)

        self.assertAlmostEqual(float(temperatures[0, 0]), 20.0, places=4)
        self.assertAlmostEqual(float(temperatures[0, 1]), 40.0, places=4)

    def test_counts_only_pixels_at_or_above_threshold_in_crop(self) -> None:
        matrix = np.asarray(
            [[20.0, 30.0, 40.0], [25.0, 35.0, 39.0]], dtype=np.float32
        )
        box = {"left": 1, "top": 0, "width": 2, "height": 2}

        hot, total = count_hot_pixels(matrix, box, 39.0)

        self.assertEqual(hot, 2)
        self.assertEqual(total, 4)

    def test_rejects_invalid_temperature_scale(self) -> None:
        image = Image.new("RGB", (2, 2), "red")
        with self.assertRaisesRegex(ValueError, "Tmax"):
            temperature_matrix(image, 30.0, 30.0)


if __name__ == "__main__":
    unittest.main()
