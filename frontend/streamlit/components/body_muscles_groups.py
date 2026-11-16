"""Agrupamento MAC: partes originais do SVG, sem alterar arquivos do fornecedor."""

PARTS = {
    'FRONT': {
        'thigh': ('Coxa', ('quads', 'adductors', 'hip-flexor')),
        'knee': ('Joelho', ('knee',)),
        'lower-leg': ('Canela', ('tibialis-anterior',)),
        'foot': ('Pé', ('foot',)),
    },
    'BACK': {
        'thigh': ('Coxa', ('hamstrings-lateral', 'hamstrings-medial')),
        'knee': ('Joelho', ('knee-back',)),
        'lower-leg': ('Canela', ('calves-gastroc-medial', 'calves-gastroc-lateral', 'calves-soleus')),
        'foot': ('Pé', ('foot-back',)),
    },
}


def custom_groups():
    groups = {}
    for view, parts in PARTS.items():
        for side, side_name in (('left', 'esquerda'), ('right', 'direita')):
            for part, (name, members) in parts.items():
                side_label = side_name if part in ('thigh', 'lower-leg') else ('esquerdo' if side == 'left' else 'direito')
                identifier = f'{view.lower()}-{part}-{side}'
                groups[identifier] = dict(id=identifier, name=f'{name} {side_label} — {"frente" if view == "FRONT" else "costas"}',
                    view=view, side=side, members=[f'{member}-{side}' for member in members])
    return groups
