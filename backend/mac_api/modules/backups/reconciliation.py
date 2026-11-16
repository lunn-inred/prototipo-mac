"""Preserva medidas e referências SQL das análises locais mantidas."""
from psycopg2 import sql
from .database_snapshot import columns


def _read(cursor, table, names, values):
    where = sql.SQL(' AND ').join(sql.SQL('{}=%s').format(sql.Identifier(name)) for name in names)
    cursor.execute(sql.SQL('SELECT * FROM public.{} WHERE {}').format(sql.Identifier(table), where), tuple(values))
    row = cursor.fetchone()
    return dict(zip([field.name for field in cursor.description], row)) if row else None


def _insert(cursor, state, table, record, *, omit=(), returning=None):
    names = [name for name in columns(state, table) if name not in omit]
    command = sql.SQL('INSERT INTO public.{} ({}) OVERRIDING SYSTEM VALUE VALUES ({})').format(
        sql.Identifier(table), sql.SQL(',').join(map(sql.Identifier, names)), sql.SQL(',').join(sql.Placeholder() for _ in names))
    if returning:
        command += sql.SQL(' RETURNING {}').format(sql.Identifier(returning))
    cursor.execute(command, tuple(record[name] for name in names))
    return cursor.fetchone()[0] if returning else None


def capture(cursor, state, retained, draft_athletes=()):
    parents, collections, definitions = {}, {}, {}
    def parent(table, names, values):
        key = (table, tuple(names), tuple(values))
        if key in parents:
            return
        record = _read(cursor, table, names, values)
        if record is None:
            raise ValueError('Análise local sem cadastro/referência correspondente no banco. Revise antes de restaurar.')
        parents[key] = record
        for fk in state['foreign_keys']:
            if fk['child'] == table:
                values = [record[name] for name in fk['columns']]
                if all(value is not None for value in values):
                    parent(fk['parent'], fk['references'], values)
    for athlete_id in sorted(set(draft_athletes)):
        parent('atleta', ['id_atleta'], [athlete_id])
    for entry in retained:
        athlete_id, day = entry['pair']
        parent('atleta', ['id_atleta'], [athlete_id])
        cursor.execute("""SELECT v.*,m.nome AS backup_measure_name FROM public.medida_valor v
            JOIN public.medida m USING(id_medida) JOIN public.grupo_medida g USING(id_grupo_medida)
            WHERE v.id_atleta=%s AND v.data::date=%s AND lower(trim(g.nome))='termografia'""", (athlete_id, day))
        fields = [field.name for field in cursor.description]
        records = [dict(zip(fields, row)) for row in cursor.fetchall()]
        collections[entry['pair']] = records
        for record in records:
            measure_id = record['id_medida']
            definition = _read(cursor, 'medida', ['id_medida'], [measure_id])
            group = _read(cursor, 'grupo_medida', ['id_grupo_medida'], [definition['id_grupo_medida']])
            definitions[measure_id] = (definition, group)
            for fk in state['foreign_keys']:
                if fk['child'] == 'medida_valor' and fk['parent'] not in ('medida', 'atleta'):
                    values = [record[name] for name in fk['columns']]
                    if all(value is not None for value in values):
                        parent(fk['parent'], fk['references'], values)
    return dict(parents=parents, collections=collections, definitions=definitions)


def apply(cursor, state, kept, remote):
    visiting, done = set(), set()
    def parent(key):
        if key in done:
            return
        if key in visiting:
            raise ValueError('Referências locais circulares: reconciliação recusada.')
        visiting.add(key)
        table, names, values = key
        old = kept['parents'][key]
        current = _read(cursor, table, names, values)
        if current:
            if table == 'atleta':
                # Não inferir que dois atletas com o mesmo ID e nomes distintos são a mesma pessoa.
                if (str(current.get('nome', '')).strip().casefold() != str(old.get('nome', '')).strip().casefold()
                        or (current.get('data_nascimento') and old.get('data_nascimento')
                            and current['data_nascimento'] != old['data_nascimento'])):
                    raise ValueError('ID de atleta associado a nomes diferentes no local e no backup. Revise o conflito antes de restaurar.')
            elif current != old:
                raise ValueError('Uma referência local tem o mesmo ID e conteúdo diferente no backup. Reconciliação recusada.')
        else:
            for fk in state['foreign_keys']:
                if fk['child'] == table:
                    values = tuple(old[name] for name in fk['columns'])
                    if all(value is not None for value in values):
                        parent((fk['parent'], tuple(fk['references']), values))
            _insert(cursor, state, table, old)
        done.add(key)
        visiting.remove(key)
    for key in kept['parents']:
        parent(key)
    mapping = {}
    for old_id, (definition, group) in kept['definitions'].items():
        cursor.execute('SELECT id_grupo_medida FROM public.grupo_medida WHERE lower(trim(nome))=lower(trim(%s))', (group['nome'],))
        candidates = cursor.fetchall()
        if len(candidates) > 1:
            raise ValueError('Grupo de medida ambíguo no backup.')
        if candidates:
            group_id = candidates[0][0]
        else:
            # Views legadas podem referenciar o ID do grupo, não somente seu nome.
            if _read(cursor, 'grupo_medida', ['id_grupo_medida'], [group['id_grupo_medida']]):
                raise ValueError('ID do grupo térmico ocupado por outro grupo no backup. Revise antes de restaurar.')
            group_id = _insert(cursor, state, 'grupo_medida', group, returning='id_grupo_medida')
        cursor.execute('SELECT id_medida FROM public.medida WHERE id_grupo_medida=%s AND upper(trim(nome))=upper(trim(%s))', (group_id, definition['nome']))
        candidates = cursor.fetchall()
        if len(candidates) > 1:
            raise ValueError('Medida ambígua no backup.')
        mapping[old_id] = candidates[0][0] if candidates else _insert(cursor, state, 'medida',
            {**definition, 'id_grupo_medida': group_id}, omit=('id_medida',), returning='id_medida')
    # Se uma versão local foi movida, eliminar também as medidas da localização antiga do backup.
    remove_pairs = {pair for pair, records in kept['collections'].items() if records} | kept.get('obsolete_pairs', set())
    for identity in remote:
        if identity in kept.get('ids', set()):
            here = kept['entries'][identity]
            if here['hashes'] != remote[identity]['hashes']:
                remove_pairs.update(pair for pair in (remote[identity]['pair'], here['pair']) if pair)
    for athlete_id, day in remove_pairs:
        cursor.execute("""DELETE FROM public.medida_valor v USING public.medida m,public.grupo_medida g
            WHERE v.id_medida=m.id_medida AND m.id_grupo_medida=g.id_grupo_medida
            AND lower(trim(g.nome))='termografia' AND v.id_atleta=%s AND v.data::date=%s""", (athlete_id, day))
    for records in kept['collections'].values():
        for record in records:
            _insert(cursor, state, 'medida_valor', {**record, 'id_medida': mapping[record['id_medida']]}, omit=('id_medida_valor',))
