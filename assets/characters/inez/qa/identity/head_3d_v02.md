# Independent identity review — actual clay head v02

Reviewer: `/root/identity_review3`. Date: 2026-10-09. Subjective visual evidence assessment, not a biometric measure.

## Decision

**HOLD: recommended `credible_head_geometry_passed: false`.** V02 is a useful geometric improvement over v01, but a focused upper-lip/resting-seam correction remains necessary before committing detailed facial textures. Eyelid fold/roll structure should be corrected in that same actual geometry iteration. This is an initial identity-geometry gate, not a demand for finished skin, hair or a final production score.

A limited weighted total happens to exceed 90% because the multi-view presentation is coherent and usable. That number does not waive the concrete supported facial geometry finding or establish a complete ≥32/35 face or ≥90/100 character result. Missing hair/materials/body/costume are reserved, not deducted. The playable rigged Three.js deliverable is still outside this review.

## Actual evidence reviewed

Both untouched original A (`references/original/inez_portraits.jpg`, final face authority) and original B (`references/original/inez_turnaround.jpg`, final body/costume authority and supplemental front face) were reopened directly. All four actual v02 renders were opened: `renders/head_v02/front.png`, `left_profile.png`, `right_profile.png`, and `three_quarter.png`. V01 front/three-quarter, accepted generated front portrait and restricted inferred left90 profile were also directly reopened; the earlier v01 side renders were already directly inspected in this review sequence. Model source is identified as `model/work/inez_head_v02.blend`, but this identity assessment is based on visible actual renders, not an unperformed topology examination.

The ordinary crop/resize comparison `qa/identity/head_3d_v02_front_comparison.png` contains A right, B face, actual v01 and actual v02, approximately normalized to pupil height/separation. No pixels were painted or repaired. Alignment is hand-estimated. Source pose, expression, perspective and clay reflectance prevent exact anatomical measurement. A remains final authority; accepted references only guide a conservative neutral reconstruction. Exact profile depth, full ears and hidden asymmetry remain unresolved.

## What improved and what still needs correction

- **Mouth spread improved.** V02 corners moved outward and read close to the lower part of the source-derived broad mouth-width band. I no longer treat v01's compressed mouth width as a primary blocker. Do not keep widening it to chase a single expression in A.
- **Lower-lip roll improved.** Front and oblique views now show a fuller, softer lower lip. Preserve that change.
- **Nose breadth improved.** Frontal alar footprint is less pinched; side/oblique tip remains softly rounded. A residual weak separation of alar wings and lower-tip volume remains, but it is secondary to the lip issue. Do not sharpen or upturn the nose, or force an exact inferred side curve.
- **Chin curvature improved.** V02 rounds the previously flatter bottom and softens the lower-face transition. A small straight/clean lower-cheek-plane impression remains in oblique, but the supported eye-to-chin interval is credible. Preserve the gain rather than globally rescaling or narrowing the head.
- **Upper lip remains insufficiently developed.** It still reads as a thin shallow band merging into the philtrum, particularly at front. The actual side/oblique roll is also modest relative to A's moderately full soft upper vermilion and Cupid's bow. Red-lip color is absent in clay and cannot define a vermilion boundary here, but a color mask should not substitute for this supported surface-roll difference. The lower lip must remain fuller than the upper without making the upper nearly flat.
- **Resting seam remains slightly open.** A small dark central wedge/gap persists. The canonical reconstruction calls for a gently closed resting mouth. Make a fine coherent resting contact seam without flattening lip volume or clamping the corners.
- **Lid structure remains weak.** Openings are still somewhat vertically compressed and the upper-fold/lower-lid support is subtle/washed out in both front and oblique. Restore a modest soft upper-lid fold and lower-lid roll around the actual eye region. Retain elongated hooded eyes; do not enlarge eyeballs/irises or turn them round/wide-open. The generated front's known slight over-open-eye caveat must not become an exact target.

All views describe the same intact anatomically plausible adult head. Bilateral profiles are coherent. Unknown sagittal/bilateral features cannot be certified from original A/B and are not grounds for arbitrary profile redesign.

## Original 100-point weights with clay scope reserved

| Category | Original maximum | Assessable | Earned | Deductions / reservation |
| --- | ---: | ---: | ---: | --- |
| Facial identity/proportions | 35 | 28 | 24.75 | −0.75 residual weak alar/tip structure; −1.25 upper-lip roll/volume and resting seam; −0.5 residual straight lower-cheek/chin transition; −0.75 compressed aperture/weak lid structure. V01 mouth-width deduction removed. Reserve 7 for exact unsupported sagittal, ear and hidden bilateral identity. |
| Body silhouette | 15 | 0 | — | All 15 reserved. |
| Hair identity | 15 | 0 | — | All 15 reserved; no deduction for bald clay. |
| Costume/accessories | 10 | 0 | — | All 10 reserved. |
| Skin/eyes/materials | 10 | 0 | — | All 10 reserved; no deduction for white clay, missing freckles/brow hairs or absent iris color. |
| Cross-view consistency | 10 | 6 | 6 | Actual front, both profiles and oblique coherently show one geometry; reserve 4 for absent full-character correspondence. No duplicate facial deductions. |
| Technical visual usability | 5 | 5 | 4.5 | −0.5 diffuse low-contrast clay lighting partly washes out nasal/lip/lid planes. Full framing and actual multi-angle evidence are useful. UVs, skinning and animation are not tested by these images. |
| **Total** | **100** | **39** | **35.25** | **61 reserved; 90.4% of this limited scope only.** |

Facial evidence is **24.75/28 eligible**, with 7 reserved. This is an improvement from v01's 21.5/28; neither is a complete final facial score. The upper-lip/resting-seam finding keeps the texture gate false despite the scoped overall percentage.

## Focused v03 actions

1. Preserve v02 mouth width, lower-lip fullness, alar breadth, rounded chin and broad eye-to-chin spacing.
2. Sculpt a moderate upper-lip surface roll and soft Cupid's bow directly from A. Close the small central resting gap through local contact geometry while retaining a natural narrow seam. Avoid an inflated upper lip, a sharp symmetric bow or tightened corners.
3. Adjust the actual upper-lid fold/lower-lid support locally in the eye region, with restrained opening correction if needed. A crease applied below the eyes or to the midface cannot address this finding. Keep eyeball/iris scale fixed and hooding natural.
4. Re-render the same four actual clay views with light sufficient to separate small folds. Reassess original A/B and the genuine model before changing the recommended gate.

No further ImageGen or body-material edit is required by this report. No detailed texture, dressed character, rig, browser likeness or production acceptance is granted.
