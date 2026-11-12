"""Pacote verificável, seleção por UUID/revisão e extração sem path traversal."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np
from PIL import Image
from backend.mac_api.modules.thermography import analysis_archive as archive
from backend.mac_api.core.settings import setting

SYSTEM_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini'}


def ignored_file(path):
    return path.name in SYSTEM_FILES or path.name.startswith('._')


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def revision(value):
    timestamp = datetime.fromisoformat(value.removesuffix('Z') + '+00:00' if value.endswith('Z') else value)
    if timestamp.tzinfo is None:
        raise ValueError('Análise sem fuso no último salvamento; revise antes de restaurar.')
    return timestamp.astimezone(timezone.utc)


def index_analyses(root, *, validate=True):
    entries = {}
    if not root.exists():
        return entries
    if root.is_symlink():
        raise ValueError('Diretório de análises não pode ser um link simbólico.')
    files = [path for path in root.rglob('*') if (path.is_file() or path.is_symlink()) and not ignored_file(path)]
    if any(path.is_symlink() for path in root.rglob('*')):
        raise ValueError('Há links simbólicos nas análises; backup recusado.')
    covered = set()
    for metadata_file in sorted(root.glob('atleta_*/*/analise_*/metadados.json')):
        if metadata_file.stat().st_size > 2 * 1024 * 1024:
            raise ValueError('Metadados de análise muito grandes.')
        metadata = json.loads(metadata_file.read_text(encoding='utf-8'))
        identity = str(UUID(metadata['analysis_id']))
        athlete_id = int(metadata['athlete_id'])
        if athlete_id < 1 or metadata.get('format_version') != archive.FORMAT_VERSION:
            raise ValueError('Formato de análise não suportado.')
        relative = Path(f'atleta_{athlete_id}') / date.fromisoformat(metadata['collected_at']).isoformat() / f'analise_{identity}'
        if metadata_file.parent != root / relative or identity in entries:
            raise ValueError('Análise duplicada ou identificador incompatível com o caminho.')
        saved_at = revision(metadata['created_at'])
        analysis_files = sorted(path for path in metadata_file.parent.rglob('*') if path.is_file() and not ignored_file(path))
        hashes = {path.relative_to(metadata_file.parent).as_posix(): digest(path) for path in analysis_files}
        if validate:
            for view, directory in (('front', 'frente'), ('back', 'verso')):
                info = metadata['views'][view]
                location = metadata_file.parent / directory
                if (location / 'temperaturas.npy').stat().st_size > 64 * 1024 * 1024 + 4096:
                    raise ValueError('Matriz térmica muito grande no backup.')
                with Image.open(location / 'original.png') as original:
                    if original.width * original.height * 4 > 64 * 1024 * 1024:
                        raise ValueError('Imagem térmica muito grande no backup.')
                    image = original.convert('RGB')
                if info.get('image_sha256') != digest(location / 'original.png'):
                    raise ValueError('Imagem não corresponde aos metadados da análise.')
                masks = {}
                for side, label in (('right', 'direita'), ('left', 'esquerda')):
                    with Image.open(location / f'mascara_{label}.png') as mask:
                        if mask.size != image.size:
                            raise ValueError('Máscara incompatível com a imagem no backup.')
                        values = np.asarray(mask.convert('L'))
                    if not np.isin(values, (0, 255)).all():
                        raise ValueError('Máscara não binária no backup.')
                    masks[side] = values > 0
                archive._validate_view({**info, 'image': image,
                    'temperatures': np.load(location / 'temperaturas.npy', allow_pickle=False, mmap_mode='r'),
                    'segmentation_masks': masks})
        covered.update(analysis_files)
        entries[identity] = dict(id=identity, path=metadata_file.parent, relative=relative,
                                 metadata=metadata, revision=saved_at, hashes=hashes,
                                 pair=(athlete_id, metadata['collected_at']))
    if set(files) != covered:
        raise ValueError('Há arquivos de análise incompletos ou fora da estrutura esperada; revise antes do backup.')
    return entries


def reconcile(local, remote):
    winners, retained = {}, []
    for identity in sorted(set(local) | set(remote)):
        here, there = local.get(identity), remote.get(identity)
        if here and there and here['revision'] == there['revision'] and here['hashes'] != there['hashes']:
            raise ValueError('A mesma análise tem conteúdos diferentes com a mesma revisão. Restauração recusada para revisão manual.')
        keep = here is not None and (there is None or here['hashes'] == there['hashes'] or here['revision'] > there['revision'])
        winners[identity] = here if keep else there
        if keep:
            retained.append(here)
    pairs = {}
    for identity, entry in winners.items():
        if entry['pair'] in pairs:
            raise ValueError('Análises distintas ocupam o mesmo atleta/data. Revise o conflito antes de restaurar.')
        pairs[entry['pair']] = identity
    return winners, retained


def package(content, destination, installation):
    files = {path.relative_to(content).as_posix(): dict(sha256=digest(path), size=path.stat().st_size)
             for path in sorted(content.rglob('*')) if path.is_file()}
    manifest = dict(format='mac-backup-v1', id=str(uuid4()), installation=installation,
                    created_at=datetime.now(timezone.utc).isoformat(), scope='public', files=files)
    if destination.exists():
        raise ValueError('O destino do pacote já existe.')
    pending = destination.with_name(destination.name + '.incomplete')
    with ZipFile(pending, 'x', compression=ZIP_DEFLATED, allowZip64=True) as output:
        pending.chmod(0o600)
        for name in files:
            output.write(content / name, name)
        output.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False))
    if destination.exists():
        raise ValueError('O destino do pacote já existe.')
    os.replace(pending, destination)
    return manifest


def unpack(source, destination):
    max_bytes = int(setting('MAC_BACKUP_MAX_EXTRACTED_BYTES', str(20 * 1024**3)))
    with ZipFile(source) as zipped:
        members = zipped.infolist()
        if len(members) > 100000 or sum(info.file_size for info in members) > max_bytes:
            raise ValueError('Backup ultrapassa o limite de tamanho/arquivos.')
        names = [info.filename for info in members]
        if len(set(names)) != len(names) or 'manifest.json' not in names:
            raise ValueError('Pacote de backup inválido.')
        for info in members:
            name = PurePosixPath(info.filename)
            if (not name.parts or name.is_absolute() or '..' in name.parts or '\\' in info.filename or ':' in info.filename
                    or name.as_posix() != info.filename or info.is_dir()
                    or stat.S_ISLNK(info.external_attr >> 16)
                    or (info.filename != 'manifest.json' and name.parts[0] not in ('analyses', 'database'))):
                raise ValueError('Caminho ou link inválido no backup.')
        if zipped.getinfo('manifest.json').file_size > 32 * 1024 * 1024:
            raise ValueError('Manifesto muito grande.')
        manifest = json.loads(zipped.read('manifest.json'))
        if manifest.get('format') != 'mac-backup-v1' or manifest.get('scope') != 'public':
            raise ValueError('Formato de backup não suportado.')
        UUID(manifest['id'])
        revision(manifest['created_at'])
        if set(manifest['files']) != set(names) - {'manifest.json'}:
            raise ValueError('Lista de arquivos não corresponde ao manifesto.')
        for name, expected in manifest['files'].items():
            if not re.fullmatch(r'[a-f0-9]{64}', str(expected.get('sha256', ''))) or expected.get('size') != zipped.getinfo(name).file_size:
                raise ValueError('Manifesto de backup inválido.')
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with zipped.open(name) as input_file, path.open('xb') as output:
                shutil.copyfileobj(input_file, output, length=1024 * 1024)
            if digest(path) != expected['sha256']:
                raise ValueError('Backup corrompido: verificação SHA-256 falhou.')
    if not (destination / 'database/database.json').is_file():
        raise ValueError('Backup não contém o banco local.')
    return manifest
