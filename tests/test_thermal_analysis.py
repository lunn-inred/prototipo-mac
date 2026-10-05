import unittest

import numpy as np
from PIL import Image

from thermal_analysis import (
    count_hot_pixels,
    extract_temperature_scale,
    segmentation_overlay,
    scale_percentage_from_temperature,
    temperature_from_scale_percentage,
    temperature_matrix,
)


class ThermalAnalysisTests(unittest.TestCase):

    def test_converts_scale_percentage_to_temperature(self) -> None:
        self.assertEqual(temperature_from_scale_percentage(20.0, 40.0, 0), 20.0)
        self.assertEqual(temperature_from_scale_percentage(20.0, 40.0, 90), 38.0)
        self.assertEqual(temperature_from_scale_percentage(20.0, 40.0, 100), 40.0)
        self.assertAlmostEqual(
            temperature_from_scale_percentage(26.8, 34.6, 90), 33.82
        )

    def test_same_percentage_respects_each_view_scale(self) -> None:
        front = temperature_from_scale_percentage(20.0, 40.0, 90)
        back = temperature_from_scale_percentage(25.0, 35.0, 90)

        self.assertEqual(front, 38.0)
        self.assertEqual(back, 34.0)

    def test_temperature_and_percentage_conversions_are_inverse(self) -> None:
        percentage = scale_percentage_from_temperature(26.8, 34.6, 33.82)
        restored = temperature_from_scale_percentage(26.8, 34.6, percentage)

        self.assertAlmostEqual(percentage, 90.0)
        self.assertAlmostEqual(restored, 33.82)

    def test_rejects_invalid_scale_percentage_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "Tmax"):
            temperature_from_scale_percentage(30.0, 30.0, 90)
        with self.assertRaisesRegex(ValueError, "porcentagem"):
            temperature_from_scale_percentage(20.0, 40.0, 101)
        with self.assertRaisesRegex(ValueError, "entre Tmin e Tmax"):
            scale_percentage_from_temperature(20.0, 40.0, 41.0)

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

        temperatures = temperature_matrix(
            image, 20.0, 40.0,
            {"left": 96, "top": 5, "width": 4, "height": 87},
        )

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

    def test_counts_hot_pixels_over_segmented_leg_area(self) -> None:
        matrix = np.asarray(
            [[20.0, 30.0, 40.0], [25.0, 35.0, 39.0]], dtype=np.float32
        )
        box = {"left": 1, "top": 0, "width": 2, "height": 2}
        mask = np.asarray(
            [[False, True, True], [False, True, False]], dtype=bool
        )

        hot, total = count_hot_pixels(matrix, box, 39.0, mask)

        self.assertEqual(hot, 1)
        self.assertEqual(total, 3)

    def test_segmentation_preview_darkens_only_background(self) -> None:
        source = np.full((10, 10, 3), 200, dtype=np.uint8)
        mask = np.zeros((10, 10), dtype=bool)
        mask[3:7, 3:7] = True
        box = {"left": 2, "top": 2, "width": 6, "height": 6}

        preview = np.asarray(segmentation_overlay(
            Image.fromarray(source), {"right": box}, {"right": mask}
        ))

        self.assertTrue(np.all(preview[5, 5] == source[5, 5]))
        self.assertTrue(np.all(preview[0, 0] < source[0, 0]))

    def test_rejects_invalid_temperature_scale(self) -> None:
        image = Image.new("RGB", (2, 2), "red")
        with self.assertRaisesRegex(ValueError, "Tmax"):
            temperature_matrix(image, 30.0, 30.0)


if __name__ == "__main__":
    unittest.main()
