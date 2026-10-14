import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from backend.mac_api.core.image_fonts import image_font
from backend.mac_api.modules.thermography.thermal_analysis import annotate_boxes


class AnnotationFontTests(unittest.TestCase):
    def test_box_labels_use_bundled_unicode_font_at_10_pixels(self):
        font = image_font(10)
        self.assertEqual(font.size, 10)
        self.assertNotEqual(bytes(font.getmask('é')), bytes(font.getmask('\u0378')))
        with patch.object(ImageDraw.ImageDraw, 'text') as text:
            annotate_boxes(Image.new('RGB', (300, 300)),
                           {'Perna direita': dict(left=10, top=10, width=180, height=250)})
        self.assertEqual(text.call_args.kwargs['font'].size, 10)
