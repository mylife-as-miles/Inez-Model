# Independent identity review — actual clay head v03

Reviewer: `/root/identity_review3`. Date: 2026-10-09. Subjective visual evidence assessment; not biometric similarity.

## Decision

**Provisional initial authoring gate PASS: recommended `credible_head_geometry_passed: true`.** The actual v03 model now supplies a visible moderate upper-lip roll, a substantially narrowed resting seam, and real upper-lid folds at eye level. Those changes address the specific v02 blockers. V02's improved mouth spread, lower-lip fullness, alar breadth and rounded chin are preserved across the four real views. There is enough supported identity geometry to permit further texture/hair/dressed authoring, with all controls editable.

This is a limited initial geometry-credibility decision. It does **not** certify final facial identity ≥32/35, whole-character ≥90/100, recovered exact profiles, production acceptance, rigging or a playable Three.js result. Residual local differences are documented below and must be reassessed on the actual textured character in the browser. Skin color, brows and freckles may help expose likeness differences but cannot be used to cover geometric errors. This recommendation should be considered with the other independent review before the artist changes the project gate.

## Evidence actually opened

Both untouched original A (`references/original/inez_portraits.jpg`, final facial authority) and B (`references/original/inez_turnaround.jpg`, final body/costume authority and supplemental near-front face) were reopened directly for v03. All four actual renders were independently opened: `renders/head_v03/front.png`, `left_profile.png`, `right_profile.png`, and `three_quarter.png`. Earlier v01/v02 four-angle views and approved front/inferred-left reference images were directly inspected in the preceding reviews. Their front renders were reopened in the comparison assembly below. Left-profile scope was reread: exact historical side depth is unknown; original B overrides the generated tail length.

Source is identified as `model/work/inez_head_v03.blend`; this visual review does not claim to have tested its topology or rig. `qa/identity/head_3d_v03_front_comparison.png` is an ordinary unretouched crop/resize board of A, B and actual v01/v02/v03 fronts, approximately aligned to pupil height/separation. No painting or generated repair was applied. Hand-estimated alignment, perspective, source expression and clay reflectance prevent exact anatomical measurement.

## Actual geometry assessment

**Corrected sufficiently for this initial gate:**

- V01's narrow mouth spread was corrected in v02 and remains. Do not widen further from a single concerned source expression.
- Lower lip remains fuller than the upper, with a soft rounded roll rather than v01's narrow shelf.
- Upper lip now separates visibly from the philtrum and presents a moderate soft roll in front, side and oblique. It is still somewhat cleaner/less full than A, but no longer reads as the nearly flat band that held v02.
- The central seam is substantially narrower and reads as a plausible gently resting contact line. Tiny dark seam shading is not itself proof of a meaningful open-mouth defect. No large wedge or exposed teeth is visible.
- Upper-lid folds are now distinctly visible above the openings, with lower-lid support present. Eyeball/iris scale stays restrained and consistent across views. The model retains horizontally elongated windows rather than round enlarged eyes.
- Nose is less pinched than v01; chin bottom and lower-cheek transition are softer than v01. Current broad eye-to-chin spacing remains credible in the qualified frontal fit.

**Residual differences to retain for later actual-model review:**

1. Alar-wing/lower-tip plane separation remains somewhat soft and simplified compared with A's appreciable wings and rounded lower-tip character. Do not narrow or sharpen it; inspect under directional light and later skin roughness before making further broad changes.
2. Upper-lip/Cupid's-bow contour remains regular and a little restrained compared with A's naturally uneven fuller roll. Do not inflate it or make a sharp symmetric bow. This is now a minor retained fit caveat rather than a blocker to initial authoring.
3. Lower-cheek-to-chin planes remain cleaner/straighter in oblique than A's soft facial fullness. Hair conceals the source contour, so exact outer-cheek width is uncertain. Avoid globally slimming or widening the head.
4. Lid folds are comparatively smooth even arcs. Preserve natural hooding and restrained aperture; avoid deep identical creases or wide-open eyes when adding brow/lash/skin detail. The generated front's known slight open/round-eye caveat remains subordinate to A.

Forehead, ears, neck and skull are anatomically plausible as a conservative editable reconstruction. Both profiles and the oblique are coherent with the front. Neither original contains a true profile: exact sagittal bridge/lip/chin projection, complete ear anatomy, skull depth beneath hair and hidden asymmetry remain reserved rather than silently certified.

## Original weights with clay-only scope

| Category | Original maximum | Assessable | Earned | Deductions / reservation |
| --- | ---: | ---: | ---: | --- |
| Facial identity/proportions | 35 | 28 | 26 | −0.75 simplified alar/tip plane structure; −0.5 regular/restrained upper-lip roll; −0.5 clean lower-cheek/chin transition; −0.25 regular lid-fold arcs. Reserve 7 for unsupported exact sagittal, ear and hidden bilateral identity. Earlier mouth-width, seam and weak-lid blockers are no longer deducted as major failures. |
| Body silhouette | 15 | 0 | — | All 15 reserved. |
| Hair identity | 15 | 0 | — | All 15 reserved; missing curls/brows are not deductions in clay. |
| Costume/accessories | 10 | 0 | — | All 10 reserved. |
| Skin/eyes/materials | 10 | 0 | — | All 10 reserved; no deduction for white clay, absent freckles/iris color or unfinished PBR. |
| Cross-view consistency | 10 | 6 | 6 | Genuine front, both profiles and oblique coherently show the same geometry. Reserve 4 for missing full-character correspondence. No duplicate facial deduction. |
| Technical visual usability | 5 | 5 | 4.5 | −0.5 low-contrast diffuse clay lighting partially washes out fine facial planes. Full framing and actual views are useful. UVs, skinning and animation remain untested here. |
| **Total** | **100** | **39** | **36.5** | **61 reserved; 93.6% of this limited geometry/presentation scope only.** |

Facial evidence is **26/28 eligible**, with 7 reserved. Do not turn that scoped fraction into a final 32/35 or biometric claim. Missing category points cannot be awarded until actual corresponding model evidence exists.

## Authoring handoff and next gate

Proceed conservatively with editable v03 geometry, original A-grounded skin/eye maps, original B-grounded hair extent and costume, and the separately restricted material guides. Preserve the v03 gains. Keep original freckle clustering/roughness irregular and restrained rather than copying synthesized macro patterns. Keep the necklace tiny and motif unresolved; do not copy the generated bead cluster. Generated body denim/boot warmth remains excluded.

Next identity assessment must inspect genuine textured/dressed model renders and real Three.js screenshots at front, side and oblique, including facial closeups and complete costume. That review can require additional sculpting if skin/hair/light exposes a supported geometry mismatch. Rigging, locomotion/blending and facial controls require separate genuine technical/browser evidence. No final identity or playable completion is approved by this clay report.
