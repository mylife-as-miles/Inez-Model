# TERRA integration for Inez: status

**Short version.** The Inez side of a TERRA pipeline is built and proven with real, permitted motion capture. TERRA itself has **not** produced any motion for Inez. Every documented TERRA retargeting path needs the SMPL-H body model, which comes only through registration. Its terms, and those of AMASS and `smplx`, do not cover a commercial game. The details are in [`INEZ_TERRA_FEASIBILITY.md`](INEZ_TERRA_FEASIBILITY.md).

No clip in this repository is TERRA-generated, and the viewer labels none as TERRA.

## What TERRA is and is not, for this project

| TERRA produces | TERRA does not produce |
|---|---|
| MyoFullBody joint trajectories (`qpos`, `qvel`, frequency) in an `.npz` | glTF, GLB, FBX or Three.js clips |
| Reconstructed terrain metadata for stairs and ramps (`_terrain.json`) | Anything on Inez's skeleton. Its output is on its own 123-joint musculoskeletal model. |
| Trained muscle-actuated tracking policies (GPU) | A runtime that can run in a browser |

So TERRA is at most a **source of motion**. A MyoFullBody trajectory is not compatible with Inez's skeleton as is. It goes through forward kinematics, the intermediate skeleton and the same retargeter as any other source.

## Architecture

```
TERRA (offline, its own venv)                 this repository (offline)                         browser
─────────────────────────────                 ────────────────────────────────────────          ─────────────────────
AMASS/markers + SMPL-H ─ terra retarget ─> qpos .npz ─ terra_to_isk.py (MuJoCo FK) ─> ISK .npz ─┐
CMU ASF/AMC ───────────────────────────────────────── cmu_to_isk.py (Acclaim FK) ──> ISK .npz ─┤
                                                                                                ├─ retarget_to_inez.py ─> clip GLB ─> AnimationLab
                                                    (any future source adapter) ─> ISK .npz ─┘   (Blender, real rig)     + clips.json   (bound by bone name)
```

- **The intermediate skeleton** (`tools/inez/motion/isk.py`) is the only contract between sources and Inez. It carries the source and licence metadata, which flow into the retarget report and the viewer label.
- **The retargeter** works on the animated master, the same rig as every exported GLB. It never edits the character files; clips are separate GLBs.
- **The viewer** (`viewer/src/animation-lab.js`) loads `animation/runtime/clips.json`, binds each clip to the loaded Inez by bone name, and tags it `procedural`, `CMU mocap`, `TERRA` or `synthetic test`. It also offers:
  - in-place travel at the clip's matching speed;
  - contact markers with a per-phase slip counter;
  - the root trail and the source stick figure for side-by-side comparison;
  - terrain presets;
  - bone inspection;
  - per-frame CPU timing.

## Milestones

| # | Milestone | Status | Evidence |
|---|---|---|---|
| 1 | Feasibility report and skeleton mapping | **Done** | `INEZ_TERRA_FEASIBILITY.md`, `INEZ_SKELETON_MAPPING.md`, `INEZ_MOTION_LICENSES.md` |
| 2 | First licensed motion through TERRA | **Blocked.** It needs the owner's SMPL-H registration, a permitted motion, and a licensing decision for commercial use. | Feasibility §3, §7 |
| 3 | Retarget, bake and play on the real Inez in Three.js | **Done for CMU motion capture**, through the bridge a TERRA trajectory would use. The TERRA adapter is tested only on a labelled synthetic MyoFullBody trajectory (below). | `INEZ_ANIMATION_QA.md`; `animation/clips/`; `animation/qa/` |
| 4 | Contact correction | **Done on flat ground**: rolling no-slip stance, platform-boot soles on the floor, swing clearance. **Not done on stairs or ramps.** The adapter keeps TERRA's support heights; the contact pass does not read them yet. | `INEZ_ANIMATION_QA.md` |
| 5 | Locomotion library | **Not started.** There is one captured walk. The procedural walk, run, turns and crouch remain the shipped set. | — |
| 6 | Horror animation layers | **Not started** as motion layers. Facial expressions and clips exist (fear, exhaustion, confusion, anger, suspicion). | `reports/INEZ_RIG_QA.md` |
| 7 | Game integration | **Viewer only.** No character motor exists in THREE BEDROOM or CORDEL yet. | `reports/INEZ_INTEGRATION.md`, `INEZ_CORDEL_INTEGRATION.md` |

## Adapter test on synthetic TERRA-format input (mechanics only)

`terra_to_isk.py --synthetic-test` writes a MyoFullBody trajectory in TERRA's file layout, driving five joints with known curves:

- `hip_flexion_l/r`;
- `knee_angle_l/r`, where positive is flexion over the model's 0–120° range;
- `elbow_flex_l`.

It then converts that trajectory through MuJoCo forward kinematics, with joints matched by name.

**Result:**

- 120 frames at 60 Hz.
- The intermediate skeleton validated with no errors or warnings.
- Rest pelvis height 0.921 m; rest head top 1.771 m.
- The test exposed a knee sign error in the adapter; it was fixed so that positive means flexion.

The data is **synthetic**: it is labelled `synthetic_myofullbody_test`, it was not committed as animation, and it is not a TERRA output. It shows the adapter's mechanics only, not motion quality.

## What the owner needs to decide

1. **Licensing.** The options are:
   - commercial SMPL/AMASS licences plus legal sign-off on `smplx` and the MyoFullBody arm;
   - TERRA for internal research only;
   - no TERRA in shipped content.
2. **If TERRA goes ahead:** provide the SMPL-H neutral model and a permitted motion, then run section B of [`INEZ_ANIMATION_PIPELINE.md`](INEZ_ANIMATION_PIPELINE.md). No training or GPU spend is needed for retargeting.
3. **Either way:** CMU motion capture (commercial inclusion permitted, with the acknowledgement) can fill milestone 5 through the same bridge today.

## Constraints kept

- No TERRA-generated clip is claimed. The only external clip is labelled CMU motion capture.
- No scientific Python, MuJoCo or simulation code reaches the browser build.
- No reinforcement-learning training was run.
- No registration or access control was bypassed. No unlicensed dataset is in the repository.
- The original character GLBs and the user's source GLBs are untouched.
