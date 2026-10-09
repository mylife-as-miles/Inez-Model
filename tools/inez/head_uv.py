"""Head material UV layout derived from the CC0 MakeHuman UV islands (no Blender).

MakeHuman packs the whole body into one 0-1 atlas, which leaves the face about
350 px wide in a 2K skin map. The head material reuses the existing head
islands unchanged in shape (no re-unwrap, so no new distortion) and only moves
them rigidly into their own 2:1 texture:

    main head island  rotated 90 deg (face upright), uniform scale
    eye sockets       same scale, stacked in the right strip
    mouth interior    0.7x scale (rarely visible), below the sockets

At 4096x2048 the face spans roughly 1100 px. The visible neck stays on the
body island/material (2K); the head/body boundary is MakeHuman's own UV seam
under the jaw.
"""
import numpy as np

HEAD_TEXTURE_SIZE = (4096, 2048)  # width, height of the desktop head maps
MARGIN_PX = 24
STRIP_PX = 520


def uv_islands(faces):
    """Island id per face from shared texcoord indices (union-find)."""
    count = 1+max(t for face in faces for _, t in face)
    parent = np.arange(count)

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root
    for face in faces:
        ts = [t for _, t in face]
        for t in ts[1:]:
            ra, rb = find(ts[0]), find(t)
            if ra != rb:
                parent[ra] = rb
    roots = [find(face[0][1]) for face in faces]
    _, ids = np.unique(roots, return_inverse=True)
    return ids


def head_islands(points, faces, head_weight):
    """Face indices of the head-material islands keyed by role."""
    points = np.asarray(points)
    ids = uv_islands(faces)
    islands = {}
    for k in np.unique(ids):
        members = np.flatnonzero(ids == k)
        verts = sorted({i for f in members for i, _ in faces[f]})
        if np.mean(head_weight[verts]) < 0.5:
            continue
        x = points[verts, 0]
        islands[k] = (members, float(x.mean()), len(members))
    if len(islands) != 4:
        raise RuntimeError(f'Expected 4 head islands (head, mouth, two sockets), found {len(islands)}')
    ordered = sorted(islands.values(), key=lambda item: -item[2])
    main, mouth = ordered[0][0], ordered[1][0]
    sockets = sorted(ordered[2:], key=lambda item: item[1])
    # Source x is the character's left (+x).
    return {'head_main': main, 'mouth_interior': mouth, 'eye_socket_R': sockets[0][0], 'eye_socket_L': sockets[1][0]}


def head_layout(texcoords, faces, islands, size=HEAD_TEXTURE_SIZE):
    """New texcoords for the head islands.

    Returns (texcoords_head, faces_head, placement) where faces_head lists the
    head faces with (vertex, new texcoord index) corners and texcoords_head are
    normalized 0-1 coordinates for a `size` (width, height) texture.
    """
    texcoords = np.asarray(texcoords, np.float64)
    W, H = size
    usable_w = W-STRIP_PX-2*MARGIN_PX

    def corners(members):
        return np.array(sorted({t for f in members for _, t in faces[f]}))
    main_t = corners(islands['head_main'])
    lo, hi = texcoords[main_t].min(0), texcoords[main_t].max(0)
    # 90 deg rotation (du, dv) -> (dv, -du): MakeHuman's head island has the
    # face running along +u (forehead to chin); this stands it upright.
    rotated_w, rotated_h = hi[1]-lo[1], hi[0]-lo[0]
    scale = min(usable_w/rotated_w, (H-2*MARGIN_PX)/rotated_h)
    placement = {}
    new_uv = {}

    def place(name, members, rotate, island_scale, origin_px):
        ts = corners(members)
        c = texcoords[ts]
        a, b = c.min(0), c.max(0)
        # Pixel rows run downward, so orientation-preserving maps are
        # rotated: (u, v) -> (v, -u) in UV space; unrotated: identity.
        if rotate:
            px = np.stack((c[:, 1]-a[1], c[:, 0]-a[0]), axis=1)*island_scale
        else:
            px = np.stack((c[:, 0]-a[0], b[1]-c[:, 1]), axis=1)*island_scale
        px += np.asarray(origin_px, float)
        for t, p in zip(ts, px):
            new_uv[(name, int(t))] = (p[0]/W, p[1]/H)
        placement[name] = {'rotated': rotate, 'px_per_atlas_unit': island_scale,
                           'bbox_px': [float(px[:, 0].min()), float(px[:, 1].min()), float(px[:, 0].max()), float(px[:, 1].max())]}
        return px[:, 0].max()-px[:, 0].min(), px[:, 1].max()-px[:, 1].min()
    place('head_main', islands['head_main'], True, scale, (MARGIN_PX, MARGIN_PX))
    x0 = W-STRIP_PX-MARGIN_PX/2
    y = MARGIN_PX
    for name in ('eye_socket_R', 'eye_socket_L'):
        _, h = place(name, islands[name], False, scale, (x0, y))
        y += h+MARGIN_PX
    mouth_t = corners(islands['mouth_interior'])
    span = texcoords[mouth_t].max(0)-texcoords[mouth_t].min(0)
    mouth_scale = min(scale*0.7, (STRIP_PX-MARGIN_PX)/span[1], (H-y-MARGIN_PX)/span[0])
    place('mouth_interior', islands['mouth_interior'], True, mouth_scale, (x0, y))
    texcoords_head, index, faces_head, face_ids = [], {}, [], []
    for name, members in islands.items():
        for f in members:
            corners_new = []
            for v, t in faces[f]:
                key = (name, int(t))
                if key not in index:
                    index[key] = len(texcoords_head)
                    u, vv = new_uv[key]
                    # Image rows run downward; UV v runs upward.
                    texcoords_head.append((u, 1.0-vv))
                corners_new.append((v, index[key]))
            faces_head.append(corners_new)
            face_ids.append(int(f))
    for name, item in placement.items():
        x0_, y0_, x1_, y1_ = item['bbox_px']
        if x0_ < 0 or y0_ < 0 or x1_ > W or y1_ > H:
            raise RuntimeError(f'Head UV island {name} outside the texture: {item["bbox_px"]}')
    return texcoords_head, faces_head, face_ids, placement


HEAD_PREFIXES = ('head', 'jaw', 'eye', 'levator', 'oris', 'orbicularis', 'oculi', 'risorius', 'temporalis',
                 'tongue', 'special', 'mandible')


def head_weight_vector(count=13380):
    """Summed licensed head-region skin weights per MakeHuman body vertex."""
    from model_source import rig_sources, source_weight_vectors
    _, weights = rig_sources()
    rows = source_weight_vectors(weights, range(count))
    out = np.zeros(count)
    for i, row in rows.items():
        out[i] = sum(v for n, v in row.items() if n.startswith(HEAD_PREFIXES))
    return out
