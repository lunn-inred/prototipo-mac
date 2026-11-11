"""Seleção paginada de análises e recuperação do rascunho de edição."""
import io
import math
import streamlit as st

from frontend.streamlit.api_client.local_analyses import list_local_analyses, load_local_analysis
from frontend.streamlit.components.player_cards import render_player_card_style, compact_player_card
from frontend.streamlit.presentation.player_data import player_name
from .draft_state import clear_analysis_draft


def load_into_wizard(entry):
    # Preparar tudo antes de descartar o rascunho atual, inclusive imagens legadas.
    from .wizard import rotated_view
    uploads, items = {}, {}
    for view, source in entry['views'].items():
        rotation = int(source.get('image_rotation', 0))
        original = source['image'].rotate(-rotation, expand=True)
        buffer = io.BytesIO(); original.save(buffer, format='PNG')
        content = buffer.getvalue()
        _image, _content, signature = rotated_view(content, rotation)
        uploads[view] = dict(name=source.get('original_filename') or f'{view}.png', content=content, rotation=rotation)
        settings = {side: dict(cuts=list(config['cuts']), axis='vertical', foot_at_end=True)
                    for side, config in source['part_settings'].items()}
        items[f'{view}:{signature}'] = dict(
            minimum_temperature=source['minimum_temperature'], maximum_temperature=source['maximum_temperature'],
            threshold_percentage=source['threshold_percentage'], threshold_temperature=source['default_threshold'],
            threshold_mode='Temperatura (°C)', image_rotation=rotation,
            manual_boxes=source['boxes'], manual_colorbar_box=source.get('colorbar_box'),
            part_settings_v4=settings,
            saved_analysis=dict(masks={side: mask.copy() for side, mask in source['segmentation_masks'].items()},
                temperatures=source['temperatures'].copy(), boxes=source['boxes'],
                minimum_temperature=source['minimum_temperature'], maximum_temperature=source['maximum_temperature'],
                colorbar_box=source.get('colorbar_box'), image_rotation=rotation))
    clear_analysis_draft()
    st.session_state['thermal_uploads'] = uploads
    st.session_state['thermography_items'] = items
    st.session_state['thermal_draft'] = dict(player=entry['athlete_id'], mass=entry['mass'],
                                            pain=entry['pain_score'], notes=entry['observations'])
    st.session_state['thermal_edit_source'] = {key: entry[key] for key in ('athlete_id', 'collected_at', 'id', 'created_at')}
    st.session_state['thermal_step'] = 0


def _choose_player(player_id):
    st.session_state['analysis_browser_player'] = player_id
    st.session_state['analysis_browser_page'] = 0
    st.session_state.pop('analysis_browser_error', None)


def _select_analysis(entry):
    try:
        load_into_wizard(load_local_analysis(entry))
    except Exception:
        st.session_state['analysis_browser_error'] = 'Não foi possível abrir esta análise. O rascunho atual foi preservado.'
    else:
        st.session_state['analysis_browser_loaded'] = True


def _page(page):
    st.session_state['analysis_browser_page'] = page


def _pagination(total, size):
    pages = max(1, math.ceil(total / size))
    page = min(st.session_state.get('analysis_browser_page', 0), pages - 1)
    st.caption(f'Página {page+1} de {pages}')
    previous, following = st.columns(2)
    previous.button('Anterior', disabled=page == 0, width='stretch', on_click=_page, args=(page-1,), key='analysis_browser_previous')
    following.button('Próxima', disabled=page == pages-1, width='stretch', on_click=_page, args=(page+1,), key='analysis_browser_next')
    return page * size


@st.dialog('Ver análises anteriores', width='large')
def show_history(athletes):
    if st.session_state.pop('analysis_browser_loaded', False):
        st.rerun()
    render_player_card_style()
    player_id = st.session_state.get('analysis_browser_player')
    if player_id not in athletes:
        query = st.text_input('Buscar atleta', key='analysis_browser_query').strip().casefold()
        if query != st.session_state.get('analysis_browser_last_query'):
            st.session_state['analysis_browser_page'] = 0
            st.session_state['analysis_browser_last_query'] = query
        players = sorted((athlete for athlete in athletes.values()
                          if query in (player_name(athlete)+' '+str(athlete.get('nome', ''))).casefold()), key=player_name)
        offset = _pagination(len(players), 6)
        visible = players[offset:offset+6]
        if not visible:
            st.info('Nenhum atleta encontrado.')
        for start in range(0, len(visible), 3):
            for column, athlete in zip(st.columns(3), visible[start:start+3]):
                with column:
                    # HTML composto contém recuos/quebras que o Markdown pode
                    # interpretar como código; não passar por st.markdown.
                    st.html(compact_player_card(athlete))
                    st.button('Selecionar atleta', width='stretch', key=f'analysis_player_{athlete["id_atleta"]}',
                              on_click=_choose_player, args=(int(athlete['id_atleta']),))
    else:
        st.markdown(f'#### Análises de {player_name(athletes[player_id])}')
        st.button('Voltar aos atletas', width='stretch', on_click=_choose_player, args=(None,), key='analysis_browser_back')
        try:
            analyses = sorted(list_local_analyses(player_id), key=lambda item: (item['collected_at'], item['created_at']), reverse=True)
        except ValueError as error:
            st.error(str(error)); return
        offset = _pagination(len(analyses), 3)
        if not analyses:
            st.info('Não há análises salvas para este atleta.')
        for column, entry in zip(st.columns(3), analyses[offset:offset+3]):
            with column:
                with st.container(border=True):
                    st.markdown(f'**{entry["collected_at"]:%d/%m/%Y}**')
                    st.image(entry['thumbnail'], width='content')
                    st.caption(f'Massa: {entry["mass"] if entry["mass"] is not None else "—"} kg · EVA: {entry["pain_score"] if entry["pain_score"] is not None else "—"}')
                    st.button('Selecionar análise', width='stretch', key=f'analysis_select_{entry["id"]}',
                              on_click=_select_analysis, args=(entry,))
    if error := st.session_state.get('analysis_browser_error'):
        st.error(error)
    st.caption('Ao abrir uma análise, o rascunho atual é substituído. Os registros só mudam ao salvar.')
    if st.button('Concluir', type='primary', width='stretch', key='analysis_browser_close'):
        st.rerun()


@st.fragment
def render_history_button(athletes):
    if st.button('Ver análises anteriores', width='stretch', disabled=not athletes, key='thermal_history_open'):
        st.session_state.pop('analysis_browser_loaded', None)
        show_history(athletes)
