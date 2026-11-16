"""Contagens consolidadas por zona nas regiões da planilha de termogramas."""
from .thermal_analysis import leg_part_metrics

ZONES = {'cold': 'FRIA', 'neutral': 'NEUTRA', 'hot': 'QUENTE'}
REGIONS = {'coxa': 'COXA', 'joelho': 'JOELHO', 'canela': 'CANELA', 'pe': 'PE'}
SIDES = {'right': 'DIREITA', 'left': 'ESQUERDA'}
VIEWS = {'front': 'FRENTE', 'back': 'VERSO'}
REGIONAL_ZONE_MEASURES = frozenset(
    f'{region}_{side}_{view}_ZONA_{zone}'
    for region in REGIONS.values() for side in SIDES.values()
    for view in VIEWS.values() for zone in ZONES.values()
)


def preview_regional_zones(views, include_totals=False):
    """Prévia sem escrita, usando a mesma validação e cálculo do registro."""
    from .analysis_archive import _validate_view
    if set(views) != {'front', 'back'}:
        raise ValueError('Informe as imagens de frente e costas.')
    measurements = regional_zone_measurements({view: _validate_view(source) for view, source in views.items()})
    if not include_totals:
        return measurements
    totals = {view: {
        zone: sum(measurements[f'{region}_{side}_{view}_ZONA_{zone}']
                  for region in REGIONS.values() for side in SIDES.values())
        for zone in ZONES.values()
    } for view in VIEWS.values()}
    return {'measurements': measurements, 'totals': totals}


def regional_zone_measurements(validated_views):
    """Use matrizes float32 e divisões validadas, sem confiar em resumos da UI.

    Cada uma das quatro regiões anatômicas tem suas próprias contagens.
    As faixas são as mesmas do assistente, inclusive fora de 28–36 °C.
    """
    measurements = {}
    for view, (_, temperatures, masks, metadata) in validated_views.items():
        for side, mask in masks.items():
            settings = metadata['part_settings'][side]
            for zone, zone_label in ZONES.items():
                parts, _ = leg_part_metrics(
                    temperatures, mask, metadata['default_threshold'],
                    tuple(settings['cuts']), axis='vertical',
                    region_box=metadata['boxes'][side], thermal_zone=zone,
                )
                for part, region_label in REGIONS.items():
                    name = f'{region_label}_{SIDES[side]}_{VIEWS[view]}_ZONA_{zone_label}'
                    measurements[name] = parts[part]['hot_pixels']
    return measurements
