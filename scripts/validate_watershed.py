"""Manual, read-only input replay through the production thermography pipeline.

Outputs are diagnostics, not clinical temperatures or segmentation accuracy.
Run from the repository root; --session DIR ROTATION GLOB can be repeated.
"""
import argparse
import csv
import html
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageOps, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.mac_api.modules.thermography.thermal_analysis import segmented_image
from backend.mac_api.modules.thermography.watershed import ALGORITHM_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', nargs=3, action='append', required=True, metavar=('DIR', 'ROTATION', 'GLOB'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    summary = []
    for number, (source, rotation, pattern) in enumerate(args.session, 1):
        source = Path(source)
        rotation = int(rotation)
        if rotation not in (0, 90, 180, 270):
            raise ValueError('Invalid rotation')
        folder = args.output/f'session_{number}'
        folder.mkdir(exist_ok=True)
        if folder.resolve().is_relative_to(source.resolve()):
            raise ValueError('Output must be outside the input directory')
        files = sorted(p for p in source.rglob(pattern) if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
        rows, cards, thumbnails = [], [], []
        hole_pixels, filled_pixels = 0, 0
        for i, path in enumerate(files, 1):
            row = dict(file=path.name, status='ok', seconds=0, pixels=0)
            image = Image.open(path).convert('RGB').rotate(rotation, expand=True)
            started = time.perf_counter()
            try:
                # Diagnostic scale only: original clinical Tmin/Tmax are not inferred here.
                result = segmented_image(image, 'front', 20, 40, 30, image_rotation=rotation)
                masks = result['masks']
                assert not np.any(masks['right'] & masks['left'])
                for side, mask in masks.items():
                    assert mask.dtype == bool and mask.shape == (image.height, image.width)
                    assert result['metrics'][side]['total_pixels'] == int(mask.sum())
                    box = result['boxes'][side]
                    inside = np.zeros(mask.shape, bool)
                    inside[box['top']:box['top']+box['height'], box['left']:box['left']+box['width']] = True
                    assert not (mask & ~inside).any()
                    contours, _ = cv2.findContours(mask.astype('uint8'), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    filled = np.zeros(mask.shape, 'uint8'); cv2.drawContours(filled, contours, -1, 1, cv2.FILLED)
                    filled_pixels += int(filled.sum())
                    hole_pixels += int(((filled > 0) & ~mask).sum())
                    Image.fromarray(mask.astype('uint8')*255).save(folder/f'{i:03d}_{side}.png')
                row['pixels'] = sum(int(m.sum()) for m in masks.values())
                union = masks['right'] | masks['left']
                cutout = np.asarray(image).copy(); cutout[~union] = 0
                panel = Image.new('RGB', (image.width*3, image.height))
                for j, preview in enumerate((image, result['overlay'], Image.fromarray(cutout))):
                    panel.paste(preview, (image.width*j, 0))
            except ValueError as error:
                row['status'] = str(error)
                panel = image
            row['seconds'] = round(time.perf_counter()-started, 3)
            panel.save(folder/f'{i:03d}.jpg')
            thumb = Image.new('RGB', (360, 190), '#222222')
            thumb.paste(ImageOps.contain(panel, (360, 165)), (0, 20))
            ImageDraw.Draw(thumb).text((3, 3), f'{path.name} | {row["status"]}', fill='white')
            thumbnails.append(thumb)
            cards.append(f'<article><h2>{html.escape(path.name)}</h2><p>{html.escape(row["status"])}</p><img loading="lazy" src="{i:03d}.jpg"></article>')
            rows.append(row)
            if i % 10 == 0 or i == len(files):
                print(f'{source.name}: {i}/{len(files)}', flush=True)
        if not rows:
            raise ValueError(f'No images: {source}')
        with (folder/'summary.csv').open('w', newline='', encoding='utf-8-sig') as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0]); writer.writeheader(); writer.writerows(rows)
        for offset in range(0, len(thumbnails), 12):
            sheet = Image.new('RGB', (1080, 760), '#222222')
            for j, thumb in enumerate(thumbnails[offset:offset+12]):
                sheet.paste(thumb, ((j%3)*360, (j//3)*190))
            sheet.save(folder/f'contact_{offset//12+1:02d}.jpg')
        (folder/'index.html').write_text('<!doctype html><meta charset="utf-8"><style>body{background:#181818;color:white;font:16px sans-serif;margin:24px}img{max-width:100%}</style><h1>'+html.escape(source.name)+'</h1><p>Original | produção watershed | recorte. Status ok não mede precisão. Escala usada para validar cálculos é ilustrativa, não clínica.</p>'+''.join(cards), encoding='utf-8')
        summary.append(dict(session=source.name, algorithm_version=ALGORITHM_VERSION, rotation=rotation, files=len(rows),
                            passed=sum(row['status']=='ok' for row in rows),
                            rejected=[row for row in rows if row['status']!='ok'],
                            internal_holes_pct=round(100*hole_pixels/max(1,filled_pixels),3)))
    (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'index.html').write_text('<!doctype html><meta charset="utf-8"><h1>Validação watershed de produção</h1><p>Execução e integridade; não mede precisão anatômica.</p>'+''.join(f'<p><a href="session_{i}/index.html">{html.escape(item["session"])}</a>: {item["passed"]}/{item["files"]} execuções válidas</p>' for i, item in enumerate(summary, 1)), encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
