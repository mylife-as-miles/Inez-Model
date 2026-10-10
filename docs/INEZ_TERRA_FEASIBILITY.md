# TERRA for Inez: feasibility audit (Milestone 1)

**Date:** 2026-10-09.
**TERRA:** `github.com/amathislab/terra` at commit `db9d0d6` ("Publish end-to-end TERRA code and guides"), package `terra-retargeting` 1.0.0.

## Verdict

**What works.** A TERRA → Inez pipeline is technically possible, and its Inez half is built and tested. The TERRA environment installs and runs on this machine.

**Blocked: no licensed inputs.** TERRA could not be run on a real motion here. Every documented retargeting path needs the neutral SMPL-H body model, and these models and motions come only through registration and acceptance of their providers' terms:

- the SMPL-H body model for retargeting;
- SMPL-X or SMPL-H, again, for marker fitting;
- an AMASS motion, or another permitted recording.

None of these is in this environment, and no access controls were bypassed.

**Blocked: commercial use.** That use is not cleared for a commercial game. TERRA's code is Apache-2.0, but:

- its required `smplx` dependency is under MPI's non-commercial research licence;
- the SMPL-H, SMPL-X and AMASS terms are research-only;
- the MyoFullBody arm and hand definition derives from a model released "solely for non-commercial purposes".

Legal clearance is needed before any TERRA-derived clip ships in THREE BEDROOM.

**What was proven instead, with permitted data:**

- **One real motion-capture walk** (CMU, which permits inclusion in commercial products) was retargeted onto Inez's actual skeleton through the same intermediate skeleton a TERRA trajectory would use. It was baked, exported as a GLB clip and played in Three.js. It is labelled as CMU motion capture, not TERRA.
- **The TERRA adapter** (MyoFullBody `qpos` → MuJoCo forward kinematics → intermediate skeleton) was exercised on a clearly labelled synthetic MyoFullBody trajectory. That checks mechanics and signs only.

No TERRA output was produced, and none is claimed.

## 1. Project audit

| Item | Finding |
|---|---|
| Architecture | Asset repository with Blender pipeline tools (`tools/inez/`), the character under `assets/characters/inez/` and a Vite viewer (`viewer/`) |
| Engine target | THREE BEDROOM on Three.js. The native CORDEL engine is planned (`docs/INEZ_CORDEL_INTEGRATION.md`); its character motor (Phase 2.2) is not built yet. |
| Three.js | `three` 0.180.0 |
| Renderer | WebGL2 by default; WebGPU on request (`WebGPURenderer`) with fallback to WebGL2 |
| Skeleton | 167 joints: CC0 MakeHuman 163-bone humanoid (spine05–01, neck01–03, head, jaw, eyes, lids, lips, cheeks, 15 finger joints per hand, toes) plus `hair.01`–`hair.04` |
| Rest pose | A-pose, facing −Y in Blender (+Z in glTF) |
| Meshes | 20 skinned mesh objects, 21 primitives (the body has two materials): body, sweater, sweater hole fill, jeans, boots, hair shell, necklace, eyeballs, irises, corneas, four lash strips, upper and lower teeth, tongue |
| Skin weights | Four influences per vertex at runtime. The largest discarded share per vertex: body 0.30, sweater 0.265, hole fill 0.22, jeans 0.13. Measured in `rig/animation_manifest.json`. |
| Blendshapes | 14 controls: 7 expressions, 5 visemes, 2 blinks. Plus 7 identity layers that must keep their defaults. |
| Existing clips | `Idle`, `Walk`, `Run`, `LookAround`, `TurnLeft/Right`, `CrouchDown/Up`, `Crouch`, `Blink` (procedural, baked); seven facial clips |
| Character motor | None in this repository. The viewer moves the character for demonstration only. |

## 2. TERRA audit

### What it is (confirmed from the repository)

- **Purpose.** Terrain-aware retargeting of human motion onto the MyoFullBody musculoskeletal model. It is followed by PPO policy training on muscle-actuated control.
- **Four components:**
  1. motion loading and conversion;
  2. terrain reconstruction from contacts;
  3. retargeting to MyoFullBody;
  4. policy training.
  `terra retarget` runs 2 and 3.
- **MyoFullBody.** Model package `musclemimic_models` 1.0.6, Apache-2.0. It has 123 joints, nq = 129, 102 bodies and a free root. Its rest pose (`qpos0`) is the anatomical position, Z up, facing −Y.

### Inputs (confirmed)

| Input | Requirement |
|---|---|
| AMASS SMPL-H `.npz` | The neutral SMPL-H model (`SMPLH_NEUTRAL.pkl`, built from MPI's SMPL-H and MANO downloads) |
| C3D / TRC / MAT markers | A marker-fitting body model (SMPL-X by default, or SMPL-H) **and** SMPL-H for the robot retargeting. MAT needs an extraction schema; TRC needs its up axis. |
| Terrain | `auto` (reconstructed from contacts), `none` (flat), or a TerrainSpec JSON |

### Outputs (confirmed)

All under `<root>/MyoFullBody/terra/<name>`:

- **`<name>.npz`** — the MyoFullBody trajectory. It holds `qpos`, `qvel` and `frequency`, plus loco_mujoco `Trajectory` fields (`joint_names`, and optionally body and site kinematics).
- **`<name>_analysis.npz`** — run metadata.
- **`<name>_terrain.json`** — terrain metadata, when non-flat.

The public `terra.validate_retarget_artifacts(cache_root, name)` checks array shapes, finiteness and frequency. It returns the frame count, frequency, dimensions and non-flat status.

**Not a GLB animation API.** TERRA outputs MuJoCo joint coordinates for its own model. Nothing in it targets glTF or an arbitrary character.

### Training and GPUs (confirmed)

- A GPU is required for PPO training and for policy evaluation.
- Motion loading, retargeting and artifact checks run on CPU.
- A trained policy is a JAX network driving a muscle simulation. Running it in a browser is not supported or documented, and is not proposed here.

## 3. What was run here

| Step | Command | Result |
|---|---|---|
| Clone | `git clone https://github.com/amathislab/terra.git` | Commit `db9d0d6`, in `~/terra-src/terra`, outside this repository |
| Environment | `uv sync --locked --python 3.11 --extra dev` | Exit 0. `.venv` is 7.9 GB (CUDA 12.6 PyTorch wheel, as documented) |
| CLI | `terra --version`, `terra --help`, `terra retarget --help` | `1.0.0`; the commands are `convert`, `retarget`, `evaluate`, `reconstruct`, `run`, `visualize`, `train` |
| Unit tests | `pytest -q` | 802 passed, 11 skipped, 3 failed. The three failures pass when run alone (5 passed in those files), so they are test-order effects (OpenGL import, fork after JAX threads). The 11 skipped need `--runslow`, licensed inputs or four JAX devices. |
| Retarget a motion | `terra retarget …` | **Not run.** There is no SMPL-H model and no permitted AMASS or marker motion with a fitting model. |
| Visualize | `terra visualize …` | **Not run.** It needs published artifacts, and the container has no working OSMesa/OpenGL context (the GL test import failed). |
| Train | `terra train …` | **Not run.** There is no GPU, no data and no approved compute budget. |

## 4. Licences

The full table is in [`INEZ_MOTION_LICENSES.md`](INEZ_MOTION_LICENSES.md).

| Component | Terms | Commercial game use |
|---|---|---|
| TERRA code | Apache-2.0 | Permitted |
| `smplx` (required dependency) | MPI non-commercial research licence | **Not cleared.** It is a tool dependency; legal review is needed even if it is not shipped. |
| SMPL-H, MANO, SMPL-X models | MPI licences, registration, non-commercial research. Commercial licences are offered separately. | **Not cleared** |
| AMASS motions | Registration, non-commercial research | **Not cleared** |
| Gait120 markers (Figshare) | CC BY 4.0 | Permitted with attribution. TERRA still needs SMPL-X/H to fit them. |
| Vielemeyer ramp walking (Figshare) | CC BY 4.0 | Same as Gait120 |
| Darmstadt stair ambulation | Not verified (the provider page refused access) | Unknown |
| PRISM | Access form | Unknown |
| MuscleMimic, `musclemimic_models` | Apache-2.0. The NOTICE flags MoBL-ARMS (arm and hand) as "solely for non-commercial purposes". | **Flag for legal review** |
| CMU Graphics Lab mocap | "Free for use in research projects. You may include this data in commercially-sold products, but you may not resell this data directly, even in converted form." | Permitted; the acknowledgement text is requested |

## 5. Can Blender → TERRA → Blender work here?

| Step | Status |
|---|---|
| Supply a permitted motion to TERRA | **Blocked.** It needs the user's registered SMPL-H model plus a motion. |
| Run `terra retarget` | Possible on CPU once the inputs exist; the environment is installed |
| Validate with `validate_retarget_artifacts` | Implemented in `tools/inez/motion/terra_to_isk.py` (`--cache-root`/`--motion`) |
| MyoFullBody trajectory → joint transforms | Implemented: MuJoCo forward kinematics, joints matched by name, or stored body poses when present. Tested on synthetic input only. |
| Joint transforms → Inez's rig, baked | Implemented and tested with real mocap (CMU). The bridge is identical for TERRA. |
| Export a GLB clip and play it in Three.js | Implemented and tested |

## 6. The categories the brief asked to keep apart

**Implemented features** (working code, run here):

- intermediate-skeleton format and validator (`tools/inez/motion/isk.py`);
- CMU ASF/AMC adapter;
- TERRA MyoFullBody adapter;
- Blender retargeter onto Inez's rig, with rolling no-slip foot contacts, platform-boot sole clearance, pelvis correction, ponytail spring simulation and per-clip QA metrics;
- clip-only GLB export;
- viewer loading of external clips with source labels;
- the TERRA environment and its CLI.

**Confirmed TERRA capabilities** (from its code and docs, not run end to end here):

- terrain-aware retargeting of AMASS or marker motion to MyoFullBody;
- terrain reconstruction (stairs, ramps);
- artifact validation;
- MuJoCo video rendering;
- PPO training of muscle-actuated tracking policies.

**Proposed conversion logic** (designed and partly tested):

- TERRA `qpos` → forward kinematics → intermediate skeleton → Inez. Tested on synthetic `qpos`.
- Per-frame support heights from TERRA terrain for stairs. The adapter stores them; the retargeter's contact pass is flat-ground only so far.

**Unsupported:**

- TERRA directly producing glTF or Three.js clips;
- running TERRA or a trained policy in the browser;
- TERRA generating actions outside its data, such as sitting from a chair, leaning, stumbles or kneeling, unless such motions are supplied as input;
- secondary motion (hair, cloth), which TERRA does not model.

**Missing licensed assets:**

- the SMPL-H neutral model and MANO;
- SMPL-X, for marker input;
- any AMASS motion;
- commercial licences for all of these.

**Environment and GPU limitations:**

- 4 CPU cores, 15 GB RAM, no GPU;
- no working OpenGL/OSMesa context, so TERRA's videos cannot be rendered here;
- about 21 GB free disk after the 7.9 GB environment.

## 7. Decision needed from the owner

1. **Licensing path.** Pick one:
   - buy commercial SMPL/AMASS licences (via Meshcapade/MPI) and get legal sign-off on `smplx` and on the MoBL-ARMS-derived arm model;
   - use TERRA only for internal research, never for shipped clips;
   - skip TERRA for shipped content.
2. **If TERRA is used:** register at AMASS and MANO/SMPL-H, download the neutral SMPL-H model and the KIT `upstairs04` motion, and run the runbook in [`INEZ_ANIMATION_PIPELINE.md`](INEZ_ANIMATION_PIPELINE.md). The Inez side is ready.
3. **For shippable locomotion now:** CMU mocap (commercial inclusion permitted) through the same bridge. The CC BY marker sets (Gait120, ramps) would need a marker-to-skeleton fitter that does not depend on SMPL.
