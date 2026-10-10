# Inez — THREE BEDROOM character

Inez is rebuilt from the user's own GLBs (`assets/characters/inez/source/`) on a rigged production body, with a Three.js viewer and an offline motion pipeline.

**State.** The character is rigged, animated, packaged and passes its browser checks. Her likeness is **not accepted**; the measured gaps are in [`assets/characters/inez/reports/INEZ_VISUAL_QA.md`](assets/characters/inez/reports/INEZ_VISUAL_QA.md). Progress and what's left: [`WORK_COMPLETED_AND_NEXT_STEPS.md`](WORK_COMPLETED_AND_NEXT_STEPS.md).

## Run the viewer

```bash
cd viewer
npm ci
npm run dev
```

Open http://localhost:4173/. The viewer loads `assets/characters/inez/model/inez_runtime.glb`. Add `?model=inez_master.glb` (or `inez_runtime_lod1.glb`, `inez_runtime_lod2.glb`) to load another export.

**Main viewer:**

- orbit, camera presets and lighting;
- material and wireframe inspection;
- WASD movement with idle, walk and run blending;
- turns and crouch;
- expressions, visemes, blink, gaze, jaw and head controls;
- the facial performance clips;
- a side-by-side comparison with the original images.

**Animation lab:**

- external retargeted clips, labelled by source;
- skeleton overlay;
- foot-contact markers with slip counters;
- root trail;
- the source motion as a stick figure;
- terrain presets;
- bone inspection.

## Checks

```bash
(cd viewer && npx vite --host 127.0.0.1 --port 4173) &
python3 tools/inez/browser_qa.py --revision browser_v02        # character: geometry, clips, morphs, controls
python3 tools/inez/browser_lab_qa.py --revision lab_v01        # external clips: labels, contact, travel
python3 tools/inez/browser_perf.py --label my_machine --gpu    # frame rate on this machine's GPU
node tools/inez/validate_glb.mjs assets/characters/inez/model/inez_runtime.glb assets/characters/inez/qa/technical/inez_runtime_validation.json
```

## Layout

| Path | Contents |
|---|---|
| `assets/characters/inez/` | The character: sources, master, exports, textures, rig, animation, renders, QA, reports ([README](assets/characters/inez/README.md)) |
| `docs/` | Identity, Three.js / CORDEL integration, the TERRA feasibility and integration status, the skeleton mapping, the animation pipeline, animation QA, motion licences |
| `tools/inez/` | Blender, packaging, measurement and browser QA scripts. `tools/inez/motion/` holds the motion bridge. |
| `viewer/` | Three.js 0.180 / Vite viewer |
| `references/` | The two original images (unchanged; authority for likeness) |
| `reports/` | Pointers and the historical reference-generation log |

The original images and the user's GLBs are never modified. Licences: `assets/characters/inez/model/base-source/` (CC0 MakeHuman base and rig), [`docs/INEZ_MOTION_LICENSES.md`](docs/INEZ_MOTION_LICENSES.md) (motion data).
