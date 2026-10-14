"""Arquivo local de análises térmicas, independente das coletas do banco."""
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import shutil
import sys
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

import numpy as np
from PIL import Image
from backend.mac_api.core.settings import setting
from .thermal_analysis import count_hot_pixels, leg_part_metrics

FORMAT_VERSION = 1
ANALYSIS_VERSION = 'thermal-rgb-grabcut-v1'


def analyses_directory():
    root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[4]
    configured = Path(setting('MAC_ANALYSES_DIR', './data/thermography') or './data/thermography').expanduser()
    return (configured if configured.is_absolute() else root / configured).resolve()


def _safe_path(path):
    root = analyses_directory()
    resolved = path.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError('Caminho de análise inválido.')
    return resolved


def _directory(athlete_id, collected_at, analysis_id):
    if int(athlete_id) < 1:
        raise ValueError('ID do atleta inválido.')
    return _safe_path(analyses_directory() / f'atleta_{int(athlete_id)}' /
                      collected_at.isoformat() / f'analise_{UUID(str(analysis_id))}')


def _validate_view(source):
    if not isinstance(source.get('image'), Image.Image):
        raise ValueError('Imagem da análise inválida.')
    image = source['image'].convert('RGB')
    temperatures = np.asarray(source['temperatures'])
    if temperatures.shape != (image.height, image.width) or temperatures.dtype.kind not in 'fi':
        raise ValueError('Matriz térmica incompatível com a imagem.')
    if temperatures.nbytes > 64 * 1024 * 1024 or not np.isfinite(temperatures).all():
        raise ValueError('Matriz térmica inválida ou muito grande.')
    # Calcular metadados com a mesma precisão que será persistida e reaberta.
    with np.errstate(over='ignore', invalid='ignore'):
        temperatures = temperatures.astype(np.float32)
    if not np.isfinite(temperatures).all():
        raise ValueError('Temperaturas fora do intervalo numérico suportado.')
    minimum, maximum, threshold = (float(source[k]) for k in ('minimum_temperature', 'maximum_temperature', 'default_threshold'))
    if not all(math.isfinite(v) for v in (minimum, maximum, threshold)) or not minimum < maximum or not minimum <= threshold <= maximum:
        raise ValueError('Escala ou limiar inválido.')
    if int(source.get('image_rotation', 0)) not in (0, 90, 180, 270):
        raise ValueError('Rotação inválida.')
    masks, metrics, boxes, parts = {}, {}, {}, {}
    for side in ('right', 'left'):
        box = source['boxes'][side]
        if any(type(box[k]) is not int for k in ('left', 'top', 'width', 'height')):
            raise ValueError('Coordenadas das caixas devem ser inteiras.')
        x, y, w, h = (box[k] for k in ('left', 'top', 'width', 'height'))
        if x < 0 or y < 0 or w < 1 or h < 1 or x+w > image.width or y+h > image.height:
            raise ValueError('Caixa fora da imagem.')
        mask = np.asarray(source['segmentation_masks'][side])
        if mask.shape != temperatures.shape or not np.isin(mask, (0, 1)).all():
            raise ValueError('Máscara incompatível com a imagem.')
        mask = mask.astype(bool)
        inside = np.zeros(mask.shape, dtype=bool); inside[y:y+h, x:x+w] = True
        if np.any(mask & ~inside):
            raise ValueError('A máscara ultrapassa a caixa da perna.')
        pixels, area = count_hot_pixels(temperatures, box, threshold, mask)
        config = source.get('part_settings', {}).get(side, {'cuts': [45, 57, 88], 'axis': 'vertical', 'foot_at_end': True})
        cuts = config['cuts']
        if len(cuts) != 3 or any(type(cut) is not int for cut in cuts) or not 0 < cuts[0] < cuts[1] < cuts[2] < 100:
            raise ValueError('Divisões anatômicas inválidas.')
        if config.get('axis', 'vertical') != 'vertical' or not config.get('foot_at_end', True):
            raise ValueError('As divisões devem seguir de cima para baixo.')
        boundaries = [y + round(h * cut / 100) for cut in cuts]
        part_metrics, _ = leg_part_metrics(temperatures, mask, threshold, tuple(cuts),
                                         axis='vertical', region_box=box)
        parts[side] = dict(cuts=cuts, axis='vertical', foot_at_end=True,
                          boundaries_pixels=boundaries, metrics=part_metrics)
        metrics[side] = dict(hot_pixels=pixels, total_pixels=area, hot_percentage=pixels/area*100)
        masks[side], boxes[side] = mask, dict(box)
    colorbar = source.get('colorbar_box')
    if colorbar is not None:
        x, y, w, h = (colorbar[k] for k in ('left', 'top', 'width', 'height'))
        if any(type(v) is not int for v in (x, y, w, h)) or x < 0 or y < 0 or w < 1 or h < 1 or x+w > image.width or y+h > image.height:
            raise ValueError('Caixa da barra térmica inválida.')
    metadata = dict(width=image.width, height=image.height, original_filename=str(source.get('original_filename', '')),
                    image_rotation=int(source.get('image_rotation', 0)), minimum_temperature=minimum,
                    maximum_temperature=maximum, default_threshold=threshold,
                    threshold_percentage=100*(threshold-minimum)/(maximum-minimum),
                    boxes=boxes, colorbar_box=colorbar, part_settings=parts, metrics=metrics)
    return image, temperatures.astype(np.float32), masks, metadata


def save_analysis(*, athlete_id, athlete_name, collected_at, views, mass=None, pain_score=None, observations=''):
    if not str(athlete_name).strip() or set(views) != {'front', 'back'}:
        raise ValueError('Informe o jogador e as duas vistas da análise.')
    if mass is not None and (not math.isfinite(float(mass)) or float(mass) <= 0):
        raise ValueError('Massa inválida.')
    if pain_score is not None and (type(pain_score) is not int or not 0 <= pain_score <= 10):
        raise ValueError('EVA Dor inválida.')
    validated = {view: _validate_view(views[view]) for view in ('front', 'back')}
    analysis_id = str(uuid4())
    target = _directory(athlete_id, collected_at, analysis_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    pending = _safe_path(target.parent / f'.pending_{analysis_id}')
    pending.mkdir()
    metadata = dict(format_version=FORMAT_VERSION, algorithm_version=ANALYSIS_VERSION,
                    analysis_id=analysis_id, athlete_id=int(athlete_id), athlete_name=str(athlete_name).strip(),
                    collected_at=collected_at.isoformat(), created_at=datetime.now(timezone.utc).isoformat(),
                    mass=None if mass is None else float(mass), pain_score=pain_score,
                    observations=str(observations or ''), views={})
    try:
        for view, (image, temperatures, masks, info) in validated.items():
            directory = pending / ('frente' if view == 'front' else 'verso'); directory.mkdir()
            image.save(directory / 'original.png')
            info['image_sha256'] = hashlib.sha256((directory / 'original.png').read_bytes()).hexdigest()
            for side, label in (('right', 'direita'), ('left', 'esquerda')):
                Image.fromarray(masks[side].astype(np.uint8)*255).save(directory / f'mascara_{label}.png')
            np.save(directory / 'temperaturas.npy', temperatures, allow_pickle=False)
            metadata['views'][view] = info
        with (pending / 'metadados.json').open('w', encoding='utf-8') as file:
            json.dump(metadata, file, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(pending, target)
    except Exception:
        shutil.rmtree(pending)
        raise
    return _summary(target, metadata)


def _metadata(directory):
    directory = _safe_path(directory)
    metadata = json.loads(_safe_path(directory / 'metadados.json').read_text(encoding='utf-8'))
    if metadata.get('format_version') != FORMAT_VERSION:
        raise ValueError('Versão dos metadados não suportada.')
    expected = _directory(metadata['athlete_id'], date.fromisoformat(metadata['collected_at']), metadata['analysis_id'])
    if expected != directory:
        raise ValueError('Identificação da análise incompatível com o diretório.')
    return metadata


def _summary(directory, metadata):
    with Image.open(_safe_path(directory / 'frente/original.png')) as image:
        thumbnail = image.convert('RGB'); thumbnail.thumbnail((170, 110))
    created = datetime.fromisoformat(metadata['created_at'])
    return dict(version=3, id=metadata['analysis_id'], analysis_id=metadata['analysis_id'],
                athlete_id=metadata['athlete_id'], athlete_name=metadata['athlete_name'],
                collected_at=date.fromisoformat(metadata['collected_at']), created_at=metadata['created_at'],
                sequence=int(created.timestamp()*1_000_000), thumbnail=thumbnail,
                mass=metadata['mass'], pain_score=metadata['pain_score'], observations=metadata['observations'])


def list_analyses(athlete_id):
    if int(athlete_id) < 1:
        raise ValueError('ID do atleta inválido.')
    directory = _safe_path(analyses_directory() / f'atleta_{int(athlete_id)}')
    results = []
    if not directory.exists(): return results
    for path in directory.glob('*/analise_*'):
        try:
            metadata = _metadata(path)
            results.append(_summary(path, metadata))
        except (OSError, ValueError, KeyError) as error:
            logging.getLogger(__name__).warning('Análise local indisponível: %s (%s)', path.name, type(error).__name__)
    return sorted(results, key=lambda item: (item['collected_at'], item['created_at'], item['id']))


def load_analysis(athlete_id, collected_at, analysis_id):
    directory = _directory(athlete_id, collected_at, analysis_id)
    if not directory.is_dir(): raise FileNotFoundError('Análise local não encontrada.')
    metadata = _metadata(directory)
    entry = _summary(directory, metadata)
    entry['metadata'] = metadata
    entry['views'] = {}
    for view, label in (('front', 'frente'), ('back', 'verso')):
        info = metadata['views'][view]
        path = directory / label
        with Image.open(_safe_path(path / 'original.png')) as image:
            image = image.convert('RGB').copy()
        temperatures = np.load(_safe_path(path / 'temperaturas.npy'), allow_pickle=False)
        masks = {}
        for side, side_label in (('right', 'direita'), ('left', 'esquerda')):
            with Image.open(_safe_path(path / f'mascara_{side_label}.png')) as mask:
                pixels = np.asarray(mask.convert('L'))
                if not np.isin(pixels, (0,255)).all():
                    raise ValueError('Máscara local não é binária.')
                masks[side] = pixels > 0
        source = {**info, 'image': image, 'temperatures': temperatures, 'segmentation_masks': masks}
        _validate_view(source)
        entry['views'][view] = source
    return entry
