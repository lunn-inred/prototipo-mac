from __future__ import annotations

import hashlib
import io
from typing import Any

import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError
from streamlit_cropper import st_cropper

from thermal_analysis import count_hot_pixels, temperature_matrix


st.set_page_config(
    page_title="MAC Performance | Termografia",
    page_icon="🌡️",
    layout="wide",
)

MAX_IMAGE_SIZE = 20 * 1024 * 1024
DEFAULT_MIN_TEMPERATURE = 20.0
DEFAULT_MAX_TEMPERATURE = 40.0
DEFAULT_HOT_FRACTION = 0.20
LEGS = {
    "Perna esquerda": "left",
    "Perna direita": "right",
}


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
        raise ValueError("A imagem não possui dimensões válidas para recorte.")
    return image


def image_signature(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def default_coordinates(box: dict[str, Any] | None) -> tuple[int, int, int, int] | None:
    if not box:
        return None
    left = int(box["left"])
    top = int(box["top"])
    return left, left + int(box["width"]), top, top + int(box["height"])


def crop_from_box(image: Image.Image, box: dict[str, int]) -> Image.Image:
    left = int(box["left"])
    top = int(box["top"])
    return image.crop(
        (left, top, left + int(box["width"]), top + int(box["height"]))
    )


@st.cache_data(show_spinner=False)
def cached_temperature_matrix(
    content: bytes,
    minimum_temperature: float,
    maximum_temperature: float,
) -> Any:
    image = load_thermography(content)
    return temperature_matrix(image, minimum_temperature, maximum_temperature)


st.title("Termografia")

uploaded_images = st.file_uploader(
    "Imagens da termografia",
    type=["png", "jpg", "jpeg"],
    accept_multiple_files=True,
    help="Envie uma ou mais imagens PNG ou JPEG de até 20 MB cada.",
)

if not uploaded_images:
    st.session_state.pop("thermography_items", None)
    st.session_state.pop("thermography_metrics", None)
    st.info("Envie uma ou mais imagens para iniciar a análise.")
    st.stop()

valid_images: dict[str, dict[str, Any]] = {}
for uploaded_image in uploaded_images:
    content = uploaded_image.getvalue()
    signature = image_signature(content)
    try:
        image = load_thermography(content)
    except ValueError as error:
        st.error(f"{uploaded_image.name}: {error}")
        continue
    valid_images.setdefault(
        signature,
        {"name": uploaded_image.name, "content": content, "image": image},
    )

if not valid_images:
    st.stop()

items: dict[str, dict[str, Any]] = st.session_state.setdefault(
    "thermography_items", {}
)
for signature, uploaded in valid_images.items():
    items.setdefault(
        signature,
        {
            "name": uploaded["name"],
            "boxes": {},
            "minimum_temperature": DEFAULT_MIN_TEMPERATURE,
            "maximum_temperature": DEFAULT_MAX_TEMPERATURE,
        },
    )
for signature in set(items) - set(valid_images):
    del items[signature]
stored_metrics: dict[str, dict[str, Any]] = st.session_state.setdefault(
    "thermography_metrics", {}
)
for signature in set(stored_metrics) - set(valid_images):
    del stored_metrics[signature]

if len(valid_images) < len(uploaded_images):
    st.caption("Arquivos idênticos ou inválidos não são exibidos em duplicidade.")

signatures = list(valid_images)
filename_counts = {
    name: sum(uploaded["name"] == name for uploaded in valid_images.values())
    for name in {uploaded["name"] for uploaded in valid_images.values()}
}
selected_signature = st.selectbox(
    "Imagem em edição",
    signatures,
    format_func=lambda signature: (
        valid_images[signature]["name"]
        if filename_counts[valid_images[signature]["name"]] == 1
        else f"{valid_images[signature]['name']} — {signature[:8]}"
    ),
)
selected_upload = valid_images[selected_signature]
selected_item = items[selected_signature]
thermography: Image.Image = selected_upload["image"]
st.caption(f"Progresso: {len(selected_item['boxes'])}/2 recortes realizados.")

with st.container(border=True):
    minimum_column, maximum_column = st.columns(2)
    with minimum_column:
        minimum_temperature = st.number_input(
            "Temperatura mínima — Tmin (°C)",
            value=float(selected_item["minimum_temperature"]),
            step=0.1,
            format="%.1f",
            key=f"thermography_tmin_{selected_signature}",
        )
    with maximum_column:
        maximum_temperature = st.number_input(
            "Temperatura máxima — Tmax (°C)",
            value=float(selected_item["maximum_temperature"]),
            step=0.1,
            format="%.1f",
            key=f"thermography_tmax_{selected_signature}",
        )

    selected_item["minimum_temperature"] = minimum_temperature
    selected_item["maximum_temperature"] = maximum_temperature
    valid_scale = maximum_temperature > minimum_temperature
    if valid_scale:
        default_threshold = maximum_temperature - DEFAULT_HOT_FRACTION * (
            maximum_temperature - minimum_temperature
        )
        slider_step = max((maximum_temperature - minimum_temperature) / 200, 0.01)
        threshold = st.slider(
            "Temperatura mínima para considerar um pixel quente (°C)",
            min_value=float(minimum_temperature),
            max_value=float(maximum_temperature),
            value=float(default_threshold),
            step=float(slider_step),
            key=(
                f"thermography_threshold_{selected_signature}_"
                f"{minimum_temperature:.4f}_{maximum_temperature:.4f}"
            ),
        )
        st.caption(
            "Valor padrão: início dos 20% mais quentes do intervalo da imagem."
        )
    else:
        threshold = minimum_temperature
        st.error("Tmax deve ser maior que Tmin.")

st.warning(
    "Conversão experimental: esta versão assume a mesma paleta Jet "
    "(azul → vermelho) em todas as imagens."
)

selected_leg = st.radio(
    "Área que será recortada",
    list(LEGS),
    horizontal=True,
    key=f"thermography_leg_{selected_signature}",
)
leg_key = LEGS[selected_leg]
saved_boxes: dict[str, dict[str, int]] = selected_item["boxes"]

st.caption(
    f"Ajuste o retângulo sobre a {selected_leg.lower()} e confirme o recorte. "
    "Depois, selecione a outra perna."
)

with st.container(border=True, key="thermography_editor"):
    editor, preview = st.columns([5, 3], gap="small")
    with editor:
        cropped_image, crop_box = st_cropper(
            thermography,
            realtime_update=True,
            default_coords=default_coordinates(saved_boxes.get(leg_key)),
            box_color="#075fc9",
            aspect_ratio=None,
            return_type="both",
            key=f"thermography_cropper_{selected_signature}_{leg_key}",
            should_resize_image=True,
            stroke_width=3,
        )
    with preview:
        display_preview = cropped_image.copy()
        display_preview.thumbnail((420, 420))
        st.image(display_preview, caption=f"Prévia — {selected_leg}")
        if st.button(
            f"Confirmar {selected_leg.lower()}",
            type="primary",
            width="stretch",
            key=f"thermography_confirm_{selected_signature}_{leg_key}",
        ):
            saved_boxes[leg_key] = {
                name: int(value) for name, value in crop_box.items()
            }
            st.success(f"Recorte da {selected_leg.lower()} confirmado.")

if saved_boxes:
    st.subheader("Recortes realizados")
    columns = st.columns(2)
    for column, (label, key) in zip(columns, LEGS.items()):
        with column:
            if key in saved_boxes:
                display_crop = crop_from_box(thermography, saved_boxes[key])
                display_crop.thumbnail((420, 420))
                st.image(display_crop, caption=label)
            else:
                st.info(f"O recorte da {label.lower()} ainda não foi confirmado.")

if saved_boxes and valid_scale:
    with st.spinner("Convertendo as cores em temperaturas aproximadas..."):
        temperatures = cached_temperature_matrix(
            selected_upload["content"],
            minimum_temperature,
            maximum_temperature,
        )

    metrics: dict[str, dict[str, float | int]] = {}
    for key, box in saved_boxes.items():
        hot_pixels, total_pixels = count_hot_pixels(temperatures, box, threshold)
        metrics[key] = {
            "hot_pixels": hot_pixels,
            "total_pixels": total_pixels,
            "threshold": threshold,
        }
    stored_metrics[selected_signature] = metrics

    st.subheader("Pixels quentes")
    metric_columns = st.columns(2)
    for column, (label, key) in zip(metric_columns, LEGS.items()):
        with column:
            with st.container(border=True):
                if key in metrics:
                    st.metric(label, f"{metrics[key]['hot_pixels']:,}".replace(",", "."))
                    st.caption(f"Temperatura ≥ {threshold:.1f} °C")
                else:
                    st.metric(label, "—")
                    st.caption("Recorte ainda não realizado")

    st.caption(
        "As métricas estão somente na sessão atual e ainda não são persistidas no banco."
    )
else:
    stored_metrics.pop(selected_signature, None)
