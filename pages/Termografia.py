from __future__ import annotations

import hashlib
import io
from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError

from thermal_analysis import (
    annotate_boxes,
    count_hot_pixels,
    detect_leg_boxes,
    temperature_matrix,
)
from legacy_thermography import extract_document
from thermography_data import (
    athlete_label,
    load_thermography_athletes,
    load_thermography_history,
)
from thermography_service import (
    DuplicateThermographyError,
    LegacyThermographyRecord,
    save_image_thermography,
    save_legacy_thermography,
)

st.set_page_config(
    page_title="MAC Performance | Termografia", page_icon="🌡️", layout="wide"
)

MAX_IMAGE_SIZE = 20 * 1024 * 1024
DEFAULT_MIN_TEMPERATURE = 20.0
DEFAULT_MAX_TEMPERATURE = 40.0
DEFAULT_HOT_FRACTION = 0.20
LEGS = {"Perna direita": "right", "Perna esquerda": "left"}
VIEW_LABELS = {"front": "Frente", "back": "Verso"}


def load_thermography(content: bytes) -> Image.Image:
    """Valida e normaliza a imagem enviada sem persistir o arquivo."""
    if not content:
        raise ValueError("A imagem enviada está vazia.")
    if len(content) > MAX_IMAGE_SIZE:
        raise ValueError("A imagem deve ter no máximo 20 MB.")
    try:
        with Image.open(io.BytesIO(content)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("O arquivo enviado não é uma imagem válida.") from error
    if image.width < 2 or image.height < 2:
        raise ValueError("A imagem não possui dimensões válidas.")
    return image


def image_signature(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def crop_from_box(image: Image.Image, box: dict[str, int]) -> Image.Image:
    left = int(box["left"])
    top = int(box["top"])
    return image.crop(
        (left, top, left + int(box["width"]), top + int(box["height"]))
    )


@st.cache_data(show_spinner=False)
def cached_leg_boxes(content: bytes) -> list[dict[str, int]]:
    return detect_leg_boxes(load_thermography(content))


@st.cache_data(show_spinner=False)
def cached_temperature_matrix(
    content: bytes,
    minimum_temperature: float,
    maximum_temperature: float,
) -> Any:
    return temperature_matrix(
        load_thermography(content), minimum_temperature, maximum_temperature
    )


def render_view(
    view_key: str,
    name: str,
    content: bytes,
    image: Image.Image,
    item: dict[str, Any],
) -> dict[str, dict[str, float | int]] | None:
    """Renderiza uma vista e retorna as métricas das duas pernas."""
    view_label = VIEW_LABELS[view_key]
    st.markdown(f"#### Imagem de {view_label.lower()}")
    st.caption(name)

    with st.container(border=True):
        minimum_column, maximum_column = st.columns(2)
        with minimum_column:
            minimum_temperature = st.number_input(
                "Temperatura mínima — Tmin (°C)",
                value=float(item["minimum_temperature"]),
                step=0.1,
                format="%.1f",
                key=f"thermography_tmin_{view_key}_{image_signature(content)}",
            )
        with maximum_column:
            maximum_temperature = st.number_input(
                "Temperatura máxima — Tmax (°C)",
                value=float(item["maximum_temperature"]),
                step=0.1,
                format="%.1f",
                key=f"thermography_tmax_{view_key}_{image_signature(content)}",
            )

        item["minimum_temperature"] = minimum_temperature
        item["maximum_temperature"] = maximum_temperature
        valid_scale = maximum_temperature > minimum_temperature
        if valid_scale:
            default_threshold = maximum_temperature - DEFAULT_HOT_FRACTION * (
                maximum_temperature - minimum_temperature
            )
            slider_step = max(
                (maximum_temperature - minimum_temperature) / 200, 0.01
            )
            threshold = st.slider(
                "Temperatura mínima para considerar um pixel quente (°C)",
                min_value=float(minimum_temperature),
                max_value=float(maximum_temperature),
                value=float(default_threshold),
                step=float(slider_step),
                key=(
                    f"thermography_threshold_{view_key}_{image_signature(content)}_"
                    f"{minimum_temperature:.4f}_{maximum_temperature:.4f}"
                ),
            )
            st.caption(
                "Valor padrão: início dos 20% mais quentes da escala informada."
            )
        else:
            threshold = minimum_temperature
            st.error("Tmax deve ser maior que Tmin.")

    with st.spinner(f"Identificando as caixas da imagem de {view_label.lower()}..."):
        detected_boxes = cached_leg_boxes(content)

    if len(detected_boxes) != 2:
        st.image(image, caption=f"Imagem de {view_label.lower()}", width="stretch")
        st.error(
            "Não foi possível identificar exatamente duas caixas R1/R2 "
            f"({len(detected_boxes)} encontrada(s))."
        )
        st.info("Nesta etapa, somente imagens com as duas caixas são processadas.")
        return None

    if view_key == "front":
        boxes = {"right": detected_boxes[0], "left": detected_boxes[1]}
        labels = {"R1 — direita": boxes["right"], "R2 — esquerda": boxes["left"]}
        convention = "Frente: R1 superior = direita; R2 inferior = esquerda."
    else:
        boxes = {"left": detected_boxes[0], "right": detected_boxes[1]}
        labels = {"R1 — esquerda": boxes["left"], "R2 — direita": boxes["right"]}
        convention = "Verso: R1 superior = esquerda; R2 inferior = direita."

    image_columns = st.columns([2, 1, 1], gap="small")
    with image_columns[0]:
        st.image(
            annotate_boxes(image, labels),
            caption=f"Detecção automática — {convention}",
            width=520,
        )
    for column, (label, key) in zip(image_columns[1:], LEGS.items()):
        with column:
            preview = crop_from_box(image, boxes[key])
            preview.thumbnail((260, 190))
            st.image(preview, caption=label, width=260)
    st.caption(convention)

    if not valid_scale:
        return None

    with st.spinner("Convertendo as cores em temperaturas aproximadas..."):
        temperatures = cached_temperature_matrix(
            content, minimum_temperature, maximum_temperature
        )

    metrics: dict[str, dict[str, float | int]] = {}
    for key, box in boxes.items():
        hot_pixels, total_pixels = count_hot_pixels(temperatures, box, threshold)
        metrics[key] = {
            "hot_pixels": hot_pixels,
            "total_pixels": total_pixels,
            "hot_percentage": hot_pixels / total_pixels * 100,
            "threshold": threshold,
        }

    st.markdown("##### Pixels quentes")
    metric_columns = st.columns(2)
    for column, (label, key) in zip(metric_columns, LEGS.items()):
        metric = metrics[key]
        with column:
            with st.container(border=True):
                st.metric(label, f"{metric['hot_pixels']:,}".replace(",", "."))
                st.caption(
                    f"{metric['hot_percentage']:.1f}% de "
                    f"{metric['total_pixels']:,} pixels · "
                    f"temperatura ≥ {threshold:.1f} °C"
                )
    return metrics


st.title("Termografia")

flash_message = st.session_state.pop("thermography_flash", None)
if flash_message:
    st.success(flash_message)

try:
    athletes = load_thermography_athletes()
except Exception as error:
    athletes = []
    st.error("Não foi possível carregar os jogadores do banco.")

athletes_by_id = {
    int(athlete["id_atleta"]): athlete for athlete in athletes
}
athlete_ids = list(athletes_by_id)

st.subheader("Histórico térmico")
with st.container(border=True):
    selected_history_athlete_id = st.selectbox(
        "Jogador",
        athlete_ids,
        index=None,
        placeholder=(
            "Todos os jogadores"
            if athlete_ids
            else "Nenhum jogador disponível"
        ),
        format_func=lambda athlete_id: athlete_label(athletes_by_id[athlete_id]),
        disabled=not athlete_ids,
        key="thermography_history_player",
    )

    try:
        history_records = load_thermography_history(
            selected_history_athlete_id
        )
    except Exception:
        history_records = []
        st.error("Não foi possível carregar o histórico térmico do banco.")

    history = pd.DataFrame(
        [
            {
                "Jogador": record["jogador"],
                "Massa": record["massa"],
                "EVA Dor": record["eva_dor"],
                "Frente": record["frente"],
                "Verso": record["verso"],
                "Observações": record["observacoes"],
            }
            for record in history_records
        ],
        columns=["Jogador", "Massa", "EVA Dor", "Frente", "Verso", "Observações"],
    )
    st.dataframe(
        history,
        width="stretch",
        hide_index=True,
        column_config={
            "Massa": st.column_config.NumberColumn(format="%.1f kg"),
            "EVA Dor": st.column_config.NumberColumn(format="%d"),
            "Frente": st.column_config.NumberColumn(format="%d"),
            "Verso": st.column_config.NumberColumn(format="%d"),
        },
    )
    if not history_records:
        st.info("Nenhuma coleta térmica encontrada para o filtro selecionado.")

st.subheader("Documentos legados")
with st.container(border=True):
    legacy_documents = st.file_uploader(
        "Planilhas e fichas preenchidas manualmente",
        type=["pdf", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
        help=(
            "Processamento inteiramente local. Envie fotografias, prints "
            "ou PDFs contendo a tabela manuscrita."
        ),
        key="thermography_legacy_documents",
    )

    if legacy_documents:
        batch_signature = hashlib.sha256(
            b"".join(
                hashlib.sha256(document.getvalue()).digest()
                for document in legacy_documents
            )
        ).hexdigest()
        if st.session_state.get("legacy_batch_signature") != batch_signature:
            st.session_state.pop("legacy_extraction_results", None)
            st.session_state.pop("legacy_edited_rows", None)

        if st.button(
            "Extrair conteúdo",
            type="primary",
            key="extract_legacy_documents",
        ):
            extracted_documents = []
            progress = st.progress(0, text="Preparando documentos...")
            for index, document in enumerate(legacy_documents):
                try:
                    pages = extract_document(
                        document.getvalue(),
                        document.name,
                        athletes,
                    )
                    extracted_documents.append(
                        {
                            "filename": document.name,
                            "pages": pages,
                            "error": None,
                        }
                    )
                except Exception as error:
                    extracted_documents.append(
                        {
                            "filename": document.name,
                            "pages": [],
                            "error": str(error),
                        }
                    )
                progress.progress(
                    (index + 1) / len(legacy_documents),
                    text=f"Processando {document.name}",
                )
            progress.empty()
            st.session_state["legacy_batch_signature"] = batch_signature
            st.session_state["legacy_extraction_results"] = extracted_documents
    else:
        st.session_state.pop("legacy_batch_signature", None)
        st.session_state.pop("legacy_extraction_results", None)
        st.session_state.pop("legacy_edited_rows", None)
        st.caption(
            "Envie os documentos e execute a extração. "
            "Nenhum arquivo é persistido pelo protótipo."
        )

editor_label_by_athlete_id = {
    athlete_id: f"{athlete_label(athlete)} — ID {athlete_id}"
    for athlete_id, athlete in athletes_by_id.items()
}
athlete_id_by_editor_label = {
    label: athlete_id for athlete_id, label in editor_label_by_athlete_id.items()
}

extraction_results = st.session_state.get("legacy_extraction_results", [])
if extraction_results:
    extracted_rows = []
    for document_result in extraction_results:
        with st.expander(document_result["filename"]):
            if document_result["error"]:
                st.error(document_result["error"])
                continue
            for page_number, page_result in enumerate(
                document_result["pages"], start=1
            ):
                st.markdown(f"**Página {page_number}**")
                diagnostic = page_result["diagnostic"].copy()
                diagnostic.thumbnail((900, 700))
                st.image(
                    diagnostic,
                    caption="Linhas candidatas identificadas em verde",
                    width=700,
                )
                if page_result.get("error"):
                    st.error(page_result["error"])
                    continue
                if page_result["date"]:
                    st.caption(f"Data identificada: {page_result['date']}")
                else:
                    st.warning("A data da página não foi identificada.")
                for row in page_result["rows"]:
                    review_row = {
                        key: value
                        for key, value in row.items()
                        if key not in {
                            "_raw",
                            "id_atleta",
                            "Confiança jogador",
                            "Confiança OCR",
                            "Revisão",
                        }
                    }
                    matched_id = row.get("id_atleta")
                    review_row["Jogador"] = (
                        editor_label_by_athlete_id.get(int(matched_id))
                        if matched_id is not None
                        else None
                    )
                    extracted_rows.append(review_row)
                if not page_result["rows"]:
                    st.warning("Nenhuma linha preenchida foi identificada.")

    if extracted_rows:
        st.markdown("#### Revisão da extração")
        st.caption(
            "Todas as células abaixo são editáveis. Confira e corrija os "
            "valores antes de registrar no banco."
        )
        review_columns = [
            "Jogador",
            "Massa",
            "EVA Dor",
            "Frente",
            "Verso",
            "Observações",
            "Data",
        ]
        review_frame = pd.DataFrame(extracted_rows).reindex(columns=review_columns)
        review_frame["Jogador"] = review_frame["Jogador"].astype("string")
        review_frame["Massa"] = pd.to_numeric(
            review_frame["Massa"], errors="coerce"
        ).astype("Float64")
        for numeric_column in ("EVA Dor", "Frente", "Verso"):
            review_frame[numeric_column] = pd.to_numeric(
                review_frame[numeric_column], errors="coerce"
            ).astype("Int64")
        review_frame["Observações"] = (
            review_frame["Observações"].fillna("").astype("string")
        )
        review_frame["Data"] = pd.to_datetime(
            review_frame["Data"], errors="coerce"
        )
        athlete_options = sorted(athlete_id_by_editor_label)
        editor_batch_key = st.session_state.get(
            "legacy_batch_signature", "sem_lote"
        )
        edited_rows = st.data_editor(
            review_frame,
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            disabled=False,
            column_order=review_columns,
            column_config={
                "Jogador": st.column_config.SelectboxColumn(
                    options=athlete_options,
                    required=True,
                ),
                "Massa": st.column_config.NumberColumn(
                    min_value=0.1, format="%.1f"
                ),
                "EVA Dor": st.column_config.NumberColumn(
                    min_value=0, max_value=10, step=1, format="%d"
                ),
                "Frente": st.column_config.NumberColumn(
                    min_value=0, step=1, format="%d"
                ),
                "Verso": st.column_config.NumberColumn(
                    min_value=0, step=1, format="%d"
                ),
                "Observações": st.column_config.TextColumn(
                    width="large",
                    default="",
                ),
                "Data": st.column_config.DateColumn(
                    format="DD/MM/YYYY",
                    required=True,
                ),
            },
            key=f"legacy_review_editor_{editor_batch_key}",
        )
        st.session_state["legacy_edited_rows"] = edited_rows.to_dict("records")
        st.info(
            "Frente e Verso dos documentos serão associados às medidas "
            "SOMA_FRENTE e SOMA_VERSO. As quatro medidas individuais por "
            "perna permanecerão vazias nos registros legados."
        )
        if st.button(
            "Registrar documentos revisados no banco",
            type="primary",
            key="save_legacy_thermography",
            disabled=not athlete_options,
        ):
            try:
                legacy_records = []
                for row_number, row in enumerate(
                    edited_rows.to_dict("records"), start=1
                ):
                    athlete_id = athlete_id_by_editor_label.get(row.get("Jogador"))
                    if athlete_id is None:
                        raise ValueError(
                            f"Linha {row_number}: selecione um jogador cadastrado."
                        )
                    raw_date = row.get("Data")
                    if raw_date is None or pd.isna(raw_date):
                        raise ValueError(
                            f"Linha {row_number}: informe a data da coleta."
                        )
                    parsed_date = pd.to_datetime(raw_date, errors="raise").date()
                    raw_observations = row.get("Observações")
                    observations_value = (
                        None
                        if raw_observations is None or pd.isna(raw_observations)
                        else str(raw_observations)
                    )
                    legacy_records.append(
                        LegacyThermographyRecord(
                            athlete_id=athlete_id,
                            collected_at=parsed_date,
                            mass=row.get("Massa"),
                            pain_score=row.get("EVA Dor"),
                            front=row.get("Frente"),
                            back=row.get("Verso"),
                            observations=observations_value,
                        )
                    )
                inserted = save_legacy_thermography(legacy_records)
            except (ValueError, RuntimeError, DuplicateThermographyError) as error:
                st.error(str(error))
            except Exception:
                st.error("Não foi possível registrar os documentos no banco.")
            else:
                load_thermography_history.clear()
                st.session_state["thermography_flash"] = (
                    f"{len(legacy_records)} coleta(s) legada(s) registrada(s) "
                    f"com {inserted} medida(s)."
                )
                st.rerun()

st.divider()
st.subheader("Nova análise térmica")
st.caption(
    "Informe os dados da coleta e envie em conjunto as imagens de frente e verso."
)

with st.container(border=True):
    record_columns = st.columns(4)
    with record_columns[0]:
        selected_player_id = st.selectbox(
            "Jogador *",
            athlete_ids,
            index=None,
            placeholder=(
                "Selecione um jogador"
                if athlete_ids
                else "Nenhum jogador disponível"
            ),
            format_func=lambda athlete_id: athlete_label(
                athletes_by_id[athlete_id]
            ),
            disabled=not athlete_ids,
            key="thermography_player",
        )
    with record_columns[1]:
        mass = st.number_input(
            "Massa (kg) *",
            min_value=0.1,
            value=None,
            step=0.1,
            format="%.1f",
            placeholder="Informe a massa",
            key="thermography_mass",
        )
    with record_columns[2]:
        collection_date = st.date_input(
            "Data da coleta *",
            value=date.today(),
            key="thermography_collection_date",
        )
    with record_columns[3]:
        pain_score = st.number_input(
            "EVA Dor *",
            min_value=0,
            max_value=10,
            value=None,
            step=1,
            placeholder="Valor de 0 a 10",
            key="thermography_pain_score",
        )
    observations = st.text_area(
        "Observações",
        placeholder="Campo opcional",
        key="thermography_observations",
    )
    st.caption("* Campos obrigatórios para o envio ao banco.")

upload_columns = st.columns(2)
with upload_columns[0]:
    front_upload = st.file_uploader(
        "Imagem de frente",
        type=["png", "jpg", "jpeg"],
        help="Imagem HIKMICRO frontal com as caixas R1 e R2 visíveis.",
        key="thermography_front_upload",
    )
with upload_columns[1]:
    back_upload = st.file_uploader(
        "Imagem do verso",
        type=["png", "jpg", "jpeg"],
        help="Imagem HIKMICRO do verso (costas) com as caixas R1 e R2 visíveis.",
        key="thermography_back_upload",
    )

if not front_upload or not back_upload:
    st.session_state.pop("thermography_metrics", None)
    missing = []
    if not front_upload:
        missing.append("frente")
    if not back_upload:
        missing.append("verso")
    st.info(f"Envie a imagem de {' e '.join(missing)} para iniciar a análise.")
    st.stop()

uploads = {"front": front_upload, "back": back_upload}
views: dict[str, dict[str, Any]] = {}
for view_key, uploaded in uploads.items():
    content = uploaded.getvalue()
    try:
        image = load_thermography(content)
    except ValueError as error:
        st.error(f"{VIEW_LABELS[view_key]} — {uploaded.name}: {error}")
        continue
    views[view_key] = {
        "name": uploaded.name,
        "content": content,
        "image": image,
        "signature": image_signature(content),
    }

if len(views) != 2:
    st.stop()

if views["front"]["signature"] == views["back"]["signature"]:
    st.warning("A mesma imagem foi selecionada para frente e verso. Confira os arquivos.")

pair_signature = hashlib.sha256(
    (views["front"]["signature"] + views["back"]["signature"]).encode()
).hexdigest()
items: dict[str, dict[str, Any]] = st.session_state.setdefault(
    "thermography_items", {}
)
active_item_keys = {
    f"{view_key}:{view['signature']}" for view_key, view in views.items()
}
for item_key in active_item_keys:
    items.setdefault(
        item_key,
        {
            "minimum_temperature": DEFAULT_MIN_TEMPERATURE,
            "maximum_temperature": DEFAULT_MAX_TEMPERATURE,
        },
    )
for item_key in set(items) - active_item_keys:
    del items[item_key]

st.info(
    "A lateralidade é invertida automaticamente entre as vistas de frente e verso."
)
st.warning(
    "Conversão experimental: a paleta é estimada pela barra térmica lateral "
    "presente em cada imagem."
)

tabs = st.tabs(["Frente", "Verso"])
view_metrics: dict[str, dict[str, dict[str, float | int]] | None] = {}
for tab, view_key in zip(tabs, ("front", "back")):
    view = views[view_key]
    item_key = f"{view_key}:{view['signature']}"
    with tab:
        view_metrics[view_key] = render_view(
            view_key,
            view["name"],
            view["content"],
            view["image"],
            items[item_key],
        )

stored_metrics: dict[str, Any] = st.session_state.setdefault(
    "thermography_metrics", {}
)
if all(view_metrics.values()):
    front_pixels = sum(
        int(view_metrics["front"][key]["hot_pixels"]) for key in LEGS.values()
    )
    back_pixels = sum(
        int(view_metrics["back"][key]["hot_pixels"]) for key in LEGS.values()
    )
    selected_player = athletes_by_id.get(selected_player_id)
    record = {
        "Jogador": (
            editor_label_by_athlete_id.get(int(selected_player_id))
            if selected_player is not None
            else None
        ),
        "Massa": mass,
        "EVA Dor": pain_score,
        "Frente": front_pixels,
        "Verso": back_pixels,
        "Observações": observations.strip(),
    }

    stored_metrics.clear()
    stored_metrics[pair_signature] = {
        "thermal_metrics": view_metrics,
        "record": record,
    }

    st.subheader("Resumo da coleta")
    summary_columns = st.columns(2)
    with summary_columns[0]:
        with st.container(border=True):
            st.metric("Frente", f"{front_pixels:,}".replace(",", "."))
            st.caption("Pixels quentes das duas pernas")
    with summary_columns[1]:
        with st.container(border=True):
            st.metric("Verso", f"{back_pixels:,}".replace(",", "."))
            st.caption("Pixels quentes das duas pernas")

    st.subheader("Registro preparado")
    st.caption(
        "Edite Jogador, Massa, EVA Dor e Observações diretamente na tabela. "
        "Frente e Verso são calculados automaticamente."
    )
    prepared_frame = pd.DataFrame([record])
    prepared_frame["Jogador"] = prepared_frame["Jogador"].astype("string")
    prepared_frame["Massa"] = pd.to_numeric(
        prepared_frame["Massa"], errors="coerce"
    ).astype("Float64")
    prepared_frame["EVA Dor"] = pd.to_numeric(
        prepared_frame["EVA Dor"], errors="coerce"
    ).astype("Int64")
    prepared_frame["Frente"] = prepared_frame["Frente"].astype("Int64")
    prepared_frame["Verso"] = prepared_frame["Verso"].astype("Int64")
    prepared_frame["Observações"] = (
        prepared_frame["Observações"].fillna("").astype("string")
    )
    edited_prepared_frame = st.data_editor(
        prepared_frame,
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        disabled=["Frente", "Verso"],
        column_config={
            "Jogador": st.column_config.SelectboxColumn(
                options=sorted(athlete_id_by_editor_label),
                required=True,
            ),
            "Massa": st.column_config.NumberColumn(
                min_value=0.1,
                step=0.1,
                format="%.1f kg",
                required=True,
            ),
            "EVA Dor": st.column_config.NumberColumn(
                min_value=0,
                max_value=10,
                step=1,
                format="%d",
                required=True,
            ),
            "Frente": st.column_config.NumberColumn(format="%d"),
            "Verso": st.column_config.NumberColumn(format="%d"),
            "Observações": st.column_config.TextColumn(
                width="large",
                default="",
            ),
        },
        key=f"thermography_record_editor_{pair_signature}",
    )
    prepared_record = edited_prepared_frame.iloc[0].to_dict()
    prepared_player_id = athlete_id_by_editor_label.get(
        prepared_record.get("Jogador")
    )
    prepared_mass = prepared_record.get("Massa")
    prepared_pain_score = prepared_record.get("EVA Dor")
    prepared_observations = prepared_record.get("Observações")
    if prepared_observations is None or pd.isna(prepared_observations):
        prepared_observations = ""
    else:
        prepared_observations = str(prepared_observations).strip()

    missing_fields = []
    if prepared_player_id is None:
        missing_fields.append("Jogador")
    if prepared_mass is None or pd.isna(prepared_mass):
        missing_fields.append("Massa")
    if prepared_pain_score is None or pd.isna(prepared_pain_score):
        missing_fields.append("EVA Dor")

    if missing_fields:
        st.warning(
            "Preencha os campos obrigatórios antes do envio ao banco: "
            + ", ".join(missing_fields)
            + "."
        )
    else:
        st.success("Registro pronto para envio. Observações permanece opcional.")

    if st.button(
        "Registrar coleta no banco",
        type="primary",
        disabled=bool(missing_fields),
        key="save_image_thermography",
    ):
        try:
            inserted = save_image_thermography(
                athlete_id=int(prepared_player_id),
                collected_at=collection_date,
                mass=prepared_mass,
                pain_score=prepared_pain_score,
                front_right=view_metrics["front"]["right"]["hot_pixels"],
                front_left=view_metrics["front"]["left"]["hot_pixels"],
                back_right=view_metrics["back"]["right"]["hot_pixels"],
                back_left=view_metrics["back"]["left"]["hot_pixels"],
                observations=prepared_observations,
            )
        except (ValueError, RuntimeError, DuplicateThermographyError) as error:
            st.error(str(error))
        except Exception:
            st.error("Não foi possível registrar a coleta no banco.")
        else:
            load_thermography_history.clear()
            st.session_state["thermography_flash"] = (
                f"Coleta registrada com {inserted} medida(s)."
            )
            st.rerun()
    st.caption("As imagens não são armazenadas; somente as medidas são enviadas.")
else:
    stored_metrics.clear()
