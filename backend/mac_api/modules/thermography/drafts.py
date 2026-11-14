"""Análises parciais: medidas SQL informadas e estado de edição local, sem pickle."""
import base64
from contextlib import nullcontext
from datetime import date, datetime, timezone
import io
import json
import logging
import math
import os
from pathlib import Path
import shutil
from threading import RLock
from uuid import UUID, uuid4

from PIL import Image
import numpy as np
from backend.mac_api.core.database import database_write_connection
from backend.mac_api.core.settings import setting
from backend.mac_api.core.wire import encode, decode
from . import analysis_archive as archive
from .analysis_registration import AnalysisChangedError, AnalysisConflictError
from .thermography_service import current_sao_paulo_date
from .thermography_service import _insert_collection
from . import collection_state
from .analysis_previews import build_thumbnails, legacy_thumbnail

LOCK = RLock()
FORMAT = 'mac-thermal-draft-v1'
ITEM_FIELDS = {'minimum_temperature', 'maximum_temperature', 'threshold_percentage', 'threshold_temperature',
               'threshold_mode', 'image_rotation', 'manual_boxes', 'manual_colorbar_box', 'part_settings_v4',
               'mask_seeds', 'mask_revision', 'saved_analysis', 'saved_analysis_revision'}


def directory(identity):
    return archive._safe_path(archive.analyses_directory() / '_drafts' / str(UUID(str(identity))))


def validate_state(state):
    if not isinstance(state, dict) or set(state) - {'step', 'draft', 'uploads', 'items', 'source'}:
        raise ValueError('Estrutura do rascunho inválida.')
    if type(state.get('step')) is not int or not 0 <= state['step'] <= 6:
        raise ValueError('Etapa do rascunho inválida.')
    draft = state.get('draft')
    if not isinstance(draft, dict) or set(draft) - {'player', 'mass', 'pain', 'notes', 'collected_at'}:
        raise ValueError('Dados da coleta inválidos.')
    if draft.get('player') is not None and (type(draft['player']) is not int or draft['player'] < 1):
        raise ValueError('Jogador inválido.')
    if draft.get('mass') is not None and (not math.isfinite(float(draft['mass'])) or float(draft['mass']) <= 0):
        raise ValueError('Massa inválida.')
    if draft.get('mass') is not None:
        draft['mass'] = float(draft['mass'])
    if draft.get('pain') is not None and (type(draft['pain']) is not int or not 0 <= draft['pain'] <= 10):
        raise ValueError('EVA Dor inválida.')
    if not isinstance(draft.get('notes', ''), str) or len(draft.get('notes', '')) > 10000:
        raise ValueError('Observações inválidas.')
    if draft.get('collected_at') is not None:
        draft['collected_at'] = date.fromisoformat(str(draft['collected_at'])).isoformat()
    uploads, items = state.get('uploads', {}), state.get('items', {})
    if not isinstance(uploads, dict) or set(uploads) - {'front', 'back'} or not isinstance(items, dict) or len(items) > 2:
        raise ValueError('Imagens ou ajustes inválidos no rascunho.')
    images = {}
    for view, upload in uploads.items():
        if set(upload) - {'name', 'content', 'rotation'} or upload.get('rotation', 0) not in (0, 90, 180, 270):
            raise ValueError('Rotação ou imagem inválida.')
        content = base64.b64decode(upload['content'], validate=True)
        if len(content) > 64 * 1024 * 1024 or len(str(upload.get('name', ''))) > 500:
            raise ValueError('Imagem do rascunho muito grande.')
        with Image.open(io.BytesIO(content)) as image:
            if image.width * image.height * 4 > 64 * 1024 * 1024:
                raise ValueError('Imagem muito grande.')
            images[view] = image.convert('RGB').rotate(upload.get('rotation', 0), expand=True)
    for key, item in items.items():
        if not isinstance(key, str) or len(key) > 100 or key.split(':')[0] not in images or not isinstance(item, dict) or set(item) - ITEM_FIELDS:
            raise ValueError('Ajustes de imagem inválidos no rascunho.')
        image = images[key.split(':')[0]]
        for side, seeds in item.get('mask_seeds', {}).items():
            if side not in ('left', 'right') or not isinstance(seeds, np.ndarray) or seeds.shape != (image.height, image.width) or not np.isin(seeds, (-1, 0, 1)).all():
                raise ValueError('Correção de máscara inválida no rascunho.')
        saved = item.get('saved_analysis')
        if saved is not None:
            temperatures = saved['temperatures']
            if temperatures.shape != (image.height, image.width) or not np.isfinite(temperatures).all():
                raise ValueError('Matriz térmica inválida no rascunho.')
            for side, mask in saved.get('masks', {}).items():
                if side not in ('left', 'right') or mask.shape != temperatures.shape or not np.isin(mask, (0, 1)).all():
                    raise ValueError('Máscara salva inválida no rascunho.')
    source = state.get('source')
    if source:
        UUID(str(source['id']))
        int(source['athlete_id'])
        source['collected_at'] = date.fromisoformat(str(source['collected_at'])).isoformat()
        datetime.fromisoformat(source['created_at'])
    return images


def _read(identity):
    root = directory(identity)
    path = archive._safe_path(root / 'draft.json')
    if not path.is_file():
        raise FileNotFoundError('Rascunho não encontrado.')
    if path.stat().st_size > 256 * 1024 * 1024:
        raise ValueError('Rascunho muito grande.')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if payload.get('format') != FORMAT or str(UUID(payload['analysis_id'])) != str(identity):
        raise ValueError('Rascunho inválido.')
    state = decode(payload['state'])
    validate_state(state)
    return payload, state


def summary(identity):
    payload, state = _read(identity)
    images = validate_state(state)
    thumbnails = build_thumbnails(images)
    return dict(id=payload['analysis_id'], analysis_id=payload['analysis_id'], is_draft=True,
        athlete_id=payload['athlete_id'], athlete_name=payload['athlete_name'],
        collected_at=date.fromisoformat(payload['collected_at']), created_at=payload['created_at'],
        sequence=int(datetime.fromisoformat(payload['created_at']).timestamp()*1_000_000),
        thumbnail=legacy_thumbnail(thumbnails), thumbnails=thumbnails,
        mass=state['draft'].get('mass'), pain_score=state['draft'].get('pain'), observations=state['draft'].get('notes', ''),
        sql_pair=payload.get('sql_pair'), sql_revision=payload.get('sql_revision'), source=state.get('source'))


def list_saved(athlete_id=None):
    root = archive._safe_path(archive.analyses_directory() / '_drafts')
    entries = []
    if not root.exists():
        return entries
    for path in root.iterdir():
        if not path.is_dir() or path.name.startswith('.'):
            continue
        try:
            entry = summary(str(UUID(path.name)))
        except (OSError, ValueError, KeyError, TypeError):
            logging.getLogger(__name__).warning('Rascunho local indisponível; revise os arquivos antes de fazer backup.')
            continue
        if athlete_id is None or entry['athlete_id'] == athlete_id:
            entries.append(entry)
    return sorted(entries, key=lambda entry: entry['created_at'])


def load(identity):
    with LOCK:
        payload, state = _read(str(identity))
        return {**summary(str(identity)), 'state': state}


def check(identity, expected_revision):
    payload, state = _read(str(identity))
    if payload['created_at'] != expected_revision:
        raise AnalysisChangedError('O rascunho foi alterado por outra sessão. Abra-o novamente antes de salvar.')
    return state


def discard(identity):
    root = directory(identity)
    _read(str(identity))
    shutil.rmtree(root)


def measurements(state, images):
    """Somente valores presentes; contagens vêm das máscaras e temperaturas."""
    data = state['draft']
    result = {}
    if data.get('mass') is not None:
        result['MASSA'] = data['mass']
    if data.get('pain') is not None:
        result['EVA_DOR'] = data['pain']
    if data.get('notes', '').strip():
        result['OBSERVACOES'] = data['notes'].strip()
    for key, item in state.get('items', {}).items():
        saved = item.get('saved_analysis')
        if not saved:
            continue
        view = key.split(':')[0]
        if (saved.get('minimum_temperature', item['minimum_temperature']) != item['minimum_temperature'] or
            saved.get('maximum_temperature', item['maximum_temperature']) != item['maximum_temperature'] or
            saved.get('image_rotation', 0) != state['uploads'][view].get('rotation', 0) or
            any(box != saved['boxes'].get(side) for side, box in item.get('manual_boxes', {}).items()) or
            item.get('manual_colorbar_box') != saved.get('colorbar_box')):
            continue
        if item['maximum_temperature'] <= item['minimum_temperature']:
            continue
        source = dict(image=images[view], temperatures=saved['temperatures'],
            segmentation_masks=saved['masks'], boxes=saved['boxes'],
            minimum_temperature=item['minimum_temperature'], maximum_temperature=item['maximum_temperature'],
            default_threshold=item.get('threshold_temperature', item['minimum_temperature'] +
                item.get('threshold_percentage', 90.) / 100 * (item['maximum_temperature'] - item['minimum_temperature'])),
            part_settings=item.get('part_settings_v4', {}))
        metrics = archive._validate_view(source)[3]['metrics']
        suffix = 'FRENTE' if view == 'front' else 'VERSO'
        result[f'PERNA_DIREITA_{suffix}'] = metrics['right']['hot_pixels']
        result[f'PERNA_ESQUERDA_{suffix}'] = metrics['left']['hot_pixels']
        result[f'SOMA_{suffix}'] = metrics['right']['hot_pixels'] + metrics['left']['hot_pixels']
    return result


def save(state, *, identity=None, expected_revision=None, overwrite=False):
    if setting('MAC_DB_TARGET', 'local') != 'local':
        raise ValueError('Salvar rascunhos exige o destino local.')
    images = validate_state(state)
    source = state.get('source')
    existing_identity = identity is not None
    identity = str(UUID(str(identity))) if identity else str(UUID(str(source['id']))) if source else str(uuid4())
    with LOCK:
        target = directory(identity)
        previous_payload = None
        if target.exists():
            prior_state = check(identity, expected_revision)
            previous_payload, _ = _read(identity)
            if prior_state.get('source') != source:
                raise ValueError('A origem de um rascunho existente não pode ser alterada.')
        elif expected_revision or existing_identity:
            raise AnalysisChangedError('O rascunho original não está mais disponível.')
        if source:
            original = archive.load_analysis(int(source['athlete_id']), date.fromisoformat(str(source['collected_at'])), source['id'])
            if original['created_at'] != source['created_at']:
                raise AnalysisChangedError('A análise completa foi alterada por outra sessão. Revise o original antes de salvar.')
        athlete_id = state['draft'].get('player') or 0
        if not athlete_id and (source or previous_payload and previous_payload.get('sql_pair')):
            raise ValueError('Selecione um jogador para atualizar a análise registrada no banco.')
        day = date.fromisoformat(str(state['draft']['collected_at'])) if state['draft'].get('collected_at') else current_sao_paulo_date()
        state['draft']['collected_at'] = day.isoformat()
        name = 'Sem atleta'
        others = [entry for entry in list_saved(athlete_id) if entry['collected_at'] == day and entry['id'] != identity] if athlete_id else []
        context = database_write_connection() if athlete_id else nullcontext(None)
        pending = target.parent / f'.pending-{uuid4()}'
        previous = target.parent / f'.previous-{uuid4()}'
        moved = published = False
        try:
            with context as connection:
                sql_pair = None
                sql_revision = None
                if connection:
                    with connection.cursor() as cursor:
                        old_pair = previous_payload.get('sql_pair') if previous_payload else None
                        if old_pair:
                            old_pair = (int(old_pair[0]), date.fromisoformat(old_pair[1]))
                        origin_pair = (int(source['athlete_id']), date.fromisoformat(str(source['collected_at']))) if source and not (previous_payload or {}).get('sql_pair') else None
                        for player in sorted({athlete_id} | ({old_pair[0]} if old_pair else set()) | ({origin_pair[0]} if origin_pair else set())):
                            cursor.execute('SELECT id_atleta FROM public.atleta WHERE id_atleta=%s FOR UPDATE', (player,))
                            if cursor.fetchone() is None:
                                raise ValueError('Jogador não encontrado no banco.')
                        if old_pair and collection_state.revision(cursor, old_pair)[0] != previous_payload['sql_revision']:
                            raise AnalysisChangedError('As medidas desta análise foram alteradas. Reabra o registro antes de salvar.')
                        cursor.execute('SELECT nome FROM public.atleta WHERE id_atleta=%s FOR UPDATE', (athlete_id,))
                        row = cursor.fetchone()
                        if row is None:
                            raise ValueError('Jogador não encontrado no banco.')
                        name = row[0]
                        owned = {pair for pair in (old_pair, origin_pair) if pair}
                        own_pair = (athlete_id, day) in owned
                        cursor.execute("""SELECT count(*) FROM public.medida_valor v JOIN public.medida m USING(id_medida)
                            JOIN public.grupo_medida g USING(id_grupo_medida)
                            WHERE v.id_atleta=%s AND v.data::date=%s AND lower(trim(g.nome))='termografia'""", (athlete_id, day))
                        sql_conflict = cursor.fetchone()[0] > 0 and not own_pair
                    file_conflict = not own_pair and any(entry['collected_at'] == day and not (source and entry['id'] == str(source['id'])) for entry in archive.list_analyses(athlete_id))
                    if (sql_conflict or file_conflict or others) and not overwrite:
                        raise AnalysisConflictError('Uma análise do atleta já foi realizada nessa data. Deseja sobrescrevê-la?')
                    with connection.cursor() as cursor:
                        for pair in sorted(owned | {(athlete_id, day)}):
                            collection_state.delete(cursor, pair)
                        values = measurements(state, images)
                        if values:
                            _insert_collection(cursor, athlete_id=athlete_id, collected_at=day,
                                measurements=values, required_measures=frozenset(values))
                        sql_pair = [athlete_id, day.isoformat()]
                        sql_revision = collection_state.revision(cursor, (athlete_id, day))[0]
                payload = dict(format=FORMAT, analysis_id=identity, athlete_id=athlete_id, athlete_name=name,
                               collected_at=day.isoformat(), created_at=datetime.now(timezone.utc).isoformat(), state=encode(state),
                               sql_pair=sql_pair, sql_revision=sql_revision)
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                pending.mkdir(mode=0o700)
                (pending / 'draft.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding='utf-8')
                (pending / 'draft.json').chmod(0o600)
                if (pending / 'draft.json').stat().st_size > 256 * 1024 * 1024:
                    raise ValueError('O rascunho excede o limite de armazenamento.')
                if target.exists():
                    os.replace(target, previous)
                    moved = True
                os.replace(pending, target)
                published = True
        except Exception:
            if published:
                shutil.rmtree(target)
            if moved:
                os.replace(previous, target)
            raise
        finally:
            if pending.exists():
                shutil.rmtree(pending)
        if previous.exists():
            shutil.rmtree(previous)
        if overwrite:
            for other in others:
                discard(other['id'])
        return summary(identity)
