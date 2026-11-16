"""Non-overlapping temperature zones; legacy threshold behavior stays available."""
import numpy as np

ZONE_LABELS = {'cold': 'Zona fria', 'neutral': 'Zona neutra', 'hot': 'Zona quente'}


def validate_zone(zone):
    if zone is not None and zone not in ZONE_LABELS:
        raise ValueError('Zona térmica inválida: use cold, neutral ou hot.')
    return zone


def selected_pixels(temperatures, threshold, thermal_zone=None):
    validate_zone(thermal_zone)
    finite = np.isfinite(temperatures)
    if thermal_zone == 'cold':
        return finite & (temperatures < 31)
    if thermal_zone == 'neutral':
        return finite & (temperatures >= 31) & (temperatures < 33)
    if thermal_zone == 'hot':
        return finite & (temperatures >= 33)
    return finite & (temperatures >= threshold)


def reference_threshold(minimum, maximum, threshold, thermal_zone=None):
    """Keep a compatible scalar for old archive/API fields, alongside zone metadata."""
    validate_zone(thermal_zone)
    if thermal_zone is None:
        return threshold
    value = minimum if thermal_zone == 'cold' else 31 if thermal_zone == 'neutral' else 33
    return float(np.clip(value, minimum, maximum))
