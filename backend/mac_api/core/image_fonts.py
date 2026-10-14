"""Fonte Unicode incluída no backend para prévias térmicas."""
from functools import lru_cache
from pathlib import Path
from PIL import ImageFont

FONT_PATH = Path(__file__).resolve().parents[1] / 'assets/fonts/DejaVuSans.ttf'


@lru_cache(maxsize=32)
def image_font(size: int):
    return ImageFont.truetype(str(FONT_PATH), size)
