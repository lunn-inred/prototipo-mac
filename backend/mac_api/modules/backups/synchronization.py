"""Drive como transporte: objetos imutáveis e publicação do índice por último.

Conflitos, inclusive publicação concorrente, bloqueiam em vez de escolher dados
pelo horário local. A aplicação SQL é incremental e usa a estrutura já instalada.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory, mkdtemp
from uuid import UUID, uuid4

from backend.mac_api.core.maintenance import exclusive_operation
from backend.mac_api.modules.thermography.analysis_archive import analyses_directory
from . import bundle, service, sync_data
from .drive import Drive
from .directory_publication import DirectoryPublication


def _head(drive):
    commits = [e for e in drive.list(sync=True) if e.get('properties', {}).get('role') == 'commit']
    if not commits:
        return None
    ids = [e['properties']['commit'] for e in commits]
    if len(ids) != len(set(ids)):
        raise ValueError('Índices de sincronização duplicados no Drive. Revise a pasta sem apagar arquivos locais.')
    for identity in ids:
        UUID(identity)
    parents = {e['properties']['parent'] for e in commits}
    if parents - set(ids) - {'root'}:
        raise ValueError('Histórico de sincronização incompleto no Drive. Preserve os índices anteriores.')
    heads = [e for e in commits if e['properties']['commit'] not in parents]
    if len(heads) != 1:
        raise ValueError('Publicações concorrentes no Drive. A sincronização foi bloqueada para '
                         'reconciliar os índices, sem sobrescrever as duas versões.')
    by_id = {e['properties']['commit']: e for e in commits}
    visited, current = set(), heads[0]['properties']['commit']
    while current != 'root' and current not in visited:
        visited.add(current)
        current = by_id[current]['properties']['parent']
    if current != 'root' or visited != set(ids):
        raise ValueError('Histórico de sincronização inválido ou ramificado. Revise os índices do Drive.')
    return {**heads[0], '_lineage': visited}


def status(*, desktop=False):
    service._assert_ready()
    with Drive(desktop=desktop) as drive:
        head = _head(drive)
        return dict(folder_id=drive.folder, folder_name='Analises MAC', initialized=head is not None,
                    revision=head['properties']['commit'] if head else None,
                    message='Pronto para sincronizar.' if head else 'Primeira sincronização ainda não realizada.')


def _identity(entry):
    return entry['properties']['commit'] if entry else None


def _scope(drive):
    config = service.local_config()
    return sync_data.fingerprint([drive.folder, {k: str(config.get(k, '')) for k in ('host', 'port', 'dbname', 'user')}])


def _baseline(path, scope):
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('scope') != scope or state.get('format') != sync_data.FORMAT:
        raise ValueError('O estado de sincronização pertence a outra pasta ou banco. '
                         'Revise a configuração antes de reutilizar esta instalação.')
    return state


def _analysis_value(entry):
    return dict(content=sync_data.fingerprint(entry['hashes']), relative=entry['relative'].as_posix(),
                revision=entry['revision'].isoformat())


def _load_remote(drive, head, work):
    if not head:
        return None
    if int(head.get('size', 0)) > 128 * 1024**2:
        raise ValueError('Índice de sincronização excede 128 MiB.')
    path = work / 'remote-index.json'
    drive.download(head['id'], path, sync=True)
    if path.stat().st_size > 128 * 1024**2:
        raise ValueError('Índice de sincronização excede 128 MiB.')
    if bundle.digest(path) != head['properties']['sha256']:
        raise ValueError('O índice mudou durante o download. Tente sincronizar novamente.')
    value = json.loads(path.read_text(encoding='utf-8'))
    if (value.get('format') != sync_data.FORMAT or value.get('id') != _identity(head)
            or value.get('parent') != head['properties']['parent']):
        raise ValueError('Formato ou identidade do índice de sincronização inválido.')
    return value


def _prepare_files(drive, winners, local, remote, stage, work):
    downloaded = 0
    for index, (identity, descriptor) in enumerate(winners.items()):
        here = local.get(identity)
        if here and _analysis_value(here) == descriptor:
            entry = here
        else:
            record = remote[identity]
            source, unpacked = work / f'{index}.zip', work / f'analysis-{index}'
            unpacked.mkdir()
            drive.download(record['file_id'], source, sync=True)
            if bundle.digest(source) != record['sha256']:
                raise ValueError('O ZIP da análise não corresponde ao índice do Drive.')
            bundle.unpack(source, unpacked, require_database=False)
            entries = bundle.index_analyses(unpacked / 'analyses')
            if set(entries) != {identity} or _analysis_value(entries[identity]) != descriptor:
                raise ValueError('O conteúdo da análise não corresponde ao índice do Drive.')
            entry = entries[identity]
            downloaded += 1
        destination = stage / entry['relative']
        shutil.copytree(entry['path'], destination, ignore=shutil.ignore_patterns(*bundle.SYSTEM_FILES, '._*'))
    entries = bundle.index_analyses(stage)
    pairs = [e['pair'] for e in entries.values() if not e.get('is_draft')]
    if len(pairs) != len(set(pairs)):
        raise ValueError('Análises distintas ocupam o mesmo jogador/data. Revise o conflito antes de sincronizar.')
    return entries, downloaded


def _publish(drive, head, merged, winners, local, remote, work, installation):
    descriptors, uploaded = {}, 0
    for index, (identity, value) in enumerate(winners.items()):
        previous = remote.get(identity)
        if previous and previous['value'] == value:
            descriptors[identity] = previous
            continue
        entry = local[identity]
        content = work / f'upload-{index}'
        content.mkdir()
        shutil.copytree(entry['path'], content / 'analyses' / entry['relative'],
                        ignore=shutil.ignore_patterns(*bundle.SYSTEM_FILES, '._*'))
        zipped = work / f'upload-{index}.zip'
        bundle.package(content, zipped, installation)
        result = drive.upload(zipped, f'analise-{identity.replace(":", "-")}-{value["content"][:16]}.zip', installation,
                              sync_properties=dict(role='analysis'))
        descriptors[identity] = dict(value=value, file_id=result['id'], sha256=bundle.digest(zipped))
        uploaded += 1
    if _identity(_head(drive)) != _identity(head):
        raise ValueError('Outro computador sincronizou durante a operação. Tente novamente; os dados locais não foram substituídos.')
    identity = str(uuid4())
    commit = dict(format=sync_data.FORMAT, id=identity, parent=_identity(head) or 'root',
                  created_at=datetime.now(timezone.utc).isoformat(), database=merged, analyses=descriptors)
    path = work / 'index.json'
    path.write_text(sync_data.canonical(commit), encoding='utf-8')
    path.chmod(0o600)
    if path.stat().st_size > 128 * 1024**2:
        raise ValueError('Índice de sincronização excede 128 MiB.')
    drive.upload(path, f'mac-sync-{identity}.json', installation, mime_type='application/json',
                 sync_properties=dict(role='commit', commit=identity, parent=commit['parent']))
    if _identity(_head(drive)) != identity:
        raise ValueError('Publicação concorrente detectada. Preserve os índices do Drive para revisão.')
    return commit, uploaded


def synchronize(*, desktop=False, progress=lambda text: None):
    service._assert_ready()
    base_path = service.backups_directory() / 'sync-state.json'
    journal = service.backups_directory() / 'restore-pending.json'
    root = analyses_directory()
    root.parent.mkdir(parents=True, exist_ok=True)
    publication = DirectoryPublication(root)
    stage = Path(mkdtemp(prefix='.mac-sync-', dir=root.parent))
    commit_started = False
    connection = None
    try:
        progress('Validando autorização e conexão com o Google Drive.')
        with Drive(desktop=desktop) as drive, TemporaryDirectory(prefix='sync-', dir=service.backups_directory()) as temporary:
            work = Path(temporary)
            scope = _scope(drive)
            baseline = _baseline(base_path, scope)
            progress('Consultando o índice de sincronização no Drive.')
            head = _head(drive)
            remote = _load_remote(drive, head, work)
            if baseline and not remote:
                raise ValueError('O índice compartilhado desapareceu. Revise a pasta antes de iniciar outra sincronização.')
            if baseline and baseline['revision'] not in head['_lineage']:
                raise ValueError('O histórico do Drive não contém o último estado desta instalação. Revise a pasta antes de sincronizar.')
            progress('Comparando registros e análises. O acesso aos dados ficará temporariamente bloqueado.')
            with exclusive_operation():
                connection = service._connection()
                try:
                    with connection.cursor() as cursor:
                        service._lock(cursor)
                        local = sync_data.capture(cursor)
                        merged = sync_data.merge_database(baseline['database'] if baseline else None,
                            local, remote['database']) if remote else local
                        local_files = bundle.index_analyses(root)
                        here = {k: _analysis_value(e) for k, e in local_files.items()}
                        there = {k: e['value'] for k, e in remote['analyses'].items()} if remote else {}
                        winners = sync_data.merge(baseline['analyses'] if baseline else {}, here, there,
                                                  scope='análises')
                        progress('Preparando somente as análises novas ou alteradas do Drive.')
                        staged, downloaded = _prepare_files(drive, winners, local_files,
                            remote['analyses'] if remote else {}, stage, work)
                        athlete_table = 'atleta' if 'atleta' in merged['tables'] else 'atletas'
                        athletes = {r['id_atleta'] for r in merged['tables'].get(athlete_table, {}).values()}
                        if any(e['metadata'].get('athlete_id') and str(e['metadata']['athlete_id']) not in athletes
                               for e in staged.values()):
                            raise ValueError('Uma análise referencia jogador ausente do banco sincronizado.')
                        safety = work / 'safety'
                        safety.mkdir()
                        service._snapshot(cursor, safety)
                        recovery = service.backups_directory() / f'recovery-sync-{uuid4().hex}.zip'
                        bundle.package(safety, recovery, service._installation())
                        service._write_journal(journal, dict(operation='sync', recovery=str(recovery),
                            previous=str(publication.previous), incoming=str(publication.incoming),
                            stage=str(stage), analyses=str(root), state=str(base_path)))
                        progress('Aplicando as diferenças no banco local e verificando os vínculos.')
                        sync_data.apply(cursor, local, merged)
                        # Renomear pelo ID existente; não criar pastas de mesmo nome.
                        drive.rename_sync_folder()
                        if remote and merged == remote['database'] and winners == there:
                            commit, uploaded = remote, 0
                            if _identity(_head(drive)) != _identity(head):
                                raise ValueError('O Drive mudou durante a leitura. Tente sincronizar novamente.')
                        else:
                            progress('Enviando ZIPs alterados e publicando o índice de sincronização.')
                            commit, uploaded = _publish(drive, head, merged, winners, local_files,
                                remote['analyses'] if remote else {}, work, service._installation())
                        publication.publish(stage)
                        commit_started = True
                        connection.commit()
                        pending = base_path.with_suffix('.pending')
                        with pending.open('w', encoding='utf-8') as output:
                            pending.chmod(0o600)
                            output.write(sync_data.canonical(dict(format=sync_data.FORMAT, scope=scope,
                                revision=commit['id'], database=merged, analyses=winners)))
                            output.flush()
                            os.fsync(output.fileno())
                        os.replace(pending, base_path)
                        publication.cleanup()
                        journal.unlink()
                except Exception:
                    # Após iniciar o commit não sabemos distinguir resposta perdida
                    # de commit confirmado: manter diário e bloquear acesso nesse caso.
                    if not commit_started:
                        connection.rollback()
                        publication.rollback()
                        journal.unlink(missing_ok=True)
                    raise
                finally:
                    connection.close()
                    connection = None
            return dict(message='Sincronização concluída. Dados locais e Drive atualizados.',
                        analyses=len(winners), uploaded=uploaded, downloaded=downloaded,
                        revision=commit['id'], recovery_copy=str(recovery))
    finally:
        if connection is not None:
            connection.close()
        if stage.exists() and not journal.exists():
            shutil.rmtree(stage)
