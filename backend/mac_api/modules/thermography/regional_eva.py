"""EVA regional: IDs do diagrama e medidas da coleta, sem EVA geral armazenado."""
REGIONS = {'thigh': 'COXA', 'knee': 'JOELHO', 'lower-leg': 'CANELA', 'foot': 'PE'}
REGIONAL_EVA = {
    f'{view}-{region}-{side}': f'EVA_{label}_{side_label}_{view_label}'
    for view, view_label in (('front', 'FRENTE'), ('back', 'VERSO'))
    for region, label in REGIONS.items()
    for side, side_label in (('left', 'ESQUERDA'), ('right', 'DIREITA'))
}
REGIONAL_EVA_MEASURES = frozenset(REGIONAL_EVA.values())


def normalize_regional_eva(values):
    """None é avaliação ausente/antiga; mapa informado completa omissões com zero."""
    if values is None:
        return None
    if not isinstance(values, dict) or set(values) - REGIONAL_EVA.keys():
        raise ValueError('Região de EVA inválida.')
    if any(type(value) is not int or not 0 <= value <= 10 for value in values.values()):
        raise ValueError('EVA regional deve ser inteiro entre 0 e 10.')
    return {identifier: values.get(identifier, 0) for identifier in REGIONAL_EVA}


def eva_measurements(values):
    normalized = normalize_regional_eva(values)
    return {} if normalized is None else {REGIONAL_EVA[key]: value for key, value in normalized.items()}


def maximum_eva(values):
    normalized = normalize_regional_eva(values)
    return None if normalized is None else max(normalized.values())
