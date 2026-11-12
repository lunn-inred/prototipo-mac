"""Dump lógico CSV do public; restaura dados somente em esquema compatível.

Não executa SQL vindo do backup, não exige pg_dump instalado e não altera schema.
"""
import json
from psycopg2 import sql


def configure(cursor):
    cursor.execute("SET LOCAL lock_timeout='30s'")
    cursor.execute('SET LOCAL row_security=off')
    cursor.execute("SET LOCAL TIME ZONE 'UTC'")
    cursor.execute("SET LOCAL DateStyle TO 'ISO, YMD'")
    cursor.execute('SET LOCAL extra_float_digits=3')
    cursor.execute('SET LOCAL search_path TO public, pg_catalog')


def schema(cursor):
    cursor.execute("""SELECT c.relname, a.attname, format_type(a.atttypid,a.atttypmod),
        a.attnotnull, a.attidentity, a.attgenerated, pg_get_expr(d.adbin,d.adrelid)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum
        WHERE n.nspname='public' AND c.relkind='r' AND NOT c.relispartition
        ORDER BY c.relname,a.attnum""")
    tables = {}
    for table, name, kind, required, identity, generated, default in cursor.fetchall():
        tables.setdefault(table, []).append(dict(name=name, type=kind, required=required,
                                                identity=identity, generated=generated, default=default))
    cursor.execute("""SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND (c.relkind IN ('p','f','m') OR c.relispartition)""")
    if cursor.fetchall():
        raise ValueError('Backup desta versão não suporta tabelas particionadas, estrangeiras ou views materializadas no public.')
    cursor.execute("""SELECT c.relname,con.conname,pg_get_constraintdef(con.oid,true)
        FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
        WHERE con.connamespace='public'::regnamespace ORDER BY 1,2""")
    constraints = [list(row) for row in cursor.fetchall()]
    cursor.execute("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1,2")
    indexes = [list(row) for row in cursor.fetchall()]
    cursor.execute("""SELECT c.relname, pg_get_viewdef(c.oid,true) FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='v' ORDER BY 1""")
    views = [list(row) for row in cursor.fetchall()]
    cursor.execute("""SELECT p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid)
        FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.prokind IN ('f','p') ORDER BY 1,2""")
    functions = [list(row) for row in cursor.fetchall()]
    cursor.execute("""SELECT c.relname,t.tgname,pg_get_triggerdef(t.oid,true) FROM pg_trigger t
        JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY 1,2""")
    triggers = [list(row) for row in cursor.fetchall()]
    cursor.execute("""SELECT c.relname,p.relname,pn.nspname,
        ARRAY(SELECT a.attname FROM unnest(con.conkey) WITH ORDINALITY k(num,ord)
              JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.num ORDER BY k.ord),
        ARRAY(SELECT a.attname FROM unnest(con.confkey) WITH ORDINALITY k(num,ord)
              JOIN pg_attribute a ON a.attrelid=p.oid AND a.attnum=k.num ORDER BY k.ord)
        FROM pg_constraint con JOIN pg_class c ON c.oid=con.conrelid
        JOIN pg_class p ON p.oid=con.confrelid JOIN pg_namespace pn ON pn.oid=p.relnamespace
        WHERE con.contype='f' AND con.connamespace='public'::regnamespace ORDER BY c.relname,con.conname""")
    foreign_keys = []
    for child, parent, namespace, columns, references in cursor.fetchall():
        if namespace != 'public':
            raise ValueError('Há vínculos fora do schema public. Restauração automática recusada.')
        foreign_keys.append(dict(child=child, parent=parent, columns=columns, references=references))
    cursor.execute("SELECT sequencename,start_value,min_value,max_value,increment_by,cycle FROM pg_sequences WHERE schemaname='public' ORDER BY 1")
    sequences = [list(row) for row in cursor.fetchall()]
    if any(row[4] <= 0 for row in sequences):
        raise ValueError('Sequências decrescentes não são suportadas nesta versão.')
    cursor.execute("""SELECT c.relname,a.attname,pg_get_serial_sequence(format('%I.%I',n.nspname,c.relname),a.attname)
        FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped
        WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname,a.attnum""")
    owners = [list(row) for row in cursor.fetchall() if row[2]]
    return dict(tables=tables, constraints=constraints, indexes=indexes, views=views, functions=functions, triggers=triggers,
                foreign_keys=foreign_keys, sequences=sequences, owners=owners)


def columns(state, table):
    return [column['name'] for column in state['tables'][table] if not column['generated']]


def ordered_tables(state):
    pending = set(state['tables'])
    order = []
    while pending:
        ready = sorted(table for table in pending if not any(
            fk['child'] == table and fk['parent'] in pending and fk['parent'] != table
            for fk in state['foreign_keys']))
        if not ready:
            raise ValueError('Referências circulares entre tabelas: restauração automática recusada.')
        order.extend(ready)
        pending.difference_update(ready)
    return order


def dump(cursor, directory):
    configure(cursor)
    state = schema(cursor)
    ordered_tables(state)
    directory.mkdir()
    sequence_values = {}
    counts = {}
    for index, table in enumerate(sorted(state['tables'])):
        names = sql.SQL(',').join(map(sql.Identifier, columns(state, table)))
        command = sql.SQL("COPY public.{} ({}) TO STDOUT WITH (FORMAT CSV, ENCODING 'UTF8')").format(sql.Identifier(table), names)
        with (directory / f'{index}.csv').open('wb') as output:
            cursor.copy_expert(command.as_string(cursor.connection), output)
        cursor.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(table)))
        counts[table] = cursor.fetchone()[0]
    for sequence, *_ in state['sequences']:
        cursor.execute(sql.SQL('SELECT last_value,is_called FROM public.{}').format(sql.Identifier(sequence)))
        sequence_values[sequence] = list(cursor.fetchone())
    result = dict(format=1, schema=state, rows=counts, sequence_values=sequence_values)
    (directory / 'database.json').write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
    return result


def reset_sequences(cursor, snapshot):
    state = snapshot['schema']
    for sequence, start, minimum, maximum, increment, cycle in state['sequences']:
        value, called = snapshot['sequence_values'][sequence]
        next_value = int(value) + increment if called else int(value)
        for table, column, owned in state['owners']:
            cursor.execute('SELECT %s::regclass = %s::regclass', (owned, f'public.{sql.Identifier(sequence).as_string(cursor.connection)}'))
            if cursor.fetchone()[0]:
                cursor.execute(sql.SQL('SELECT max({}) FROM public.{}').format(sql.Identifier(column), sql.Identifier(table)))
                highest = cursor.fetchone()[0]
                if highest is not None:
                    next_value = max(next_value, int(highest) + increment)
        if not minimum <= next_value <= maximum:
            raise ValueError('Sequência fora de intervalo; revise antes de restaurar.')
        # ALTER é transacional; setval não seria revertido em um rollback.
        cursor.execute(sql.SQL('ALTER SEQUENCE public.{} RESTART WITH {}').format(sql.Identifier(sequence), sql.Literal(next_value)))


def restore(cursor, directory, snapshot):
    configure(cursor)
    state = schema(cursor)
    if state != snapshot['schema']:
        raise ValueError('O esquema local difere do backup. Atualize o projeto/banco compatível antes de restaurar; nenhuma coluna será criada.')
    order = ordered_tables(state)
    if not order:
        raise ValueError('Backup sem tabelas do public.')
    cursor.execute(sql.SQL('TRUNCATE TABLE {} RESTART IDENTITY').format(
        sql.SQL(',').join(sql.SQL('public.{}').format(sql.Identifier(table)) for table in order)))
    for table in order:
        index = sorted(state['tables']).index(table)
        command = sql.SQL("COPY public.{} ({}) FROM STDIN WITH (FORMAT CSV, ENCODING 'UTF8')").format(
            sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, columns(state, table))))
        with (directory / f'{index}.csv').open('rb') as source:
            cursor.copy_expert(command.as_string(cursor.connection), source)
        cursor.execute(sql.SQL('SELECT count(*) FROM public.{}').format(sql.Identifier(table)))
        if cursor.fetchone()[0] != snapshot['rows'][table]:
            raise ValueError('Contagem de registros do backup incompatível.')
    reset_sequences(cursor, snapshot)
