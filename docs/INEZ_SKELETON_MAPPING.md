# Inez skeleton mapping

Motion reaches Inez through one hand-off format, the **intermediate skeleton (ISK)**. It is defined in `tools/inez/motion/isk.py`.

- Each source has its own adapter that writes the ISK.
- `tools/inez/motion/retarget_to_inez.py` reads only the ISK and poses Inez's real rig in Blender.
- Bones are never matched by name between skeletons. Every mapping below goes through joint centres and segment rotations, in a common frame and relative to each skeleton's own rest pose.

## Common frame (ISK)

- **Units and axes.** Metres, right-handed, +Z up.
- **Facing.** The performer faces −Y at the first frame. This is the direction Inez faces in Blender; it is +Z in glTF and Three.js.
- **Positions.** World joint centres per frame.
- **Rotations.** World rotation of 7 segments *relative to the source's own rest pose* (identity = as in rest).
- **Rest positions.** The rest pose's joint centres, also turned to face −Y.
- **Contacts.** Optional per-foot support flags.
- **Validation.** `isk.validate()` checks:
  - the joint set and array shapes;
  - finite values and unit quaternions;
  - frame counts;
  - per-joint speed spikes (above 12 m/s) and per-segment rotation steps (above 30°/frame);
  - segment-length variation.

## Joint centres

| ISK joint | Inez bone (head position) | CMU ASF bone (end point) | MyoFullBody body (origin) |
|---|---|---|---|
| `pelvis` | `root` | `root` (position) | midpoint of `femur_l` / `femur_r` |
| `spine` | (spine05–01, distributed) | `lowerback` | `lumbar1` |
| `chest` | `neck01` | `thorax` | `cervical_spine` |
| `neck` | `head` | `upperneck` | `head` |
| `head` / `head_top` | — | mid / end of `head` | `head` origin + 8.5 / 17 cm along the head's rest up axis |
| `hip_l/r` | `upperleg01.L/R` | `lhipjoint` / `rhipjoint` | `femur_l` / `femur_r` |
| `knee_l/r` | `lowerleg01.L/R` | `lfemur` / `rfemur` | `tibia_l` / `tibia_r` |
| `ankle_l/r` | `foot.L/R` | `ltibia` / `rtibia` | `talus_l` / `talus_r` |
| `toe_l/r` (ball of foot) | `foot.L/R` tail | `lfoot` / `rfoot` | `toes_l` / `toes_r` |
| `shoulder_l/r` | `upperarm01.L/R` | `lclavicle` / `rclavicle` | `humerus_l` / `humerus_r` |
| `elbow_l/r` | `lowerarm01.L/R` | `lhumerus` / `rhumerus` | `ulna_l` / `ulna_r` |
| `wrist_l/r` | `wrist.L/R` | `lradius` / `rradius` | `lunate_l` / `lunate_r` |
| `hand_l/r` | (finger bases) | `lhand` / `rhand` | `3proxph_l` / `3proxph_r` |

**Segments.** The rest-relative rotations come from:

| ISK segment | CMU bone | MyoFullBody body |
|---|---|---|
| `pelvis` | `root` | `pelvis` |
| `chest` | `thorax` | `thorax` |
| `head` | `head` | `head` |
| `foot_l/r` | `lfoot` / `rfoot` | `calcn_l` / `calcn_r` |
| `hand_l/r` | `lhand` / `rhand` | `capitate_l` / `capitate_r` |

## How each Inez bone is driven

| Inez bones | Method | Why |
|---|---|---|
| `root` | **Rotation:** source pelvis rest-relative rotation × Inez's rest orientation. **Position:** Inez's standing pelvis plus the source pelvis motion scaled by the leg-length ratio, then lowered by a measured offset and per-frame reach drops (see *Contacts*). | The two rests are both upright standing poses. |
| `spine05` … `spine01` | The pelvis-to-chest relative rotation is spread over the 5 bones, slerped by k/5 | The chain has no 1:1 counterpart. |
| `neck01` … `neck03`, `head` | The chest-to-head relative rotation is spread over the 4 bones, slerped by k/4 | Same reason as the spine |
| `upperarm01`, `lowerarm01` | Aimed along the source shoulder→elbow and elbow→wrist directions with Inez's own segment lengths (`aim_chain`). Twist bones keep their inherited transform. | CMU rests in a T-pose, MyoFullBody with arms down, Inez in an A-pose. Rest-relative rotation would carry the wrong rest. |
| `wrist` | Neutral by default: along the forearm, palm rolled toward the body, fingers relaxed 10°. `--hand-mode source` aims along the source hand segment instead. | Optical hand segments are noisy. In CMU 02_01 they produced open, palm-forward hands. |
| `upperleg01`, `lowerleg01` | Two-bone IK from Inez's hip to an ankle target, the hip plus the source hip→ankle vector scaled by the leg-length ratio. The knee plane comes from the source knee. | Keeps the source's leg geometry at Inez's size |
| `foot` | World rotation = rest-relative swing of the source ankle→toe direction × Inez's rest foot | It must not depend on the shin, so the contact planner and the bake agree. |
| `toe*`, `finger*` (other), facial bones | Unchanged (bind pose), except the finger curl | No source data |
| `hair.01`–`04` | Damped spring chain simulated per frame on the posed head (3.2 / 2.6 / 2.1 / 1.7 Hz, ζ 0.32) | Secondary motion; TERRA and mocap do not model hair |

## Contacts (Inez side)

Inez wears boots with 4.6 cm platform soles. Their support points come from the boot mesh (`boot_vectors`), so contact is solved on her actual soles.

1. **Free solve.** Then the median floating height of planted soles becomes a constant pelvis offset. The sources' rest poses hold the feet differently from stance, so their rest pelvis height does not put Inez's soles on the floor.
2. **Rolling no-slip plan.**
   - Each stance phase is anchored at mid-stance and integrated outward.
   - Between frames, the sole point in contact at the later frame keeps its ground position, so the foot rolls heel to toe without slipping. That point is put at the floor height.
   - Lift-off and touchdown blend over three frames.
3. **Swing clearance.** The lowest sole point stays at least 3 mm above the floor.
4. **Reach.** Where a planted leg could not reach, the pelvis is lowered. This uses a 5-frame running maximum, then a 5-frame mean.
5. **In place.** The straight-line average root velocity is removed. It is reported as the clip's matching speed, and the viewer moves the character at that speed.

## Source-specific notes

- **CMU ASF/AMC.**
  - Acclaim forward kinematics, world rotation = parent · C · M · C⁻¹, in Rz·Ry·Rx order.
  - Units ×0.056444 m.
  - Y up converted to Z up.
  - The zero pose is the rest pose: T-pose arms, facing −Y after conversion.
- **TERRA / MyoFullBody.**
  - Z up and already facing −Y at `qpos0`, which is the rest pose (anatomical position, arms down).
  - MuJoCo forward kinematics runs with `qpos` columns matched to model joints by name.
  - TERRA fits the SMPL body to the robot, so the stock model is used for forward kinematics.
  - Relevant joints: `hip_flexion/adduction/rotation_l/r`; `knee_angle_l/r` (0–120°, positive = flexion); `ankle_angle_l/r`; `subtalar_angle_l/r`; `mtp_angle_l/r`; lumbar `flex_extension`, `lat_bending`, `axial_rotation`; the shoulder `elv_angle` / `shoulder_elv` / `shoulder_rot`; `elbow_flex`; `pro_sup`.
  - Muscle and tendon states are not used.
- **Not transferred:**
  - fingers (except relaxed curl), toes and face;
  - muscle activations;
  - the clavicles, which follow the chest; MyoFullBody's sternoclavicular and acromioclavicular joints are left out.

## Checks run on every retargeted clip

These are written to `animation/qa/<clip>_retarget.json`:

- ISK validation;
- every driven bone keyed; unit quaternions;
- largest per-frame rotation step (fails above 30°);
- frame count preserved against the source duration;
- IK reach error;
- stance slip per phase, before and after the contact pass;
- lowest sole height (penetration);
- planted sole height range;
- root path length (source, scaled source, Inez);
- knee flexion (stance mean and maximum, swing maximum) and trunk lean, for source and Inez side by side.
