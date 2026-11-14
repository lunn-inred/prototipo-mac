"""Prévias de apresentação; não altera imagens originais nem matrizes térmicas."""
from PIL import Image

PREVIEW_SIZE = (640, 480)


def build_thumbnails(images):
    previews = {}
    for view in ('front', 'back'):
        if view not in images:
            continue
        preview = images[view].convert('RGB')
        preview.thumbnail(PREVIEW_SIZE, Image.Resampling.LANCZOS)
        previews[view] = preview
    return previews


def legacy_thumbnail(previews):
    image = next(iter(previews.values()), Image.new('RGB', (170,110), '#d8dee8')).copy()
    image.thumbnail((170,110), Image.Resampling.LANCZOS)
    return image
