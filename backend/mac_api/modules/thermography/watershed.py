"""Watershed segmentation of upright rainbow-palette thermograms.

Camera annotations are suppressed only in a processing copy. RGB values used
by temperature_matrix are never modified. Anatomical laterality is assigned
by the caller; the pair returned here follows left-to-right image position.
"""
import cv2
import numpy as np


ALGORITHM_VERSION = 'thermal-rgb-watershed-v2'


def largest(mask):
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype('uint8'))
    if count < 2:
        return np.zeros(mask.shape, dtype=bool)
    return labels == (1 + np.argmax(stats[1:, cv2.CC_STAT_AREA]))


def mask_box(mask):
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise ValueError('A segmentação não encontrou pixels da perna.')
    return dict(left=int(xs.min()), top=int(ys.min()),
                width=int(xs.max()-xs.min()+1), height=int(ys.max()-ys.min()+1))


def prepare(image):
    rgb = np.asarray(image.convert('RGB'))
    if min(rgb.shape[:2]) < 16:
        raise ValueError('A imagem é pequena demais para segmentar as pernas.')
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    white = ((hsv[..., 1] < 45) & (hsv[..., 2] > 190)).astype('uint8')
    broad = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((7, 7), 'uint8'))
    thin = white & ~cv2.dilate(broad, np.ones((3, 3), 'uint8'))
    clean = cv2.inpaint(rgb, cv2.dilate(thin, np.ones((3, 3), 'uint8'))*255,
                       3, cv2.INPAINT_TELEA)
    hsv = cv2.cvtColor(clean, cv2.COLOR_RGB2HSV)
    # Red spans BOTH ends of OpenCV's circular hue interval, 0..179.
    colored = ((hsv[..., 0] < 110) | (hsv[..., 0] >= 175)) & (hsv[..., 1] > 60) & (hsv[..., 2] > 55)
    hot_white = (hsv[..., 1] < 75) & (hsv[..., 2] > 185)
    candidate = (colored | hot_white).astype('uint8')
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_OPEN, np.ones((3, 3), 'uint8'))
    candidate = cv2.morphologyEx(candidate, cv2.MORPH_CLOSE, np.ones((5, 5), 'uint8'))
    # Neutral backgrounds may be dark gray OR brighter than the hot-white rule.
    # Only broad neutral components connected to the image perimeter are
    # background; isolated white hot regions inside a limb remain candidates.
    neutral = cv2.morphologyEx((hsv[..., 1] < 45).astype('uint8'), cv2.MORPH_OPEN,
                              np.ones((3, 3), 'uint8'))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(neutral)
    edge_labels = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1])))
    exterior = [label for label in edge_labels if label and stats[label, cv2.CC_STAT_AREA] >= candidate.size*.01]
    if exterior:
        candidate[np.isin(labels, exterior)] = 0
    return clean, hsv, candidate


def grow(clean, sides):
    support = np.logical_or.reduce(sides).astype('uint8')
    expanded = cv2.dilate(support, np.ones((5, 5), 'uint8'))
    markers = np.zeros(support.shape, 'int32')
    markers[expanded == 0] = 1
    # Always reserve the image perimeter for the background label.
    markers[[0, -1], :] = 1
    markers[:, [0, -1]] = 1
    for i, side in enumerate(sides):
        core = cv2.erode(side.astype('uint8'), np.ones((7, 7), 'uint8'))
        if not core.any():
            raise ValueError('A região da perna é pequena demais para segmentar.')
        markers[core > 0] = i+2
    cv2.watershed(cv2.cvtColor(clean, cv2.COLOR_RGB2BGR), markers)
    return [largest((markers == i+2) & (expanded > 0)) for i in range(len(sides))]


def segment_pair(image):
    """Return full-resolution image-left/image-right masks without R1/R2."""
    clean, _, candidate = prepare(image)
    h, w = candidate.shape
    # Find a continuous non-body corridor, not a particular background hue.
    # Keep this before geometric clipping so the clipped margins cannot create
    # artificial evidence of a gap. Bilateral thermal support is checked below.
    background = candidate == 0
    candidate[:int(.1*h)] = 0
    candidate[int(.94*h):] = 0
    candidate[:, :int(.06*w)] = 0
    candidate[:, int(.96*w):] = 0
    choices = []
    for x in range(int(.35*w), int(.66*w)):
        for y in range(int(.18*h), int(.56*h)):
            depth = max(1, int(.10*h))
            gap_depth = max(1, int(.20*h))
            if background[y:y+gap_depth, x].mean() < .95:
                continue
            band = candidate[y:y+depth]
            left = band[:, max(0, x-int(.30*w)):x-max(1, int(.02*w))].mean()
            right = band[:, x+max(1, int(.02*w)):min(w, x+int(.30*w))].mean()
            if min(left, right) > .22:
                choices.append((y, abs(x-w*.5), x))
                break
    if not choices:
        raise ValueError('Não foi possível separar as duas pernas. Gire a imagem para deixar '
                         'os pés para baixo ou delimite as duas pernas em Ajustar regiões.')
    crotch, _, center = min(choices)
    top = max(int(.12*h), crotch-int(.055*h))
    candidate[:top] = 0
    _, xx = np.indices(candidate.shape)
    sides = [largest(candidate.astype(bool) & (xx < center)),
             largest(candidate.astype(bool) & (xx >= center))]
    masks = grow(clean, sides)
    for mask in masks:
        mask[:top] = False
        if int(mask.sum()) < h*w*.02:
            raise ValueError('Uma das pernas ficou pequena demais. Confira a orientação '
                             'ou delimite as duas pernas em Ajustar regiões.')
    return masks


def validate_seeds(seeds, shape):
    if seeds is None:
        return None
    seeds = np.asarray(seeds)
    if seeds.shape != shape or not np.isin(seeds, (-1, 0, 1)).all():
        raise ValueError('A máscara de correção deve ter as dimensões da imagem e valores -1, 0 ou 1.')
    return seeds


def correct_mask(mask, seeds):
    result = mask.copy()
    seeds = validate_seeds(seeds, result.shape)
    if seeds is not None:
        result[seeds < 0] = False
        result[seeds > 0] = True
    if not result.any():
        raise ValueError('A segmentação não encontrou pixels da perna.')
    return result


def segment_region(image, box, seeds=None):
    """Explicit manual-region recovery, independent of pair/gap detection."""
    clean, _, candidate = prepare(image)
    h, w = candidate.shape
    try:
        values = [box[k] for k in ('left', 'top', 'width', 'height')]
        if any(not isinstance(v, (int, float)) or not np.isfinite(v) or int(v) != v for v in values):
            raise ValueError
        x, y, bw, bh = map(int, values)
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ValueError('Coordenadas de região inválidas.') from None
    if x < 0 or y < 0 or bw <= 0 or bh <= 0 or x+bw > w or y+bh > h:
        raise ValueError('A região deve ter área positiva e estar dentro da imagem.')
    inside = np.zeros((h, w), bool)
    inside[y:y+bh, x:x+bw] = True
    seed = validate_seeds(seeds, inside.shape)
    if seed is not None and np.any((seed > 0) & ~inside):
        raise ValueError('A inclusão manual ultrapassa a região da perna.')
    support = candidate.astype(bool) & inside
    if seed is not None:
        support[seed < 0] = False
        support[seed > 0] = True
    if support.any():
        mask = grow(clean, [largest(support)])[0] & inside
    else:
        mask = np.zeros((h, w), bool)
    return correct_mask(mask, seed)
