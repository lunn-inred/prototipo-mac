import unittest
from frontend.streamlit.components.image_fonts import FONT_PATH, image_font


class ImageFontTests(unittest.TestCase):
    def test_bundled_font_is_used_at_requested_size(self):
        font = image_font(25)
        self.assertTrue(FONT_PATH.is_file())
        self.assertEqual(font.path, str(FONT_PATH))
        self.assertEqual(font.size, 25)

    def test_portuguese_accents_do_not_use_missing_character_glyph(self):
        font = image_font(25)
        missing = bytes(font.getmask('\u0378'))
        for letter in 'éáãçõ':
            with self.subTest(letter=letter):
                self.assertNotEqual(bytes(font.getmask(letter)), missing)
