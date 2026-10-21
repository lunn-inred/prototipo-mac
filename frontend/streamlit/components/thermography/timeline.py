from __future__ import annotations
import hashlib
import io
from datetime import date
from typing import Any
import numpy as np
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from streamlit_drawable_konva import crop_box_from_json, st_canvas
from frontend.streamlit.api_client.contracts import (unique_matching_athlete_id)
from frontend.streamlit.api_client.thermal_client import compare_temperature_maps
from frontend.streamlit.api_client.thermal_client import (annotate_boxes, compare_hot_masks, count_hot_pixels, detect_colorbar_box, detect_leg_boxes, hot_pixels_overlay, segmentation_overlay, segment_leg_mask, temperature_matrix, DEFAULT_PART_CUTS, LEG_PARTS, leg_part_metrics, scale_percentage_from_temperature, temperature_from_scale_percentage)
from frontend.streamlit.presentation.thermography_data import (
    athlete_label,
    load_thermography_athletes,
    load_thermography_history,
)
from frontend.streamlit.api_client.contracts import (DuplicateThermographyError, LegacyThermographyRecord, current_sao_paulo_date)
from frontend.streamlit.api_client.service_gateway import (
    extract_thermography_scale,
    extract_legacy_documents,
    save_image_thermography,
    save_legacy_thermography,
)
from frontend.streamlit.components.thermography.editor import LEGS, VIEW_LABELS
from frontend.streamlit.api_client.local_analyses import save_local_analysis, list_local_analyses, load_local_analysis

@st.cache_data(ttl=60, show_spinner=False)
def _load_saved_entry(entry):
    return load_local_analysis(entry)


def _timeline_sort_key(entry: dict[str, Any]) -> tuple[date, int]:
    return entry["collected_at"], int(entry["sequence"])


def _timeline_entry_by_id(entry_id: str | None) -> dict[str, Any] | None:
    if entry_id is None:
        return None
    return next(
        (
            entry
            for entry in st.session_state.get("thermography_timeline", [])
            if str(entry["id"]) == str(entry_id)
        ),
        None,
    )


def _analyses_by_date(entries: list[dict[str, Any]]) -> dict[date, dict[str, Any]]:
    """Uma coleta por data; em duplicatas, vence a última registrada."""
    return {entry['collected_at']: entry for entry in sorted(entries, key=_timeline_sort_key)}


def _select_baseline(entry_id: str, athlete_id: int) -> None:
    """Callback: atualiza o basal antes da renderização da comparação."""
    entry = _timeline_entry_by_id(entry_id)
    if entry is None or int(entry['athlete_id']) != athlete_id:
        st.session_state['thermography_timeline_message'] = 'A análise selecionada não está mais disponível.'
        return
    st.session_state[f'thermography_timeline_basal_{athlete_id}'] = str(entry['id'])
    st.session_state['thermography_timeline_t0'] = str(entry['id'])


@st.dialog("Mudar Basal", width="large")
def choose_baseline(athlete_id: int) -> None:
    st.caption("Selecione uma análise deste jogador para usar como basal.")
    entries = st.session_state.get('thermography_timeline', [])
    columns = st.columns(3)
    for index, entry in enumerate(entries):
        if int(entry['athlete_id']) != athlete_id:
            continue
        with columns[index % 3]:
            with st.container(border=True):
                thumbnail = entry['thumbnail'].copy()
                thumbnail.thumbnail((250, 180))
                st.image(thumbnail, width='content')
                st.write(entry['collected_at'].strftime('%d/%m/%Y'))
                st.caption(f"Análise {entry['id'][:8]}")
                if st.button('Selecionar', key=f"timeline_basal_{entry['id']}",
                             width='stretch', on_click=_select_baseline,
                             args=(str(entry['id']), athlete_id)):
                    st.rerun()


def _timeline_view_at_threshold(source, threshold):
    from frontend.streamlit.api_client.thermal_client import timeline_view_at_threshold
    return timeline_view_at_threshold(source, threshold)


@st.cache_data(ttl=60, max_entries=64, show_spinner=False)
def _cached_comparison(baseline_entry, current_entry, limit=None, gamma=0.5):
    baseline = _load_saved_entry(baseline_entry)
    current = _load_saved_entry(current_entry)
    front = compare_temperature_maps(baseline['views']['front'], current['views']['front'], limit=limit, gamma=gamma)
    back = compare_temperature_maps(baseline['views']['back'], current['views']['back'],
                                    limit=limit, palette=front.get('palette'), gamma=gamma)
    return {'front': front, 'back': back}


def _render_comparison(t0: dict[str, Any], ti: dict[str, Any]) -> None:
    st.markdown('#### Comparação Basal × Atual')
    gamma = st.slider(
        'Contraste das cores (gamma)', min_value=0.2, max_value=1.0,
        value=0.5, step=0.05, key='timeline_comparison_gamma',
        help='Valores menores destacam diferenças pequenas. 1 mantém o contraste linear. '
             'Não altera temperaturas, limiares ou métricas e também pode realçar ruído.',
    )
    try:
        with st.spinner('Preparando comparação térmica…'):
            comparisons = _cached_comparison(t0, ti, gamma=gamma)
            t0, ti = _load_saved_entry(t0), _load_saved_entry(ti)
    except ValueError as error:
        st.error(f'Não foi possível carregar a comparação: {error}')
        return
    st.caption(
        'A coleta atual é alinhada por coxa, joelho, canela e pé na segmentação basal. '
        'O encaixe é aproximado e depende das divisões e máscaras revisadas pelo usuário.'
    )
    tabs = st.tabs(['Frente', 'Costas'])
    for tab, view_key in zip(tabs, ('front', 'back')):
        with tab:
            baseline = t0['views'][view_key]
            current = ti['views'][view_key]
            comparison = comparisons[view_key]
            t0_column, ti_column, map_column, metrics_column = st.columns(
                [1.1, 1.1, 1.4, 1.2], gap='medium'
            )
            with t0_column:
                st.markdown(f"##### Basal ({t0['collected_at'].strftime('%d/%m/%Y')})")
                st.image(baseline['image'], width='stretch')
                button_key = 'timeline_change_basal' if view_key == 'front' else 'timeline_change_basal_back'
                if st.button('Mudar Basal', key=button_key, width='stretch'):
                    choose_baseline(int(t0['athlete_id']))
            with ti_column:
                st.markdown(f"##### Atual ({ti['collected_at'].strftime('%d/%m/%Y')})")
                st.image(current['image'], width='stretch')
            with map_column:
                st.markdown('##### Mapa comparativo')
                if not comparison['has_overlap']:
                    st.warning('As segmentações não possuem área em comum para comparação.')
                map_columns = st.columns(2)
                # Vista frontal: a direita anatômica aparece à esquerda de quem vê.
                leg_order = list(LEGS.items())
                if view_key == 'front':
                    leg_order.reverse()
                for column, (label, side) in zip(map_columns, leg_order):
                    with column:
                        st.image(comparison['images'][side], caption=label, width='stretch')
                st.image(comparison['legend'], width='stretch')
            with metrics_column:
                st.markdown('##### Área quente comparada')
                for label, side in LEGS.items():
                    previous = comparison['summaries'][side]['baseline']['total']['hot_percentage']
                    actual = comparison['summaries'][side]['current']['total']['hot_percentage']
                    if previous is None or actual is None:
                        st.caption(f'{label}: sem pixels válidos para calcular a área quente.')
                        continue
                    st.metric(f'Área quente — {label}', f'{actual:.1f}%',
                              delta=f'{actual - previous:+.1f} p.p.')
                    st.caption(f'Basal: {previous:.1f}% da área segmentada.')



def render_timeline(athletes: list[dict[str, Any]]) -> None:
    players = {int(athlete['id_atleta']): athlete for athlete in athletes}
    selector_key = 'thermography_timeline_player'
    if st.session_state.get(selector_key) not in players:
        st.session_state.pop(selector_key, None)
    selected_player_id = st.selectbox(
        'Jogador da timeline', list(players), index=None,
        format_func=lambda player_id: athlete_label(players[player_id]),
        placeholder='Selecione um jogador para consultar suas análises',
        disabled=not players, key=selector_key,
    )
    if message := st.session_state.pop("thermography_timeline_message", None):
        st.warning(message)
    if selected_player_id is None:
        st.caption("Selecione um jogador para visualizar e comparar suas análises salvas localmente.")
        return

    try:
        entries = sorted(list_local_analyses(selected_player_id), key=_timeline_sort_key)
    except ValueError as error:
        st.error(f"Não foi possível carregar as análises locais: {error}")
        return
    st.session_state["thermography_timeline"] = entries
    valid_ids = {str(entry['id']) for entry in entries}
    if not entries:
        st.session_state.pop('thermography_timeline_t0', None)
        st.session_state.pop('thermography_timeline_ti', None)
        st.caption(
            "Analise um par de imagens e use “Adicionar à timeline”. "
            "As imagens e máscaras serão salvas no diretório local da API."
        )
        return

    by_date = _analyses_by_date(entries)
    dates = list(by_date)
    basal_key = f'thermography_timeline_basal_{selected_player_id}'
    if st.session_state.get(basal_key) not in valid_ids:
        st.session_state[basal_key] = str(by_date[dates[0]]['id'])
    st.session_state['thermography_timeline_t0'] = st.session_state[basal_key]
    t0 = _timeline_entry_by_id(st.session_state['thermography_timeline_t0'])

    # Reserva o espaço das prévias acima da barra; calcula depois de ler a data
    # para que a comparação reflita a seleção já no mesmo rerun.
    comparison_container = st.container()
    date_key = f'thermography_timeline_date_{selected_player_id}'
    if st.session_state.get(date_key) not in by_date:
        st.session_state[date_key] = dates[-1]
    if len(dates) == 1:
        selected_date = dates[0]
        st.caption(f"Coleta atual: {selected_date.strftime('%d/%m/%Y')} · Única data disponível.")
    else:
        selected_date = st.select_slider(
            'Data da coleta atual', options=dates,
            format_func=lambda value: value.strftime('%d/%m/%Y'),
            key=date_key,
            help='Arraste para uma data com coleta. O basal permanece fixo.',
        )
    ti = by_date[selected_date]
    st.session_state['thermography_timeline_ti'] = str(ti['id'])
    if ti['collected_at'] < t0['collected_at']:
        st.warning(
            'A coleta Atual está registrada antes da Basal. A comparação '
            'continua disponível, mas confira se essa ordem foi intencional.'
        )
    with comparison_container:
        _render_comparison(t0, ti)


def add_to_timeline(
    athlete_id: int,
    collected_at: date | None,
    views: dict[str, dict[str, Any]],
    items: dict[str, dict[str, Any]],
    *, athlete_name=None, mass=None, pain_score=None, observations="",
) -> None:
    stored_views = {}
    for view_key, view in views.items():
        item = items[f"{view_key}:{view['signature']}"]
        analysis = item["analysis"]
        stored_views[view_key] = {
            "image": view["image"], "original_filename": view.get("name", ""),
            "image_rotation": item.get("image_rotation", 0),
            "minimum_temperature": float(item["minimum_temperature"]),
            "maximum_temperature": float(item["maximum_temperature"]),
            "default_threshold": float(analysis["threshold"]),
            "boxes": analysis["boxes"], "colorbar_box": analysis.get("colorbar_box"),
            "temperatures": analysis["temperatures"], "segmentation_masks": analysis["masks"],
            "part_settings": item.get("part_settings_v4", {}),
        }
    entry = save_local_analysis(athlete_id, athlete_name or f"Atleta {athlete_id}",
                               collected_at or current_sao_paulo_date(), stored_views,
                               mass=mass, pain_score=pain_score, observations=observations)
    _load_saved_entry.clear()
    st.session_state['thermography_timeline_player'] = int(athlete_id)
    st.session_state["thermography_timeline_ti"] = entry["id"]
    # Ao retornar após um novo registro, iniciar pela data mais recente disponível,
    # mesmo quando a análise recém-enviada tiver uma data histórica.
    st.session_state.pop(f'thermography_timeline_date_{athlete_id}', None)
    st.session_state["thermography_timeline_message"] = "Análise salva localmente e adicionada à timeline."


@st.dialog("Data da coleta")
def confirm_timeline_date(
    athlete_id: int,
    views: dict[str, dict[str, Any]],
    items: dict[str, dict[str, Any]],
    pair_signature: str,
    *, athlete_name=None, mass=None, pain_score=None, observations="",
) -> None:
    st.caption("Informe a data em que as imagens termográficas foram coletadas.")
    collected_at = st.date_input(
        "Data de registro da coleta",
        value=current_sao_paulo_date(),
        key=f"timeline_collection_date_{pair_signature}",
    )
    if st.button(
        "Confirmar e adicionar à timeline",
        type="secondary",
        use_container_width=True,
        key=f"confirm_timeline_date_{pair_signature}",
    ):
        try:
            add_to_timeline(athlete_id, collected_at, views, items,
                            athlete_name=athlete_name, mass=mass, pain_score=pain_score,
                            observations=observations)
        except (ValueError, OSError) as error:
            st.error(f"Não foi possível salvar a análise local: {error}")
        else:
            st.rerun()

    if st.button('Concluir', type='primary', width='stretch', key=f'close_timeline_collection_{pair_signature}'):
        st.rerun()

