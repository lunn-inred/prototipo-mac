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
                if st.button('Selecionar basal', key=f"timeline_basal_{entry['id']}",
                             width='stretch', on_click=_select_baseline,
                             args=(str(entry['id']), athlete_id)):
                    st.rerun()


def _timeline_view_at_threshold(source, threshold):
    from frontend.streamlit.api_client.thermal_client import timeline_view_at_threshold
    return timeline_view_at_threshold(source, threshold)


def _render_comparison(t0: dict[str, Any], ti: dict[str, Any]) -> None:
    try:
        t0, ti = _load_saved_entry(t0), _load_saved_entry(ti)
    except ValueError as error:
        st.error(f"Não foi possível carregar as imagens da análise: {error}")
        return
    st.markdown("#### Comparação Basal × Atual")
    st.caption(
        f"Basal: {t0['collected_at'].strftime('%d/%m/%Y')} · "
        f"Atual: {ti['collected_at'].strftime('%d/%m/%Y')}"
    )
    tabs = st.tabs(["Frente", "Verso"])
    for tab, view_key in zip(tabs, ("front", "back")):
        with tab:
            baseline_source = t0["views"][view_key]
            current_source = ti["views"][view_key]
            threshold_columns = st.columns(2)
            with threshold_columns[0]:
                baseline_threshold = st.slider(
                    "Limiar da coleta basal (°C)",
                    min_value=float(baseline_source["minimum_temperature"]),
                    max_value=float(baseline_source["maximum_temperature"]),
                    value=float(baseline_source["default_threshold"]),
                    step=max(
                        (
                            float(baseline_source["maximum_temperature"])
                            - float(baseline_source["minimum_temperature"])
                        ) / 200,
                        0.01,
                    ),
                    key=f"timeline_threshold_t0_{t0['id']}_{view_key}",
                )
            with threshold_columns[1]:
                current_threshold = st.slider(
                    "Limiar da coleta atual (°C)",
                    min_value=float(current_source["minimum_temperature"]),
                    max_value=float(current_source["maximum_temperature"]),
                    value=float(current_source["default_threshold"]),
                    step=max(
                        (
                            float(current_source["maximum_temperature"])
                            - float(current_source["minimum_temperature"])
                        ) / 200,
                        0.01,
                    ),
                    key=f"timeline_threshold_ti_{ti['id']}_{view_key}",
                )
            st.caption(
                "O mapa e todas as métricas abaixo são recalculados imediatamente "
                "quando um dos limiares é alterado."
            )
            baseline = _timeline_view_at_threshold(
                baseline_source, baseline_threshold
            )
            current = _timeline_view_at_threshold(
                current_source, current_threshold
            )
            t0_column, ti_column, map_column, metrics_column = st.columns(
                [1.1, 1.1, 1.4, 1.2], gap="medium"
            )
            with t0_column:
                st.markdown("##### Basal")
                st.image(baseline["image"], width="stretch")
            with ti_column:
                st.markdown("##### Atual")
                st.image(current["image"], width="stretch")
            with map_column:
                st.markdown("##### Mapa comparativo")
                map_columns = st.columns(2)
                for column, (label, side) in zip(map_columns, LEGS.items()):
                    comparison = compare_hot_masks(
                        baseline["hot_masks"][side],
                        current["hot_masks"][side],
                        baseline["boxes"][side],
                        current["boxes"][side],
                    )
                    with column:
                        st.image(comparison["image"], caption=label, width="stretch")
                        compared_total = sum(
                            int(comparison[key])
                            for key in (
                                "new_pixels", "persistent_pixels", "resolved_pixels"
                            )
                        )
                        def category_value(key: str) -> str:
                            value = int(comparison[key])
                            percentage = value / compared_total * 100 if compared_total else 0.0
                            return f"{value:,} ({percentage:.1f}%)"
                        st.caption(
                            f"Novos: {category_value('new_pixels')} · "
                            f"Persistentes: {category_value('persistent_pixels')} · "
                            f"Resolvidos: {category_value('resolved_pixels')}"
                        )
                st.caption(
                    "Vermelho: novos · Amarelo: persistentes · Azul: resolvidos"
                )
            with metrics_column:
                st.markdown("##### Métricas atuais")
                st.caption(
                    f"Tmin {current['minimum_temperature']:.1f} °C · "
                    f"Tmax {current['maximum_temperature']:.1f} °C · "
                    f"limiar {current['threshold']:.1f} °C"
                )
                current_hot_total = sum(
                    int(current["metrics"][side]["hot_pixels"])
                    for side in LEGS.values()
                )
                baseline_hot_total = sum(
                    int(baseline["metrics"][side]["hot_pixels"])
                    for side in LEGS.values()
                )
                current_area_total = sum(
                    int(current["metrics"][side]["total_pixels"])
                    for side in LEGS.values()
                )
                baseline_area_total = sum(
                    int(baseline["metrics"][side]["total_pixels"])
                    for side in LEGS.values()
                )
                current_view_percentage = current_hot_total / current_area_total * 100
                baseline_view_percentage = baseline_hot_total / baseline_area_total * 100
                st.metric(
                    "Total da vista",
                    f"{current_hot_total:,} px".replace(",", "."),
                    delta=f"{current_hot_total - baseline_hot_total:+,} px".replace(",", "."),
                )
                st.caption(
                    f"{current_view_percentage:.1f}% "
                    f"({current_view_percentage - baseline_view_percentage:+.1f} p.p.)"
                )
                for label, side in LEGS.items():
                    current_metric = current["metrics"][side]
                    baseline_metric = baseline["metrics"][side]
                    hot_delta = int(current_metric["hot_pixels"]) - int(
                        baseline_metric["hot_pixels"]
                    )
                    percentage_delta = float(current_metric["hot_percentage"]) - float(
                        baseline_metric["hot_percentage"]
                    )
                    st.metric(
                        f"Pixels quentes — {label}",
                        f"{int(current_metric['hot_pixels']):,} px".replace(",", "."),
                        delta=f"{hot_delta:+,} px".replace(",", "."),
                    )
                    st.caption(
                        f"{float(current_metric['hot_percentage']):.1f}% "
                        f"({percentage_delta:+.1f} p.p.) · área: "
                        f"{int(current_metric['total_pixels']):,} px".replace(",", ".")
                    )


def render_timeline(athletes: list[dict[str, Any]]) -> None:
    st.subheader("Timeline térmica")
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

    baseline_column, button_column = st.columns([3, 1])
    with baseline_column:
        st.caption(f"Basal: {t0['collected_at'].strftime('%d/%m/%Y')}")
    with button_column:
        if st.button('Mudar Basal', key='timeline_change_basal', width='stretch'):
            choose_baseline(selected_player_id)

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
    st.caption('Análises armazenadas localmente no servidor da API. A seleção não altera os arquivos salvos.')
    if ti['collected_at'] < t0['collected_at']:
        st.warning(
            'A coleta Atual está registrada antes da Basal. A comparação '
            'continua disponível, mas confira se essa ordem foi intencional.'
        )
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

