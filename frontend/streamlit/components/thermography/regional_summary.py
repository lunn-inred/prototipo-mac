"""Revisão compacta das contagens calculadas pela API."""
import pandas as pd
import streamlit as st
from frontend.streamlit.api_client.thermal_client import preview_regional_zones
from .timeline import views_for_storage


@st.cache_data(show_spinner=False, max_entries=8)
def _preview(sources):
    return preview_regional_zones(sources)


def regional_frame(measurements, view, side):
    frame = pd.DataFrame([
        {'Região': label, **{
            zone_label: measurements[f'{region}_{side}_{view}_ZONA_{zone}']
            for zone, zone_label in (('FRIA', 'Fria'), ('NEUTRA', 'Neutra'), ('QUENTE', 'Quente'))
        }}
        for region, label in (('COXA', 'Coxa'), ('JOELHO', 'Joelho'), ('CANELA', 'Canela'), ('PE', 'Pé'))
    ])
    frame.loc[len(frame)] = {'Região': 'Total', **{
        zone: int(frame[zone].sum()) for zone in ('Fria', 'Neutra', 'Quente')
    }}
    return frame


def render_regional_summary(views, items, reviewed_record=None):
    st.markdown('#### Pixels por região e zona')
    st.caption('Fria < 31 °C · Neutra de 31 a < 33 °C · Quente ≥ 33 °C. As três zonas serão registradas.')
    try:
        with st.spinner('Preparando as contagens por região…'):
            measurements = _preview(views_for_storage(views, items))
    except Exception:
        st.error('Não foi possível conferir as contagens por região. Confira se a API está atualizada e tente novamente.')
        return False
    for tab, view in zip(st.tabs(['Frente', 'Costas']), ('FRENTE', 'VERSO')):
        with tab:
            for column, side, label in zip(st.columns(2), ('ESQUERDA', 'DIREITA'), ('Perna esquerda', 'Perna direita')):
                with column:
                    with st.container(border=True):
                        st.markdown(f'**{label}**')
                        st.dataframe(
                            regional_frame(measurements, view, side), hide_index=True,
                            width='stretch', height=213,
                            column_config={name: st.column_config.NumberColumn(
                                name, format='%d', help='Contagem de pixels segmentados nesta zona.')
                                for name in ('Fria', 'Neutra', 'Quente')},
                        )
    st.caption('Contagens calculadas pelas imagens. Para corrigir os valores, ajuste as divisões ou a segmentação.')
    for column, label, step, key in zip(
        st.columns(2), ('Ajustar divisões anatômicas', 'Ajustar segmentação'),
        (3, 4), ('regional_edit_parts', 'regional_edit_masks'),
    ):
        if column.button(label, key=key, width='stretch'):
            if reviewed_record is not None:
                st.session_state.setdefault('thermal_draft', {}).update(reviewed_record)
            st.session_state['thermal_step'] = step
            st.rerun()
    return True
