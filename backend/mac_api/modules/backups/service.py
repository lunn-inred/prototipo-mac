"""Snapshot consistente, cópia preventiva e restauração reconciliada local."""
import json
import logging
import os
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory, mkdtemp
from datetime import datetime, timezone
from uuid import uuid4

import psycopg2
from psycopg2 import sql
from backend.mac_api.core.database import database_write_config
from backend.mac_api.core.settings import setting
from backend.mac_api.core.maintenance import exclusive_operation
from backend.mac_api.modules.thermography.analysis_archive import analyses_directory
from . import bundle, database_snapshot as db, reconciliation
from .drive import Drive


def backups_directory(*, create=True):
    root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[4]
    configured = Path(setting('MAC_BACKUPS_DIR', './data/backups') or './data/backups').expanduser()
    destination = (configured if configured.is_absolute() else root / configured).resolve()
    analyses = analyses_directory()
    if (destination == root or analyses == root or destination == destination.parent or analyses == analyses.parent
            or destination.is_relative_to(analyses) or analyses.is_relative_to(destination)):
        raise ValueError('Diretórios de backup e análises devem ser separados e não podem ser a raiz do projeto/disco.')
    if create:
        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    return destination


def pending_recovery():
    return (backups_directory(create=False) / 'restore-pending.json').exists()


def local_config():
    if setting('MAC_DB_TARGET', 'local') != 'local':
        raise ValueError('Backup e restauração são permitidos exclusivamente no banco local.')
    return database_write_config()


def _connection():
    connection = psycopg2.connect(**local_config())
    connection.set_session(readonly=False, isolation_level='REPEATABLE READ', autocommit=False)
    return connection


def _installation():
    path = backups_directory() / 'installation.txt'
    try:
        from uuid import UUID
        return str(UUID(path.read_text(encoding='ascii').strip()))
    except FileNotFoundError:
        identity = str(uuid4())
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='ascii') as output:
            output.write(identity)
        return identity


def _lock(cursor):
    db.configure(cursor)
    state = db.schema(cursor)
    if not state['tables']:
        raise ValueError('Banco local sem tabelas do public. Inicialize-o antes de usar backups.')
    cursor.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.SQL(',').join(
        sql.SQL('public.{}').format(sql.Identifier(name)) for name in sorted(state['tables']))))


def _snapshot(cursor, content):
    _lock(cursor)
    source = analyses_directory()
    bundle.index_analyses(source)
    snapshot = db.dump(cursor, content / 'database')
    if source.exists():
        shutil.copytree(source, content / 'analyses', ignore=shutil.ignore_patterns(*bundle.SYSTEM_FILES, '._*'))
    else:
        (content / 'analyses').mkdir()
    return snapshot


def _assert_ready():
    local_config()
    if pending_recovery():
        raise ValueError('Há uma restauração interrompida. Preserve restore-pending.json e a cópia preventiva; revise a recuperação antes de continuar.')


def list_backups(*, desktop=False):
    local_config()
    with Drive(desktop=desktop) as drive:
        return drive.list()


def create_backup(*, desktop=False, progress=lambda text: None):
    _assert_ready()
    installation = _installation()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination = backups_directory() / f'mac-backup-{stamp}-{installation[:8]}-{uuid4().hex[:8]}.zip'
    # Confirmar autorização antes de gerar um pacote potencialmente grande.
    with Drive(desktop=desktop) as drive, TemporaryDirectory(prefix='create-', dir=backups_directory()) as temporary:
        progress('Preparando banco e análises; aguarde o término das operações em andamento.')
        with exclusive_operation():
            connection = _connection()
            try:
                with connection, connection.cursor() as cursor:
                    snapshot = _snapshot(cursor, Path(temporary))
            finally:
                connection.close()
        progress('Compactando a cópia local. O sistema já está liberado para uso.')
        manifest = bundle.package(Path(temporary), destination, installation)
        progress('Enviando o pacote ao Google Drive. O sistema já está liberado para uso.')
        entry = drive.upload(destination, destination.name, installation)
    return dict(file=entry, backup_id=manifest['id'], rows=snapshot['rows'],
                local_copy=str(destination), message='Backup enviado ao Drive. A cópia local também foi mantida.')


def _write_journal(path, value):
    with path.open('x', encoding='utf-8') as output:
        path.chmod(0o600)
        json.dump(value, output, ensure_ascii=False)
        output.flush()
        os.fsync(output.fileno())


def restore_downloaded(source, work, *, progress=lambda text: None):
    """Aplicação local; o chamador já baixou um arquivo verificado do Drive."""
    _assert_ready()
    unpacked = work / 'incoming'
    unpacked.mkdir()
    bundle.unpack(source, unpacked)
    descriptor = unpacked / 'database/database.json'
    if descriptor.stat().st_size > 16 * 1024 * 1024:
        raise ValueError('Descritor do banco muito grande no backup.')
    snapshot = json.loads(descriptor.read_text(encoding='utf-8'))
    if snapshot.get('format') != 1:
        raise ValueError('Versão do dump lógico não suportada.')
    remote = bundle.index_analyses(unpacked / 'analyses')
    journal = backups_directory() / 'restore-pending.json'
    recovery = backups_directory() / f'recovery-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}.zip'
    root = analyses_directory()
    root.parent.mkdir(parents=True, exist_ok=True)
    previous = root.parent / f'.mac-before-{uuid4().hex}'
    stage = Path(mkdtemp(prefix='.mac-restore-', dir=root.parent))
    swapped, moved_old, committed, commit_started = False, False, False, False
    connection = None
    try:
        progress('Validando os dados e criando a cópia preventiva local.')
        with exclusive_operation():
            connection = _connection()
            try:
                with connection.cursor() as cursor:
                    local = bundle.index_analyses(root)
                    winners, retained = bundle.reconcile(local, remote)
                    safe_content = work / 'safety'
                    safe_content.mkdir()
                    local_snapshot = _snapshot(cursor, safe_content)
                    if local_snapshot['schema'] != snapshot['schema']:
                        raise ValueError('Esquema do backup incompatível com o banco local; nada foi substituído.')
                    bundle.package(safe_content, recovery, _installation())
                    sql_retained = [entry for entry in retained if entry.get('pair')]
                    draft_athletes = [entry['metadata']['athlete_id'] for entry in retained
                                      if entry.get('is_draft') and entry['metadata'].get('athlete_id')]
                    kept = reconciliation.capture(cursor, local_snapshot['schema'], sql_retained, draft_athletes=draft_athletes)
                    kept['ids'] = {entry['id'] for entry in sql_retained}
                    kept['entries'] = {entry['id']: entry for entry in sql_retained}
                    kept['obsolete_pairs'] = set()
                    for entry in sql_retained:
                        if entry.get('is_draft'):
                            origin = entry['metadata']['state'].get('source')
                            if origin:
                                old_pair = (int(origin['athlete_id']), origin['collected_at'])
                                if old_pair != entry['pair']:
                                    kept['obsolete_pairs'].add(old_pair)
                    for entry in winners.values():
                        shutil.copytree(entry['path'], stage / entry['relative'], ignore=shutil.ignore_patterns(*bundle.SYSTEM_FILES, '._*'))
                    _write_journal(journal, dict(recovery=str(recovery), previous=str(previous), stage=str(stage), analyses=str(root)))
                    progress('Restaurando o banco e preservando as análises locais iguais ou mais recentes.')
                    db.restore(cursor, unpacked / 'database', snapshot)
                    reconciliation.apply(cursor, snapshot['schema'], kept, remote)
                    db.reset_sequences(cursor, snapshot)
                    if root.exists():
                        os.replace(root, previous)
                        moved_old = True
                    os.replace(stage, root)
                    swapped = True
                    commit_started = True
                    connection.commit()
                    committed = True
            except Exception:
                try:
                    connection.rollback()
                    if swapped:
                        # Stage está vazio/disponível após a publicação por rename.
                        os.replace(root, stage)
                    if moved_old:
                        os.replace(previous, root)
                    if not (commit_started and connection.closed):
                        journal.unlink(missing_ok=True)
                except Exception as recovery_error:
                    raise RuntimeError('Restauração interrompida: preserve a cópia preventiva e o diário para recuperação.') from recovery_error
                raise
            finally:
                connection.close()
                connection = None
            journal.unlink(missing_ok=True)
        try:
            if previous.exists():
                shutil.rmtree(previous)
        except OSError:
            logging.getLogger(__name__).warning('Restauração concluída; diretório temporário antigo requer revisão: %s', previous.name)
        return dict(message='Backup restaurado com reconciliação das análises locais.',
                    analyses=len(winners), preserved_local=len(retained), recovery_copy=str(recovery))
    finally:
        if connection is not None:
            connection.close()
        if stage.exists() and not journal.exists():
            shutil.rmtree(stage)


def restore_backup(file_id, expected_sha256, *, desktop=False, progress=lambda text: None):
    _assert_ready()
    with Drive(desktop=desktop) as drive, TemporaryDirectory(prefix='download-', dir=backups_directory()) as temporary:
        work = Path(temporary)
        progress('Baixando e verificando o backup do Drive; os dados locais ainda não foram alterados.')
        metadata = drive.metadata(file_id)
        if not expected_sha256 or metadata.get('properties', {}).get('sha256') != expected_sha256:
            raise ValueError('O backup selecionado mudou. Atualize a lista e confirme novamente.')
        source = work / 'download.zip'
        drive.download(file_id, source)
        if bundle.digest(source) != expected_sha256:
            raise ValueError('O conteúdo do backup mudou durante o download. Atualize a lista e confirme novamente.')
        return restore_downloaded(source, work, progress=progress)
