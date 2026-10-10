# Inez and the CORDEL engine

CORDEL ([mylife-as-miles/cordel-engine](https://github.com/mylife-as-miles/cordel-engine),
`0.1.0-dev`) is the native C++20 runtime planned for THREE BEDROOM. This note
maps the delivered Inez asset onto CORDEL's current state. It records
decisions only; no CORDEL code was changed by this work.

## Where CORDEL is today (read at `057d304`)

- **Phase 2.1 is done.** It covers the collision/query adapter and the Jolt
  physics selection. The next milestones are 2.2 (character motor), 2.3
  (follow camera) and 2.4 (basic locomotion: "import one licensed skeleton and
  idle/walk/run clips, blend with motor state").
- **The glTF loader is a static, translation-only fixture.** It is
  cgltf-based. `native/phase1_host` explicitly rejects
  rotation/scale/matrix/skin/hierarchy content.
- **CORDEL cannot load Inez yet.** Skinning, animation sampling and morph
  targets are prerequisites of Phase 2.4.
- **Conventions.** Right-handed, +Y up, +X right, −Z forward, metres. glTF
  quaternions are (x, y, z, w). Matrices are row-major and act on column
  vectors.

## Which Inez file to use

| File | Contents | For CORDEL |
|---|---|---|
| `assets/characters/inez/model/inez_master.glb` | Full-resolution master; JPEG/PNG textures; no compression extensions | **Phase 2.4 test asset.** It needs only core glTF 2.0 with skins, animations and morph targets. |
| `model/inez_runtime.glb` (+ `_lod1`, `_lod2`) | `KHR_texture_basisu` (KTX2) and `EXT_meshopt_compression` | Later, once CORDEL's cooker decodes Basis Universal and meshopt (Phase 4.2 asset cooking) |
| `model/inez_master.blend` | Editable source: rig, actions, identity layers | Offline authoring only |

Both GLB variants share the same skeleton, clip names and morph target names.

## Contract the importer must honour

**Axes and scale.** Metres, glTF +Y up. Inez's rest pose faces glTF **+Z**.
CORDEL's yaw zero looks −Z, so a character facing away from a default camera
needs yaw π. Feet stand on y = 0, including the 4.6 cm platform soles.

**Skeleton.** 167 joints, all deforming:

- the CC0 MakeHuman 163-bone humanoid with facial bones (jaw, eyes, lids,
  brows, lips);
- four ponytail bones, `hair.01`–`hair.04`, under `head`.

Skin weights are limited to four influences per vertex and normalised.
Skinned meshes are children of the armature node: the validator reports
`NODE_SKINNED_MESH_NON_ROOT`, which glTF allows. Ignore the mesh node's own
transform as the specification requires.

**Morph targets.** These must keep their default weights:

- The body carries identity layers at weight 1.0: `Inez_HeadFit_v03`,
  `Inez_HeadRefine_v05`, `Inez_SourceBodyFit_v05`, `Inez_SourceHeadWrap_v05`
  and `Inez_FaceCorrect_v05`.
- `Inez_HeadFit_v01` and `_v02` stay at 0.

These layers **are** Inez's face and body. An importer that zeroes unknown
morph weights, or bakes only the base mesh, produces a different person.
Either honour `mesh.weights` or bake the defaults into the cooked mesh.

Controllable targets are:

- expressions: `Neutral`, `Confused`, `Suspicious`, `SubtleFear`,
  `IntenseFear`, `Anger`, `Exhaustion`;
- visemes: `Viseme_AA`, `Viseme_EE`, `Viseme_OH`, `Viseme_MM`, `Viseme_FV`;
- blinks: `Blink_L`, `Blink_R`.

The lashes carry the same control names so they follow the lids; the lower teeth and tongue follow the jaw in the visemes.

**Body clips.** All are sampled at 24 fps and in place (no root translation).

| Clip | Notes |
|---|---|
| `Idle` | 4 s breathing loop |
| `Walk` | 0.92 m/s at matching playback |
| `Run` | 2.40 m/s at matching playback |
| `LookAround` | 6 s loop |
| `TurnLeft`, `TurnRight` | One-shot. The root ends rotated ±90°: move that yaw to the gameplay transform on completion, then resume Idle with no blend. |
| `CrouchDown`, `CrouchUp` | One-shot |
| `Crouch` | Loop |
| `Blink` | Lid bones, optional |

Matching speeds and the one-shot and root-rotation metadata are in
`assets/characters/inez/rig/animation_manifest.json` (`clip_info`).

**Facial clips.** `Expr_SubtleFear`, `Expr_Confusion`, `Expr_Anger`,
`Expr_Exhaustion`, `Expr_IntenseFear`, `Expr_Suspicious` and `Expr_Blink`
animate only morph `weights` and touch no bones. Play them as an additive
layer over any body clip.

Every keyframe repeats the identity defaults. A sampler that writes all
weights stays correct; one that writes only the changed targets must leave
the others at their defaults.

**Ponytail.** Secondary motion is baked into every body clip: a simulated
damped spring chain. A runtime physics chain can replace it later; keep the
bind pose.

**Materials.** glTF metallic-roughness:

- base colour textures are sRGB; data maps are linear;
- `KHR_materials_specular` is present on the hair (warm specular tint);
- the corneas are alpha-blended (draw after opaque).

## Suggested CORDEL milestones using Inez

1. **2.4 locomotion slice.** Extend the cgltf import to skins, joint
   hierarchies, `weights` and animation samplers. Load `inez_master.glb`.
   Play `Idle`/`Walk`/`Run` driven by the motor's speed, using the manifest's
   matching speeds so the feet do not slide. Gate the slice on the audit
   values in `INEZ_RIG_QA.md`:
   - boots on the ground within 1 cm during stance;
   - identity morphs unchanged after a minute of play.
2. **4.2 asset cooking.** Hash the GLB, decode KTX2/meshopt or re-encode to
   the cooked format, and record the identity-weight bake.
3. **4.4 animation layers.** Facial clips as an additive morph layer; turn
   and crouch one-shots with explicit root-yaw hand-off; head and eye look-at
   on top of clips (the Three.js viewer shows one implementation).

## Licences

- **Rig and skin weights.** CC0 MakeHuman assets
  (`model/base-source/LICENSE.ASSETS.md`).
- **Geometry and colour.** Taken from the user's own models (`source/`).
- **Scan data.** None. See `docs/INEZ_SCAN_SOURCE_EVALUATION.md`.

No third-party asset with redistribution limits is embedded.
