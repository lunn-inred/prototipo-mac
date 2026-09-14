from __future__ import annotations

import hashlib
import io
from typing import Any

import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError
from streamlit_cropper import st_cropper


st.set_page_config(
    page_title="MAC Performance | Termografia",
    page_icon="🌡️",
    layout="wide",
)

MAX_IMAGE_SIZE = 20 * 1024 * 1024
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


def reset_crops_for_image(signature: str) -> None:
    """Impede que recortes de uma imagem anterior sejam reutilizados."""
    if st.session_state.get("thermography_image_signature") == signature:
        return
    st.session_state["thermography_image_signature"] = signature
    st.session_state["thermography_crops"] = {}
    st.session_state["thermography_crop_boxes"] = {}


def default_coordinates(box: dict[str, Any] | None) -> tuple[int, int, int, int] | None:
    if not box:
        return None
    left = int(box["left"])
    top = int(box["top"])
    return (
        left,
        left + int(box["width"]),
        top,
        top + int(box["height"]),
    )


st.title("Termografia")

uploaded_image = st.file_uploader(
    "Imagem da termografia",
    type=["png", "jpg", "jpeg"],
    help="Envie uma imagem PNG ou JPEG de até 20 MB.",
)

if uploaded_image is None:
    st.info("Envie uma imagem para iniciar a seleção das pernas.")
    st.stop()

image_content = uploaded_image.getvalue()
image_signature = hashlib.sha256(image_content).hexdigest()
reset_crops_for_image(image_signature)

try:
    thermography = load_thermography(image_content)
except ValueError as error:
    st.error(str(error))
    st.stop()

selected_leg = st.radio(
    "Área que será recortada",
    list(LEGS),
    horizontal=True,
)
leg_key = LEGS[selected_leg]
saved_boxes: dict[str, dict[str, Any]] = st.session_state[
    "thermography_crop_boxes"
]

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
            key=f"thermography_cropper_{image_signature}_{leg_key}",
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
        ):
            st.session_state["thermography_crops"][leg_key] = cropped_image.copy()
            st.session_state["thermography_crop_boxes"][leg_key] = {
                name: int(value) for name, value in crop_box.items()
            }
            st.success(f"Recorte da {selected_leg.lower()} confirmado.")

confirmed_crops: dict[str, Image.Image] = st.session_state["thermography_crops"]
if confirmed_crops:
    st.subheader("Recortes realizados")
    columns = st.columns(2)
    for column, (label, key) in zip(columns, LEGS.items()):
        with column:
            if key in confirmed_crops:
                display_crop = confirmed_crops[key].copy()
                display_crop.thumbnail((420, 420))
                st.image(display_crop, caption=label)
            else:
                st.info(f"O recorte da {label.lower()} ainda não foi confirmado.")
