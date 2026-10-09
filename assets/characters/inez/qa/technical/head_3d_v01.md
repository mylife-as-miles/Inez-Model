# Inez actual clay head v01 — independent technical critique

Reviewer: `/root/technical_review3`, independent TECHNICAL CRITIC. This is a review of an actual Blender mesh and its four actual clay renders, not a generated portrait or a browser character. No model, reference, ledger or production-status file was changed by this reviewer.

## Gate decision

**`credible_head_geometry_passed: false`**

The licensed, editable quad mesh is a useful fitting foundation, and the four cameras show a coherent head. It does not yet preserve Inez's nasal width, resting lip volumes, eyelid construction and lower-face contour sufficiently to clear the credible-head gate. Correct those geometric issues and re-render clay before detailed facial materials or dressed character execution. A texture pass cannot establish the missing facial volumes.

This decision is not a production approval. No whole-character 90/100 score, completed rig, valid GLB, working animation or Three.js likeness acceptance is claimed.

## Evidence opened independently

- Both original JPEGs: `references/original/inez_portraits.jpg` (A, facial authority) and `references/original/inez_turnaround.jpg` (B, body/costume authority and supplemental front face).
- `references/approved/01_face_front_neutral.png` and `references/approved/02_face_left_profile.png`, including the profile's mandatory scope. The generated profile is an initial depth hypothesis; neither original contains a true 90-degree view.
- Actual `renders/head_v01/front.png`, `left_profile.png`, `right_profile.png`, and `three_quarter.png`.
- `model/work/inez_head_v01.blend`, opened with Blender 4.3.2 for read-only data inspection; `qa/model/model_head_v01_manifest.json`; the build source; identity lock, production log and prior technical reports.
- Plain inspection crops saved alongside this report: `head_v01_front_feature_crop.png`, `head_v01_three_quarter_eye_crop.png`, and `head_v01_original_B_feature_crop.png`. They are crops only; no source or render pixels were painted, designed or repaired.

## Original 100-point rubric, evidence-limited scope

Scores are subjective visual judgments, not biometric similarity percentages. The category weights remain 35/15/15/10/10/10/5. Only 44 points have sufficiently assessable evidence for this clay-head stage; **56 points are reserved**.

| Category | Original weight | Assessable | Award | Deductions / reservations |
| --- | ---: | ---: | ---: | --- |
| Facial identity and geometry | 35 | 35 | 25 | −3 nose: the front alar/tip region is too narrow and insufficiently rounded relative to A/B; the silhouette also reads sharper in the clay profiles than the conservative generated hypothesis. −3 eyes/lids: shallow, thin lid rims and a largely smooth upper orbit fail to reproduce the visible upper-lid fold and hooding; oblique eye exposure reads too spherical. −2 lips: the upper lip is flattened/reduced, the corners are sharply pinched, and the dark resting seam has an irregular angular contour rather than the sources' narrow natural seam. −2 lower face: lower cheeks and chin read as a broad, smooth shelf with weak local transitions rather than the sources' soft cheek fullness, gradual jaw taper and compact rounded chin. These are geometry deductions; absent skin texture or brows are not used to reduce this category. |
| Body silhouette | 15 | 0 | Reserved | No actual clothed full-body render is supplied for this pass. Source body mesh existence does not establish dressed silhouette. |
| Hair | 15 | 0 | Reserved | No actual hair geometry is present in the clay renders. Bald cranial volume is not penalized as hairstyle failure. |
| Costume and accessories | 10 | 0 | Reserved | No actual clothing, boots, chain or pendant is rendered. Rejected generated-body materials are not scored or approved here. |
| Skin, eyes and materials | 10 | 0 | Reserved | Flat clay and gray gaze-marker disks intentionally lack production skin, hazel irises, cornea/tearline appearance, freckles and PBR detail. No material points are invented. Eye/lid shape is assessed above as geometry. |
| Cross-view consistency | 10 | 6 | 6 | No deduction within the static assessed scope: nose/lips/chin/ears rotate coherently, near/far-eye occlusion is plausible at the supplied profiles, and there is no duplicated or changing feature between renders. Four points remain reserved for source-undetermined bilateral/depth anatomy and later deforming-view consistency. Internal coherence does not prove historical profile likeness. |
| Technical usability | 5 | 3 | 3 | No deduction within the static assessed scope: complete head framing, legible orthographic cameras, editable quad topology, UVs, weights and separated eyes are actually present. Two points remain reserved for deformation/eye-contact tests and exported/browser behavior. Skeleton existence is not proof of usable facial rigging. |

**Assessed subtotal: 34/44 (77.3% of available evidence). Facial geometry: 25/35. Reserved: 56/100.** This is not a full-character score and does not meet the face ≥32/35 working target. The gate remains false independently of any normalized subtotal.

## Geometric findings and required correction

1. **Broaden and round the nasal alar/tip construction.** The front render has pupil spacing about 165–170 pixels. The softly lit outer alar region appears roughly 70–85 pixels wide (about 0.42–0.51 IPD; approximate visual reading, not a calibrated landmark solution). Original B's observed band is approximately 0.58–0.68 IPD. The original A portraits independently show a substantial rounded tip and visible nasal wings. Define the outer wings from the original forms rather than merely enlarging nostril holes. Preserve the narrow-to-moderate bridge and gradual bridge-to-tip widening. Do not use the generated lateral view as factual nasal projection authority.

2. **Reconstruct upper lids and orbit-to-eye wrapping.** The clay front has a readable pair of elongated openings, but the upper-lid fold/hood and lower-lid thickness are weak. In three-quarter view the white eye surface appears disproportionately exposed and the surrounding socket looks like a smooth opening around it. This is a visible contact/shape concern, **not a proven mesh penetration count**. Adjust eyelid loops, eye placement and canthus thickness together. Re-render close front/three-quarter and test a closed blink plus left/right gaze after the static correction. No bright white wedge should appear outside the intended lid opening during rotation.

3. **Restore the resting lips and mouth corners.** The lower lip remains fuller, which is supported, but the upper lip's body/Cupid's-bow transition is reduced and the seam has a sharp irregular gap. Keep a narrow resting seam with softly turning corners and a natural upper-lip volume; do not inflate the lower lip to compensate. The originals' tension may be neutralized, but lip dimensions should survive that operation. Verify jaw opening separately; this clay opening does not establish mouth-interior quality.

4. **Refine lower-cheek, jaw and chin transitions conservatively.** The front chin is broad and rather flattened, and the oblique lower face is smoothly generalized. Retain the source's compact rounded chin with visible width and soft cheek volume. Avoid solving this with a pointed chin or hollow cheeks. Exact posterior skull, hidden ear contours and true sagittal chin projection remain hypotheses; no automatic penalty is assigned for the unobserved bald cranium.

These four tasks are focused sculpt/fitting changes to the actual continuous head. Retain the editable basis and fitting key, original reference authority and inference labels. Another four-angle clay review should precede any gate update.

## Read-only Blender audit: confirmed facts and limits

- `Inez_ContinuousHumanMesh_UNAPPROVED`: **13,380 vertices, 13,378 four-sided polygons**, UV layer `MakeHuman_CC0_UV`, 139 vertex groups, armature modifier, editable subdivision and two shape keys (`Basis_FemaleYoung_Source`, `Inez_HeadFit_v01`). The fitted key is active at 1.0.
- A polygon-edge incidence audit found **zero one-face boundary edges and zero edges used by more than two polygons** on the body mesh. Every body vertex has at least one weight entry. These facts support continuity and editability, but do not certify loop placement, normalized weights in the eventual export, self-intersection freedom or expression deformation.
- Both `EyeGeometry_L/R` are separate **72-vertex, 70-quad closed meshes** with UVs, an eye-bone attachment and subdivision. Their gray iris and pupil markers are additional 49-vertex/48-triangle disk meshes with radial UVs. The disks' open circumference is expected for temporary surface landmarks; they are not production corneas or textured eye components.
- `InezRig_PROTOTYPE` contains **163 bones**, including eyes, jaw and facial bones. **No animation actions exist in this reviewed blend.** Only the fitted-head shape key exists beyond the basis; no blink or expression morph is yet proven. No hair, dressed-body or production texture construction exists in this evidence set.
- One actual camera is stored as orthographic. Build inspection confirms front 0°, left +90°, right −90°, and three-quarter +45° rotations around the same head target. The resulting profiles expose the near eye as a narrow wedge; they do not show an extra far eye. Crown, chin and ears remain inside all supplied frames. The neck exits the portrait frame as expected.
- UV coordinates exist and lie within the recorded 0–1 range. Their presence does **not** establish a final face atlas, seam quality, texel density, lack of UV overlap or production PBR readiness.
- No model was exported or loaded by this reviewer. Idle/Walk/Run, blending, playable control, eyes/jaw/blink, hair motion, material integrity and real browser screenshots remain separate required gates for the user's primary Three.js deliverable.

## Handoff

**Hold `credible_head_geometry_passed` false.** Proceed with a targeted actual-head revision and clay review. Root owns the ledger/status decision; the model artist owns geometry changes. Material/dressed preparation may be retained, but it cannot substitute for clearing this head gate. Later technical review must inspect the actual skinned GLB, facial deformations, animation clips/blends and browser screenshots before any playable-character claim.
