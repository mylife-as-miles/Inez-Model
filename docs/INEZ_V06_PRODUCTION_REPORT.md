# Inez V06 production recovery — current continuation checkpoint

2026-10-10 continuation from fetched commit `7c430b5a`: the four isolated
Walk/Run/CrouchDown/CrouchUp clips now have refined runtime contact. The default
`inez_recovery_v06.glb` equals the tested contact-r01 export, retaining the
original face, restored color and original PBR. See
[contact refinement and current QA](INEZ_V06_CONTACT_REFINEMENT.md) for source
subframe diagnosis, actual 120/241/480-Hz results and matched rendered evidence.
Maximum measured stance slip is 0.056 mm in actual Three.js at 120 Hz and
0.259 mm in the exported 241-Hz audit, with no sampled runtime penetration.
Original sources/references remain untouched; R02 and production approval stay
held. The user explicitly requested committing and pushing this continuation,
its QA evidence, remaining work and next-agent prompt to the same development
branch. No main merge or production/artistic approval is authorized.

The material below describes the **paused `7c430b5a` snapshot**, including its
historical residuals and final-named reports. Current continuation reports and
the next steps above supersede that contact gate. The paused GLB is retained as
`model/v06/inez_recovery_v06_paused.glb`.

## Paused handoff

Date: 2026-10-10. Development branch: `feat/inez-v06-digital-human`.
Starting production commit: `14b8452f861c303ccdee99b0b17c850bfd9dfb7a` on `claude/inez-character-production-5wc4cq`. This is an existing-character recovery, not a replacement. User requested pause and push of the development snapshot. No merge into main; no production or artistic approval.

## Completed and saved

- Audited the actual production assets and reports; retained original masters, supplied models, portrait references, skeleton, UVs, facial controls, CMU tools and clips.
- Created versioned Blender/GLB sources in `assets/characters/inez/model/v06/`. Default viewer model is `inez_recovery_v06.glb`: original facial geometry with restored color and boot/contact corrections. Original PBR remains default; enhanced skin is optional.
- Traced dark skin to the earlier source color gain changing by a factor of 0.42. Derived restored albedo maps invert that gain in linear space with explicit sRGB decoding/encoding. Restored medium-brown hair color from the earlier source targets. Added neutral white studio lighting without changing the existing studio preset. This follows the user's explicit color references; it is not an exact photometric match or a reason to repaint away renderer differences.
- Preserved 167 joints, four ponytail bones, 17 embedded clip names and seven identity defaults. Required defaults remain HeadFit v01=0, v02=0, v03=1; HeadRefine v05, SourceBodyFit v05, SourceHeadWrap v05 and FaceCorrect v05=1.
- Created localized mouth/jaw correction candidates. R02 repairs R01's asymmetric control-point pairing; maximum actual vertex displacement is 1.4484 mm. Nose, face length and eyelids were not blindly scaled. Same-camera/light R02 landmarks improve mouth/IPD 0.7741→0.7445 and jaw/IPD 1.7305→1.7016, but the identity critic found insufficient evidence for promotion. `inez_v06_candidate_r02.*` remains an unapproved candidate; R01 is historical, not a preferred asset.
- Corrected rigid sole weights (1,742 incorrectly weighted lowest-sole vertices identified), blended ankle transition and preserved shaft deformation. Repaired leg contact curves while retaining authored upper-body, facial and hair tracks. Export timing is normalized; authored durations are preserved, not assumed byte-identical to the earlier runtime export.
- Implemented optional real WebGL2 screen-space RGB Gaussian skin diffusion, based on GPU Gems 3 chapter 14. Diffuse is separated from specular; depth/normal/skin visibility gates reject discontinuities and other materials. Existing albedo/normal/roughness maps remain in use; micro-normal and geometry-derived thickness attributes are added. Four scene passes (beauty MSAA, visibility, diffuse, normals) plus a composite are required. Optional single-light thin-region attenuation is a shadow-unaware approximation, off by default, not multilayer scattering.
- Viewer controls: original/enhanced material rollback, SSS, strength/radius, roughness variation, micro-normal, thin transmission, debug views, lighting, quality, screenshots and backend diagnostics. Existing animation, locomotion, reference, facial and browser APIs remain available.
- Prepared a standalone fixed-60-Hz world-space XPBD guide solver, presets, local asset-intake inventory and hair documentation. Six solver fixture tests passed. It is NOT bound to Inez or the selected Fab hair and is not a completed hair simulation.

## Evidence and tests

Paths below are relative to `assets/characters/inez/`.

- `qa/browser_v06_baseline.json` and `qa/browser_v06_recovery_final.json`: 14/14 actual browser checks, no runtime errors; final captures `renders/v06_recovery_final/` include views, expressions and animation poses.
- `qa/v06/v06_skin_final.json`: 17/17 technical checks, no shader/browser failures; 21 actual screenshots in `renders/v06_skin_final/`. Neutral SSS on/off mean absolute RGB difference 0.04182/255, maximum 22/255; apartment maximum 7/255. Non-skin interior pixels unchanged. Effect is subtle; extreme settings blur pigmentation and are not accepted defaults.
- `renders/v06_recovery_matched/` versus `renders/v06_candidate_r02_matched/`: identical neutral camera/light six-view comparison. `renders/v06_baseline/` is the dark original baseline. Color and lighting both differ in the neutral restoration; do not describe that pair as an isolated albedo test.
- Recovery and R02 Khronos validation: zero errors, 20 existing non-root warnings. `qa/v06/exported_animation_validation.json`: actual exported deformation checks across all 17 clips, zero failures. Original baseline validation also saved.
- Viewer build passed (existing large-chunk warning). Character-controls six tests and hair-solver six tests passed. No tests certify AAA likeness or final hair integration.
- Independent identity review holds R02 promotion; rendering review accepts a limited skin prototype with remaining source defects; technical review confirms preserved rig/control integrity, with backend and hardware limitations.

### Actual exported GLB foot contact at 120 Hz

Same material point accumulated during planted phases, with matching character travel. Loop seam is measured separately and is not evidence of no sliding.

| Clip | Before L/R maximum stance slip (mm) | Recovery L/R (mm) |
|---|---:|---:|
| Walk | 50.17 / 70.78 | 2.17 / 3.59 |
| Run | 57.90 / 101.58 | 1.56 / 9.54 |
| CrouchDown | 44.59 / 42.23 | 4.15 / 4.27 |
| CrouchUp | 44.59 / 42.23 | 4.00 / 4.11 |

Authoritative reports: `qa/v06/baseline/exported_boot_contact.json` and `qa/v06/exported_boot_contact.json`. Matching velocities: Walk 0.9247252747 m/s, Run 2.3961904762 m/s. Blender source audit (`boot_contact_after.json`) is approximately zero, but exported interpolation retains the residuals above and up to 2.31 mm sole penetration. Address that discrepancy next; do not report source-only results as runtime perfection.

### Renderer and performance limits

Actual shader tests ran on WebGL2/CPU SwiftShader, not a target GPU. Requested WebGPU test (`qa/v06/v06_backend_webgpu.json`) used **WebGL2 (WebGPU fallback)** and preserved original PBR; native WebGPU SSS was not tested or implemented. No Quadro T1000, VR, or universal FPS acceptance. Full-scene controlled performance benchmark remains pending at pause. Diagnostics include render calls, memory estimates and CPU submission timing; no isolated GPU pass timing. Diffusion target allocation estimate at 900×680 with MSAA4 is 53,856,000 bytes, excluding driver and asset textures.

## Hair source and CORDEL blockers

Public listing: https://www.fab.com/listings/a3425afb-5801-455e-a6a1-e27632d493db . The user supplied this URL again in response to the local-package question; it is not a downloaded source package. Listing metadata advertises Additional Files ZIP containing FBX hair cards/scalp/head, PNG/TGA maps and ABC groom. No selected FBX/ABC/MHPKG package was found locally. Do not bypass authentication/licensing, claim download, or submit NoAI source assets to generative services. Obtain the legitimately downloaded Additional Files ZIP and inspect actual contents first.

Canonical style/color are locked to the user's references: medium-brown, naturally wavy, loosely gathered high ponytail, face-framing curls, realistic scalp coverage. Fit hair to Inez; never reshape her face to fit hair. Existing hair remains in use.

Read-only CORDEL inspection at `057d304c5958e00913dae3d4d1383dff6dbf81fa`: phase1 scene import rejects skin, hierarchy and transforms; skeletal runtime/character motor roadmap is pending. No CORDEL files changed. Native hair integration requires actual skeleton and per-frame attachment interfaces. See `docs/INEZ_HAIR_PHYSICS.md` and `assets/characters/inez/hair/qa/asset_audit.json`.

## Remaining work in order

1. Reproduce final tests and inspect saved actual renders. Fix exported contact interpolation residuals and penetration before calling locomotion contact complete.
2. Repair source baked diagonal facial shading, scalp intersections/crown ridges, stringy curl silhouette, flat eye response, sweater smears/back stripe continuity and costume interfaces using controlled changes. Preserve restored skin/hair color and all original identity layers.
3. Continue original-two-reference landmark/visual comparisons. Keep R02 unpromoted until independent identity review supports a real improvement. Do not shorten the face/narrow alae based on stale percentages.
4. Profile full Inez on real target hardware (Dell Precision 5540, Quadro T1000 4 GB, conservative 16 GB RAM); record backend and costs honestly. Investigate native version-specific TSL/WebGPU only separately; retain working WebGL2 fallback.
5. Obtain licensed selected hair sources, perform local intake, duplicate and fit in Blender, design asset-derived guides/colliders and bone weights, then bind the tested solver to actual animation. Execute animation/collision visual QA and export/load tests. Fixtures are not acceptance evidence for Inez hair.
6. Only after skin and likeness gates, consider advanced eye, hair shading, fuzz and optional calibrated DoF. Do not conceal defects with blur or restart TERRA research; permitted CMU motion remains the near-term path.

## Reproduction entry points

```sh
cd viewer
npm ci
npm run build
node --test qa/*.test.mjs
npm run dev -- --port 4173
```

From repository root, with Chromium, Python dependencies and Blender 4.3.2 available:

```sh
INEZ_CHROMIUM=/usr/bin/chromium python3 tools/inez/browser_qa.py --url http://127.0.0.1:4173/ --revision next_agent_browser --model v06/inez_recovery_v06.glb
python3 tools/inez/v06_skin_qa.py --url http://127.0.0.1:4173/ --revision next_agent_skin --skip-performance
python3 tools/inez/v06_skin_qa.py --url http://127.0.0.1:4173/ --revision next_agent_performance --performance-only --frames 120 --hardware
```

The last command requests hardware browser flags; confirm the actual adapter before labeling results GPU evidence. Inspect each tool's `--help` before regenerating Blender/export/contact reports. Reproduction requires external Python/Blender dependencies; the temporary downloaded MediaPipe landmark model is not bundled. Failed/intermediate QA (`browser_v06_recovery.json`, early skin reports) is retained as history; final-named reports above are authoritative for this snapshot. Original approved sources were not overwritten.
