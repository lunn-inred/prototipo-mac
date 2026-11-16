"""Identidade/revisão das medidas de uma coleta, sem adicionar colunas SQL."""
import hashlib
import json


def revision(cursor, pair):
    cursor.execute("""SELECT v.id_medida_valor,upper(trim(m.nome)),v.valor,v.valor_texto,v.data
        FROM public.medida_valor v JOIN public.medida m USING(id_medida)
        JOIN public.grupo_medida g USING(id_grupo_medida)
        WHERE v.id_atleta=%s AND v.data::date=%s AND lower(trim(g.nome))='termografia'
        ORDER BY v.id_medida_valor""", pair)
    rows = cursor.fetchall()
    # IDs mudam legitimamente na restauração de backups; compare conteúdo lógico.
    values = sorted(((str(row[1]), None if row[2] is None else float(row[2]), row[3], str(row[4])) for row in rows), key=repr)
    return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest(), bool(rows)


def delete(cursor, pair):
    cursor.execute("""DELETE FROM public.medida_valor v USING public.medida m, public.grupo_medida g
        WHERE v.id_medida=m.id_medida AND m.id_grupo_medida=g.id_grupo_medida
        AND lower(trim(g.nome))='termografia' AND v.id_atleta=%s AND v.data::date=%s""", pair)
