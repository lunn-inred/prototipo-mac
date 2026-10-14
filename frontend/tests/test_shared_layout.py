import unittest
from unittest.mock import patch
from frontend.streamlit.components.ui import apply_global_style


class SharedLayoutTests(unittest.TestCase):
    @patch('frontend.streamlit.components.ui.st.logo')
    @patch('frontend.streamlit.components.ui.st.markdown')
    def test_global_theme_has_centered_bounded_responsive_width(self, markdown, _logo):
        apply_global_style()
        css = markdown.call_args.args[0]
        self.assertIn('width: 90%', css)
        self.assertIn('max-width: 1440px', css)
        self.assertIn('margin-inline: auto', css)
        self.assertIn('@media (max-width: 900px)', css)
        self.assertIn('width: 100%', css)
