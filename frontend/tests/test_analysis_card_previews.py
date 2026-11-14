import base64
from datetime import date
import io
import re
import unittest
from PIL import Image
from streamlit.testing.v1 import AppTest


class AnalysisCardPreviewTests(unittest.TestCase):
    def app(self, entry):
        app = AppTest.from_string('''
import streamlit as st
from frontend.streamlit.components.thermography.analysis_cards import render_analysis_card_style, selectable_analysis_card
def select():
    st.session_state['fixture_selected'] = True
render_analysis_card_style()
selectable_analysis_card(st.session_state['fixture_entry'],key='fixture_card',on_click=select,args=(),details='Massa e EVA')
''')
        app.session_state['fixture_entry'] = dict(collected_at=date(2026,11,14), **entry)
        return app.run()

    def test_two_high_resolution_previews_are_not_reduced_again_and_card_stays_clickable(self):
        app = self.app(dict(thumbnails=dict(front=Image.new('RGB',(640,480),'red'),back=Image.new('RGB',(640,480),'blue'))))
        self.assertFalse(app.exception)
        label = app.button(key='fixture_card').label
        self.assertIn('**Frente**\n![Frente]',label)
        self.assertIn('**Costas**\n![Costas]',label)
        images = re.findall(r'data:image/png;base64,([A-Za-z0-9+/=]+)',label)
        self.assertEqual(len(images),2)
        decoded = [Image.open(io.BytesIO(base64.b64decode(value))) for value in images]
        self.assertEqual([image.size for image in decoded],[(640,480),(640,480)])
        self.assertEqual(decoded[0].getpixel((0,0)),(255,0,0))
        self.assertEqual(decoded[1].getpixel((0,0)),(0,0,255))
        app.button(key='fixture_card').click().run()
        self.assertTrue(app.session_state['fixture_selected'])

    def test_missing_view_is_labelled_instead_of_duplicating_the_existing_one(self):
        app = self.app(dict(is_draft=True,thumbnails=dict(front=Image.new('RGB',(640,480),'red'))))
        self.assertFalse(app.exception)
        label = app.button(key='fixture_card').label
        self.assertEqual(label.count('Imagem não enviada'),1)
        self.assertIn(':red[Análise incompleta]',label)
        self.assertIn('**Costas**',label)

    def test_empty_partial_and_legacy_summary_are_still_supported(self):
        empty = self.app(dict(is_draft=True,thumbnails={}))
        self.assertEqual(empty.button(key='fixture_card').label.count('Imagem não enviada'),2)
        legacy = self.app(dict(thumbnail=Image.new('RGB',(80,120),'red')))
        self.assertFalse(legacy.exception)
        self.assertIn('![Análise de 14/11/2026]',legacy.button(key='fixture_card').label)
