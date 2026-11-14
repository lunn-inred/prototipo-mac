"""Display labels only; temperature selection is calculated by the API."""
ZONE_NAMES = {'cold': 'Zona fria', 'neutral': 'Zona neutra', 'hot': 'Zona quente'}
ZONE_BUTTONS = {'cold': 'Zona fria · < 31 °C', 'neutral': 'Zona neutra · 31–33 °C',
                'hot': 'Zona quente · ≥ 33 °C'}


def normalize_zone_selection(item):
    """Upgrade an incomplete session draft without dropping masks or edits."""
    zone = item.get('thermal_zone')
    if not isinstance(zone, str) or zone not in ZONE_NAMES:
        zone = 'hot'
        item['thermal_zone'] = zone
        item.pop('analysis_config', None)
    return zone


def zone_caption(analysis, zone):
    """Presentation metadata is optional; it must never break the draft UI."""
    label = analysis.get('zone_label')
    if isinstance(label, str) and label.strip():
        return label
    return ZONE_NAMES.get(zone, 'Zona quente')
