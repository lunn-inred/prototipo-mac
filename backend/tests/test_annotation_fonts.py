import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from backend.mac_api.core.image_fonts import image_font
from backend.mac_api.modules.thermography.thermal_analysis import annotate_boxes


class AnnotationFontTests(unittest.TestCase):
    def test_box_labels_use_bundled_unicode_font(self):
        font = image_font(10)
        self.assertEqual(font.size, 10)
        self.assertNotEqual(bytes(font.getmask('é')), bytes(font.getmask('\u0378')))
        with patch.object(ImageDraw.ImageDraw, 'text') as text:
            annotate_boxes(Image.new('RGB', (300, 300)),
                           {'Perna direita': dict(left=10, top=10, width=180, height=250)})
        # O tamanho visual pode ser ajustado manualmente; preservar a fonte Unicode.
        self.assertEqual(text.call_args.kwargs['font'].path, font.path)
