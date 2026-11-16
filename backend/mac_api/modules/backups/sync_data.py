"""Mesclagem em três vias: nunca escolhe um vencedor pelo relógio do computador."""
import hashlib
import json
from psycopg2 import sql
from . import database_snapshot as db

FORMAT = 'mac-sync-v1'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def merge(base, local, remote, *, scope):
    """Ausência após a primeira sincronização representa exclusão, não esquecimento."""
    result, conflicts = {}, []
    for key in sorted(set(base) | set(local) | set(remote)):
        old, here, there = base.get(key), local.get(key), remote.get(key)
        if here == there or there == old:
            winner = here
        elif here == old:
            winner = there
        else:
            conflicts.append(key)
            continue
        if winner is not None:
            result[key] = winner
    if conflicts:
        # Somente identificadores: nomes/dados pessoais não devem ir para logs.
        raise ValueError(f'Conflito de sincronização em {scope}: {len(conflicts)} registro(s), '
                         f'identificadores {", ".join(conflicts[:5])}. Nenhum vencedor foi escolhido. '
                         'Revise as duas cópias antes de sincronizar novamente.')
    return result


def capture(cursor):
    db.configure(cursor)
    schema = db.schema(cursor)
    db.ordered_tables(schema)
    cursor.execute("""SELECT c.relname, ARRAY(SELECT a.attname
        FROM unnest(i.indkey) WITH ORDINALITY k(num,ord)
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.num ORDER BY k.ord)
        FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE i.indisprimary AND n.nspname='public' ORDER BY c.relname""")
    keys = dict(cursor.fetchall())
    if set(keys) != set(schema['tables']):
        raise ValueError('Sincronização exige chave primária em todas as tabelas public. '
                         'Atualize a estrutura por migração antes de continuar.')
    tables = {}
    for table in db.ordered_tables(schema):
        names = db.columns(schema, table)
        # Texto PostgreSQL preserva precisão de numeric, timestamps, arrays e bytea.
        fields = sql.SQL(',').join(sql.SQL('{}::text').format(sql.Identifier(name)) for name in names)
        cursor.execute(sql.SQL('SELECT {} FROM public.{}').format(fields, sql.Identifier(table)))
        rows = {}
        for values in cursor.fetchall():
            row = dict(zip(names, values))
            identity = canonical([row[name] for name in keys[table]])
            rows[identity] = row
        tables[table] = rows
    sequences = {}
    for name, *_ in schema['sequences']:
        cursor.execute(sql.SQL('SELECT last_value,is_called FROM public.{}').format(sql.Identifier(name)))
        sequences[name] = list(cursor.fetchone())
    return dict(schema=schema, schema_version=fingerprint(schema), keys=keys, tables=tables,
                sequence_values=sequences)


def validate(snapshot, reference):
    if (snapshot.get('schema') != reference['schema'] or snapshot.get('keys') != reference['keys']
            or snapshot.get('schema_version') != reference['schema_version']):
        raise ValueError('Estrutura incompatível entre instalações (tabelas, views ou demais contratos). '
                         'Atualize o aplicativo e aplique as migrações locais antes de sincronizar. '
                         'SQL recebido do Drive nunca é executado.')
    if set(snapshot.get('tables', {})) != set(reference['tables']):
        raise ValueError('Índice de tabelas da sincronização inválido.')
    for table, rows in snapshot['tables'].items():
        names = set(db.columns(reference['schema'], table))
        for identity, row in rows.items():
            if (set(row) != names or any(v is not None and not isinstance(v, str) for v in row.values())
                    or identity != canonical([row[k] for k in reference['keys'][table]])):
                raise ValueError('Registro inválido no índice de sincronização.')


def merge_database(base, local, remote):
    validate(remote, local)
    if base:
        validate(base, local)
    result = {**local, 'tables': {}}
    for table in local['tables']:
        result['tables'][table] = merge((base or {}).get('tables', {}).get(table, {}),
            local['tables'][table], remote['tables'][table], scope=f'tabela {table}')
    result['sequence_values'] = {name: max(local['sequence_values'][name], remote['sequence_values'][name])
                                 for name in local['sequence_values']}
    return result


def apply(cursor, local, merged):
    """INSERT/UPDATE/DELETE somente dos registros alterados; sem TRUNCATE."""
    state = local['schema']
    order = db.ordered_tables(state)
    for table in order:
        names = db.columns(state, table)
        types = {c['name']: c['type'] for c in state['tables'][table]}
        primary = local['keys'][table]
        for identity, row in merged['tables'][table].items():
            old = local['tables'][table].get(identity)
            if old == row:
                continue
            if old is None:
                # Os tipos vêm exclusivamente do esquema LOCAL já conferido.
                command = sql.SQL('INSERT INTO public.{} ({}) OVERRIDING SYSTEM VALUE VALUES ({})').format(
                    sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, names)),
                    sql.SQL(',').join(sql.SQL('%s::{}').format(sql.SQL(types[n])) for n in names))
                cursor.execute(command, [row[n] for n in names])
            else:
                columns = [n for n in names if n not in primary]
                if not columns:
                    continue
                command = sql.SQL('UPDATE public.{} SET {} WHERE {}').format(sql.Identifier(table),
                    sql.SQL(',').join(sql.SQL('{}=%s::{}').format(sql.Identifier(n), sql.SQL(types[n])) for n in columns),
                    sql.SQL(' AND ').join(sql.SQL('{}=%s::{}').format(sql.Identifier(n), sql.SQL(types[n])) for n in primary))
                cursor.execute(command, [row[n] for n in columns + primary])
    for table in reversed(order):
        for identity in local['tables'][table].keys() - merged['tables'][table].keys():
            row = local['tables'][table][identity]
            types = {c['name']: c['type'] for c in state['tables'][table]}
            primary = local['keys'][table]
            cursor.execute(sql.SQL('DELETE FROM public.{} WHERE {}').format(sql.Identifier(table),
                sql.SQL(' AND ').join(sql.SQL('{}=%s::{}').format(sql.Identifier(n), sql.SQL(types[n])) for n in primary)),
                [row[n] for n in primary])
    db.reset_sequences(cursor, merged)
    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
