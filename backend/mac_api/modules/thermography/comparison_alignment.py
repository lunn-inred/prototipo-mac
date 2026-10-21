"""Approximate anatomical registration onto the saved basal leg geometry.

This is not optical flow or a clinical anatomical registration: user-defined
part boundaries and segmented row spans establish the correspondence.
"""
import cv2
import numpy as np


def _leg(source, side):
    temperatures = np.asarray(source['temperatures'], dtype=np.float64)
    mask = np.asarray(source['segmentation_masks'][side], dtype=bool)
    if temperatures.ndim != 2 or mask.shape != temperatures.shape:
        raise ValueError('A máscara e a matriz térmica devem ter as mesmas dimensões.')
    box = source['boxes'][side]
    x, y, width, height = (int(box[key]) for key in ('left', 'top', 'width', 'height'))
    if x < 0 or y < 0 or width < 1 or height < 1 or x + width > temperatures.shape[1] or y + height > temperatures.shape[0]:
        raise ValueError('Caixa da perna fora da matriz térmica.')
    settings = source.get('part_settings', {}).get(side, {})
    axis = settings.get('axis', 'vertical')
    cuts = np.asarray(settings.get('cuts', (45, 57, 88)), dtype=float)
    if axis not in ('vertical', 'horizontal') or cuts.shape != (3,) or not np.isfinite(cuts).all() or not 0 < cuts[0] < cuts[1] < cuts[2] < 100:
        raise ValueError('Divisões anatômicas inválidas.')
    reverse = not settings.get('foot_at_end', True)
    values = temperatures[y:y + height, x:x + width]
    support = mask[y:y + height, x:x + width]
    if axis == 'horizontal':
        values, support = values.T, support.T
    if reverse:
        values, support = values[::-1], support[::-1]
    boundaries = [0, *(round(values.shape[0] * cut / 100) for cut in cuts), values.shape[0]]
    return values, support, boundaries, axis, reverse


def align_leg_to_baseline(baseline, current, side):
    """Map each current anatomical region into the corresponding basal region.

    Y is mapped separately within coxa/joelho/canela/pé. X follows each row's
    segmented span. Holes, missing rows and missing regions remain invalid;
    no nearest-region filling is performed. The basal mask is never deformed.
    """
    base, base_mask, base_parts, axis, reverse = _leg(baseline, side)
    values, mask, parts, _, _ = _leg(current, side)
    valid = mask & np.isfinite(values)
    base_valid = base_mask & np.isfinite(base)
    # Identical coordinates and identical masks/fields do not need resampling.
    # In particular a mask-only edit must not create temperature differences.
    identity = (base.shape == values.shape and base_parts == parts
                and (np.array_equal(base_mask, mask) or np.array_equal(base, values, equal_nan=True)))
    if identity:
        aligned = np.where(base_valid & valid, values, np.nan)
    else:
        map_x = np.full(base.shape, -1, dtype=np.float32)
        map_y = np.full(base.shape, -1, dtype=np.float32)
        for b0, b1, c0, c1 in zip(base_parts[:-1], base_parts[1:], parts[:-1], parts[1:]):
            if b1 <= b0 or c1 <= c0:
                continue
            for row in range(b0, b1):
                columns = np.flatnonzero(base_valid[row])
                if not columns.size:
                    continue
                target_y = np.clip(c0 + (row - b0 + .5) * (c1 - c0) / (b1 - b0) - .5, c0, c1 - 1)
                current_columns = np.flatnonzero(valid[int(np.rint(target_y))])
                if not current_columns.size:
                    continue
                left, right = columns[0], columns[-1]
                first, last = current_columns[0], current_columns[-1]
                fraction = (columns - left + .5) / (right - left + 1)
                map_x[row, columns] = np.clip(first + fraction * (last - first + 1) - .5, first, last)
                map_y[row, columns] = target_y
        weights = cv2.remap(valid.astype(np.float64), map_x, map_y, cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        sampled = cv2.remap(np.where(valid, values, 0), map_x, map_y, cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        support = cv2.remap(valid.astype(np.uint8), map_x, map_y, cv2.INTER_NEAREST,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0).astype(bool)
        aligned = np.divide(sampled, weights, out=np.full(base.shape, np.nan),
                            where=base_valid & support & (weights > 0))
    # Return in the original basal image orientation, not in current geometry.
    def restore(array):
        if reverse:
            array = array[::-1]
        return array.T if axis == 'horizontal' else array
    return restore(base), restore(aligned), restore(base_mask)


def fit_baseline_field(values, mask, canvas_size):
    """Display a field on the basal crop, preserving aspect and invalid pixels."""
    width, height = canvas_size
    if width <= 0 or height <= 0:
        raise ValueError('As dimensões do mapa comparativo devem ser positivas.')
    scale = min(width / values.shape[1], height / values.shape[0])
    size = (max(1, round(values.shape[1] * scale)), max(1, round(values.shape[0] * scale)))
    valid = mask & np.isfinite(values)
    weights = cv2.resize(valid.astype(float), size, interpolation=cv2.INTER_LINEAR)
    sampled = cv2.resize(np.where(valid, values, 0.0), size, interpolation=cv2.INTER_LINEAR)
    sampled = np.divide(sampled, weights, out=np.zeros_like(sampled), where=weights > 0)
    support = cv2.resize(valid.astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool)
    canvas = np.full((height, width), np.nan)
    x, y = (width - size[0]) // 2, (height - size[1]) // 2
    canvas[y:y + size[1], x:x + size[0]] = np.where(support & (weights > 0), sampled, np.nan)
    return canvas
