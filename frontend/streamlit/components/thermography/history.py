"""Seleção rolável de análises e recuperação do rascunho de edição."""
import io
import base64
from copy import deepcopy
from datetime import date
import streamlit as st

from frontend.streamlit.api_client.local_analyses import list_local_analyses, load_local_analysis
from frontend.streamlit.components.player_cards import render_player_card_style, selectable_player_card
from frontend.streamlit.presentation.player_data import player_name
from .draft_state import clear_analysis_draft, set_metadata_widgets
from .analysis_cards import render_analysis_card_style, selectable_analysis_card


def load_into_wizard(entry):
    if entry.get('is_draft'):
        state = entry['state']
        uploads = {view: {**upload, 'content': base64.b64decode(upload['content'], validate=True)}
                   for view, upload in state.get('uploads', {}).items()}
        from .wizard import rotated_view
        items = {}
        for view, upload in uploads.items():
            _image, _content, signature = rotated_view(upload['content'], upload['rotation'])
            original = next((item for key, item in state.get('items', {}).items() if key.split(':')[0] == view), None)
            if original is not None:
                items[f'{view}:{signature}'] = original
        draft = dict(state['draft'])
        draft['collected_at'] = date.fromisoformat(draft['collected_at']) if draft.get('collected_at') else None
        step = min(state['step'], 5)
        if any(draft.get(field) is None for field in ('player', 'mass', 'pain')):
            step = 0
        elif set(uploads) != {'front', 'back'}:
            step = min(step, 1)
        source = state.get('source')
        if source:
            source = {**source, 'collected_at': date.fromisoformat(source['collected_at'])}
        clear_analysis_draft()
        st.session_state.update(thermal_uploads=uploads, thermography_items=items,
            thermal_draft=draft, thermal_step=step,
            thermal_saved_draft={key: entry[key] for key in ('id', 'created_at')})
        set_metadata_widgets(draft)
        if source:
            st.session_state['thermal_edit_source'] = source
        return
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
            manual_boxes=deepcopy(source['boxes']), manual_colorbar_box=deepcopy(source.get('colorbar_box')),
            part_settings_v4=settings,
            saved_analysis=dict(masks={side: mask.copy() for side, mask in source['segmentation_masks'].items()},
                temperatures=source['temperatures'].copy(), boxes=deepcopy(source['boxes']),
                minimum_temperature=source['minimum_temperature'], maximum_temperature=source['maximum_temperature'],
                colorbar_box=deepcopy(source.get('colorbar_box')), image_rotation=rotation))
    clear_analysis_draft()
    st.session_state['thermal_uploads'] = uploads
    st.session_state['thermography_items'] = items
    st.session_state['thermal_draft'] = dict(player=entry['athlete_id'], mass=entry['mass'],
                                            pain=entry['pain_score'], notes=entry['observations'], collected_at=entry['collected_at'])
    set_metadata_widgets(st.session_state['thermal_draft'])
    st.session_state['thermal_edit_source'] = {key: entry[key] for key in ('athlete_id', 'collected_at', 'id', 'created_at')}
    st.session_state['thermal_step'] = 0


def _choose_player(player_id):
    st.session_state['analysis_browser_player'] = player_id
    st.session_state.pop('analysis_browser_error', None)


def _select_analysis(entry):
    try:
        load_into_wizard(load_local_analysis(entry))
    except Exception:
        st.session_state['analysis_browser_error'] = 'Não foi possível abrir esta análise. O rascunho atual foi preservado.'
    else:
        st.session_state['analysis_browser_loaded'] = True


@st.dialog('Ver análises anteriores', width='large')
def show_history(athletes):
    if st.session_state.pop('analysis_browser_loaded', False):
        st.rerun()
    render_player_card_style()
    athletes = {**athletes, 0: dict(id_atleta=0, nome='Sem atleta (rascunhos)', posicao='Análises ainda não associadas', status='não associado')}
    # Os editores de imagem não têm scroll; somente esta lista é rolável.
    st.html('''<style>
        [data-testid="stDialog"]:has(.st-key-analysis_browser_results) {
            box-sizing: border-box;
            align-items: center !important;
        }
        [data-testid="stDialog"]:has(.st-key-analysis_browser_results) > div {
            margin-block: 0 !important;
            height: calc(100dvh - 2rem) !important;
            max-height: calc(100dvh - 2rem) !important;
        }
        [data-testid="stDialog"]:has(.st-key-analysis_browser_results) [role="dialog"] {
            height: 100% !important;
            max-height: 100% !important;
            padding-bottom: 0 !important;
            display: flex;
            flex-direction: column;
        }
        [data-testid="stDialog"]:has(.st-key-analysis_browser_results)
        [role="dialog"] > div:has(.st-key-analysis_browser_results) {
            display: flex;
            flex-direction: column;
            flex: 1 1 0%;
            min-height: 0;
            padding-bottom: 16px;
            overflow: hidden;
        }
        [data-testid="stDialog"]:has(.st-key-analysis_browser_results)
        :is([data-testid="stVerticalBlock"], [data-testid="stLayoutWrapper"]):has(.st-key-analysis_browser_results) {
            flex: 1 1 0% !important;
            min-height: 0 !important;
            height: auto !important;
            overflow: hidden;
        }
        .st-key-analysis_browser_results {
            /* O flex usa o espaço restante real, sem reservar 300 px fixos. */
            flex: 1 1 0% !important;
            min-height: 0 !important;
            height: auto !important;
            max-height: none !important;
            padding-bottom: 4px;
            overflow-y: auto;
            scrollbar-gutter: stable;
        }
    </style>''')
    player_id = st.session_state.get('analysis_browser_player')
    if player_id not in athletes:
        query = st.text_input('Buscar atleta', key='analysis_browser_query').strip().casefold()
        players = sorted((athlete for athlete in athletes.values()
                          if query in (player_name(athlete)+' '+str(athlete.get('nome', ''))).casefold()), key=player_name)
        if not players:
            st.info('Nenhum atleta encontrado.')
        with st.container(border=False, key='analysis_browser_results'):
            for start in range(0, len(players), 3):
                for column, athlete in zip(st.columns(3), players[start:start+3]):
                    with column:
                        selectable_player_card(athlete, on_click=_choose_player)
    else:
        render_analysis_card_style()
        st.markdown(f'#### Análises de {player_name(athletes[player_id])}')
        try:
            analyses = sorted(list_local_analyses(player_id, include_drafts=True), key=lambda item: (item['collected_at'], item['created_at']), reverse=True)
        except ValueError as error:
            st.error(str(error))
            analyses = None
        if analyses == []:
            st.info('Não há análises salvas para este atleta.')
        with st.container(border=False, key='analysis_browser_results'):
            for start in range(0, len(analyses or []), 3):
                for column, entry in zip(st.columns(3), analyses[start:start+3]):
                    with column:
                        selectable_analysis_card(
                            entry, key=f'analysis_select_{entry["id"]}',
                            on_click=_select_analysis, args=(entry,),
                            details=f'Massa: {entry["mass"] if entry["mass"] is not None else "—"} kg · EVA: {entry["pain_score"] if entry["pain_score"] is not None else "—"}',
                        )
        st.button('Voltar aos atletas', width='stretch', on_click=_choose_player, args=(None,), key='analysis_browser_back')
    if error := st.session_state.get('analysis_browser_error'):
        st.error(error)


def _reset_browser():
    # Callback do botão: não reiniciar durante reruns internos do diálogo.
    for key in list(st.session_state):
        if key.startswith('analysis_browser_'):
            st.session_state.pop(key, None)


@st.fragment
def render_history_button(athletes):
    if st.button('Ver análises anteriores', width='stretch',
                 key='thermal_history_open', on_click=_reset_browser):
        show_history(athletes)
