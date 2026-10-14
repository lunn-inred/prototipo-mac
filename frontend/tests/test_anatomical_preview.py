import unittest
from PIL import Image
from frontend.streamlit.components.thermography.editor import _parts_preview


class AnatomicalPreviewTests(unittest.TestCase):
    def test_preview_draws_current_user_box_without_mutating_image(self):
        image = Image.new('RGB', (300, 500), 'black')
        analysis = {'overlay': image, 'boxes': {'right': dict(left=40, top=50, width=180, height=400)}}
        settings = {'right': dict(cuts=[45, 57, 88], axis='vertical', foot_at_end=True)}
        preview = _parts_preview(image, analysis, settings)
        self.assertEqual(preview.getpixel((40, 50)), (0, 229, 255))
        self.assertEqual(preview.getpixel((219, 449)), (0, 229, 255))
        self.assertEqual(image.getpixel((40, 50)), (0, 0, 0))
