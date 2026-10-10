# Inez animation pipeline: runbook

How a motion becomes a clip that plays on Inez in Three.js. Every step is a command in this repository or in TERRA's documented CLI. The method behind each step is in [`INEZ_SKELETON_MAPPING.md`](INEZ_SKELETON_MAPPING.md), the licence rules in [`INEZ_MOTION_LICENSES.md`](INEZ_MOTION_LICENSES.md), and the measured results in [`INEZ_ANIMATION_QA.md`](INEZ_ANIMATION_QA.md).

```
licensed motion ──adapter──> intermediate skeleton (.npz) ──retarget_to_inez.py (Blender, real rig)──>
    baked action ──clip-only GLB──> animation/clips/ ──runtime/clips.json──> viewer (bound by bone name)
```

Python, MuJoCo, TERRA and Blender run offline only. The browser loads GLB clips and JSON, nothing else. The viewer's only runtime dependency is `three`; `vite`, glTF-Transform and the glTF validator are development tools (`viewer/package.json`).

## Folders (`assets/characters/inez/animation/`)

| Folder | Holds |
|---|---|
| `terra_source/` | TERRA artifacts copied in for provenance: `<name>.npz`, `_analysis.npz`, `_terrain.json`. Empty until a licensed TERRA run exists. |
| `motion_inputs/` | Raw licensed source motions, e.g. `cmu/02.asf`, `02_01.amc`. Provenance only, never distributed as a motion pack. |
| `retargeted/` | Intermediate-skeleton files (`*_isk.npz`) |
| `blender/` | The baked action on Inez's armature, one `.blend` per clip |
| `clips/` | Clip-only GLBs: armature plus one action, no meshes |
| `runtime/` | `clips.json`, the viewer's manifest with source, licence, in-place flag and matching speed; per-clip source and target trajectories for the viewer lab |
| `previews/` | Cycles frames of each clip on the full model |
| `qa/` | Adapter, retarget and browser reports |

## A. Motion capture (CMU) — works today

```bash
# 1. Source -> intermediate skeleton (plain Python with numpy)
python3 -I tools/inez/motion/cmu_to_isk.py \
  assets/characters/inez/animation/motion_inputs/cmu/02.asf \
  assets/characters/inez/animation/motion_inputs/cmu/02_01.amc \
  assets/characters/inez/animation/retargeted/cmu_02_01_isk.npz \
  --name cmu_02_01_walk --report assets/characters/inez/animation/qa/cmu_02_01_isk_report.json

# 2. Retarget onto the real rig, bake, export (Blender 4.3, the animated master)
A=assets/characters/inez/animation
blender -b assets/characters/inez/model/inez_master.blend \
  --python tools/inez/motion/retarget_to_inez.py -- \
  --isk $A/retargeted/cmu_02_01_isk.npz --name Mocap_Walk_CMU_02_01 \
  --output-glb $A/clips/inez_mocap_walk_cmu_02_01.glb \
  --report $A/qa/inez_mocap_walk_cmu_02_01_retarget.json \
  --trajectory-json $A/runtime/inez_mocap_walk_cmu_02_01_trajectory.json \
  --preview-dir $A/previews/mocap_walk_cmu_02_01 \
  --save-blend $A/blender/inez_mocap_walk_cmu_02_01.blend
```

**Step 3: register the clip.** Add an entry to `animation/runtime/clips.json`, copying `matching_speed_m_s` from the retarget report. The fields are `name`, `file`, `trajectory`, `kind`, `terra`, `label`, `licence`, `in_place`, `matching_speed_m_s` and `report`.

**Step 4: check it in the browser.**

```bash
(cd viewer && npx vite --host 127.0.0.1 --port 4173) &
python3 tools/inez/browser_lab_qa.py --revision lab_v02
```

The retarget report's `checks` must all be true before a clip is registered. `exported_clip_matches_bake` reads the written GLB back. It guards against an exporter writing a different action than the one baked; that happened once (see QA).

**Options:**

| Option | Effect |
|---|---|
| `--no-contact-fix` | Skips the contact pass. Use it only for comparison clips. |
| `--root-motion` | Keeps travel in the clip instead of in place |
| `--hand-mode source` | Takes hand orientation from the source. The default, `forearm`, is a neutral relaxed hand. |
| `--finger-curl N` | Relaxed finger flexion in degrees |
| `--fps` | Bake rate. The default is 30. |

## B. TERRA — ready on the Inez side, blocked on licensed inputs

TERRA's environment is installed at `~/terra-src/terra/.venv` (commit `db9d0d6`), outside this repository.

**Prerequisites.** These are the owner's actions, through the providers' registration:

- `SMPLH_NEUTRAL.pkl`, built from MPI's SMPL-H and MANO downloads;
- a permitted motion. TERRA's tutorial uses AMASS `KIT/3/upstairs04_poses.npz`;
- for commercial shipping, licences and legal sign-off (feasibility §7).

```bash
# 1. TERRA retarget, CPU, from TERRA's README
source ~/terra-src/terra/.venv/bin/activate
export TERRA_MODEL_ROOT="$HOME/terra-models/smplh"
export TERRA_ARTIFACT_ROOT="$HOME/terra-results"
terra retarget "$HOME/terra-data/AMASS/KIT/3/upstairs04_poses.npz" \
  --smpl-model-path "$TERRA_MODEL_ROOT" \
  --output-root "$TERRA_ARTIFACT_ROOT/inez" --name KIT/upstairs04

# 2. Validate with TERRA's read-side API, then convert to the intermediate skeleton.
#    MuJoCo forward kinematics on MyoFullBody; runs inside TERRA's environment.
python tools/inez/motion/terra_to_isk.py \
  --cache-root "$TERRA_ARTIFACT_ROOT/inez" --motion KIT/upstairs04 \
  assets/characters/inez/animation/retargeted/terra_kit_upstairs04_isk.npz \
  --report assets/characters/inez/animation/qa/terra_kit_upstairs04_isk_report.json

# 3. Copy the TERRA artifacts into animation/terra_source/ for provenance.
```

Steps 4 to 6 are the same as A.2 to A.4, with `--name Terra_Upstairs_KIT_04`. The manifest entry must carry `"kind": "terra", "terra": true` and the licence of the source motion. The viewer then labels the clip `TERRA`.

**Known gap for stairs and ramps.** The adapter stores per-frame support heights from TERRA's terrain. The retargeter's contact pass assumes flat ground so far. A stair clip would retarget with its feet on z = 0 until the contact pass reads those heights. That is milestone 4 on non-flat terrain.

**Never run here without an approved budget:** `terra train`, which needs a GPU, and policy evaluation. Both are research tools; nothing in the game depends on them.

## C. Procedural clips (embedded in the character GLB)

`Idle`, `Walk`, `Run`, `LookAround`, the turns, the crouch set, `Blink` and the facial `Expr_*` clips are built by `tools/inez/animation_build.py` and `glb_expression_clips.py` during packaging (`tools/inez/package_character.py`). They live inside `model/inez_runtime*.glb`. The viewer labels them `procedural`.

## D. Rules

- The character GLBs are never rewritten by the motion pipeline. External clips are separate files bound by bone name.
- A clip's source label comes only from `clips.json`. The viewer shows `procedural`, `CMU mocap`, `TERRA` or `synthetic test`.
- At most three correction rounds per clip in a run. Each round is a retarget with changed options or code, followed by both QA reports.
