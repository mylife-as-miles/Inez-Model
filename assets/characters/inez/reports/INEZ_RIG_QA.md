# Inez rig and animation QA

**Subject.** The master Blender file `model/inez_master.blend` and every GLB
exported from it.

**How it is built.** `tools/inez/animation_build.py` runs on the assembled
master. The tables below are generated from `rig/animation_manifest.json` by
`tools/inez/rig_qa_tables.py`; they are measured values, not estimates.

**Evidence.**

- Contact strips of every clip: `renders/rig_review/*_strip.png`.
- Expression close-ups: `renders/rig_review/expr_*.png`.
- Browser checks: `qa/browser_browser_v02.json` and the frames in
  `renders/browser_v02/`.

## 1. Skeleton

**Humanoid.** 167 deforming joints. Of these, 163 come from the CC0 MakeHuman
default rig (`model/base-source/default.mhskel`, licence in
`LICENSE.ASSETS.md`):

- root, pelvis and spine
- neck01–03 and the head
- clavicles, arms, twist bones, hands and 15 finger joints per side
- legs, feet and toes
- face: jaw, eyes, upper and lower lids (`orbicularis03/04`), brows
  (`oculi`), lips (`oris`), cheeks (`risorius`, `levator`), tongue

**Ponytail.** Four bones, `hair.01`–`hair.04`, are added under `head` along
the centreline of the ponytail inside Asset B's hair shell.

**Bind pose.** A-pose. Bone rolls are the source's anatomical rolls; see
`bone_axes` in the manifest for the glTF bind axes of head, neck, eyes and
jaw.

## 2. Skinning

| Part | Method |
|---|---|
| Body | Licensed MakeHuman weights, kept through every identity layer |
| Sweater, jeans, necklace | Part-aware transfer. Each vertex takes the weights of the nearest body vertices of the same body part (arm, leg, torso), so a sleeve never inherits torso weights. Head and face bones are excluded and their share is handed to the neck, so the collar never opens with the jaw. |
| Boots | Below the ankle, rigid to `foot.L/R`: the dressed base removes the feet hidden inside the boots, so there is nothing to copy from. Shafts follow the shins. |
| Hair shell | `head`, plus the ponytail chain. The root of the tail and any hair lying on the scalp blend back to `head`, so the shell never tears. |
| Teeth and tongue | Upper teeth rigid to `head`. Lower teeth and tongue rigid to `jaw`. |
| Eyes, lashes, tearlines | Eye bones and lid bones, as built by the dressed base |
| Sweater hole-fill | Build weights, with face bones moved to `neck03` |

**Runtime limit.** Four influences per vertex, the limit of Three.js's
standard skinned mesh. The largest discarded share is reported below; the
remaining weights are renormalised. Per-mesh results are in the manifest
under `runtime_weight_adaptation` and `skin_weight_integrity`.

**Integrity.** Every vertex of every skinned mesh is weighted and normalised
(`weight_failures: []`).

## 3. Controls

| Required control | Implementation |
|---|---|
| Head / neck | `head`, `neck01–03` bones. The viewer's head yaw/pitch/roll sliders apply in head-relative space. |
| Eyes | `eye.L` / `eye.R` bones (rigid 12 mm eyeballs, iris, cornea). Gaze sliders ±25° / ±20°. |
| Blink | Morphs `Blink_L` / `Blink_R` on body, lashes and tearlines. `Blink` clip on the lid bones. Facial clip `Expr_Blink`. Viewer auto-blink. |
| Jaw | `jaw` bone with the lower teeth and tongue. Five visemes (AA, EE, OH, MM, FV) include the jaw rotation. |
| Blendshapes | Expressions `Neutral`, `Confused`, `Suspicious`, `SubtleFear`, `IntenseFear`, `Anger`, `Exhaustion`; visemes; blinks |
| Shoulders / arms / spine / hands | Bone chains. Baked clips drive spine01/03, arms, wrists and every finger; fingers curl into a loose fist in the run. |
| Legs / feet | Two-bone IK solved during the bake against planted foot targets; boot soles stay on the ground (§5) |
| Ponytail secondary motion | Damped spring chain (3.2 / 2.6 / 2.1 / 1.7 Hz, damping ratio 0.32) simulated per frame on the posed head and baked into every clip. Looping clips pre-roll two cycles so the baked loop starts in steady state. |

## 4. Clips

**Body clips** are in place and sampled at 24 fps:

- **Locomotion.** `Idle` (4 s breathing loop), `Walk`, `Run`.
- **Looking.** `LookAround`: head and neck sweep ±38° with the eyes leading.
- **Turns.** `TurnLeft` and `TurnRight`: 90° in place over two steps. These
  are one-shots; their final yaw is handed to the character transform by the
  viewer.
- **Crouch.** `CrouchDown`, a looping `Crouch` and `CrouchUp`.
- **Blink.** Lid bones.

**Facial clips** animate morph weights only and are added to the exported
GLB by `glb_expression_clips.py`:

| Clip | Duration (s) |
|---|---|
| `Expr_SubtleFear` | 3.0, with a blink |
| `Expr_Confusion` | 3.0 |
| `Expr_Anger` | 2.8 |
| `Expr_Exhaustion` | 4.0, with heavy lids |
| `Expr_IntenseFear` | 2.6 |
| `Expr_Suspicious` | 3.0 |
| `Expr_Blink` | 0.24 |

Each keyframe keeps every identity weight at its default.

The table is generated from the manifest:

- Boot-ground error is the lowest boot point during planted (stance)
  frames. One-shot and idle clips report the largest |lowest point| over all
  sampled frames.
- The loop ankle error compares the first and last frames.
- The pelvis drop is relative to the bind pose: the walk rises over
  mid-stance and dips in double support.

<!-- RIG_TABLES -->

## 5. Audit results

- **Feet.** Boots stay within 8.7 mm of the ground during the walk's planted
  frames and 8.3 mm in the run. The heel-strike and toe-off pitch frames
  account for this. Turns stay within 7.1 mm; Idle, LookAround and crouch
  within 0.1 mm.
  - Earlier failure, now fixed: the v01 gait used a constant pelvis drop that
    kept the knees bent, so it looked crouched.
  - Earlier failure, now fixed: the first transfer weighted the boot soles to
    the torso, so the soles sank 5–15 cm in motion.
- **Loops.** Ankle positions match exactly at loop seams (0.0 mm). The
  ponytail simulation is pre-rolled so its loop is continuous.
- **IK.** No target was out of reach in any clip (0.0 mm reach error).
- **Identity.** Every identity morph keeps its exact source default after the
  bake (table above). The browser check re-verifies this after playing body
  clips, static expressions and the facial clips.
- **Facial deformation.**
  - Expressions and visemes move the body up to about 27 mm (jaw in AA), the
    lower teeth and tongue with the jaw, and the lashes and tearlines with the
    lids.
  - Lateral lip motion fades to zero across the 12 mm either side of the
    midline. A hard sign switch had folded the philtrum into a crease in the
    OH viseme.
- **Mouth.** Teeth and tongue are built from the MakeHuman helpers at the
  fitted positions. The upper arch is lowered 5.5 mm so about 3 mm of incisor
  shows in an open mouth, and none shows at rest. See
  `renders/rig_review/mouth_*.png`.

## 6. Visual clipping review

**Method.** The strips were rendered on the final master with the neutral
studio rig and reviewed frame by frame.

**Findings:**

- **Walk.** Upright, heel-to-toe, natural arm swing (22°) and hip bob
  (4.4 cm).
  - The knees pass close together at mid-swing. The jeans' wide legs touch
    but do not pass through each other in the sampled frames.
  - There is no cloth simulation: the denim follows the leg rigidly.
- **Run.** Knees and elbows flexed, hands in loose fists from chest to hip.
  The large stance flexion (pelvis drop up to 10.7 cm) reads as a jog rather
  than a sprint.
- **Crouch.** Feet stay planted. The torso folds forward, the head stays level
  and the arms hang in front of the knees.
  - The sweater hem rides over the jeans' waistband with no gap.
  - The knit stretches at the shoulders at full depth; this is skinning only,
    with no corrective shapes.
- **Turns.** The feet step in two beats while the upper body leads. Up to
  about 7 mm of foot slide is possible at the pivot.
- **Ponytail.** It lags and settles in turns and the run and stays outside the
  sweater in the sampled frames. **No collision is solved**, so extreme
  manual head pitch can push it into the shoulders.

## 7. Limitations (not claimed as done)

- **Clips are procedural.** They are computed from gait curves and IK; there
  is no motion capture. They read as plausible but carry no captured nuance.
- **No root motion.** Locomotion is in place; the game moves the character.
  Turn clips hand over their yaw.
- **No corrective shapes or cloth simulation.** The garments deform by
  skinning alone, so extreme poses (deep crouch, arms overhead) will stretch
  the knit.
- **Ponytail.** Baked spring motion with no runtime physics. It does not
  react to gameplay accelerations beyond what the clips contain.
- **Expressions are restrained extrapolations.** The originals show only
  worried and sad faces; anger and confusion are plausible extrapolations,
  not references.
- **Viewer gaze and head controls** are additive overlays. They are not an
  IK look-at system.
