"""Reprodução visual isolada, sem banco ou API externa."""
import ast
from pathlib import Path
import streamlit as st
from PIL import Image
from frontend.streamlit.components.thermography.dialog_layout import dialog_canvas_limits
from frontend.streamlit.components.thermography.editor import _display_image

st.set_page_config(layout='wide')
page = Path(__file__).resolve().parents[2] / 'streamlit/pages/Termografia.py'
for node in ast.walk(ast.parse(page.read_text())):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'html':
        st.html(ast.literal_eval(node.args[0]))

@st.dialog('Teste de primeira abertura', width='large')
def editor():
    st.caption('Controles de teste')
    limits = dialog_canvas_limits('browser_test', toolbar=False)
    if limits is None:
        return
    width, height = limits
    st.caption(f'MEASURED {width} {height}')
    preview, _ = _display_image(Image.new('RGB', (400, 600), 'navy'), max_width=width, max_height=height)
    st.image(preview)
    if st.button('Concluir', type='primary'):
        st.rerun()

if st.button('Abrir'):
    editor()
