"""Banco do instalador: bootstrap vazio e migrations autenticadas pelo pacote.

Não é chamado pela API web e nunca adota automaticamente um banco existente.
O histórico fica fora de public para não sincronizar identidades da instalação.
"""
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

import psycopg2
from backend.mac_api.modules.backups.database_snapshot import schema

ROOT = Path(__file__).resolve().parents[2]
LOCK_ID = 764102839


def digest(content):
    return hashlib.sha256(content).hexdigest()


def fingerprint(cursor):
    # pg_get_* qualifica nomes conforme search_path; manter o mesmo contexto
    # no bootstrap, após reconectar e nos backups/restaurações.
    cursor.execute('SET LOCAL search_path TO public, pg_catalog')
    return digest(json.dumps(schema(cursor), sort_keys=True, ensure_ascii=False).encode('utf-8'))


def package_plan(root=ROOT):
    manifest = json.loads((root / 'bootstrap/manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1:
        raise RuntimeError('Manifesto de banco inválido.')
    scripts = {p.name: p.read_bytes().replace(b'\r\n', b'\n') for p in sorted((root / 'migrations').glob('*.sql'))}
    for name, checksum in manifest['includes'].items():
        if name not in scripts or digest(scripts[name]) != checksum:
            raise RuntimeError('Uma migration histórica foi alterada. Use um pacote íntegro.')
    baseline = (root / 'bootstrap/initial.sql').read_bytes().replace(b'\r\n', b'\n')
    return manifest, scripts, baseline


def transactional_sql(content):
    # Os arquivos históricos têm BEGIN/COMMIT próprios; o gerenciador controla
    # uma única transação incluindo o histórico, sem commits intermediários.
    return re.sub(r'^\s*(?:BEGIN|COMMIT);[ \t]*$', '', content.decode('utf-8'), flags=re.M | re.I)


def run_migrations(config, installation_id, *, initialize=False, root=ROOT, backup=None):
    if config.get('host') != '127.0.0.1' or config.get('dbname') not in ('mac_dev', 'mac_test'):
        raise RuntimeError('Migrações automáticas exigem banco local identificado.')
    identity = str(UUID(str(installation_id)))
    manifest, scripts, baseline = package_plan(root)
    baseline_id = manifest['baseline']
    expected = {baseline_id: digest(baseline), **{name: digest(body) for name, body in scripts.items()}}
    connection = psycopg2.connect(**config)
    try:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(%s)', (LOCK_ID,))
            if not cursor.fetchone()[0]:
                raise RuntimeError('Outra atualização do banco está em andamento.')
            cursor.execute("SELECT to_regclass('mac_internal.installation')")
            initialized = cursor.fetchone()[0] is not None
            if not initialized:
                cursor.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','v','m','S','p','f')")
                if not initialize or cursor.fetchone()[0]:
                    raise RuntimeError('Banco existente sem histórico do instalador. Não será recriado ou adotado automaticamente.')
            connection.autocommit = False
            if not initialized:
                cursor.execute('CREATE SCHEMA mac_internal')
                cursor.execute('CREATE TABLE mac_internal.installation (singleton boolean PRIMARY KEY CHECK(singleton), identity uuid NOT NULL, schema_hash text NOT NULL)')
                cursor.execute('CREATE TABLE mac_internal.schema_migrations (version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())')
                cursor.execute(baseline.decode('utf-8'))
                for name in [baseline_id, *manifest['includes']]:
                    cursor.execute('INSERT INTO mac_internal.schema_migrations(version,checksum) VALUES(%s,%s)', (name, expected[name]))
                cursor.execute('INSERT INTO mac_internal.installation VALUES(true,%s,%s)', (identity, fingerprint(cursor)))
            cursor.execute('SELECT identity::text,schema_hash FROM mac_internal.installation WHERE singleton')
            owner, previous_hash = cursor.fetchone()
            if owner != identity:
                raise RuntimeError('O banco pertence a outra instalação.')
            cursor.execute('SELECT version,checksum FROM mac_internal.schema_migrations')
            applied = dict(cursor.fetchall())
            if any(name not in expected or expected[name] != checksum for name, checksum in applied.items()):
                raise RuntimeError('Banco mais novo que o aplicativo ou migration alterada. Atualize/repare o pacote.')
            if fingerprint(cursor) != previous_hash:
                raise RuntimeError('A estrutura do banco mudou fora do instalador. Não serão aplicadas mudanças automáticas.')
            pending = [name for name in scripts if name not in applied]
            if pending and initialized:
                if backup is None:
                    raise RuntimeError('Atualização exige um backup verificado antes das migrations.')
                backup(config)
            cursor.execute("SET LOCAL lock_timeout='30s'")
            for name in pending:
                cursor.execute(transactional_sql(scripts[name]))
                cursor.execute('INSERT INTO mac_internal.schema_migrations(version,checksum) VALUES(%s,%s)', (name, expected[name]))
            cursor.execute('UPDATE mac_internal.installation SET schema_hash=%s WHERE singleton', (fingerprint(cursor),))
            connection.commit()
            return pending
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()  # Libera também o advisory lock de sessão.
