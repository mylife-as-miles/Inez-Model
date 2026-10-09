"""Build the corrected v04 dressed Inez source from the reviewed head .blend.

    blender -b assets/characters/inez/model/work/inez_head_v03.blend -t 4 \
      --python tools/inez/model_dress_v04.py -- \
      --config tools/inez/model_head_config_v03.json \
      --gate assets/characters/inez/qa/model/model_gate.json \
      --head-gate assets/characters/inez/qa/model/credible_head_gate.json \
      --revision v04 \
      --output-blend assets/characters/inez/model/work/inez_dressed_v04.blend \
      --output-glb assets/characters/inez/model/work/inez_dressed_v04.glb \
      --texture-dir assets/characters/inez/model/textures/v04

The reviewed head source is opened read-only (never saved). Outputs are a new
revision: the canonical model/inez.blend and model/inez.glb are refused here;
promotion happens only after animation and browser validation. The identity
fit keys keep their exact source values (Inez_HeadFit_v01=0, v02=0, v03=1).
No image generator is called.
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bmesh
import bpy
import numpy as np
from mathutils import Vector

from model_build import mesh_from_group, attach_weights, point_camera
from model_clothing_v04 import (BodyWeights, SweaterPlan, sweater_faces, jean_faces, shape_jeans, build_boots,
                                rib_extension, add_jean_details_v04, necklace_v04, smoothstep, garment_relax,
                                vertex_normals)
from model_dress import fit_body_pose, rest_joint_fit, export_glb
from model_face_v04 import build_face_v04
from model_geometry import skin_source_nearest, actual_thickness, smooth_geometry, boundary_loops
from model_hair_v04 import build_hair_v04
from model_materials import material, detail_tile
from model_materials_v04 import skin_pbr_v04, sweater_pbr_v04, denim_pbr_v04
from model_source import CHARACTER, read_obj, shape_vertices, fit_vertices, rig_sources, joint_point

PLATFORM_UNITS = 0.434  # 4.6 cm platform under the foot (original B chunky soles)


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--gate', required=True)
    parser.add_argument('--head-gate', required=True)
    parser.add_argument('--revision', default='v04')
    parser.add_argument('--output-blend', required=True)
    parser.add_argument('--output-glb', required=True)
    parser.add_argument('--texture-dir', required=True)
    parser.add_argument('--texture-resolution', type=int, default=2048)
    parser.add_argument('--skip-hair', action='store_true')
    parser.add_argument('--refine', help='head refinement JSON (CC0 target weights) layered over the v03 fit')
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:])


def garment_levels(points, rig):
    """Garment boundaries in source units (y up). See manifest for evidence."""
    shoulder = joint_point(points, rig, rig['bones']['upperarm01.L']['head'])
    hip = joint_point(points, rig, rig['bones']['upperleg01.L']['head'])
    ground = min(p[1] for p in points[:13380])
    return {
        'neck_y': 5.20,                    # crew neck boundary (v03 reviewed collar height)
        'armpit_y': shoulder[1]-0.85,      # drape starts below the armpit
        'knit_bottom_y': 2.37,             # knit body ends; rib below (hem at ~elbow level, original B)
        'hem_y': 2.06,                     # rib hem bottom, ~3.3 cm rib
        'waist_top_y': 1.75,               # high-rise waistband top; ~3 cm midriff gap (original B)
        'crotch_y': hip[1]-0.62,
        'jean_hem_y': ground+2.21,         # 0.28 m above the sole bottom incl. platform (original B)
        'boot_top_y': ground+2.68,         # shaft top hidden under the jean hem
        'foot_bottom_y': ground,
        'platform_units': PLATFORM_UNITS,
        'cuff_t': 0.93,                    # sleeve knit ends; rib cuff covers the wrist
        'necklace_top_y': 5.30,
        'pendant_y': 4.40,
    }


def classify_loops(obj, shaped, levels):
    """Only the real openings get ribs: highest loop = crew neck, the largest
    lateral loop per side = cuff, the largest remaining low loop = hem. Any
    other boundary (a selection hole) is reported, never trimmed."""
    attr = obj.data.attributes['makehuman_source_index']
    loops = []
    for loop in boundary_loops(obj):
        src = [attr.data[i].value for i in loop]
        pts = np.asarray([shaped[i] for i in src])
        loops.append((len(loop), src, pts, pts.mean(axis=0)))
    chosen = []
    remaining = sorted(loops, key=lambda item: -item[0])
    neck = max((l for l in remaining if abs(l[3][0]) < 1.0 and l[3][1] > levels['neck_y']-0.8),
               key=lambda l: l[3][1], default=None)
    if neck:
        chosen.append(('CrewNeck',)+neck[1:])
        remaining.remove(neck)
    for sign in (1, -1):
        cuff = next((l for l in remaining if l[3][0]*sign > 1.8), None)
        if cuff:
            chosen.append(('Cuff',)+cuff[1:])
            remaining.remove(cuff)
    hem = next((l for l in remaining if l[3][1] < levels['armpit_y'] and abs(l[3][0]) < 1.0), None)
    if hem:
        chosen.append(('RibbedHem',)+hem[1:])
        remaining.remove(hem)
    obj['unexpected_boundary_loops'] = len(remaining)
    return chosen


def build_trims(sweater, shaped, levels, plan, transform, arm, body_points, weights, ribbed):
    trims = []
    for index, (kind, src, pts, center) in enumerate(classify_loops(sweater, shaped, levels)):
        if kind == 'RibbedHem':
            direction = np.array([0.0, -1.0, 0.0])
            obj = rib_extension('Inez_Sweater_RibbedHem', pts, center, direction,
                                levels['knit_bottom_y']-levels['hem_y'], 0.05, transform, ribbed, rows=5, ribs=90)
        elif kind == 'Cuff':
            side = 'L' if center[0] > 0 else 'R'
            frame = plan.arm_frames[side]
            axis = (frame.points[2]-frame.points[1])/frame.lengths[1]
            obj = rib_extension('Inez_Sweater_Cuff_'+side, pts, center, axis, 0.52, 0.22, transform, ribbed,
                                rows=6, ribs=36)
        else:
            obj = rib_extension('Inez_Sweater_CrewNeck', pts, center, np.array([0.0, 1.0, 0.0]), 0.20, 0.07,
                                transform, ribbed, rows=4, ribs=80)
        skin_source_nearest(obj, arm, body_points, weights, transform)
        actual_thickness(obj, .0030, clamp=1.0)
        obj['costume_status'] = 'v04 ribbed extension of the actual garment boundary'
        trims.append(obj)
    return trims


def waistband(jeans, shaped, levels, transform, arm, body_points, weights, denim):
    attr = jeans.data.attributes['makehuman_source_index']
    for loop in boundary_loops(jeans):
        src = [attr.data[i].value for i in loop]
        pts = np.asarray([shaped[i] for i in src])
        if pts[:, 1].mean() > levels['waist_top_y']-0.3 and len(loop) > 20:
            center = pts.mean(axis=0)
            band = rib_extension('Inez_Jeans_Waistband', pts*np.array([1.0, 1.0, 1.0]), center,
                                 np.array([0.0, -1.0, 0.0]), 0.42, -0.012, transform, denim, rows=4, ribs=1)
            # Push the band slightly proud of the jeans surface.
            for v in band.data.vertices:
                radial = Vector((v.co.x, v.co.y-transform(tuple(center))[1], 0))
                if radial.length > 1e-6:
                    v.co += radial.normalized()*0.002
            skin_source_nearest(band, arm, body_points, weights, transform)
            actual_thickness(band, .0022, clamp=1.0)
            return band
    raise RuntimeError('Jeans waist boundary not found')


def collide_with_body(obj, body, faces_keep, clearance_m):
    """After subdivision (which shrinks convex garment areas), push any garment
    vertex closer than clearance_m to the selected body faces back outside."""
    from mathutils.bvhtree import BVHTree
    key = body.data.shape_keys.key_blocks[-1]
    verts = [d.co.copy() for d in key.data]
    polys = [list(p.vertices) for p, keep in zip(body.data.polygons, faces_keep) if keep]
    bvh = BVHTree.FromPolygons(verts, polys)
    moved = 0
    for v in obj.data.vertices:
        nearest, normal, _, distance = bvh.find_nearest(v.co)
        if nearest is None:
            continue
        outside = (v.co-nearest).dot(normal) >= 0
        # Only correct small violations: a deep 'inside' reading in a concave
        # armpit/crotch is a nearest-face ambiguity, and moving it made spikes.
        if (outside and distance < clearance_m) or (not outside and distance < 0.012):
            v.co = nearest+normal*clearance_m
            moved += 1
    obj.data.update()
    return moved


def delete_hidden_body(body, below_z):
    """Remove body faces fully enclosed by the boots (no toe poke-through)."""
    bm = bmesh.new()
    bm.from_mesh(body.data)
    key = bm.verts.layers.shape.get(body.data.shape_keys.key_blocks[-1].name)
    doomed = []
    for face in bm.faces:
        zs = [(v[key].z if key else v.co.z) for v in face.verts]
        if max(zs) < below_z:
            doomed.append(face)
    bmesh.ops.delete(bm, geom=doomed, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    return len(doomed)


def main():
    args = arguments()
    config = json.loads(Path(args.config).read_text())
    gate = json.loads(Path(args.gate).read_text())
    headgate = json.loads(Path(args.head_gate).read_text())
    if not gate.get('front_profile_body_initial_gate_passed'):
        raise RuntimeError('Initial reference geometry gate has not passed')
    if not headgate.get('credible_head_geometry_passed'):
        raise RuntimeError('Actual clay head must hold its independent credible-geometry review')
    canonical = {(CHARACTER/'model/inez.blend').resolve(), (CHARACTER/'model/inez.glb').resolve()}
    outputs = [Path(args.output_blend).resolve(), Path(args.output_glb).resolve()]
    if any(o in canonical for o in outputs):
        raise RuntimeError('v04 build writes a separate revision; promotion to canonical is a later validated step')
    body = bpy.data.objects.get('Inez_ContinuousHumanMesh_UNAPPROVED')
    arm = bpy.data.objects.get('InezRig_PROTOTYPE')
    if body is None or arm is None or body.data.shape_keys is None:
        raise RuntimeError('Open the reviewed fitted head .blend')
    if any(o.name == 'Inez_Sweater' for o in bpy.data.objects):
        raise RuntimeError('Dressed geometry already exists: open the reviewed head .blend, not a dressed file')
    keys = body.data.shape_keys.key_blocks
    identity_defaults = {k.name: float(k.value) for k in keys if k.name.startswith('Inez_HeadFit_')}
    source, uv, groups = read_obj()
    basis = shape_vertices(source, config['source_shape_weights'])
    fitted = fit_vertices(basis, config['fit_controls'])
    ground = min(basis[i][1] for i in range(13380))
    height = max(basis[i][1] for i in range(13380))-ground
    scale = config['provisional_height_m']/height
    lift_m = PLATFORM_UNITS*scale
    old_ground = ground

    def old_inverse(co):
        return (co.x/scale, co.z/scale+old_ground, -co.y/scale)
    ground_eff = ground-PLATFORM_UNITS

    def transform(p):
        return (p[0]*scale, -p[2]*scale, (p[1]-ground_eff)*scale)
    fitkey = keys[-1]
    attr = body.data.attributes.get('makehuman_source_index')
    for vi, item in enumerate(attr.data):
        fitted[item.value] = old_inverse(fitkey.data[vi].co)
    # Optional refinement layer (CC0 feature targets) over the reviewed fit,
    # applied to body and helper geometry alike (eyes, overlays, rig follow).
    refine = np.zeros((len(fitted), 3))
    refine_report = None
    if args.refine:
        from model_head_targets import refinement_delta
        refine_data = json.loads(Path(args.refine).read_text())
        refine = refinement_delta(fitted, refine_data['weights'], CHARACTER/'model/base-source/targets')
        refine_report = {'config': args.refine, 'weights': refine_data['weights'],
                         'max_displacement_m': float(np.linalg.norm(refine, axis=1).max()*scale)}
    fitted = [list(np.asarray(p)+refine[i]) for i, p in enumerate(fitted)]
    posed = fit_body_pose(fitted, config)
    # Lift every stored shape and helper mesh by the platform so the feet stand
    # on the sole. Identity fit key values are untouched.
    for key in keys:
        for d in key.data:
            d.co.z += lift_m
    for v in body.data.vertices:
        v.co.z += lift_m
    # The active v03 key carries the arm pose; the refinement is its own key.
    for vi, item in enumerate(attr.data):
        unrefined = np.asarray(posed[item.value])-refine[item.value]
        fitkey.data[vi].co = transform(unrefined)
    if args.refine:
        refkey = body.shape_key_add(name='Inez_HeadRefine_'+args.revision, from_mix=False)
        refkey.relative_key = keys[0]
        for vi, item in enumerate(attr.data):
            d = refine[item.value]
            refkey.data[vi].co = keys[0].data[vi].co+Vector((d[0]*scale, -d[2]*scale, d[1]*scale))
        refkey.value = 1.0
        identity_defaults[refkey.name] = 1.0
        keys = body.data.shape_keys.key_blocks
    fitted = posed
    for name in ('EyeGeometry_L', 'EyeGeometry_R', 'IrisQA_L', 'IrisQA_R', 'PupilQA_L', 'PupilQA_R'):
        obj = bpy.data.objects.get(name)
        if obj:
            for v in obj.data.vertices:
                v.co.z += lift_m
    for k in keys:
        k.value = identity_defaults.get(k.name, k.value)
    rig, weights = rig_sources()
    rest_joint_fit(arm, fitted, rig, transform)
    texdir = Path(args.texture_dir)
    texdir.mkdir(parents=True, exist_ok=True)
    eye_l = joint_point(fitted, rig, rig['bones']['eye.L']['head'])
    eye_r = joint_point(fitted, rig, rig['bones']['eye.R']['head'])
    ipd = abs(eye_l[0]-eye_r[0])
    # Upper lid-margin rows (same indexed rows as the lash roots, mirrored).
    upper_ids = [6847, 6844, 6841, 6838, 6785, 6784, 6790, 6793, 6796, 6799, 6802]
    src = np.asarray(fitted[:13380])
    mirrored = [int(np.argmin(np.sum((src-np.asarray(fitted[i])*np.array([-1, 1, 1]))**2, axis=1))) for i in upper_ids]
    lid_lines = [[fitted[i] for i in upper_ids], [fitted[i] for i in mirrored]]
    body.data.materials.clear()
    body.data.materials.append(skin_pbr_v04(fitted, uv, groups['body'], texdir, (eye_l[0], eye_l[1]), ipd,
                                            args.texture_resolution, lid_lines=lid_lines))
    face_objects, face_report = build_face_v04(body, fitted, uv, groups, rig, weights, transform, arm, texdir)
    levels = garment_levels(fitted, rig)
    bw = BodyWeights(weights)
    plan = SweaterPlan(fitted, bw, rig, levels)
    sweaterfaces = sweater_faces(fitted, groups, bw, plan.arm_frames, levels)
    sweater_ids = {i for f in sweaterfaces for i, t in f}
    shaped = plan.shape(sweater_ids)
    # Collision bodies exclude parts a garment never wraps (hands near the hips
    # previously pushed relaxed jean vertices into the hip).
    def collision_faces(keep):
        out = []
        for f in groups['body']:
            ids_ = [i for i, t in f]
            if keep(np.mean([bw.arm[i] for i in ids_]), np.mean([bw.hand[i] for i in ids_]),
                    np.mean([bw.head[i] for i in ids_])):
                out.append(f)
        return out
    sweater_collision = collision_faces(lambda arm_w, hand_w, head_w: hand_w < 0.3 and head_w < 0.5)
    jean_collision = collision_faces(lambda arm_w, hand_w, head_w: arm_w < 0.3 and hand_w < 0.1 and head_w < 0.5)
    shaped = garment_relax(shaped, sweaterfaces, sweater_ids, fitted, sweater_collision, 0.09, iterations=10)
    shaped = shaped+plan.fold
    neck_loop = [shaped[i] for i in sweater_ids if shaped[i][1] > levels['neck_y']-0.25 and abs(shaped[i][0]) < 0.3]
    levels['stripe_top_y'] = float(min(p[1] for p in neck_loop)) if neck_loop else levels['neck_y']-0.15
    levels['stripe_bottom_y'] = levels['hem_y']
    attrs = np.stack((plan.arm_t, plan.sleeve), axis=1)
    sweatermat = sweater_pbr_v04(shaped, attrs, uv, sweaterfaces, texdir, levels, args.texture_resolution)
    sweater, sweaterids = mesh_from_group('Inez_Sweater', sweaterfaces, shaped.tolist(), uv, transform, sweatermat)
    attach_weights(sweater, sweaterids, weights, arm)
    ribbed = detail_tile('CharcoalRibbedKnitTrims', texdir, (.255, .255, .265), .90, 'ribbed')
    trims = build_trims(sweater, shaped, levels, plan, transform, arm, fitted, weights, ribbed)
    jeanfaces = jean_faces(fitted, groups, bw, levels)
    jean_ids = {i for f in jeanfaces for i, t in f}
    normals = vertex_normals(fitted[:13380], groups['body'])
    jeanpoints, jeanfolds = shape_jeans(fitted, jean_ids, bw, rig, levels, normals)
    jeanpoints = garment_relax(jeanpoints, jeanfaces, jean_ids, fitted, jean_collision, 0.06, iterations=12)
    jeanpoints = jeanpoints+jeanfolds
    denim = denim_pbr_v04(jeanpoints, uv, jeanfaces, texdir, args.texture_resolution)
    jeans, jeanids = mesh_from_group('Inez_Jeans', jeanfaces, jeanpoints.tolist(), uv, transform, denim)
    attach_weights(jeans, jeanids, weights, arm)
    band = waistband(jeans, jeanpoints, levels, transform, arm, fitted, weights, denim)
    thread = material('Inez_Jeans_SubtleSeamThread', (.020, .021, .021), .88)  # linear ~0.15 sRGB
    details = add_jean_details_v04(jeans, jeanpoints, fitted, transform, arm, weights, denim, thread, levels)
    body_face_keep = {}
    for name, keep in (('sweater', lambda a, h, d: h < 0.3 and d < 0.5), ('jeans', lambda a, h, d: a < 0.3 and h < 0.1 and d < 0.5)):
        body_face_keep[name] = [keep(np.mean([bw.arm[i] for i in f]), np.mean([bw.hand[i] for i in f]),
                                     np.mean([bw.head[i] for i in f])) for f in (list(p.vertices) for p in body.data.polygons)]
    collision_report = {}
    for garment, name, clearance in ((sweater, 'sweater', 0.009), (jeans, 'jeans', 0.008)):
        smooth_geometry(garment, 1)
        collision_report[name] = collide_with_body(garment, body, body_face_keep[name], clearance)
        # Thickness grows outward so the inner surface keeps its clearance.
        actual_thickness(garment, .0021 if garment == sweater else .0016, clamp=1.0, offset=1.0)
        garment['costume_status'] = 'v04 original-B guided loose skinned garment; actual-render review required'
    boots, boot_report = build_boots(fitted, bw, rig, transform, arm, texdir, levels)
    jewelry = necklace_v04(fitted, shaped, sweater_ids, transform, arm, weights, texdir, levels)
    hair, hair_report = ([], {}) if args.skip_hair else build_hair_v04(fitted, uv, groups, transform, arm, texdir)
    removed = delete_hidden_body(body, transform((0, levels['boot_top_y']-0.15, 0))[2])
    preserved = {k.name: float(k.value) for k in body.data.shape_keys.key_blocks
                 if k.name.startswith(('Inez_HeadFit_', 'Inez_HeadRefine_'))}
    if preserved != identity_defaults:
        raise RuntimeError('Identity fit defaults changed: %s vs %s' % (preserved, identity_defaults))
    body['identity_status'] = 'Fitted dressed playable foundation v04; independent final artistic review pending'
    arm['rig_status'] = '163 actual bones/normalized source weights; v04 dressed; animation review pending'
    scene = bpy.context.scene
    scene['INEZ_STAGE'] = 'v04 corrected dressed prototype (separate revision); animation and browser gates pending'
    scene['provisional_height_m'] = config['provisional_height_m']
    scene['platform_lift_m'] = lift_m
    scene['source_basis_preserved'] = True
    scene['material_authority'] = 'Original A face; original B costume; generated body guides geometry only'
    camera = scene.camera
    if camera:
        target = Vector((0, 0, .9))
        camera.location = target+Vector((0, -3, 0))
        point_camera(camera, target)
    blend, glb = Path(args.output_blend), Path(args.output_glb)
    blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    export_glb(glb)
    manifest = {
        'revision': args.revision, 'stage': scene['INEZ_STAGE'], 'source_head_blend': bpy.data.filepath,
        'head_config': args.config, 'blend': str(blend), 'glb': str(glb), 'texture_dir': str(texdir),
        'identity_morph_source_defaults': identity_defaults, 'identity_morph_values_after_build': preserved,
        'head_refinement': refine_report,
        'provisional_body_height_m': config['provisional_height_m'], 'platform_lift_m': lift_m,
        'garment_levels_source_units': levels, 'stripe_evidence': {
            'torso_dark_band_fractions_neckline_to_hem': [list(b) for b in __import__('model_clothing_v04').TORSO_DARK_BANDS],
            'sleeve_dark_band_fractions_shoulder_to_cuff': [list(b) for b in __import__('model_clothing_v04').SLEEVE_DARK_BANDS],
            'measurement': 'navy-minus-red row runs on original B front torso/sleeve centerlines'},
        'boots': boot_report, 'hair': hair_report, 'face': face_report,
        'body_faces_removed_inside_boots': removed,
        'post_subdivision_collision_vertices_moved': collision_report,
        'actual_authored_meshes': sorted(o.name for o in scene.objects if o.type == 'MESH'),
        'corrections_vs_v03': [
            'sweater hangs from bust/shoulder blades with straight sides (no bust conforming)',
            'stripe phase from original B; sleeve bands along the arm axis (no shoulder patches)',
            'unstable garment normal fixed (v03 hem/forearm spike)',
            'jeans: straight barrel legs, narrower hips, gathered hem over the boot shaft (no skin gap)',
            'boots: platform under the foot, footprint encloses all foot vertices, hidden body faces removed',
            'skin/hair/eye colors calibrated to original sRGB samples; no transmissive cornea; no aliasing normal map',
            'hair rebuilt: close scalp cap with alpha hairline, curly locks, framing ringlets, voluminous ponytail'],
        'final_artistic_identity_approved': False, 'production_complete': False,
        'units': 'meters; glTF Y up, +Z forward',
    }
    report = CHARACTER/'qa/model'/('model_dressed_'+args.revision+'_manifest.json')
    report.write_text(json.dumps(manifest, indent=2, default=float)+'\n')
    print('INEZ_DRESSED_V04_READY '+json.dumps({'blend': str(blend), 'glb': str(glb), 'removed_faces': removed,
                                                 'identity': preserved}), flush=True)


if __name__ == '__main__':
    main()
