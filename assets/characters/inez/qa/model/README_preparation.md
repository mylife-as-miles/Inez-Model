# Inez 3D preparation — geometry not authored

**Status: blocked at the initial reference gate. No fitted Inez mesh, .blend,
.glb, 3D render, clothing/hair geometry or tested rig has been created.**
The neutral front portrait is available. The initial body still has an
unresolved boot detail; true profiles have not been approved. Preparation
does not bypass the user's front/profile/body prerequisite.

## Preserved and prepared

- `model/base-source/`: unchanged MakeHuman hm08 continuous human topology,
  CC0 female-young shape targets, CC0 humanoid/facial skeleton and indexed
  skin weights, original license texts and URL/SHA-256 provenance.
- `qa/model/model_source_inventory.json`: source inspection only; body has
  13,380 vertices, 13,378 quads, existing UVs and a 163-bone source skeleton.
- `tools/inez/model_source.py`: indexed OBJ/UV/group/target/joint readers and
  explicit smooth local fitting controls.
- `tools/inez/model_prepare.py`: source inventory; does not construct geometry.
- `tools/inez/model_build.py`: prepared Blender import, original-reference
  packing, separate source/fitted shape keys, UV retention, licensed weight
  normalization, bone planes, geometry-only eye landmarks and four clay views.
- `tools/inez/model_head_config.json`: **draft and deliberately unfitted**;
  empty fit controls. It does not assert reconstruction or likeness.
- `tools/inez/model_fit_plan.md`: original-based measurements, limits and
  head-first fitting priorities.
- `tools/inez/model_export.py` / `model_validate_glb.py`: prepared export and
  actual binary/UV/skin/resource checks. Neither has exported a model.

Blender 4.3.2, its Python API, Cycles settings, bone roll method and glTF
exporter were checked without constructing a character. Python scripts pass
syntax compilation. These checks do not establish character quality.

## Resume after the recorded gate

1. Obtain passing initial front, profile and body reviews, within the user's
   generation limits or after their explicitly authorized budget revision.
   Record the root artist's explicit `FRONT/PROFILE/BODY INITIAL GATE PASSED`
   message and evidence in a copy of `model_gate.template.json` named
   `qa/model/model_gate.json`. The template is false and is not approval.
2. Measure the source head and calibrate **nonempty** nose, eyelid, mouth,
   cheek, jaw/chin controls to the originals. Retain the source as a separate
   base shape key. The draft source eye-to-chin ratio is about 1.74 IPD,
   exceeding original B's approximate 1.5–1.65 band. Nose/mouth vertical
   positions must be evaluated independently; do not shorten the whole face
   indiscriminately. Original A outranks a generated front/profile.
3. Set the config revision and truthful prototype stage, then run from
   `/workspace`:

   ```bash
   blender -b -t 4 --python tools/inez/model_build.py -- \
     --config tools/inez/model_head_config.json \
     --gate assets/characters/inez/qa/model/model_gate.json --render
   ```

   The entry point refuses absent/false gate evidence, absent approved initial
   references, and an empty fitting-control set. After it is legitimately
   enabled, output goes to `model/work/inez_head_vNN.blend`, four actual clay
   views in `renders/head_vNN/` and `qa/model/model_head_vNN_manifest.json`.
4. Have independent identity/technical critics compare actual clay front,
   profiles and three-quarter against both originals. Iterate underlying
   geometry first. Do not author detailed face maps or dressed whole-body
   output until head proportions are credible.
5. Export and browser-test only actual authored geometry; keep artistic
   approval separate from valid file structure. If likeness remains poor,
   retain the editable continuous mesh as an **unapproved prototype** and
   state the manual sculpting requirement.

The CC0 source is a topology substrate, not a finished or fitted Inez model.
The provisional 1.70 m scale is a workflow assumption, not measured stature.
Vendor target filenames are not claims about the character's ethnicity.
