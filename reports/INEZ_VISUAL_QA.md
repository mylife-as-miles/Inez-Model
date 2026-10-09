## GitHub checkpoint — 2026-10-09

Actual dressed v03 source/export and staged animation v01 now exist. Dressed rendering identified tight sweater/bust fit, incorrect shoulder stripe patches, boot/cuff skin exposure, protruding toes, a stray forearm seam, and hair crown discrepancies. These remain unapproved. Canonical Khronos GLB validation: 0 errors, 85 non-root skinned-node warnings. Chromium reached model-ready state, but screenshot capture timed out; actual browser render/animation acceptance remains pending. See `WORK_COMPLETED_AND_NEXT_STEPS.md` for current work and prioritized corrections. No final likeness pass is claimed.

# Inez visual QA and production log

Created 2026-10-08. This is a live report; no reference or model is approved at initialization.

**Current status (9 October 2026): actual editable clay head v03 passed both critics' provisional initial geometry gate after two real mesh refinements. Final facial likeness remains below target (technical30/35), not production approved. Actual dressed geometry/PBR authoring is enabled; motions and real Three.js model/animation review are pending. Reference body materials remain rejected; originals control clothing.**

## Phase 0 — inspected

Both original JPEGs opened with `view_image` before any generation. Byte-identical copies and SHA-256 manifest saved under `assets/characters/inez/references/original/`; requested convenience paths also established.

Workspace inspection found no game repository, renderer, package manifest, source character, or local AGENTS.md. Blender 4.3.2 CLI is available (Python API inside Blender), Python/Pillow/numpy, Node, Chromium and Playwright are available. Three.js is not an existing repository dependency. Independent subagents are available and authorized by the user.

Built-in `image_gen.imagegen` is available. Its full instructions were read before generation. Executor/cloud skill catalogs and filesystem skill locations were searched; there is no separately supplied ImageGen SKILL.md. The built-in tool is the chosen generator; no substitute generator is used. The cloud-environment runtime skill and networking reference were read; HTTP policy is currently unrestricted/enforced. No credentials were printed or persisted.

## Phase 1 — identity specification

`docs/INEZ_CHARACTER_IDENTITY.md` records visual invariants, uncertain geometry, source hierarchy, measured image-space landmark bands, and production gates. Original B's front head truncation is specifically excluded. True profiles, pendant motif, real height and unseen details remain unresolved.

Independent reviews: root = artist; `/root/identity_critic` = identity; `/root/technical_critic` = modeling usability. Each critic opens originals independently. Their full notes are stored under `assets/characters/inez/qa/identity/` and `qa/technical/`.

Both critics independently inspected originals and confirmed the identity locks. Reports: `qa/identity/00_original_identity_observations.md` and `qa/technical/00_original_reference_constraints.md`. No factual disagreement requires an identity-spec change. Stage status: original inspection and identity lock accepted as reconstruction guidance. Next: canonical neutral front face, then full-body front, with review and refinement before additional views.

## Budget and scoring

Initial generation cap: **24 calls**, including failed attempts and edits. At most three initial refinement passes per problematic view. Call ledger: `assets/characters/inez/qa/generation_ledger.json`. Every prompt is retained under `qa/prompts/`.

Weights: facial identity 35; body silhouette 15; hair 15; costume/accessories 10; skin/eyes/materials 10; cross-view consistency 10; technical usability 5. Subjective human/vision review, not biometric measurement. Whole-character target ≥90 and face ≥32; partial crops reserve unassessable points and cannot establish whole-character acceptance. Original-only rear/profile unknowns remain qualified even if a generated view is internally coherent.

## Attempts and decisions

Call 1: built-in invocation failed schema validation with `missing prompt`; no image produced. The saved prompt was reloaded from disk for call 2. Call 1 is conservatively retained against the 24-call cap. No quality score is assigned to a missing image. This was a tool invocation failure, not a critic rejection.

Candidates are never promoted to `references/approved/` before both critiques are considered. Rejected alternatives remain in `references/generated/` with version suffixes. Acceptance for reference modeling does not prove completed 3D fidelity.

### Call 2 — front portrait v02

Candidate: `references/generated/01_face_front_neutral_v02.png` (1071 × 1468). Artist inspected the actual output and made `qa/01_face_front_v02_comparison.png`, a simple image-processing comparison with original A and B using approximate manual eye-spacing normalization. This is not a biometric or calibrated alignment.

Independent identity report: `qa/identity/01_face_front_neutral_v02.md`. Face **32.5/35**; visible scope **61/66 (92.4%)**. Reserved 34 points: body 15, unseen hair 3, unseen costume 6, cross-view 10. Deductions: slightly rounder/open eyes, more regular Cupid's bow, cleaner/narrower chin taper (angle-confounded), denser/even freckles, more uniform cheek/lip gloss, soft background gradient.

Independent technical report: `qa/technical/01_face_front_neutral_v02.md`. **70/75 assessable (93.3%)**, face 33/35. Body and cross-view 25 reserved. Deductions: slightly lengthened lower mouth/chin interval and reduced mouth spread (expression confound), more even long curls, slightly chunkier knit, more uniform freckle/redness coverage. True front/relaxed gaze, crown framing and anatomy pass.

Artist decision: **provisional portrait reference accepted**, copied to `references/approved/01_face_front_neutral.png`. Preserve this version; no mandatory portrait refinement requested. Neither scoped score is a whole-character 90/100 approval. Check lids, mouth/chin and freckle density in subsequent views and the real head sculpt; original A remains final authority. Call 3 is the separately anchored full-body front candidate, not a sheet.

### Call 3 — full-body front v01

Actual output reviewed by artist and both independent critics. Full crown, fingers, boots and soles are visible. Face recognizable and three torso band phases retained. **Hold/reject for targeted correction** despite a good scoped score.

Identity: `qa/identity/05_body_front_v01.md`, face **33/35**, **83/91 assessable (91.2%)**; 9 points reserved. Deductions: unsupported gold/tan welt and bright eyelets, weak A-pose arm separation, denim wash/hardware contrast, fine facial-detail uncertainty at the small face scale.

Technical: `qa/technical/05_body_front_v01.md`, **81/90 assessable (90%)**, cross-view 10 reserved; face 33/35, body 14/15, hair 14/15, costume 7/10, materials 9/10, usability 4/5. Deductions explained in full report: unsupported colored welt and exaggerated sole grooves; approximately 8–11-degree arms-down pose; slight gray denim wash and chunky knit/curl differences. Boot comparison crops are preserved in technical QA.

Call 4 edits v01 with **both originals**, v01, and accepted front portrait attached. Primary fixes: all-black subdued boot construction and clearer shallow 15-degree A-pose. Identity critic suggested 20–25 degrees; artist chose the technically requested 15-degree pose to retain the original garment silhouette, contingent on visible modeling clearance. Denim wash is secondary and not a reason to rebuild the face. No candidate is silently approved on attractiveness or score alone.

### Call 4 — full-body front v02

Both reviewers inspected actual v02 and enlarged boot evidence. A-pose clearance improved and accepted. Face, silhouette and stripe phase retained.

Identity: `qa/identity/05_body_front_v02.md`, face **33/35**, **85/91 assessable (93.4%)**, provisional front-body accept with deductions for faint remaining tan stitches and denim wash. Technical: `qa/technical/05_body_front_v02.md`, **83/90 assessable**, face 33, body 14, hair 14, costume 8, materials 9, usability 5; cross-view 10 reserved. Technical gate remains **rejected** because periodic warm thread dashes are still visible and cannot be dismissed as neutral specular highlights.

Artist decision: **keep v02 over v01, hold approval**; honor the remaining concrete technical finding. Call 5 is a boots-only material correction, with originals and v02 attached. No other anatomy or costume edit is requested.

Viewer preparation: `viewer/` builds successfully. Headless Chromium WebGL2 preflight reports no page errors, no viewer errors, and successfully loads original A in comparison mode. Preflight is under `qa/`, not presented as a real-character render. Model loading, animation and material validation remain untested until an actual GLB exists. WebGPU is available as an optional requested backend with WebGL2 fallback; only WebGL2 has been exercised so far.

### Call 5 — full-body front v03

Artist inspected output and assembled `qa/05_boots_refinement_comparison.png` by ordinary crop processing. No manual design repair was applied. Technical critic still finds repeated warm-colored stitch dashes, **83/90** assessable, gate unresolved (`qa/technical/05_body_front_v03.md`). Identity critic finds face/pose intact but a new fine scratch/crackle-like denim texture absent from B; v02 is better overall and remains the keeper. The attempted boot edit did not establish a pass.

Call 6: final initial body refinement (third edit after v01). **Uses v02 as the edit base**, rather than accumulating v03's denim regression. v02 is the first attached edit target, both untouched originals follow, and an inspected nearest-neighbor crop of B's boots is an additional source-detail guide. Prompt deletes the entire contrasting stitch-dash pattern and protects all denim/anatomy. No more initial body edits are authorized beyond this pass without a revised budget/permission if this gate remains blocked.

### Call 6 — full-body front v04: initial allowance exhausted

Actual full image and enlarged boots inspected by artist and both critics. `qa/05_body_front_v04_boots_inspection.png` exposes persistent periodic warm tan/brown/ochre thread at both toe and side welts. Enlarged denim again has pale branching/squiggle/scratch detail absent from B. These are observed output differences; the edit prompt is not evidence that they were corrected.

Identity: `qa/identity/05_body_front_v04.md`, **33/35 face**, **84.25/91 assessable (92.6%)**, 9 reserved; **HOLD correction gate**. Face, body proportions, pose and stripe layout retained; warm boot trim and patterned denim remain. Earlier v02 acceptance covered recognizable front identity/silhouette with recorded material residuals, not joint exact costume approval.

Technical: `qa/technical/05_body_front_v04.md`, **82/90 assessable**, 10 cross-view reserved; **REJECT costume gate**. Face 33/35 remains recognizable. No missing anatomy or crop failure, but warm thread and denim pattern remain unsupported design/material changes. Every deduction is recorded in the independent report.

Artist decision: **v02 remains best body keeper; v03 and v04 rejected as attempted corrections**. No fabricated passing score, no whole-character ≥90/100 claim, and no body copy promoted to `references/approved/`. Initial body attempt plus three refinements are exhausted. Total calls **6/24** (five image outputs and one schema failure). Remaining 18 global calls do not waive the user's per-view refinement stopping rule.

Proposed reviewable next step, requiring revised per-view authorization: up to **two** additional built-in ImageGen calls within the original 24-call total cap—one tightly cropped boots correction using both originals and source-detail guides, then one full-body application using the corrected detail and the v02 keeper. Do not paint the reference in Python, substitute another generator, or propagate v03/v04's denim scratches. If approval is not supplied, preserve all work and keep the gate blocked.

## Required outputs — actual status at pause

### Resumed authorization — boots extension 01

The user replied **“Approve”** to the concrete proposal for up to two additional calls: a tightly cropped boots correction, then application to the v02 full-body keeper, within the existing 24-call total cap. Recorded in `generation_ledger.json` as `boots_extension_01`, planned calls 7–8. The body limit extends only through v05. Other views retain their initial candidate plus up to three refinement allowance. This is permission to attempt correction, not visual acceptance. Paid work resumes; model gates remain pending.

The user also clarified the primary deliverable: a **playable, fully rigged character visibly rendered in Three.js**, with orbit/camera/light/facial inspection, idle/walk/run and blending. Reference sheets and an editable Blender source alone do not constitute completion. Geometry/material, rig/animation, and browser implementation are being advanced toward that contract; no working character is claimed before actual browser tests.

### Call 7 — tight boots correction

Candidate `references/generated/13_boots_closeup_v01.png` (1438 × 1093) inspected by artist and both independent critics. Original A/B, a clean v02 target crop, original-B enlarged boots and full v02 were attached. The warm periodic welt dashes now read black/neutral gray.

Identity: `qa/identity/13_boots_closeup_v01.md`, **9.75/10 assessable**, 90 points explicitly reserved. Technical: `qa/technical/13_boots_closeup_v01.md`, scoped material/geometry guide accepted; exact lug/groove/stitch/grain microdetail remains extrapolated because source B cannot resolve it. Both shafts, toes and entire soles visible; visible cuffs have coherent dark denim and no branching scratch pattern.

Decision: **scoped boot-material reference accepted**, copied to `references/approved/13_boots_closeup.png`. This is neither whole-body nor playable-character completion. Call 8 applies its corrected material to the cleaner v02 body; face/body/sweater/denim/pose are protected and both originals remain attached.

| Output | Actual status |
| --- | --- |
| `01_face_front_neutral.png` | Provisionally accepted portrait-only reference; in `references/approved/`; originals retain authority |
| `02_face_left_profile.png` | Not generated; retained draft request is only preparation |
| `03_face_right_profile.png` | Not generated |
| `04_face_three_quarter.png` | Not generated |
| `05_body_front.png` | No approved file; v01–v04 retained; v02 best unapproved keeper |
| `06_body_side.png` | Not generated |
| `07_body_back.png` | Not generated |
| `08_eyes_closeup.png` | Not generated |
| `09_lips_closeup.png` | Not generated |
| `10_skin_freckles_closeup.png` | Not generated |
| `11_necklace_closeup.png` | Not generated; original pendant motif still unresolved |
| `12_sweater_material_closeup.png` | Not generated |
| `13_boots_closeup.png` | Not generated |
| `INEZ_MASTER_TURNAROUND.png` | Not assembled: there is no complete approved set; QA comparison boards are not a master turnaround |

## Major-stage progress at pause

1. **Files created:** byte-identical original copies/manifest, identity specification, five versioned generated images, approved front portrait, retained prompts and six-call ledger, independent identity/technical reports, comparison crops, Three.js viewer source/lockfile, CC0 mesh/targets/rig sources and licenses, guarded Blender fitting/export preparation scripts. Full inventory is in the review package manifest.
2. **Reviewed:** both originals; front portrait v02; body front v01, v02, v03, v04; detailed boot and denim crops. Independent critics inspected actual outputs, not just prompts.
3. **Findings:** front likeness provisionally passes its scoped gate. Body pose and face pass; boot accent removal failed, and later edits introduced denim texture drift.
4. **Corrected:** clearer shallow A-pose and more subdued eyelets/trim in v02. No complete black-welt correction is confirmed. v03/v04 are not accepted improvements.
5. **Remaining differences:** slightly rounder front-portrait eyes, more regular lips/chin taper, denser/even freckles; body boot warmth and stronger denim wash; unknown true profiles, hidden anatomy, exact pendant motif and world stature.
6. **Stage decision:** Phases 0–1 complete; canonical portrait provisionally accepted; Phase 2 blocked at the canonical body review gate; initial per-view refinements exhausted. Independent review loop was performed, not skipped.
7. **Next step:** obtain authorization for the concrete two-call boots-focused strategy, re-review both critics, then generate the remaining separate views. Actual Blender modeling remains downstream of accepted front/profile/body references.

## Later-stage status

Phases 4–7 **not started for an actual character**. No `inez.blend`, `inez.glb`, fitted geometry, authored rig, PBR texture set, expression animation or real-character render exists. Licensed source assets and scripts are preparation, not a reconstructed Inez. Detailed facial texture authoring and 3D likeness claims remain prohibited until actual head geometry passes its separate review.

Model preparation report: `qa/model/README_preparation.md`; source inventory and false gate template retained. The builder requires a recorded true gate, existing approved front/profile/body references and nonempty explicit fitting controls. It cannot silently turn the unfitted stock female source into a claimed Inez asset. Scripts compile; Blender 4.3.2/Cycles/glTF APIs were checked without building a character.

Viewer source/build preflight is accepted as a validation-tool foundation only. It displays the current blocked status, loads original comparisons and initializes WebGL2 in Chromium without errors. No GLB load, UV export, skinning, expression, animation, material or browser-character fidelity check has passed because no actual model exists. WebGPU path has fallback code but was not hardware-validated. Nothing has been deployed or integrated into a nonexistent game repository.


### Call 8 — full-body front v05: paid body edits stopped

Actual v05 retained face/pose but did not transfer the black thread guide reliably and visibly strengthened unsupported pale branching/scratch denim texture. Both independent critics reject it as a material correction. V02 remains the better keeper. Ordinary inspection crops: `qa/05_body_front_v05_material_inspection.png`; no pixels were painted or repaired. The two user-approved extra calls are exhausted; no additional body ImageGen is being attempted. Total calls now 9/24 including the separately authorized left profile in progress.

**Separate geometry scope:** both independent critics explicitly found no visible geometric blocker in v02 and accepted its proportions, complete anatomy and shallow A-pose as a supplementary fitting guide. `references/approved/05_body_front.png` is a copy of v02 with an adjacent mandatory `05_body_front.scope.json`. Ledger status is `approved_geometry_only`. **The full-image material gate remains rejected.** This is not a fabricated 90/100 acceptance. Original A and the portrait control head identity; original B controls clothing, denim, boots and all material decisions. Approved13 is only a neutral black-seam guide. Warm thread and unverified microtexture must never be copied into the 3D asset. This restricted geometric evidence allows useful head/body reconstruction while honoring the user's primary playable-3D deliverable; real model likeness and costume will be assessed separately in browser.

### Call 9 — left profile candidate

One true left 90-degree profile is being generated with both untouched originals and the accepted front portrait. Original A contains no true side photograph, so side depth is explicitly an inferred proposal rather than historical fact. Actual modeling remains waiting on a usable profile and independent initial geometry review.


### Call 11 — corrected left profile v02 and initial geometry gate

Artist inspected actual v02; both independent critics confirmed far-eye occlusion and accepted its visible left90 orientation for conservative head fitting. Identity preserves reserved points for unsupported sagittal/bilateral evidence; technical face33/35 remains broadly consistent. Hair caveat: side portrait tail appears longer than originalB rear evidence, so originalB remains sole authority for tail length. The original images contain no true profile; this is not a claim of historically exact sagittal shape. Scoped profile copied to approved with adjacent.scope.json.

`qa/model/model_gate.json` now records a true **initial geometry-fitting gate**, supported by independent reviews of front portrait, corrected profile, and restricted front-body geometry. This does not clear the held generated-body material gate or grant character/production approval. A licensed continuous mesh will be fitted and rendered in clay. Detailed skin textures and dressed execution wait for a separate credible-head review.

Calls12–14 are separately anchored eye, lip and freckled-skin material-reference candidates in progress. They are not painted textures, editable geometry or browser renders.


## Actual 3D head loop — v01 and v02

Source `model/work/inez_head_v01.blend` is actual licensed continuous fittedgeometry with UVs and normalized sourceweights/skeleton, not an image sheet or primitive mannequin. Four genuine clay camera renders under `renders/head_v01/` were opened against both originals by root and both new independent critics after session continuation. Identity `qa/identity/head_3d_v01.md`:32/39 assessable,61reserved, face21.5/28eligible. Technical `qa/technical/head_3d_v01.md`:34/44 assessable,56reserved, face25/35. **Credible-head gate failed.** Deductions concern pinched alar/tip footprint, compressed mouth/lipvolume, flat/planar lowerface and weak lidfold/support. Missing hair, skin,body andcostume were reserved instead of dishonest penalties or scores.

Actualv02 retained Basis and originalv01 fittedshape(inactive), introduced independently editable cumulativev02 fit(active) and rendered samefour real cameras. Nose/mouthwidth, lowerlip and roundedchin improved; both critics still held upperlip roll/vermilion,seamgap andsuperiorlid/lowerlid form. Exactprofiledepthremains hypothetical. `qa/model/credible_head_gate.json` is false. A focused actualv03 is correcting those topologyregions before any detailedPBR/dressedexecution. Body/hair/materialauthoring remains preparedcode; no completedcharacter claim.

## Viewer implementation and continued reference work

Viewer supports real GLTFLoader asset inspection, orbit/camerapresets, adjustable studio/apartment lights, PBR/debugmaterials, named facial controls, Idle/Walk/Run selection andcrossfades, automatic locomotionweights, smoothed WASD andShiftRun. Source build and headless WebGL foundation checks pass (`viewer/qa/unavailable_preflight.json`); this checked missing-model truthfulness,not actualcharactermotion. Six synthetic controlregressions also pass. Root integration test `tools/inez/browser_qa.py` will require actualvertexdeformation andrealbrowserscreenshots,not presence of a skeleton.

Calls12–16 outputs recovered and visually opened from retained ImageGenfiles after continuation: eyes/lips/skin/rightrprofile/threequarter. Both critics wrote individualreports. Macro references accepted only in stated qualitative scopes; true-right90 onhold duevisiblefar-lashsliver. Threequarter face accepted with pendant excluded whereenlarged. Call17 sidebody left no image after executioncell disappeared; conservatively counted failed instead of fabricatingoutput. Calls18–19 retainedqueued requests are now submitted, call20 retries missing sidebody withinits perview allowance. Total20/24; no extra05bodycalls allowed.


### Actual 3D head v03 — initial authoring gate accepted, final likeness pending

Actual source `model/work/inez_head_v03.blend` preserves original Basis and previous inactive fits plus active combinedv03. Four true clay renders under `renders/head_v03/` were opened by root and both critics. Explicit indexed exterior lid rows now carry actual hood/roll/fold geometry; actual upper vermilion and paired mouthseam were sculpted without changing eyeball/iris dimensions. Topology evidence `qa/model/model_head_v03_topology_inspection.json`; read-only technical eye/iris/pupil hashes remain identical to prior meshes.

Independent identity `qa/identity/head_3d_v03.md`:face26/28eligible,7reserved;36.5/39scope,61reserved. Technical `qa/technical/head_3d_v03.md`:face30/35 (below final32),39/44scope,56reserved. Both recommend only provisional credible underlying geometry for further authoring. Residual nasal-plane, lip/lid regularity and lowerface differences remain; no whole-character90/100 or historicalexactprofile claim. `qa/model/credible_head_gate.json` is now true in that specific scope.

Actual dressed continuous source, real garments/curly hair/accessories and separate UV PBR maps are authorized. OriginalA governshead/skin; originalB all costume/hairlength. Generated scratchdenim/warmwelt and resolved decorative pendant motif must not propagate. After the actual dressedasset is saved, animation bake will use actualbones/weights/morphs and browser checks will require real deformation, blending, movement and screenshots.

Call20 failed because built-in ImageGen allows at most5 anchors; no image was produced, counted against cap. Generator helper now checks count while preserving both originals. Call21 corrects rightprofile orientation; call22 retries sidebody with five anchors. Currentbudget22/24, two unspent calls; no05bodyextra.
