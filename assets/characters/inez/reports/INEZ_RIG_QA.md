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
| Eyes and lashes | Eye bones and lid bones, as built by the dressed base. The tearline strips were removed in pass 3: they rendered as pale wedges at the inner corners. |
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
| Blink | Morphs `Blink_L` / `Blink_R` on the body's face and the lashes. `Blink` clip on the lid bones. Facial clip `Expr_Blink`. Viewer auto-blink. |
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

| Clip | Duration (s) | Loop | Matching speed (m/s) | Pelvis drop range (cm) | IK reach error (mm) | Boot-ground error (mm) | Loop ankle error (mm) |
|---|---|---|---|---|---|---|---|
| Idle | 4.00 | yes | — | -1.2 … -1.2 | 0.0 | 0.0 | 0.0 |
| Walk | 1.08 | yes | 0.92 | -6.3 … -1.9 | 0.0 | 8.7 | 0.0 |
| Run | 0.75 | yes | 2.40 | -10.7 … -3.5 | 0.0 | 8.3 | 0.0 |
| LookAround | 6.00 | yes | — | — | 0.0 | 0.0 | 0.0 |
| TurnLeft | 1.21 | one-shot | — | — | 0.0 | 7.1 | — |
| TurnRight | 1.21 | one-shot | — | — | 0.0 | 7.1 | — |
| CrouchDown | 0.79 | one-shot | — | — | 0.0 | 0.0 | — |
| CrouchUp | 0.79 | one-shot | — | — | 0.0 | 0.0 | — |
| Crouch | 3.00 | yes | — | — | 0.0 | 0.0 | 0.0 |
| Blink | 0.21 | yes | — | — | — | — | — |

| Identity layer | Default after the bake |
|---|---|
| `Inez_HeadFit_v01` | 0 |
| `Inez_HeadFit_v02` | 0 |
| `Inez_HeadFit_v03` | 1 |
| `Inez_HeadRefine_v05` | 1 |
| `Inez_SourceBodyFit_v05` | 1 |
| `Inez_SourceHeadWrap_v05` | 1 |
| `Inez_FaceCorrect_v05` | 1 |

| Mesh | Vertices >4 influences (pruned) | Max discarded weight | Unweighted |
|---|---|---|---|
| Inez_Sweater | 9665 | 0.265 | 0 |
| Inez_Jeans | 8706 | 0.131 | 0 |
| Inez_Boots | 0 | 0.000 | 0 |
| Inez_Hair | 0 | 0.000 | 0 |
| Inez_FineSilverNecklace | 915 | 0.060 | 0 |
| Inez_TeethUpper | 0 | 0.000 | 0 |
| Inez_TeethLower | 0 | 0.000 | 0 |
| Inez_Tongue | 0 | 0.000 | 0 |
| Inez_ContinuousHumanMesh_UNAPPROVED | 1359 | 0.300 | 0 |
| Inez_Eyeball_L | 0 | 0.000 | 0 |
| Inez_Eyeball_R | 0 | 0.000 | 0 |
| Inez_Iris_L | 0 | 0.000 | 0 |
| Inez_Iris_R | 0 | 0.000 | 0 |
| Inez_Cornea_L | 0 | 0.000 | 0 |
| Inez_Cornea_R | 0 | 0.000 | 0 |
| Inez_LashesUpper_L | 0 | 0.000 | 0 |
| Inez_LashesLower_L | 0 | 0.000 | 0 |
| Inez_LashesUpper_R | 0 | 0.000 | 0 |
| Inez_LashesLower_R | 0 | 0.000 | 0 |
| Inez_Sweater_HoleFill | 1428 | 0.218 | 0 |

| Mesh with facial controls | Targets | Max displacement (mm) |
|---|---|---|
| Inez_ContinuousHumanMesh_UNAPPROVED | 14 | 26.7 |
| Inez_TeethLower | 14 | 25.7 |
| Inez_Tongue | 14 | 23.1 |
| Inez_LashesUpper_L | 14 | 4.2 |
| Inez_LashesLower_L | 14 | 7.5 |
| Inez_LashesUpper_R | 14 | 4.1 |
| Inez_LashesLower_R | 14 | 6.8 |


- Ponytail: 4 deforming bones inside the Asset B hair shell, head-blended root; bones ['hair.01', 'hair.02', 'hair.03', 'hair.04']; 26128 shell vertices; span 0.372 m
- Bones: 167; weight failures: []

## 5. Audit results

- **Feet.** Boots stay within 8.7 mm of the ground during the walk's planted
  frames and 8.3 mm in the run. The heel-strike and toe-off pitch frames
  account for this. Turns stay within 7.1 mm; Idle, LookAround and crouch
  within 0.1 mm.
  - **Foot slip.** The per-boot audit on the deformed mesh
    (`tools/inez/boot_contact_audit.py`, `qa/technical/boot_contact_audit.json`)
    measured slip for the first time. At the matching speed the planted boots
    slide 45 / 49 mm (L / R) per stance in `Walk` and 36 / 69 mm in `Run`,
    5–19 mm in the turns, and 42–45 mm in `CrouchDown` / `CrouchUp`. Idle,
    LookAround and the crouch loop hold within 0.01 mm. These are open
    defects of the procedural gait; see `docs/INEZ_ANIMATION_QA.md`.
  - The earlier per-side ground figures took the lowest point of the whole
    boots mesh, which holds both boots, so a floating stance boot could hide
    behind the other one. The audit now splits the boots by skin weight.
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
    lower teeth and tongue with the jaw, and the lashes with the lids.
  - The body exports as two primitives, one per material. The facial
    targets live on the face primitive (`..._Geometry_1` in Three.js); the
    torso primitive carries only the jaw-weighted neck vertices. The browser
    check samples the face primitive.
  - Lateral lip motion fades to zero across the 12 mm either side of the
    midline. A hard sign switch had folded the philtrum into a crease in the
    OH viseme.
- **Mouth.** Teeth and tongue are built from the MakeHuman helpers at the
  fitted positions. The upper arch is lowered 5.5 mm so about 3 mm of incisor
  shows in an open mouth, and none shows at rest. See
  `renders/rig_review/expr_Viseme_AA.png` and `expr_Viseme_OH.png`.

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
- **Crouch.** The soles stay on the floor, but each foot slides about 27 mm
  outward and turns out about 8° during `CrouchDown`. That was missed by eye
  and measured by the audit above. The torso folds forward, the head stays
  level and the arms hang in front of the knees.
  - The sweater hem rides over the jeans' waistband with no gap.
  - The knit stretches at the shoulders at full depth; this is skinning only,
    with no corrective shapes.
- **Turns.** The feet step in two beats while the upper body leads. The
  planted boot slides 5–19 mm per phase at the pivot (audit above).
- **Ponytail.** It lags and settles in turns and the run and stays outside the
  sweater in the sampled frames. **No collision is solved**, so extreme
  manual head pitch can push it into the shoulders.

## 7. Limitations (not claimed as done)

- **Embedded clips are procedural.** They are computed from gait curves and
  IK. They read as plausible but carry no captured nuance. One motion-capture
  walk (CMU 02_01) is retargeted onto this rig as a separate clip file; see §8.
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

## 8. Retargeted motion-capture clip (separate file)

`animation/clips/inez_mocap_walk_cmu_02_01.glb` holds Inez's armature and a single action, `Mocap_Walk_CMU_02_01`. The viewer binds it to the loaded character by bone name; the character file itself is unchanged.

- **Source.** CMU motion capture, subject 02, trial 01 (walk). It is labelled `CMU mocap` in the viewer, not TERRA.
- **Route.** ASF/AMC → intermediate skeleton → `tools/inez/motion/retarget_to_inez.py` on this rig → baked → clip-only GLB.

Full method: `docs/INEZ_SKELETON_MAPPING.md`. Metrics: `animation/qa/inez_mocap_walk_cmu_02_01_retarget.json`.

| Measure | Contact-corrected | Raw (`_Raw`, comparison only) |
|---|---|---|
| Frames (30 fps) / duration | 86 / 2.83 s (source 343 at 120 Hz, 2.85 s) | same |
| Matching speed (in place) | 1.128 m/s | same |
| Largest stance slip per phase (retargeter's support points) | 0.004 mm L, 0.006 mm R | 43.9 mm L, 47.5 mm R |
| Lowest sole point | −0.0006 mm | −41.7 mm (through the floor) |
| Planted sole height range | −0.0006 … +0.0013 mm | — |
| IK reach error | 0.0 mm | 0.0 mm |
| Largest rotation step per frame | 17.8° (`lowerleg01.L`) | — |
| Knee flexion, stance mean L / R (source) | 26.4° / 26.9° (26.6° / 25.3°) | — |
| Knee flexion, swing max L / R (source) | 73.6° / 74.1° (73.5° / 73.0°) | — |
| Trunk lean, mean (source) | −1.7° (+1.2°) | — |

The per-boot mesh audit and the browser check are in `docs/INEZ_ANIMATION_QA.md`.

**Correction rounds on this clip:**

1. The first bake put the soles 5 cm under the floor and slid them 4–7 cm per stance. This was fixed by the contact pass: the pelvis offset is taken from the median stance sole height, plus rolling no-slip anchoring and swing clearance.
2. The left knee bent 5–11° more than the source. The cause was a shared helper, `boot_vectors`: it took every vertex of the boots mesh, which holds both boots, as each foot's support points. Each foot therefore carried a phantom copy of the other boot about 20 cm to the side. Under the captured foot roll the phantom dipped below the real sole, so it was planted while the real left sole floated about 1 cm. Restricting each foot to its own boot removed the phantom. The knees now match the source within 1.6°.
3. The clip-only GLB export wrote a 0.2 s constant pose instead of the bake: inside the full character scene the exporter also picked up the character's own actions. The export now runs on a scene holding only the armature and the baked action, and the written file is read back and checked (`exported_clip_matches_bake`).

**Open item.** The trunk leans about 3° further back than the source, and the cause is not yet diagnosed. This was the third round, so it waits for the next run.
