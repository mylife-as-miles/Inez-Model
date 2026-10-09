"""v04 UV-space PBR maps for Inez (corrections after actual browser review).

v03 maps authored "linear-looking" values into sRGB images (dark, orange skin
and near-black hair), used high-frequency sinusoids that aliased into banding
("wood grain") in the skin normal map, and exported the cornea with
KHR_materials_transmission, which WebGL renders as an opaque white cap.

v04 calibrates base colors against sRGB samples of the original references,
uses blurred random noise for pores/microdetail, paints dense natural brows
into the skin at the measured brow band, and exports a clear alpha-blended
cornea. Hidden-surface detail remains disclosed extrapolation.
"""
import json
import math

import bpy
import numpy as np

from model_materials import material, save_image, connect_pbr, dilate_maps, normal_from_height, \
    actual_lip_color_field


def raster_attributes(points, attributes, texcoords, faces, resolution):
    """Rasterize per-vertex 3D positions and extra per-vertex attributes into
    every indexed UV triangle. Returns (positions HxWx3, attrs HxWxC, mask)."""
    points = np.asarray(points, dtype=np.float32)
    attrs = np.asarray(attributes, dtype=np.float32) if attributes is not None else None
    texcoords = np.asarray(texcoords, dtype=np.float32)
    channels = 3+(attrs.shape[1] if attrs is not None else 0)
    data = np.concatenate((points, attrs), axis=1) if attrs is not None else points
    raster = np.zeros((resolution, resolution, channels), np.float32)
    mask = np.zeros((resolution, resolution), bool)
    for face in faces:
        for j in range(1, len(face)-1):
            tri = [face[0], face[j], face[j+1]]
            values = data[[v for v, t in tri]]
            uv = texcoords[[t for v, t in tri]]*(resolution-1)
            lo = np.maximum(0, np.floor(uv.min(axis=0)).astype(int))
            hi = np.minimum(resolution-1, np.ceil(uv.max(axis=0)).astype(int))
            if (hi < lo).any():
                continue
            xx, yy = np.meshgrid(np.arange(lo[0], hi[0]+1), np.arange(lo[1], hi[1]+1))
            den = ((uv[1, 1]-uv[2, 1])*(uv[0, 0]-uv[2, 0])+(uv[2, 0]-uv[1, 0])*(uv[0, 1]-uv[2, 1]))
            if abs(den) < 1e-9:
                continue
            a = ((uv[1, 1]-uv[2, 1])*(xx-uv[2, 0])+(uv[2, 0]-uv[1, 0])*(yy-uv[2, 1]))/den
            b = ((uv[2, 1]-uv[0, 1])*(xx-uv[2, 0])+(uv[0, 0]-uv[2, 0])*(yy-uv[2, 1]))/den
            c = 1-a-b
            inside = (a >= -0.01) & (b >= -0.01) & (c >= -0.01)
            interpolated = a[:, :, None]*values[0]+b[:, :, None]*values[1]+c[:, :, None]*values[2]
            region = raster[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
            region[inside] = interpolated[inside]
            mask[lo[1]:hi[1]+1, lo[0]:hi[0]+1] |= inside
    return raster[:, :, :3], raster[:, :, 3:], mask


def blur(image, radius):
    """Separable box blur (three passes approximate a gaussian), wraps edges."""
    out = image.astype(np.float32)
    r = max(1, int(radius))
    for _ in range(3):
        for axis in (0, 1):
            cumulative = np.cumsum(np.pad(out, [(r+1, r) if a == axis else (0, 0) for a in range(out.ndim)], mode='wrap'), axis=axis)
            out = (np.take(cumulative, np.arange(2*r+1, cumulative.shape[axis]), axis=axis)
                   - np.take(cumulative, np.arange(0, cumulative.shape[axis]-2*r-1), axis=axis))/(2*r+1)
    return out


def noise(shape, radius, seed):
    rng = np.random.default_rng(seed)
    field = blur(rng.standard_normal(shape).astype(np.float32), radius)
    return field/max(1e-6, float(field.std()))


def srgb(color):
    return np.asarray(color, np.float32)


# ------------------------------------------------------------------- skin

def brow_field(x, y, z, eye_center, ipd):
    """Natural dense brows painted on the skin at the measured brow band.

    Original A/B: largely straight inner section, restrained outer arch,
    tapering tail. Band height is a fraction of inter-pupil distance (IPD),
    measured with face landmarks on original B (brow bottom ~0.18 IPD and top
    ~0.34 IPD above the pupil at the middle of the brow).
    """
    ex, ey = eye_center
    ax = np.abs(x)
    u = (ax-0.17*ipd)/(0.82*ipd)          # 0 inner end .. 1 tail
    inside_u = (u > -0.06) & (u < 1.03)
    middle = ey+ipd*(0.250+0.060*np.exp(-((u-0.60)/0.28)**2)-0.07*np.clip(u-0.78, 0, 1))
    half = ipd*(0.060-0.032*np.clip(u, 0, 1)**1.4)
    distance = np.abs(y-middle)/np.maximum(half, 1e-4)
    soft = np.clip(1.3-distance, 0, 1)
    soft *= np.clip((u+0.06)/0.10, 0, 1)*np.clip((1.03-u)/0.10, 0, 1)
    front = np.clip((z-0.85)*3.0, 0, 1)
    return np.where(inside_u, soft, 0)*front


def skin_pbr_v04(points, texcoords, faces, directory, eye_center, ipd, resolution=2048, lid_lines=()):
    positions, _, mask = raster_attributes(points, None, texcoords, faces, resolution)
    x, y, z = positions[:, :, 0], positions[:, :, 1], positions[:, :, 2]
    shape = mask.shape
    fine = noise(shape, 1.2, 101)
    pores = noise(shape, 0.8, 102)
    mottling = noise(shape, 9, 103)
    # Base albedo calibrated so studio-lit renders land near original B's lit
    # cheek/forehead sRGB samples (~0.66-0.68, 0.50-0.54, 0.44-0.46).
    albedo = np.empty((*shape, 3), np.float32)
    albedo[:] = srgb((0.725, 0.568, 0.488))
    albedo += mottling[:, :, None]*np.array([.010, .009, .007], np.float32)
    albedo += fine[:, :, None]*np.array([.006, .005, .004], np.float32)
    head = (y > 6.2) & (z > 0.35)
    front = np.clip((z-0.75)*3.2, 0, 1)
    cheeks = np.exp(-((np.abs(x)-0.40)/0.24)**2-((y-6.50)/0.22)**2)*front
    nose = np.exp(-(x/0.15)**2-((y-6.50)/0.20)**2)*front
    albedo += (cheeks*0.8+nose)[:, :, None]*np.array([.030, -.012, -.010], np.float32)
    under = np.exp(-((np.abs(x)-0.29)/0.18)**2-((y-6.68)/0.06)**2)*front
    albedo -= under[:, :, None]*np.array([.030, .034, .020], np.float32)
    # Freckles: concentrated over the nose bridge and upper cheeks, smaller
    # and sparser on the forehead (original A). Exact unseen marks unknown.
    rng = np.random.default_rng(1299)
    freckle = np.zeros(shape, np.float32)
    hm = mask & head & (y > 6.25) & (y < 7.55) & (z > 0.70)
    hx, hy = x[hm], y[hm]
    spots = np.zeros(hx.shape, np.float32)
    centers = []
    for _ in range(560):
        cx = rng.normal(0, 0.30)
        cy = rng.normal(6.58, 0.12)
        if abs(cx) > 0.64:
            continue
        centers.append((cx, cy, rng.uniform(.0035, .0105), rng.uniform(.14, .40)))
    for _ in range(80):
        centers.append((rng.uniform(-.45, .45), rng.uniform(6.95, 7.40), rng.uniform(.003, .007), rng.uniform(.08, .18)))
    for cx, cy, radius, strength in centers:
        d2 = ((hx-cx)**2+(hy-cy)**2)/radius**2
        near = d2 < 9
        spots[near] += np.exp(-d2[near]*1.4)*strength
    freckle[hm] = spots*front[hm]
    albedo -= np.minimum(freckle, .50)[:, :, None]*np.array([.26, .22, .17], np.float32)
    # Upper lash line and lid crease shadow along the actual lid-margin rows.
    lash = np.zeros(shape, np.float32)
    crease = np.zeros(shape, np.float32)
    eye_region = mask & (y > 6.6) & (y < 7.0) & (z > 0.8)
    if lid_lines:
        ex, ey_, ez = x[eye_region], y[eye_region], z[eye_region]
        d_line = np.full(ex.shape, 1e9, np.float32)
        d_crease = np.full(ex.shape, 1e9, np.float32)
        for line in lid_lines:
            line = np.asarray(line, np.float32)
            for a, b in zip(line[:-1], line[1:]):
                ab = b-a
                t = np.clip(((ex-a[0])*ab[0]+(ey_-a[1])*ab[1]+(ez-a[2])*ab[2])/max(float(ab@ab), 1e-9), 0, 1)
                d = np.sqrt((ex-a[0]-t*ab[0])**2+(ey_-a[1]-t*ab[1])**2+(ez-a[2]-t*ab[2])**2)
                d_line = np.minimum(d_line, d)
                # Crease ~4 mm above the margin.
                dc = np.sqrt((ex-a[0]-t*ab[0])**2+(ey_-a[1]-t*ab[1]-0.040)**2+(ez-a[2]-t*ab[2])**2)
                d_crease = np.minimum(d_crease, dc)
        lash[eye_region] = np.exp(-(d_line/0.011)**2)
        crease[eye_region] = np.exp(-(d_crease/0.018)**2)*0.35
    albedo = albedo*(1-0.70*lash[:, :, None])+srgb((0.10, 0.07, 0.06))*0.70*lash[:, :, None]
    albedo *= (1-0.18*crease)[:, :, None]
    # Brows painted into the albedo with hair-stroke breakup.
    strokes = noise(shape, 0.7, 104)
    brow = brow_field(x, y, z, eye_center, ipd)*mask
    # Hair-stroke breakup elongated along the brow (outward/upward strokes).
    stroke_dir = blur(noise(shape, 0.6, 107), 1)
    brow_alpha = np.clip(brow*(0.48+0.40*np.clip(strokes*0.6+stroke_dir*0.6, -1, 1)), 0, 0.78)
    browcolor = srgb((0.190, 0.130, 0.095))
    albedo = albedo*(1-brow_alpha[:, :, None])+browcolor*brow_alpha[:, :, None]
    # Lips: actual vermilion topology field, muted rose-brown.
    lipweight, lip_topology = actual_lip_color_field(positions, points)
    lipgrain = noise(shape, 0.6, 105)*0.008
    lipcolor = srgb((0.585, 0.345, 0.312))+lipgrain[:, :, None]
    albedo = albedo*(1-lipweight[:, :, None])+lipcolor*lipweight[:, :, None]
    rough = np.full(shape, .56, np.float32)
    rough -= nose*.10
    rough -= np.exp(-(x/0.5)**2-((y-7.14)/0.29)**2)*front*.05
    rough += fine*.012
    rough = rough*(1-lipweight)+(.40+lipgrain*1.5)*lipweight
    rough = rough*(1-brow_alpha*0.6)+0.72*brow_alpha*0.6
    height = pores*0.55+fine*0.25
    height = height*(1-lipweight)+noise(shape, 0.9, 106)*0.6*lipweight
    normal = normal_from_height(height, .055)
    albedo, rough, normal = dilate_maps([albedo, rough, normal], mask, passes=8)
    images = [save_image('inez_skin_albedo', albedo, directory),
              save_image('inez_skin_roughness', rough, directory, True),
              save_image('inez_skin_normal', normal, directory, True)]
    mat = material('Inez_Skin_Freckles_Pores_Lips_PBR', tuple(albedo[resolution//2, resolution//2]), .56)
    connect_pbr(mat, *images, normal_strength=.35)
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Subsurface Weight'].default_value = .05
    bsdf.inputs['Subsurface Radius'].default_value = (1.0, .42, .24)
    bsdf.inputs['IOR'].default_value = 1.42
    mat['texture_evidence'] = ('v04: base sRGB calibrated to original lit samples; freckles distributed per '
                               'original A (nose bridge/upper cheeks, sparse forehead); brows painted at '
                               'landmark-measured band; blurred-noise pores (no aliasing sinusoids)')
    mat['hidden_surface_status'] = 'Unseen marks and pores are extrapolated; not calibrated source albedo'
    mat['actual_vermilion_topology'] = json.dumps(lip_topology)
    return mat


# ------------------------------------------------------------------- eyes

def iris_pbr_v04(directory, resolution=512):
    q = np.linspace(-1, 1, resolution, dtype=np.float32)
    x, y = np.meshgrid(q, q)
    r = np.sqrt(x*x+y*y)
    a = np.arctan2(y, x)
    rng = np.random.default_rng(7)
    fibers = np.zeros_like(r)
    for k in range(5):
        freq = rng.uniform(40, 140)
        fibers += np.sin(a*freq+rng.uniform(0, 6.3)+r*rng.uniform(5, 30))/(k+1)
    fibers /= np.abs(fibers).max()
    # Muted green-hazel (original A/B samples ~0.31,0.26,0.19 in shadowed
    # photos): olive/gray-green outer field, warm golden-brown collarette,
    # darker limbal ring. No emerald saturation.
    outer = srgb((0.27, 0.285, 0.165))
    inner = srgb((0.36, 0.265, 0.13))
    limbal = srgb((0.12, 0.125, 0.085))
    t_inner = np.clip(1-(r-0.30)/0.22, 0, 1)
    albedo = outer*(1-t_inner[:, :, None])+inner*t_inner[:, :, None]
    albedo *= (1+0.10*fibers)[:, :, None]
    lim = np.clip((r-0.80)/0.18, 0, 1)
    albedo = albedo*(1-lim[:, :, None])+limbal*lim[:, :, None]
    pupil = np.clip((0.34-r)/0.04, 0, 1)
    albedo = albedo*(1-pupil[:, :, None])+srgb((0.02, 0.02, 0.02))*pupil[:, :, None]
    rough = np.full((resolution, resolution), .45, np.float32)
    normal = normal_from_height(fibers*0.25, .12)
    images = [save_image('inez_iris_olive_hazel_albedo', albedo, directory),
              save_image('inez_iris_roughness', rough, directory, True),
              save_image('inez_iris_normal', normal, directory, True)]
    mat = material('Inez_Muted_GreenHazel_Iris_PBR', (.27, .285, .165), .45)
    connect_pbr(mat, *images, normal_strength=.08)
    mat['color_evidence'] = 'Iris median samples at MediaPipe iris landmarks on original A/B; shadow-adjusted'
    return mat


def clear_cornea_v04(side):
    """Thin clear surface for corneal highlights; alpha blended, no
    transmission extension (WebGL rendered v03's transmissive cornea white)."""
    mat = bpy.data.materials.new('Inez_ClearCornea_'+side)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    # Black base: no diffuse haze over the iris (a white base at low alpha
    # washed the iris out); the blended layer contributes corneal highlights.
    bsdf.inputs['Base Color'].default_value = (0, 0, 0, 1)
    bsdf.inputs['Roughness'].default_value = .03
    bsdf.inputs['Alpha'].default_value = .20
    bsdf.inputs['IOR'].default_value = 1.376
    mat.blend_method = 'BLEND'
    mat.use_backface_culling = True
    mat['eye_status'] = 'Clear alpha-blended corneal dome for highlights only'
    return mat


def sclera_v04(directory, resolution=256):
    q = np.linspace(-1, 1, resolution, dtype=np.float32)
    x, y = np.meshgrid(q, q)
    vessels = noise((resolution, resolution), 1.0, 11)
    albedo = np.empty((resolution, resolution, 3), np.float32)
    albedo[:] = srgb((0.78, 0.735, 0.685))
    albedo += np.clip(vessels-1.6, 0, 1)[:, :, None]*np.array([.08, -.04, -.04])
    rough = np.full((resolution, resolution), .30, np.float32)
    normal = normal_from_height(vessels*0.05, .1)
    images = [save_image('ScleraOffWhite_albedo', albedo, directory),
              save_image('ScleraOffWhite_roughness', rough, directory, True),
              save_image('ScleraOffWhite_normal', normal, directory, True)]
    mat = material('Inez_ScleraOffWhite_PBR', (.83, .79, .74), .30)
    connect_pbr(mat, *images, normal_strength=.05)
    return mat


# ------------------------------------------------------------------- hair

def hair_tile(name, directory, base, tip, roughness, seed, resolution=512):
    """Strand-direction texture for tube/card hair (V runs along the lock).

    Colors are sRGB samples of original A/B hair (medium brown with restrained
    warm highlights; ponytail median ~0.20-0.23, 0.15-0.17, 0.11-0.13).
    """
    rng = np.random.default_rng(seed)
    u = np.arange(resolution, dtype=np.float32)/resolution
    strands = np.zeros(resolution, np.float32)
    for k in range(6):
        strands += np.sin(2*np.pi*u*rng.integers(20, 90)+rng.uniform(0, 6.3))/(k+1)
    strands /= np.abs(strands).max()
    along = np.linspace(0, 1, resolution, dtype=np.float32)
    streak = strands[None, :]*np.ones((resolution, 1), np.float32)
    streak += 0.25*noise((resolution, resolution), 2, seed+1)
    t = along[:, None]
    color = srgb(base)*(1-t[:, :, None]*0.55)+srgb(tip)*(t[:, :, None]*0.55)
    albedo = color*(1+0.16*streak[:, :, None])
    rough = np.full((resolution, resolution), roughness, np.float32)+0.05*streak
    normal = normal_from_height(streak*0.6, .25)
    images = [save_image(name+'_albedo', albedo, directory), save_image(name+'_roughness', rough, directory, True),
              save_image(name+'_normal', normal, directory, True)]
    mat = material('Inez_'+name+'_PBR', base, roughness)
    connect_pbr(mat, *images, normal_strength=.35)
    mat['color_evidence'] = 'Original A/B hair sRGB samples; strand texture along lock'
    return mat


# ------------------------------------------------------------------- fabric

def sweater_pbr_v04(points, attributes, texcoords, faces, directory, levels, resolution=2048):
    """Stripes: torso bands by height between neckline and hem; sleeve bands
    by arm-axis fraction. attributes columns: [arm_t, sleeve_weight]."""
    from model_clothing_v04 import TORSO_DARK_BANDS, SLEEVE_DARK_BANDS, smoothstep
    positions, attrs, mask = raster_attributes(points, attributes, texcoords, faces, resolution)
    y = positions[:, :, 1]
    arm_t = attrs[:, :, 0]
    sleeve = attrs[:, :, 1]
    f = (levels['stripe_top_y']-y)/(levels['stripe_top_y']-levels['stripe_bottom_y'])
    soft = 0.012
    torso_dark = np.zeros(mask.shape, np.float32)
    for a, b in TORSO_DARK_BANDS:
        torso_dark = np.maximum(torso_dark, smoothstep(a-soft, a+soft, f)*(1-smoothstep(b-soft, b+soft, f)))
    sleeve_dark = np.zeros(mask.shape, np.float32)
    ts = arm_t/levels['cuff_t']
    for a, b in SLEEVE_DARK_BANDS:
        sleeve_dark = np.maximum(sleeve_dark, smoothstep(a-soft, a+soft, ts)*(1-smoothstep(b-soft, b+soft, ts)))
    seam = smoothstep(0.45, 0.55, sleeve)
    dark = torso_dark*(1-seam)+sleeve_dark*seam
    # Knit: rib columns + row texture from 3D position, kept below Nyquist.
    x, z = positions[:, :, 0], positions[:, :, 2]
    column = np.where(seam > 0.5, np.arctan2(z, np.abs(x))*28.0, x*95.0)
    row = np.where(seam > 0.5, arm_t*210.0, y*120.0)
    knit = (np.cos(column*2*np.pi/2.2)**2)*0.6+0.4*np.cos(row*2*np.pi/2.4)**2
    fuzz = noise(mask.shape, 1.0, 21)
    gray = srgb((0.255, 0.255, 0.265))
    navy = srgb((0.090, 0.098, 0.140))
    albedo = gray*(1-dark[:, :, None])+navy*dark[:, :, None]
    albedo *= (0.93+0.10*knit+0.04*fuzz)[:, :, None]
    rough = np.full(mask.shape, .90, np.float32)+0.03*fuzz
    height = knit*0.9+fuzz*0.25
    normal = normal_from_height(height, .30)
    albedo, rough, normal = dilate_maps([albedo, rough, normal], mask, passes=8)
    images = [save_image('Sweater_ThreeDarkBands_albedo', albedo, directory),
              save_image('Sweater_ThreeDarkBands_roughness', rough, directory, True),
              save_image('Sweater_ThreeDarkBands_normal', normal, directory, True)]
    mat = material('Inez_Sweater_ThreeDarkBands_PBR', (.255, .255, .265), .90)
    connect_pbr(mat, *images, normal_strength=.55)
    mat['original_evidence'] = ('Original B stripe phase: torso bands at neckline-to-hem fractions %s; sleeve '
                                'bands at shoulder-to-cuff fractions %s' % (TORSO_DARK_BANDS, SLEEVE_DARK_BANDS))
    return mat


def denim_pbr_v04(points, texcoords, faces, directory, resolution=2048):
    positions, _, mask = raster_attributes(points, None, texcoords, faces, resolution)
    x, y, z = positions[:, :, 0], positions[:, :, 1], positions[:, :, 2]
    twill = np.sin((x*0.7+y)*260.0)*0.5+0.5
    wash = noise(mask.shape, 14, 31)
    fine = noise(mask.shape, 0.8, 32)
    albedo = np.empty((*mask.shape, 3), np.float32)
    albedo[:] = srgb((0.080, 0.083, 0.088))
    albedo += wash[:, :, None]*0.010+fine[:, :, None]*0.006+twill[:, :, None]*0.006
    rough = np.full(mask.shape, .86, np.float32)+0.02*fine
    normal = normal_from_height(twill*0.5+fine*0.3, .22)
    albedo, rough, normal = dilate_maps([albedo, rough, normal], mask, passes=8)
    images = [save_image('WashedBlackDenim_albedo', albedo, directory),
              save_image('WashedBlackDenim_roughness', rough, directory, True),
              save_image('WashedBlackDenim_normal', normal, directory, True)]
    mat = material('Inez_WashedBlackDenim_PBR', (.080, .083, .088), .86)
    connect_pbr(mat, *images, normal_strength=.35)
    mat['original_evidence'] = 'Original B: matte washed near-black denim; no decorative distressing'
    return mat
