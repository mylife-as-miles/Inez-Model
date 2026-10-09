# Inez — THREE BEDROOM character reconstruction

Editable character reconstruction and a standalone Three.js inspection/play viewer. **This is an unapproved production checkpoint, not a finished likeness or browser-validated playable character.**

See [Work completed and next steps](WORK_COMPLETED_AND_NEXT_STEPS.md) for the full handoff, evidence, limitations, and priorities.

## Run the viewer

```bash
cd viewer
npm ci
npm run dev
```

Open http://localhost:4173/. The viewer loads `assets/characters/inez/model/inez.glb`. Orbit, camera presets, lighting and material inspection are implemented. Movement, animation blending and facial controls require matching rig/clip/morph data in the loaded GLB. The canonical export at this checkpoint is the dressed rest-pose prototype; the separate animated prototype lives under `model/work/` and is awaiting runtime validation.

## Project files

- `docs/INEZ_CHARACTER_IDENTITY.md`: supported identity and reference uncertainties.
- `assets/characters/inez/`: original and generated references, editable Blender sources, GLB exports, textures, rig/animation work, real renders, and QA.
- `reports/INEZ_VISUAL_QA.md`: reference-generation and model review history.
- `tools/inez/`: reproducible modeling, animation, export, validation and packaging scripts.
- `viewer/`: Three.js / Vite application and viewer tests.

The original references retain final authority. Generated-reference approvals have explicit limited scopes; they are not blanket approvals of likeness or materials. Licensed base-mesh provenance and CC0 asset license are under `model/base-source/`. Dependencies, disposable caches, duplicate ImageGen originals, backup `.blend1` files and stale ZIP packages are excluded; their actual production copies and editable sources are retained.
