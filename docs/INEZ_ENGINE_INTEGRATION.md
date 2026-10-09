> Checkpoint update (2026-10-09): actual dressed Blender/GLB sources and a separate staged animated prototype now exist. Production approval and real browser animation/render QA are pending. See [the current handoff](../WORK_COMPLETED_AND_NEXT_STEPS.md). Historical planning below may predate these assets.

# Inez engine integration — pending a validated character export

No game repository existed in the supplied workspace. A standalone Three.js viewer was prepared at `viewer/`; no game integration or deployment is claimed. There is no `inez.glb` yet. This note describes the intended integration contract, not an available production asset.

The future validated GLB should use meters, a consistent humanoid rest pose, glTF Y-up export, embedded or resolvable PBR textures, and a recorded root/skeleton hierarchy. Inez's exact height is not supplied; the preparation config's 1.70 m is explicitly provisional. Source bone names and weights are not evidence of a correctly fitted/animated rig.

Once an actual reviewed GLB exists, load it using Three.js `GLTFLoader`:

```js
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { AnimationMixer } from 'three';

const gltf = await new GLTFLoader().loadAsync('/characters/inez/model/inez.glb');
scene.add(gltf.scene);
const mixer = new AnimationMixer(gltf.scene);
// Populate actions from actual gltf.animations; do not assume clips exist.
const actions = new Map(gltf.animations.map(clip => [clip.name, mixer.clipAction(clip)]));
// In the frame loop: mixer.update(deltaSeconds).
```

Use sRGB output and albedo color spaces; glTF loaders treat non-color roughness/normal data separately. Keep neutral lighting during geometry/material QA. The viewer uses ACES tone mapping without bloom/sharpening. Apartment lighting is a visibility test, not a way to conceal geometry.

Before engine adoption, run the retained Khronos structural validator `node tools/inez/validate_glb.mjs`, inspect actual browser screenshots against both originals, test hierarchy/UVs/materials/skin weights/head/eyes/blinks/jaw/mouth shapes/pony-tail motion and all required expressions, and record clipping/resource performance. These validations are **not yet performed** on a character. A prototype, if created later, must remain clearly labeled until the real 3D likeness loop passes.
