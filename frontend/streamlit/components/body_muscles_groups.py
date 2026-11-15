"""Agrupamento MAC: partes originais do SVG, sem alterar arquivos do fornecedor."""

PARTS = {
    'FRONT': {
        'coxa': ('Coxa', ('quads', 'adductors', 'hip-flexor')),
        'joelho': ('Joelho', ('knee',)),
        'canela': ('Canela', ('tibialis-anterior',)),
        'pe': ('Pé', ('foot',)),
    },
    'BACK': {
        'coxa': ('Coxa', ('hamstrings-lateral', 'hamstrings-medial')),
        'joelho': ('Joelho', ('knee-back',)),
        'canela': ('Canela', ('calves-gastroc-medial', 'calves-gastroc-lateral', 'calves-soleus')),
        'pe': ('Pé', ('foot-back',)),
    },
}


def custom_groups():
    groups = {}
    for view, parts in PARTS.items():
        for side, side_name in (('left', 'esquerda'), ('right', 'direita')):
            for part, (name, members) in parts.items():
                side_label = side_name if part in ('coxa', 'canela') else ('esquerdo' if side == 'left' else 'direito')
                identifier = f'{view.lower()}-{part}-{side}'
                groups[identifier] = dict(id=identifier, name=f'{name} {side_label} — {"frente" if view == "FRONT" else "costas"}',
                    view=view, side=side, members=[f'{member}-{side}' for member in members])
    return groups
