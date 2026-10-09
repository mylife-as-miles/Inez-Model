"""CC0 MakeHuman facial feature targets used by the v04 head refinement.

Shared by tools/inez/head_refine_fit.py (fitting, needs scipy) and
tools/inez/model_dress_v04.py (Blender build). Files live in
model/base-source/targets with provenance.json.
"""
from pathlib import Path

import numpy as np

from model_source import read_target

# Signed modifiers -> (decrease target, increase target). Symmetric pairs move together.
MODIFIERS = {
    'chin-height': ['chin/chin-height-decr', 'chin/chin-height-incr'],
    'chin-width': ['chin/chin-width-decr', 'chin/chin-width-incr'],
    'chin-jaw-drop': ['chin/chin-jaw-drop-decr', 'chin/chin-jaw-drop-incr'],
    'chin-bones': ['chin/chin-bones-decr', 'chin/chin-bones-incr'],
    'mouth-scale-horiz': ['mouth/mouth-scale-horiz-decr', 'mouth/mouth-scale-horiz-incr'],
    'mouth-scale-vert': ['mouth/mouth-scale-vert-decr', 'mouth/mouth-scale-vert-incr'],
    'mouth-trans-vert': ['mouth/mouth-trans-down', 'mouth/mouth-trans-up'],
    'mouth-lowerlip-height': ['mouth/mouth-lowerlip-height-decr', 'mouth/mouth-lowerlip-height-incr'],
    'mouth-upperlip-height': ['mouth/mouth-upperlip-height-decr', 'mouth/mouth-upperlip-height-incr'],
    'mouth-lowerlip-volume': ['mouth/mouth-lowerlip-volume-decr', 'mouth/mouth-lowerlip-volume-incr'],
    'mouth-upperlip-volume': ['mouth/mouth-upperlip-volume-decr', 'mouth/mouth-upperlip-volume-incr'],
    'mouth-lowerlip-width': ['mouth/mouth-lowerlip-width-decr', 'mouth/mouth-lowerlip-width-incr'],
    'mouth-upperlip-width': ['mouth/mouth-upperlip-width-decr', 'mouth/mouth-upperlip-width-incr'],
    'mouth-cupidsbow-width': ['mouth/mouth-cupidsbow-width-decr', 'mouth/mouth-cupidsbow-width-incr'],
    'nose-scale-horiz': ['nose/nose-scale-horiz-decr', 'nose/nose-scale-horiz-incr'],
    'nose-scale-vert': ['nose/nose-scale-vert-decr', 'nose/nose-scale-vert-incr'],
    'nose-nostrils-width': ['nose/nose-nostrils-width-decr', 'nose/nose-nostrils-width-incr'],
    'nose-point-width': ['nose/nose-point-width-decr', 'nose/nose-point-width-incr'],
    'nose-width1': ['nose/nose-width1-decr', 'nose/nose-width1-incr'],
    'nose-width2': ['nose/nose-width2-decr', 'nose/nose-width2-incr'],
    'nose-width3': ['nose/nose-width3-decr', 'nose/nose-width3-incr'],
    'nose-trans-vert': ['nose/nose-trans-down', 'nose/nose-trans-up'],
    'nose-base': ['nose/nose-base-down', 'nose/nose-base-up'],
    'head-scale-horiz': ['head/head-scale-horiz-decr', 'head/head-scale-horiz-incr'],
    'head-scale-vert': ['head/head-scale-vert-decr', 'head/head-scale-vert-incr'],
    'head-oval': [None, 'head/head-oval'],
    'head-round': [None, 'head/head-round'],
    'head-square': [None, 'head/head-square'],
    'head-triangular': [None, 'head/head-triangular'],
    'head-invertedtriangular': [None, 'head/head-invertedtriangular'],
    'head-fat': ['head/head-fat-decr', 'head/head-fat-incr'],
    'cheek-volume': [('cheek/l-cheek-volume-decr', 'cheek/r-cheek-volume-decr'), ('cheek/l-cheek-volume-incr', 'cheek/r-cheek-volume-incr')],
    'cheek-bones': [('cheek/l-cheek-bones-decr', 'cheek/r-cheek-bones-decr'), ('cheek/l-cheek-bones-incr', 'cheek/r-cheek-bones-incr')],
    'cheek-inner': [('cheek/l-cheek-inner-decr', 'cheek/r-cheek-inner-decr'), ('cheek/l-cheek-inner-incr', 'cheek/r-cheek-inner-incr')],
    'eye-height1': [('eyes/l-eye-height1-decr', 'eyes/r-eye-height1-decr'), ('eyes/l-eye-height1-incr', 'eyes/r-eye-height1-incr')],
    'eye-height2': [('eyes/l-eye-height2-decr', 'eyes/r-eye-height2-decr'), ('eyes/l-eye-height2-incr', 'eyes/r-eye-height2-incr')],
    'eye-corner1': [('eyes/l-eye-corner1-down', 'eyes/r-eye-corner1-down'), ('eyes/l-eye-corner1-up', 'eyes/r-eye-corner1-up')],
    'eye-corner2': [('eyes/l-eye-corner2-down', 'eyes/r-eye-corner2-down'), ('eyes/l-eye-corner2-up', 'eyes/r-eye-corner2-up')],
    'eye-scale': [('eyes/l-eye-scale-decr', 'eyes/r-eye-scale-decr'), ('eyes/l-eye-scale-incr', 'eyes/r-eye-scale-incr')],
}


def target_delta(directory, names, count):
    delta = np.zeros((count, 3))
    if names is None:
        return None
    if isinstance(names, str):
        names = (names,)
    for name in names:
        path = Path(directory)/(name.replace('/', '__')+'.target')
        for index, d in read_target(path).items():
            delta[index] += d
    return delta




# Procedural fields (fit_vertices-style compact ellipsoid controls, front
# faces only) for proportions MakeHuman targets do not isolate: a tapering jaw
# and lower cheeks without changing cheekbone volume. Weight 1 = listed delta.
FIELDS = {
    'jaw-narrow': [
        {'center': [0.60, 5.98, 0.55], 'radius': [0.34, 0.48, 0.62], 'delta': [-0.085, 0.0, 0.0], 'falloff': 'compact'},
        {'center': [-0.60, 5.98, 0.55], 'radius': [0.34, 0.48, 0.62], 'delta': [0.085, 0.0, 0.0], 'falloff': 'compact'}],
    'lower-cheek-narrow': [
        {'center': [0.64, 6.36, 0.80], 'radius': [0.30, 0.34, 0.55], 'delta': [-0.065, 0.0, 0.0], 'falloff': 'compact'},
        {'center': [-0.64, 6.36, 0.80], 'radius': [0.30, 0.34, 0.55], 'delta': [0.065, 0.0, 0.0], 'falloff': 'compact'}],
    'chin-taper': [
        {'center': [0.30, 5.82, 0.95], 'radius': [0.26, 0.30, 0.45], 'delta': [-0.045, -0.025, 0.0], 'falloff': 'compact'},
        {'center': [-0.30, 5.82, 0.95], 'radius': [0.26, 0.30, 0.45], 'delta': [0.045, -0.025, 0.0], 'falloff': 'compact'}],
}
FIELD_LIMIT_Y = (5.2, 6.9)  # never touch the eyes/brows or the neck base


def field_delta(points, name):
    from model_source import fit_vertices
    pts = [list(p) for p in points]
    moved = np.asarray(fit_vertices(pts, FIELDS[name]))
    delta = moved-np.asarray(points)
    y = np.asarray(points)[:, 1]
    delta[(y < FIELD_LIMIT_Y[0]) | (y > FIELD_LIMIT_Y[1])] = 0
    return delta


def refinement_delta(points, weights, target_dir):
    """Total refinement for {name: signed weight}: targets then fields."""
    points = np.asarray(points, float)
    total = np.zeros_like(points)
    for name, weight in weights.items():
        if name in MODIFIERS:
            lo, hi = MODIFIERS[name]
            delta = target_delta(target_dir, hi if weight > 0 else lo, len(points))
            if delta is not None:
                total += delta*abs(weight)
    for name, weight in weights.items():
        if name in FIELDS:
            total += field_delta(points+total, name)*weight
    return total
