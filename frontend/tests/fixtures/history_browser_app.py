"""Diagnóstico visual do histórico; somente atletas/análises fictícios, sem API."""
import ast
from datetime import date, timedelta
from pathlib import Path
import streamlit as st
from PIL import Image
from frontend.streamlit.components.thermography import history
from frontend.streamlit.components.ui import apply_global_style

st.set_page_config(layout='wide')
apply_global_style()
page = Path(__file__).resolve().parents[2] / 'streamlit/pages/Termografia.py'
for node in ast.walk(ast.parse(page.read_text())):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'html':
        st.html(ast.literal_eval(node.args[0]))

history.list_local_analyses = lambda athlete_id, **kwargs: [
    dict(id=f'test-{index}', athlete_id=athlete_id, collected_at=date(2026, 1, 1) + timedelta(days=index),
         created_at=f'2026-01-01T00:00:{index:02d}+00:00', mass=75., pain_score=0,
         thumbnail=Image.new('RGB', (160, 240), 'navy'), is_draft=index % 3 == 0)
    for index in range(30)
]
history.render_history_button({index: dict(id_atleta=index, nome=f'Atleta {index:02d}', posicao='Meia')
                               for index in range(1, 61)})
