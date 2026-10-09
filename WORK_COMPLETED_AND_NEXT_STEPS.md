# Inez production handoff — 2026-10-09

## Current outcome

The repository contains actual editable 3D geometry, UVs, a fitted humanoid rig, authored PBR maps, exported GLBs, a Three.js viewer, reference-generation work and independent review reports. **Inez is not production approved. The requested fully playable, visually validated character is still incomplete.** No generated portrait is presented as a screenshot of the 3D character.

## Work completed

1. Inspected both supplied images and preserved their original bytes in `assets/characters/inez/references/original/`. Created `docs/INEZ_CHARACTER_IDENTITY.md` covering facial landmarks, costume, hair, proportions and details that cannot reliably be inferred. Portraits govern facial identity; the body sheet governs costume and silhouette.
2. Used the built-in ImageGen tool with original identity anchors. Recorded 22 calls against the initial cap of 24, including failed calls. Produced all 13 requested individual reference outputs, retained candidates and prompts, and assembled `references/approved/INEZ_MASTER_TURNAROUND.png` from individual images using Pillow. Independent identity and technical critics reviewed candidates and refinements. Approval scope is recorded per image: body views are geometry-only, and several closeups are qualitative guides. Warm boot welts, scratched denim, long ponytail variants and invented pendant details remain excluded.
3. Acquired and documented a CC0 MakeHuman base mesh, UVs and skeleton. Own Blender Python scripts fit continuous topology to Inez rather than building a primitive mannequin. Preserved head versions v01–v03, actual clay renders and independent critiques. The v03 head passed an initial geometry credibility gate only; its technical facial identity assessment was 30/35, below the required 32/35 final target.
4. Built dressed geometry: fitted sweater, jeans, boots, lace details, eyes/cornea, brows/lashes, necklace and hair meshes. Authored 42 albedo/roughness/normal maps. `model/inez.blend` is editable; `model/inez.glb` is the canonical dressed rest-pose prototype. The export contains 85 skinned meshes, UVs, embedded textures and a 163-bone skeleton. Actual Blender renders are stored under `renders/`.
5. Produced a separate editable animation prototype in `model/work/inez_animated_v01.blend` and `.glb`, with a reported 166-bone rig, Idle/Walk/Run/Blink clips, expression/viseme work and ponytail bones. Build evidence is in `qa/animation_v01_build.json`. These files are staging outputs, not a declaration that browser animation, deformation, contacts or likeness passed. They do not overwrite the canonical dressed export at this checkpoint.
6. Implemented a standalone Three.js 0.180 / Vite viewer using GLTFLoader and AnimationMixer: orbit/zoom, face/body presets, studio/apartment lighting adjustments, reference comparison, material/wireframe inspection, measured renderer statistics, camera-relative keyboard locomotion, idle/walk/run blending, facial/viseme controls and a deterministic browser QA API. WebGL2 is the default; optional WebGPU remains unvalidated.
7. Added build, GLB and browser QA tools. Viewer build and synthetic control regressions passed; those tests do not certify the actual character. Khronos validation of the canonical dressed GLB reported zero errors and 85 `NODE_SKINNED_MESH_NON_ROOT` warnings. A real Chromium load reached viewer ready state, but screenshot capture timed out; no successful actual browser screenshot or playable-animation acceptance is claimed.

## Known failures and limitations

- Actual dressed render reveals a sweater that follows the bust too closely instead of the loose reference silhouette, incorrect dark shoulder stripe patches, exposed skin at jean/boot interfaces, toes protruding at boot edges, a stray forearm seam line, and hair crown shape/color requiring correction.
- Head likeness remains below the final facial acceptance target. Lip/lid regularity, nose planes and clean lower-face surface need further original-reference comparison and skilled geometry work.
- True side-view depth, exact pendant motif, physical height, hidden anatomy and underside boot construction are not determined by the originals. A 1.7 m height is provisional, not reference evidence.
- Actual animation export deformation, loops, foot contacts, clothing/hair clipping, facial targets and Three.js blending still need validation. A generated reference approval cannot satisfy this gate.
- Real browser capture/performance is unresolved in the software-GPU environment. WebGPU/hardware compatibility is not established. The viewer's implemented controls must not be mistaken for completed model-dependent QA.

## Next steps, in priority order

1. Correct dressed geometry in a separate v04 source while preserving the reviewed v03 head and original references. Fix loose sweater silhouette and stripe construction, boot enclosure, cuff coverage and stray seams. Restore original ponytail/crown/framing curls and material colors. Render front/profile/back before accepting the revision.
2. Review the staged animated GLB and build report; validate actual skin deformation, normalized runtime weights, morph defaults, facial/viseme targets, Idle/Walk/Run loops, feet, secondary hair and clothing clipping. Preserve `Inez_HeadFit_v01=0`, `v02=0`, `v03=1`; do not turn all fit targets on. Transfer verified motion to corrected geometry and promote source/export together only after validation.
3. Resolve Chromium capture/performance, then run `tools/inez/browser_qa.py` against the real animated asset. Capture actual front/left/right/three-quarter portraits, body front/side/back, neutral/fear and apartment-light screenshots, plus walk/run evidence. Inspect real vertex deformation and blending, not just animation names.
4. Have independent identity and technical critics compare those real screenshots directly with both originals. Iterate geometry, materials and rigging until the required 90/100 overall and 32/35 facial thresholds are supported with deductions explained, without critical anatomy/cropping failures. Manual sculpting may be needed for final likeness.
5. Resolve the GLB skin hierarchy warnings and optimize hair, material draw calls and texture memory after correctness. Verify color spaces, physically based response, scale, UVs, textures and engine integration on target hardware.
6. Only after actual browser QA passes, create a distributable using `tools/inez/package_playable.py`, update production status and integration docs, and perform the final game-engine acceptance. Until then preserve prototype labels.

## Reproduction and evidence

Run the viewer with `cd viewer && npm ci && npm run dev` and open http://localhost:4173/. Build with `npm run build`; control tests use `node --test qa/character-controls.test.mjs` from `viewer/`. The application public directory is `assets/`, and its default URL is `/characters/inez/model/inez.glb`.

Modeling scripts require Blender 4.3-compatible Python, NumPy/Pillow where used and the documented base-source files. Browser tools require Python Playwright and Chromium. Consult script arguments and retained build logs before rerunning: some scripts overwrite outputs. Avoid rebuilding accepted reference images or source files unintentionally.

Key evidence: `reports/INEZ_VISUAL_QA.md`, `qa/generation_ledger.json`, `qa/identity/`, `qa/technical/`, `qa/model/`, `qa/glb_validation.json`, `qa/animation_v01_build.json`, `rig/`, `animations/`, and `renders/` under the Inez asset directory. Per-image `.scope.json` files constrain generated-reference approvals. Generation budget has two unused calls; the extended front-body refinement allowance has been used. Further paid generation beyond authorized limits requires renewed authorization; no new generation is necessary to publish this checkpoint.

Original SHA-256 values: portraits `ce76f4cc025d81b5eb54b41e864c6aa53c0039b2889d607f385cbd632f6a764b`; turnaround `9482e1a589ac7cde2da520680400e9b32c38daaddecafb7ea2badaa5b2f64d39`.

Git excludes installed dependencies, build distributions, Python caches, duplicate generator-output files, scratch directories, stale ZIPs and Blender backup duplicates. Current editable sources, meaningful versioned sources, real asset exports, original/generated/approved references, authored textures and QA reports are included. No API credentials belong in this repository.
