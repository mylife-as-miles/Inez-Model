# Digital-human skin work: status and handoff (2026-10-10)

**Read this first.** The AAA digital-human work is an **unfinished, unvalidated experiment**. The user judged the result worse than the existing look, and the evidence I captured agrees. Nothing here is approved, and **nothing in the main viewer (`viewer/index.html`) was changed by it**. The new code lives only in `viewer/digital-human.html` and `viewer/src/rendering/digital-human/`. The default character, GLBs and main viewer are as committed in `14b8452`.

## What exists (all committed, all experimental)

| Piece | Where | State |
|---|---|---|
| Research notes (GPU Gems 3 ch.14, Epic digital humans, three.js 0.180 API mapping) | `docs/INEZ_DIGITAL_HUMAN_RESEARCH.md` | Written from fetched sources. Pixar RenderMan page and three.js docs pages **not read**. |
| Lab app (WebGPURenderer, WebGL2 backend, TSL), controls, QA API `window.inezDH` | `viewer/digital-human.html`, `viewer/src/rendering/digital-human/app.ts` | Loads and renders on WebGL2. Controls are wired to real uniforms. |
| TSL skin material (calibrated albedo gain, region roughness, micro-normal, cavity) | `skin/skin-material.ts`, `attach.ts` | Renders, but looks **worse** than the original (see below). |
| Identity-layer normal correction (recompute normals for the seven identity morphs) | `skin/identity-normals.ts` | Unit-tested on a synthetic sphere. On Inez it changes normals by median 4.9 deg, p95 15 deg, max 156 deg vs the linear delta sum. **Not visually proven to be an improvement.** |
| SSS profiles (six-Gaussian skin data + reductions) | `skin/profiles.ts` | Data and tests only. **No SSS pass is implemented.** |
| Lighting presets A-F (black-body colours, PMREM room env) | `lighting/presets.ts` | Built; only studio was rendered. |
| Albedo calibration from the originals | `tools/inez/dh_skin_calibration.py` -> `textures/digital_human/skin_calibration.json` | Gain about 2.0-2.4x per channel. Likely **too bright and too pink**; unverified. |
| Procedural micro-normal tile | `tools/inez/dh_skin_detail.py` | Generated, looked plausible as a texture; its effect on the face was never judged. |
| Capture tool | `tools/inez/dh_lab_capture.py` | Works. Fixed camera/preset, one config per run. |
| Tests | `viewer/src/rendering/digital-human/tests/` | 8 pass (`npm test` also runs the older 6). Type check passes (`npm run typecheck`). |

**Not started:** screen-space or texture-space SSS, ear transmission, refractive eyes, hair shading, peach fuzz, depth of field, quality presets, GPU benchmarks. Do not describe any of them as done.

## Why it looks worse (evidence and honest unknowns)

- The single successful lab render (`TSL skin`, studio light, neutral tone mapping) shows a pale, pink, flat face with strong freckles and less depth than the earlier Cycles and viewer renders. Cause not isolated: candidates are (1) the ~2x albedo gain, (2) the calibration targeting a skin/knit luminance ratio from one panel, (3) the neutral tone mapping and studio rig, (4) the region/micro/cavity terms.
- The planned controlled comparison (A GLB+ACES, B normals fixed, C neutral tone map, D TSL uncalibrated, E calibrated, F region roughness, G micro detail) **never completed**: the capture of config A hung. Its frames were exploded geometry, so I deleted them. There is **no before/after evidence** for any step.
- The user's question "why is the face darker" was about the *existing* viewer: it measured skin luminance 0.07 in the browser against 0.148 in the original panel and 0.265 in the Cycles render (AgX + bright area light). That is lighting and tone mapping, not albedo (albedo median luminance is 0.115). I did not resolve it.

## Open bug that blocks all comparisons

On the **WebGL2 backend of `WebGPURenderer`**, with the runtime GLB (`inez_runtime.glb`), the body renders as **exploded faces whenever the GLB's own `MeshStandardMaterial` is used with the GLB's own normals** (`?materials=glb&normals=glb`). With the recomputed normals (`normals=fixed`) or the TSL skin material the face renders. I ruled out: morph packing code (reads normalised values correctly), missing tangents (tangent attribute already exists, Int16 normalized, non-interleaved). Geometry facts from the browser probe: position and normal are **interleaved normalized Int16**; morph position and normal targets are the same; `morphTargetsRelative` is true; 21 targets. Unproven suspect: an interleaved-quantized `NORMAL` morph target path in the node renderer. First experiments: load `inez_master.glb` (float, not quantized) in the same URL; disable normal morph targets; compare `WebGLRenderer` (legacy viewer renders this GLB fine).

## Platform facts

- **WebGPU is unusable here.** Chromium + SwiftShader exposes a WebGPU adapter, but the device is lost on first use, even for a one-sphere test (`viewer/qa/webgpu-smoke.html`). The WebGL2 backend of the same renderer works. Test WebGPU only on real hardware.
- Software rendering is slow: one capture config takes minutes. Keep captures small (500x500, one preset).

## Instructions for the next coding agent

1. **Do not start new shader features.** First get a trustworthy baseline. Reproduce: `cd viewer && npm ci && npm run typecheck && npm test`, start Vite on 4173, then `python3 tools/inez/dh_lab_capture.py --out /tmp/x --config a "materials=glb&normals=glb" --config b "materials=glb" --width 500 --height 500`.
2. **Fix or sidestep the exploded-geometry bug** (above) so a GLB-material baseline renders in the lab. Alternative: use the legacy `WebGLRenderer` main viewer for baselines and port only the skin node material once it is proven.
3. **Run the controlled comparison one change at a time**, identical camera/light/pose, at 500x500, and *look at the saved PNGs* each step: GLB baseline -> normals fixed -> neutral vs AgX -> TSL skin without calibration -> calibrated -> region roughness -> micro detail. Record results in `docs/INEZ_VISUAL_QA.md`. **Revert any step that looks worse.** Also compare against `references/inez_portraits.jpg` and `references/inez_turnaround.jpg`.
4. **Re-derive the albedo gain** with a neutral view transform and matched exposure; check the render's skin chroma and skin/knit ratio with `tools/inez/skin_tone_compare.py` against all three reference panels before trusting `skin_calibration.json`. If in doubt, set `calibrated=0` (URL) or gain 1.
5. Only after skin is verified better than the baseline: SSS (benchmark screen-space vs texture-space; profiles are ready), ear transmission, then eyes, hair (needs strand direction data the shell lacks), fuzz, DoF, presets, real-GPU benchmarks.
6. **Constraints that still hold:** do not change Inez's face geometry or identity; keep all seven identity morph defaults (v01=0, v02=0, v03=1, four `_v05` = 1); never reset morphs globally; originals and `source/` are read-only; no unlicensed scans or datasets; no ImageGen; don't claim WebGPU, GPU performance or visual improvement without saved evidence; likeness is still **not accepted** (`assets/characters/inez/reports/INEZ_VISUAL_QA.md`).
7. Earlier open items (unchanged): re-weight boot soles rigid to the foot, fix the procedural gait slip, cut CMU walk loops, SMPL-H/AMASS licensing decision for TERRA. See `WORK_COMPLETED_AND_NEXT_STEPS.md`.
