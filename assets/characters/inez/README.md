# Inez — character asset

**Status.** Rigged, animated, packaged and browser-tested. The likeness is **not accepted**: about 75/100 against a 90 target. That figure is a judgment, explained in `reports/INEZ_VISUAL_QA.md`, not a measured score. The master is built from the user's own GLBs, transferred onto a rigged production body. The originals in `references/` remain the authority.

## Files

| Path | What it is |
|---|---|
| `model/inez_master.blend` | Editable master: rig, identity layers, clips. Textures are linked from `textures/master/`. |
| `model/inez_master.glb` | Full-quality export: 289,896 triangles, JPEG textures, 47.6 MB |
| `model/inez_runtime.glb` | Default runtime: 144,450 triangles, KTX2 + meshopt, 30.4 MB |
| `model/inez_runtime_lod1.glb`, `_lod2.glb` | LODs: 85,449 and 57,450 triangles |
| `source/asset_a`, `asset_b`, `asset_c` | The user's Drive GLBs, byte-for-byte and read-only (SHA-256 in `reports/GLB_ASSET_AUDIT.md`) |
| `references/` | The two original images (unchanged) and the reference-generation history |
| `rig/animation_manifest.json` | Rig, clip, weight and morph measurements from the build |
| `animation/` | Retargeted motion: inputs, intermediate skeletons, baked clips, viewer manifest, previews, QA (`docs/INEZ_ANIMATION_PIPELINE.md`) |
| `renders/final_v05/`, `likeness_v05/`, `rig_review/` | Final Cycles renders, matched-angle likeness overlays, clip and expression strips |
| `renders/browser_v02/`, `lab_v01/` | Frames captured from the real model in Chromium |
| `qa/` | Validator, browser, lab, boot-contact and performance results |

All the GLBs share the same rig: 167 joints, 21 morph targets and 17 embedded clips. Validation reports 0 errors on every file.

## Reports

- `reports/GLB_ASSET_AUDIT.md`: what the user's three GLBs contain.
- `reports/INEZ_MODEL_COMPARISON.md`: which parts of which asset are used, and why.
- `reports/INEZ_IDENTITY_SPEC.md`: measured identity targets and acceptance checks.
- `reports/INEZ_VISUAL_QA.md`: measured gates, deductions and passes used.
- `reports/INEZ_RIG_QA.md`: skeleton, skinning, controls and clip metrics.
- `reports/INEZ_PERFORMANCE.md`: sizes, draw calls, texture memory, and software-renderer frame rates. **No GPU has been measured yet.**
- `reports/INEZ_INTEGRATION.md`: loading Inez in Three.js / THREE BEDROOM.

## Never

- Reset the identity morphs. `Inez_HeadFit_v01`/`v02` stay at 0; `v03` and the four `_v05` layers stay at 1.
- Overwrite `source/` or the original references.
- Label a clip with a source other than its manifest entry (`procedural`, `CMU mocap`, `TERRA`).
