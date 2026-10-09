# Inez actual clay head v03 — independent technical review

Reviewer `/root/technical_review3` independently opened all four actual `renders/head_v03/{front,left_profile,right_profile,three_quarter}.png`, both untouched originals, approved portrait and scoped left profile; compared actual v01/v02 evidence; inspected `model/work/inez_head_v03.blend` read-only in Blender 4.3.2 and read the manifest/topology inspection. Original A remains facial authority; B remains body/costume/ponytail authority. All exact side depth remains a hypothesis.

## Gate recommendation

**`credible_head_geometry_passed: true` — LIMITED initial geometry credibility for prototype materials and dressed construction.**

V03 resolves the principal technical blocker recorded at v02: the upper lid now has a visibly modeled fleshy roll/canopy and separate fold, with a readable lower rim. The upper-lip body and resting seam also improve. The head is coherent, continuous, editable and anatomically plausible across all four real cameras; no static malformed feature, extra eye, severe gap or proven intersection blocks downstream prototyping.

**This is not completed facial likeness or production approval.** Face remains **30/35**, below the ≥32/35 working target for final likeness. The limited pass permits materials/hair/clothing to be built and reviewed on the actual mesh while retaining editable head revisions; it does not freeze the sculpt, approve textures, waive the independent identity critic's decision or establish a finished character. Root should require further original-based shape refinement if later actual material/browser views retain these differences.

This narrower construction decision differs from v02's hold because the visible lid-construction failure has been materially corrected. It is not an invented ≥90 score or an assumption that texture will recover missing anatomy. Residual source-shape differences remain scored below.

## Original 100-point rubric, available evidence

Weights remain 35/15/15/10/10/10/5. Only **44 points** are assessable for this static clay-head pass, with **56 reserved**. Scores are visual judgments, not biometric similarity percentages.

| Category | Weight | Assessable | Award | Every deduction / reservation |
| --- | ---: | ---: | ---: | --- |
| Facial geometry/identity | 35 | 35 | 30 | −1.5: the newly legible bilateral upper folds are more regular and ridge-like than A's restrained asymmetric hooding; construction is credible, but shape finesse remains. −1: nasal wing/tip transition is still generalized compared with A's substantial softly rounded tissue; improved breadth is retained and no failed exact width ratio is asserted. −1.5: upper-lip/seam body improves, but Cupid's-bow/corner contour remains angular and more regular than the natural originals. −1: lower cheeks/chin remain broadly smoothed with less localized soft fullness than A. Absent hair/brows/materials are not geometry deductions. |
| Body silhouette | 15 | 0 | Reserved | No actual dressed-body silhouette in these renders. |
| Hair | 15 | 0 | Reserved | No actual hair; bald skull is not penalized as a hairstyle error. |
| Costume/accessories | 10 | 0 | Reserved | No actual dress/boots/necklace. Generated-body material hold remains active. |
| Skin/eyes/materials | 10 | 0 | Reserved | Flat clay and gray landmark disks; no PBR skin/iris/cornea score invented. |
| Cross-view | 10 | 6 | 6 | No static-scope deduction: one coherent head across front/±90°/45°, plausible near-eye-only profiles, intact facial silhouette and no changing or duplicated features. Four points reserved for original-undetermined bilateral depth and deforming-view consistency. |
| Technical usability | 5 | 3 | 3 | No static-scope deduction: readable complete cameras, continuous editable quads/revision keys, UVs and weighted separate eyes. Two points reserved for tested deformation/export/browser behavior. |

**39/44 assessable (88.6%); 56/100 reserved. Face 30/35.** No whole-character ≥90/100, full head likeness acceptance, completed rig or playable result follows.

## Actual changes and remaining work

- The upper roll and crease are now visible in front and three-quarter, with a lid-to-orbit transition that v01/v02 lacked. Left/right silhouettes remain coherent. Folds should be softened and varied to match A rather than made into identical decorative ridges. This refinement can occur alongside prototype material work; it is not a reason to enlarge irises or eyeballs.
- The upper lip is fuller, lower lip remains fuller than the upper, and the resting seam is narrower. Preserve these gains. Further soften corners and the regular/angular bow; do not inflate lips or hide a poor seam with albedo. A visible narrow dark seam is normal and not itself a failure.
- Nasal base improvement from v02 remains; tip/alar tissue rounding changes are modest. Assess alar outline rather than nostril-center separation. Soft clay shading does not support a new exact width-ratio claim. Original A/B guide frontal breadth; generated profile controls only a conservative unverified depth proposal.
- Chin remains compact/rounded rather than pointed. Local lower-cheek/chin transitions can still be refined from the original oblique volumes. Exact posterior skull and complete hidden ear morphology are unresolved and receive no speculative redesign penalty.

## Geometry and rig audit

- Continuous mesh remains **13,380 vertices / 13,378 quads**, with UV layer `MakeHuman_CC0_UV`, 139 vertex groups, armature/subdivision and retained editable Basis/v01/v02/v03 keys; v03 is active. Every body vertex has a weight entry. Edge-incidence audit again finds no one-face body boundaries and no edge used by more than two polygons. These are meaningful continuity facts, not a complete self-intersection/loop/deformation guarantee.
- Read-only coordinate hashes of actual `EyeGeometry_L/R`, `IrisQA_L/R` and `PupilQA_L/R` match v02: **globe and iris/pupil mesh coordinates were not resized or blanket translated**. The reviewed topology-inspection JSON records localized exterior superior-lid rows, lower-roll vertices, upper-vermilion vertices and matched mouth-seam pairs. The resulting visible change is actual mesh construction.
- A visual exposed-sphere concern in prior renders did not prove an intersection. V03's rest construction is now credible; no arbitrary contact translation is recommended. A proper blink/gaze test must check lid contact throughout rotation/closure on the exported mesh.
- The armature contains **163 bones**, including eye/jaw/facial bones; there are **no animation actions** in this reviewed blend. Fitting shape keys are not a tested expression set. UV presence does not establish final atlas density, seams or texture quality.
- Actual orthographic front, ±90° profile and +45° oblique views have complete crown/chin/ears and coherent scale. No far eye is spuriously exposed in either actual profile. Newly generated right-profile corrections are separate evidence, not replacements for these renders.

## Downstream constraints

Proceed only after root reconciles this limited technical pass with the independent identity review. Keep head revisions editable, original-B garment materials and rear ponytail length authoritative, and rejected warm welt/denim scratches excluded. Skin, brows, lashes, cornea/tearline, hair, dressed silhouette and tiny unresolved pendant require their own actual-mesh reviews.

No GLB or browser character is approved here. Later review must inspect actual UV/material export, normalized skinning, eye/jaw/blink deformations, Idle/Walk/Run and blending, weighted hair behavior and real Three.js screenshots/controls. Those are required for the user's primary playable-character deliverable.
