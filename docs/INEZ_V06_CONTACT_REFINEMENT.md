# Inez V06 contact interpolation — continuation checkpoint

2026-10-10. Fetched and inspected `feat/inez-v06-digital-human` at
`7c430b5a6dff52945e3e19d2a3d36223df1c8107` (the paused development snapshot).
The user explicitly requested committing and pushing this development
continuation with its completed work, remaining tasks and next-agent prompt.
No unrelated branch or main merge is authorized. Production and likeness
approval remain **false**.

The default `model/v06/inez_recovery_v06.glb` now contains the tested contact
refinement. Its bytes equal `inez_recovery_v06_contact_r01.glb`.
`inez_recovery_v06_paused.glb` preserves the fetched recovery for rollback.
The new editable source is `inez_recovery_v06_contact_r01.blend`; the original
recovery Blend, original masters, supplied assets, restored textures, portrait
references and R02 likeness candidate are untouched.

## Diagnosis and controlled change

The original source audit sampled integer frames at 60 Hz. Evaluating the same
Blend at 120 Hz reproduces the exported residuals: Walk 2.16/3.59 mm, Run
1.55/9.54 mm, CrouchDown 4.15/4.27 mm and CrouchUp 4.00/4.11 mm. The exporter
was already sampling at 120 Hz; increasing export sampling alone cannot repair
the foot movement between the source's contact keys. The legacy source audit
also rounded the half-frame crouch endpoint. Its near-zero result was not a
runtime contact guarantee. `boot_contact_audit.py --hz` now evaluates subframes
and includes the exact authored endpoint.

`v06_refine_contacts.py` solves contact at 480 Hz against the actual emitted
parent interpolation and exported sole geometry. It retains the existing
60-Hz world-space foot pitch/roll, anchors rolling contacts using the same
material point, and blends the small correction through swing. A 0.25-mm sole
clearance remains below the audit's 2-mm planted threshold. Quaternion signs
are kept continuous. Only `upperleg01`, `lowerleg01` and `foot` rotations on
each side change in Walk, Run, CrouchDown and CrouchUp.

The GLB patch appends those 24 channels' samples while retaining the entire
original binary prefix and all other animation channels. Geometry, normals,
UVs, skin weights, joint hierarchy, textures, original face morphs and material
data retain their bytes. All 167 joints, four ponytail bones, 17 clip names,
clip durations and seven identity defaults remain intact. Source action frame
ranges remain exact. No global morph reset was added.

## Actual measurements

Paths below are relative to `assets/characters/inez/`. These are accumulated
same-material-point stance displacement, including matching +Z character
travel: Walk **0.9247252747252749 m/s**, Run **2.3961904761904758 m/s**.
Loop seam is reported separately and is not used to establish stance contact.

| Clip | Paused GLB L/R at 120 Hz (mm) | Refined GLB L/R at 120 Hz (mm) | Actual Three.js L/R at 120 Hz (mm) |
|---|---:|---:|---:|
| Walk | 2.167 / 3.590 | 0.051 / 0.030 | 0.056 / 0.043 |
| Run | 1.556 / 9.540 | 0.042 / 0.029 | 0.047 / 0.034 |
| CrouchDown | 4.152 / 4.271 | 0.014 / 0.012 | 0.020 / 0.019 |
| CrouchUp | 3.999 / 4.115 | 0.014 / 0.013 | 0.020 / 0.021 |

The additional 241-Hz audit samples between the new keys: worst stance slip
**0.259 mm** (Run right). At 480 Hz the worst is **0.072 mm**. Runtime sole
minima across these exported audits remain at least **0.243 mm above ground**;
no sampled runtime penetration remains. Three.js and the independent Python
GLB evaluator agree within **0.013 mm**. These finite samples do not certify
all possible times, blend weights, movement speeds or terrain. The full source
mesh at 120 Hz differs slightly from its runtime LOD/parent interpolation:
up to 0.07-mm stance slip and a rounded 0.01-mm negative sole minimum remain;
source results are not substituted for the emitted-GLB measurements.

Authoritative continuation reports:

- `qa/v06/contact_source_before_120hz.json`, `contact_source_final_120hz.json`:
  actual source subframe comparison.
- `qa/v06/contact_exported_before_120hz.json`, `contact_exported_after_120hz.json`,
  `contact_exported_after_241hz.json`, `contact_exported_after_480hz.json`:
  actual saved before/after runtime contact, with loop seam separate.
- `qa/v06/contact_refinement_r01.json`, `contact_integrity.json`:
  input hashes, preserved channels, exact durations and 18 protected file hashes.
  Sampled deformation changes are at most 5.687 mm (Walk), 4.770 mm (Run),
  and 0.865 mm (crouch transitions); sampled head deformation change is zero.
- `qa/v06/v06_contact_r01_matched_review.json`: independent actual Three.js
  contact, six passed checks, identical neutral camera/light and original PBR.
  `renders/v06_contact_r01_matched_review/{before,after}/` holds 58 actual PNGs:
  full body, uncropped boot motion and the pixel-identical rest portrait.

Inspected the saved original portraits, paused renders, actual matched body
and boot sequences, final browser run pose and final neutral skin PNGs. No
new knee, boot sole, shaft or clothing deformation problem was observed in
these captures. Existing costume interfaces, facial shading bands, crown/scalp
intersections and eye/hair defects remain; this is not artistic acceptance.
Earlier `matched_final` close-ups cropped some boot travel; the wider
`matched_review` capture is the preferred visual evidence.

## Reproduced and final checks

Baseline build and all 12 unit tests passed before edits. The initial read-only
browser/skin reproduction used files verified byte-for-byte against the fetched
commit while the full clone downloaded; build and 12 tests also passed in the
finished checkout. Reproduction reports are `qa/browser_v06_contact_repro_browser.json`
and `qa/v06/v06_contact_repro_skin.json` (14/14 and 17/17).

Final browser regression: `qa/browser_v06_contact_r01_browser_final.json`,
**14/14**, zero runtime errors, 19 actual screenshots. Final skin regression:
`qa/v06/v06_contact_r01_skin_final.json`, **17/17**, zero shader/browser errors,
21 actual screenshots. Skin comparison metrics exactly equal the paused final
report. Neutral lighting and original PBR remain the default; enhanced WebGL2
skin remains optional. Native WebGPU and target GPU performance were not tested
here; these browser results use CPU SwiftShader.

`qa/v06/contact_r01_animation_validation.json` passes actual exported
deformation checks across all 17 clips, with zero failures.
`qa/v06/contact_r01_glb_validation.json`: zero Khronos errors, the same 20
existing warnings, 52 infos (including retained unused historical samplers).
The GLB grows by 169,236 bytes. This is an asset-size observation, not a GPU
performance measurement. The default-path smoke test is saved separately as
`qa/v06/contact_default_smoke.json`. It distinguishes the 17 embedded clips
from the viewer's two existing external CMU clips. The initial count assertion
incorrectly treated all 19 as embedded; its report is retained as
`contact_default_smoke_initial.json`, with the correction explained in the
final report. No animation was removed to satisfy that assertion.

The final refinement tool was rerun from the untouched recovery Blend and
paused GLB into separate temporary outputs. `qa/v06/contact_reproduction.json`
records the byte-identical runtime output and unchanged source frame ranges.

The first browser launch received Vite's HTML fallback for the newly created
GLB because the startup public-file cache had not seen it. Restarting Vite
resolved that setup failure; failed launch evidence remains in
`qa/browser_v06_contact_r01_browser.json` and
`qa/v06/contact_initial_launch_failure.json`. Final-named reports above passed.

## Reproduce and continue

Run the viewer build/tests as in the production report. Restart Vite after
creating new model filenames: generated asset writes are intentionally ignored
by its watcher. Inspect each tool's `--help` before generating new reports.
Use new output/revision names, because the refinement and matched-capture tools
refuse to overwrite existing outputs.

```sh
blender -b assets/characters/inez/model/v06/inez_recovery_v06.blend \
  --python tools/inez/v06_refine_contacts.py -- \
  --input-glb assets/characters/inez/model/v06/inez_recovery_v06_paused.glb \
  --output-blend /tmp/inez_contact_repro.blend \
  --output-glb /tmp/inez_contact_repro.glb --report /tmp/inez_contact_repro.json

python3 tools/inez/v06_contact_glb.py \
  --input assets/characters/inez/model/v06/inez_recovery_v06.glb \
  --hz 241 --report /tmp/inez_contact_241hz.json

INEZ_CHROMIUM=/usr/bin/chromium python3 tools/inez/v06_contact_qa.py \
  --url http://127.0.0.1:4174/ --revision next_contact_review
```

The corrected Blend keeps fractional 480-Hz leg keys on its original 60-fps
timeline. Use the surgical refinement export above to preserve the tested
runtime parent tracks and sampling; a generic 120-Hz export discards the denser
keys and is a different artifact requiring fresh QA.

## Remaining implementation, in order

1. Reproduce the current gates, then repair the source's baked diagonal facial
   shading, scalp/crown intersections, stringy curl silhouette, sweater smears,
   back stripe continuity and costume interfaces in controlled passes. Keep
   restored albedo/color, original face geometry and all identity layers.
   Compare actual saved renders at identical camera/light; distinguish albedo
   changes from lighting. Hold or revert a change if visual evidence worsens.
2. Continue comparisons against the two original portrait references. R02
   mouth/jaw geometry remains an unpromoted candidate. No face shortening,
   alar narrowing or candidate promotion is justified by stale measurements.
   Turning clips and arbitrary gait blends still require their own contact and
   deformation QA; the four isolated clips do not certify those behaviors.
3. Profile full Inez on the actual Dell Precision 5540 / Quadro T1000 4 GB,
   using a conservative 16 GB RAM budget. Record the real adapter, backend and
   costs before GPU/FPS claims. All current browser evidence is CPU SwiftShader.
   Native WebGPU SSS remains unavailable; any version-specific implementation
   needs separate validation while preserving the working WebGL2 fallback.
4. Obtain the legitimately downloaded Fab Additional Files ZIP and license/
   receipt note. Local search found no FBX/ABC/MHPKG/ZIP package; see
   `hair/qa/local_source_search_v02.json`. Inventory without extraction first,
   then duplicate and fit actual FBX cards locally to Inez's existing face.
   Preserve medium-brown, loose wavy high-ponytail hair and distinctive face
   curls. Derive guides, skin weights and colliders from real geometry; bind the
   tested XPBD solver to actual character animation and save rendered head/body,
   stop, turn, crouch, teleport and fixed-step comparison evidence. Fixtures and
   GLB skinning alone do not implement character-bound simulation.
5. Reinspect current CORDEL skeleton/import/per-frame attachment interfaces
   before integration. The audited `057d304c5958e00913dae3d4d1383dff6dbf81fa`
   rejects the required skinned hierarchy. Expose no Jolt-specific types and
   claim no CORDEL integration until real runtime loading/attachment tests pass.
6. Keep advanced eyes, fuzz and calibrated DoF behind the earlier skin/likeness
   gates. Do not hide source defects with blur, use ImageGen/replacement models,
   bypass Fab authentication/licensing/NoAI restrictions, or restart TERRA
   research. Permitted CMU motion remains the near-term path.

No selected-hair acquisition, fitting, character-bound simulation, NoAI service
submission, target GPU profiling or CORDEL integration occurred in this
continuation. The exact continuation prompt is
[INEZ_NEXT_AGENT_PROMPT.md](INEZ_NEXT_AGENT_PROMPT.md).
