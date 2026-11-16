"""Snapshot read-only da nuvem e restauração explícita em mac_dev vazio."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import psycopg2
from psycopg2 import sql

from backend.mac_api.core.database import cloud_database_config, database_write_config
from backend.mac_api.core.settings import setting

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'postgres:17-alpine'


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(command, cwd=ROOT, stderr=subprocess.PIPE, **kwargs)
    if result.returncode:
        # Não exibir stderr bruto: COPY/erros SQL podem conter dados pessoais.
        raise RuntimeError(f'{Path(command[0]).name}: operação falhou (código {result.returncode}). '
                           'Nenhum destino remoto foi usado para restauração.')
    return result


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(connection) -> dict:
    """Descrição sem dados pessoais; hashes independem da ordem física das linhas."""
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL TIME ZONE 'UTC'")
        # Supabase pode usar extra_float_digits=0; canonicalizar evita hashes
        # diferentes para os mesmos floats restaurados sem perda pelo pg_dump.
        cursor.execute('SET LOCAL extra_float_digits=3')
        cursor.execute('SET LOCAL search_path TO public, pg_catalog')
        cursor.execute("SELECT c.relname, c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                       "WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S') ORDER BY 1")
        relations = cursor.fetchall()
        tables, views, sequences = {}, {}, []
        for name, kind in relations:
            if kind == 'S':
                sequences.append(name)
                continue
            cursor.execute("SELECT a.attname, format_type(a.atttypid,a.atttypmod), a.attnotnull, "
                           "a.attidentity, pg_get_expr(d.adbin,d.adrelid) "
                           "FROM pg_attribute a LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                           "WHERE a.attrelid=%s::regclass AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum",
                           (f'public.{sql.Identifier(name).as_string(connection)}',))
            columns = [list(row) for row in cursor.fetchall()]
            if kind in ('v', 'm'):
                cursor.execute('SELECT pg_get_viewdef(%s::regclass, true)', (f'public.{name}',))
                views[name] = {'columns': columns, 'definition': cursor.fetchone()[0]}
            else:
                cursor.execute(sql.SQL(
                    "SELECT count(*), md5(COALESCE(string_agg(md5(to_jsonb(t)::text), '' "
                    "ORDER BY md5(to_jsonb(t)::text)), '')) FROM public.{} t"
                ).format(sql.Identifier(name)))
                count, digest = cursor.fetchone()
                tables[name] = {'columns': columns, 'rows': count, 'digest': digest}
        cursor.execute("SELECT c.relname, con.conname, pg_get_constraintdef(con.oid, true) "
                       "FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid "
                       "WHERE con.connamespace='public'::regnamespace ORDER BY 1,2")
        constraints = [list(row) for row in cursor.fetchall()]
        cursor.execute("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1,2")
        indexes = [list(row) for row in cursor.fetchall()]
        return {'tables': tables, 'views': views, 'sequences': sequences,
                'constraints': constraints, 'indexes': indexes}


def export_cloud() -> Path:
    config = cloud_database_config()  # Não depende do destino da aplicação.
    parent = ROOT / 'data/backups'
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    directory = parent / f'cloud-{stamp}-{uuid4().hex[:8]}.incomplete'
    directory.mkdir(mode=0o700)
    dump = directory / 'banco.dump'
    os_environment = dict(os.environ)
    os_environment.update(PGPASSWORD=str(config['password']), PGSSLMODE=str(config['sslmode']),
                          PGCONNECT_TIMEOUT='15', PGOPTIONS='-c default_transaction_read_only=on')
    with psycopg2.connect(**config) as connection:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
        with connection.cursor() as cursor:
            cursor.execute('SHOW transaction_read_only')
            if cursor.fetchone()[0] != 'on':
                raise RuntimeError('A origem não confirmou modo read-only.')
            cursor.execute('SHOW server_version_num')
            version = int(cursor.fetchone()[0])
            if version // 10000 != 17:
                raise RuntimeError('Origem deve usar PostgreSQL 17; revise a imagem antes de exportar.')
            cursor.execute('SELECT pg_export_snapshot()')
            snapshot = cursor.fetchone()[0]
        command = ['docker', 'run', '--rm', '--env', 'PGPASSWORD', '--env', 'PGSSLMODE',
                   '--env', 'PGCONNECT_TIMEOUT', '--env', 'PGOPTIONS', IMAGE, 'pg_dump',
                   '--host', str(config['host']), '--port', str(config['port']),
                   '--username', str(config['user']), '--dbname', str(config['dbname']),
                   '--no-password', '--format=custom', '--schema=public', '--strict-names',
                   '--no-owner', '--no-acl', '--snapshot', snapshot]
        with dump.open('xb') as output:
            dump.chmod(0o600)
            run(command, stdout=output, env=os_environment)
        state = inventory(connection)
    manifest = {'format': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                'postgres_version_num': version, 'scope': 'public', 'sha256': sha256(dump),
                'inventory': state}
    with (directory / 'manifesto.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
    final = directory.with_suffix('')
    directory.rename(final)
    print(f'Snapshot read-only concluído: {final.relative_to(ROOT)}')
    print('Linhas:', json.dumps({name: table['rows'] for name, table in state['tables'].items()}))
    return final


def local_config() -> dict:
    if setting('MAC_DB_TARGET', 'local') != 'local':
        raise RuntimeError('Restauração exige MAC_DB_TARGET=local.')
    config = database_write_config()
    if config['dbname'] != 'mac_dev':
        raise RuntimeError('Esta ferramenta restaura somente mac_dev, nunca o banco de testes.')
    return config


def read_manifest(directory: Path) -> dict:
    manifest = json.loads((directory / 'manifesto.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or manifest.get('scope') != 'public':
        raise RuntimeError('Formato de snapshot não reconhecido.')
    if sha256(directory / 'banco.dump') != manifest.get('sha256'):
        raise RuntimeError('Hash do dump não corresponde ao manifesto. Restauração recusada.')
    return manifest


def verify(directory: Path) -> None:
    expected = read_manifest(directory)
    config = local_config()
    with psycopg2.connect(**config) as connection:
        connection.set_session(readonly=True, isolation_level='REPEATABLE READ')
        actual = inventory(connection)
        if actual != expected['inventory']:
            different = [part for part in actual if actual[part] != expected['inventory'].get(part)]
            raise RuntimeError('A cópia diverge do snapshot em: ' + ', '.join(different))
        with connection.cursor() as cursor:
            for view in actual['views']:
                cursor.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(view)))
                print(f'View {view}: {cursor.fetchone()[0]} linha(s)')
    print('Cópia validada: hashes dos dados, colunas, views, índices, constraints e nomes das sequências.')


def restore(directory: Path, *, confirmed: bool) -> None:
    if not confirmed:
        raise RuntimeError('Informe --confirm para restaurar explicitamente em mac_dev vazio.')
    read_manifest(directory)
    config = local_config()
    with psycopg2.connect(**config) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace")
        relations = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace")
        functions = cursor.fetchone()[0]
        if relations or functions:
            raise RuntimeError('mac_dev já contém objetos. Nenhuma tabela foi apagada ou sobrescrita.')
    # Target fixo: executa dentro do serviço db-dev e conecta apenas no loopback
    # do container. Nenhuma URL, host remoto ou --clean é aceito do usuário.
    environment = dict(os.environ, PGPASSWORD=str(config['password']))
    command = ['docker', 'compose', 'exec', '-T', '--env', 'PGPASSWORD', 'db-dev',
               'pg_restore', '--host=127.0.0.1', '--port=5432', '--username', str(config['user']),
               '--dbname=mac_dev', '--no-password', '--no-owner', '--no-acl',
               '--schema=public', '--single-transaction', '--exit-on-error']
    with (directory / 'banco.dump').open('rb') as stream:
        run(command, stdin=stream, stdout=subprocess.DEVNULL, env=environment)
    verify(directory)


def copy_cloud_to_empty_local(*, confirmed: bool) -> Path:
    """Exporta a origem read-only e restaura apenas em mac_dev vazio."""
    if not confirmed:
        raise RuntimeError('Informe --confirm para copiar a nuvem para mac_dev vazio.')
    config = local_config()
    with psycopg2.connect(**config) as connection:
        connection.set_session(readonly=True)
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace")
            relations = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace")
            functions = cursor.fetchone()[0]
            if relations or functions:
                raise RuntimeError('mac_dev já contém objetos. Nenhuma tabela foi apagada ou sobrescrita.')
    directory = export_cloud()
    restore(directory, confirmed=True)
    return directory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('export', help='Snapshot read-only do schema public da nuvem.')
    copy_command = commands.add_parser('copy', help='Exporta a nuvem read-only e restaura em mac_dev vazio.')
    copy_command.add_argument('--confirm', action='store_true')
    for name in ('restore', 'verify'):
        command = commands.add_parser(name)
        command.add_argument('snapshot', type=Path)
        if name == 'restore':
            command.add_argument('--confirm', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'export':
            export_cloud()
        elif args.command == 'copy':
            copy_cloud_to_empty_local(confirmed=args.confirm)
        elif args.command == 'restore':
            restore(args.snapshot.resolve(), confirmed=args.confirm)
        else:
            verify(args.snapshot.resolve())
    except (RuntimeError, psycopg2.Error, OSError, ValueError) as error:
        # Não expor mensagens de conexão/SQL que possam incluir informações privadas.
        if isinstance(error, RuntimeError):
            parser.exit(1, f'{error}\n')
        parser.exit(1, 'Operação interrompida; verifique conexão, permissões e os arquivos locais.\n')


if __name__ == '__main__':
    main()
