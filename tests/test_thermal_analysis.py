import unittest

import numpy as np
from PIL import Image

from thermal_analysis import (
    count_hot_pixels, extract_temperature_scale, temperature_matrix,
)


class ThermalAnalysisTests(unittest.TestCase):

    def test_extracts_temperature_scale_with_sol_ia_regions(self) -> None:
        image = Image.new("RGB", (1000, 500), "black")
        outputs = iter(["34.6 C", "26,8 C"])

        minimum, maximum = extract_temperature_scale(
            image, ocr=lambda _region: next(outputs)
        )

        self.assertEqual(minimum, 26.8)
        self.assertEqual(maximum, 34.6)

    def test_rejects_incomplete_or_inverted_ocr_scale(self) -> None:
        image = Image.new("RGB", (1000, 500), "black")
        for outputs in (("", "26.8"), ("20.0", "30.0")):
            values = iter(outputs)
            with self.assertRaisesRegex(ValueError, "reconhecer|Tmax"):
                extract_temperature_scale(
                    image, ocr=lambda _region: next(values)
                )

    def test_maps_extracted_colorbar_extremes_to_temperature_limits(self) -> None:
        pixels = np.zeros((100, 100, 3), dtype=np.uint8)
        gradient = np.linspace(255, 0, 87, dtype=np.uint8)
        pixels[5:92, 96:100] = gradient[:, None, None]
        pixels[50, 0] = (0, 0, 0)
        pixels[50, 1] = (255, 255, 255)
        image = Image.fromarray(pixels)

        temperatures = temperature_matrix(image, 20.0, 40.0)

        self.assertAlmostEqual(float(temperatures[50, 0]), 20.0, places=4)
        self.assertAlmostEqual(float(temperatures[50, 1]), 40.0, places=4)

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
