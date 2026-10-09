# Integrating Inez into THREE BEDROOM (Three.js)

The deliverables live under `assets/characters/inez/`.

| Path | Use |
|---|---|
| `model/inez_runtime.glb` | **Game asset (LOD0).** KTX2 textures + meshopt geometry |
| `model/inez_runtime_lod1.glb`, `model/inez_runtime_lod2.glb` | Distance levels (same rig, clips and morphs) |
| `model/inez_master.glb` | Full-resolution export; JPEG/PNG textures, no compression extensions |
| `model/inez_master.blend` | Editable master (Blender 4.3): rig, actions, identity layers; textures in `textures/master/` |
| `rig/animation_manifest.json` | Clip metadata: matching walk/run speeds, one-shot flags, turn root yaw, audits |
| `rig/expression_clips.json` | Facial clip timelines and the identity defaults they preserve |
| `viewer/` (repo root) | Reference implementation of everything below |

Sizes, triangle counts and measured costs are in `INEZ_PERFORMANCE.md`.

## Loading

```js
import * as THREE from 'three';                       // tested with three 0.180.0
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

const ktx2 = new KTX2Loader()
  .setTranscoderPath('/basis/')     // copy three/examples/jsm/libs/basis/* here
  .detectSupport(renderer);
const loader = new GLTFLoader().setKTX2Loader(ktx2).setMeshoptDecoder(MeshoptDecoder);
const gltf = await loader.loadAsync('/characters/inez/model/inez_runtime.glb');
const inez = gltf.scene;                // metres, +Y up, faces +Z, feet on y = 0
scene.add(inez);
```

`viewer/vite.config.js` shows how to serve the Basis transcoder without
copying it into the repository.

The master GLB loads with a plain `GLTFLoader`.

## Never reset the identity morphs

The body mesh carries identity layers as morph targets with **default weight
1**:

- `Inez_HeadFit_v03`
- `Inez_HeadRefine_v05`
- `Inez_SourceBodyFit_v05`
- `Inez_SourceHeadWrap_v05`
- `Inez_FaceCorrect_v05`

`Inez_HeadFit_v01` and `_v02` stay at 0. GLTFLoader applies these defaults
automatically.

Code must **never** call `morphTargetInfluences.fill(0)` or otherwise "reset"
the whole array: that turns Inez into a different face and body. Change only
the named control targets. `viewer/src/character-controls.js`
(`FacialControls`) is a safe implementation.

## Animation

```js
const mixer = new THREE.AnimationMixer(inez);
const clip = name => THREE.AnimationClip.findByName(gltf.animations, name);
const idle = mixer.clipAction(clip('Idle')).play();
// every frame: mixer.update(dt)
```

**Body clips (in place, 24 fps sampling):**

- **Locomotion.** `Idle` (breathing), `Walk`, `Run`.
- **Looking.** `LookAround`.
- **Turns.** `TurnLeft`, `TurnRight` are one-shots.
- **Crouch.** `CrouchDown` and `CrouchUp` are one-shots; `Crouch` loops.
- **Blink.** `Blink` drives the lid bones.

**Locomotion blending.** Blend `Idle`/`Walk`/`Run` by speed. Advance `Walk`
and `Run` by a shared phase at `speed / matching_speed`, using
`clip_info.Walk.matching_viewer_speed_m_s` and the matching value for `Run`.
The feet then do not slide; see `AnimationController` in the viewer.

**Turns.** Set `LoopOnce` and `clampWhenFinished`. On the mixer's `finished`
event:

1. Add `clip_info.TurnLeft.root_rotation_deg` (+90; −90 for `TurnRight`) to
   the character's yaw.
2. Switch to `Idle` with zero fade.

The end pose equals Idle rotated, so the swap is invisible.

**Crouch.** Play `CrouchDown`, then `Crouch` (loop), then `CrouchUp`, chained
on `finished`.

**Facial clips.** `Expr_SubtleFear`, `Expr_Confusion`, `Expr_Anger`,
`Expr_Exhaustion`, `Expr_IntenseFear`, `Expr_Suspicious` and `Expr_Blink`
animate only morph weights. Play them on top of any body clip with their own
action; never stop the body action for them.

**Static expressions and lip-sync.** Add to the named targets:

- expressions: `Confused`, `Suspicious`, `SubtleFear`, `IntenseFear`,
  `Anger`, `Exhaustion`;
- visemes: `Viseme_AA`, `_EE`, `_OH`, `_MM`, `_FV`;
- blinks: `Blink_L`, `Blink_R`.

Lashes and tearlines have the same names. Drive every mesh that has a target.

**Gaze, head and jaw.** Rotate the `eye.L`, `eye.R`, `head` and `jaw` bones
after `mixer.update()`, and restore them before the next update. The viewer
does this in head-relative space because the bones carry anatomical roll.

## Level of detail

```js
const lod = new THREE.LOD();
lod.addLevel(lod0.scene, 0);   // full face and hair detail: dialogue and close camera
lod.addLevel(lod1.scene, 6);
lod.addLevel(lod2.scene, 15);
```

Each level is a complete skinned copy with its own skeleton. Drive all three
from one mixer per level, or keep one level live at a time and copy the
mixer's time on switch. The rig, clip names and morph names are identical
across levels.

## Materials and rendering

- **Colour management.** `renderer.outputColorSpace = SRGBColorSpace`. The
  viewer uses ACES filmic tone mapping.
- **Skin, sweater, jeans and boots** are opaque.
- **Cornea and tearline** are alpha-blended and render after opaque objects.
- **Hair** uses `KHR_materials_specular` for a warm specular tint and is
  opaque (sculpted shell).
- **Necklace** is metallic silver.
- **Shadows.** Set `castShadow` on all meshes. The cornea and tearline
  should not cast.

## THREE BEDROOM hooks

- **Height.** Provisional: 1.70 m barefoot plus 4.6 cm soles, 1.783 m to the
  top of the hair. Scale uniformly if the game team fixes a different height.
  The clips stay valid.
- **Capsule.** A suggested starting point is radius 0.22 m, height 1.70 m,
  centre at y = 0.85.
- **Expressions per scene.** `SubtleFear` for unease, `IntenseFear` for
  threat, `Exhaustion` after chases, `Confused` for discoveries. Strength 0.4–0.7
  reads naturally at gameplay distance.

## Before shipping

- Run `node tools/inez/validate_glb.mjs <file> <report.json>` (Khronos
  validator). It must report 0 errors.
- Run `python3 tools/inez/browser_qa.py --model inez_runtime.glb`. It runs the
  automated browser checks and captures frames.
- Measure frame time on the target GPUs. The numbers in
  `INEZ_PERFORMANCE.md` come from a software renderer and do **not**
  represent hardware.
