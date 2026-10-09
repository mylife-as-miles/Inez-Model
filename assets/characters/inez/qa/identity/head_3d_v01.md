# Independent identity review — actual clay head v01

Reviewer: `/root/identity_review3`. Date: 2026-10-09. Subjective visual review; no biometric similarity claim.

## Decision

**HOLD the credible-head identity geometry gate. Recommended `credible_head_geometry_passed: false`.** This is a coherent editable adult head, but its visible nose, mouth, lid and lower-face geometry still differs materially from original A. Do not commit detailed facial textures to this version. A material pass must not be used to hide these proportion differences. Continue an actual clay geometry refinement and re-render the same four views.

This finding concerns visible geometry. Missing brown curls, freckles, green-hazel iris color, brow hairs and skin materials are **reserved**, never scored as identity defects in a clay stage. No completed-character ≥90/100 claim is possible from these images, and the actual rigged playable Three.js deliverable remains separately unassessed.

## Evidence actually opened

- Both untouched originals: `references/original/inez_portraits.jpg` (A, final facial authority) and `references/original/inez_turnaround.jpg` (B, final body/costume authority; supplemental near-front face).
- Accepted front portrait `references/approved/01_face_front_neutral.png`, inferred left90 profile `references/approved/02_face_left_profile.png`, and restricted body geometry guide `references/approved/05_body_front.png`; adjacent scope JSONs were read. Generated body materials remain rejected. Original B governs all costume materials and ponytail length.
- Actual model renders: `renders/head_v01/front.png`, `left_profile.png`, `right_profile.png`, and `three_quarter.png`. These are real clay geometry views, not generated reference pictures.
- Identity specification, live visual QA report and earlier original/front/profile identity reports were read.
- `qa/identity/head_3d_v01_front_comparison.png` is an ordinary crop/resize assembly of A right, B face, accepted portrait and actual model front, aligned approximately to pupil height and a common apparent pupil separation. It contains no painted geometry or design repair. Hand-estimated alignment, perspective, expression, source lighting and clay reflectance preclude precise anatomical measurement.

## Geometry findings

1. **Nose:** the frontal alar footprint and rounded lower-tip structure read too constricted relative to eye spacing. The model has two small nostril shadows under a weakly separated tip/wing transition, whereas both originals show appreciable alar width and a substantial softly rounded tip. The actual three-quarter view also lacks the originals' soft wing/tip volumes. This is supported frontal/oblique evidence; it is not a claim that the exact sagittal bridge is known.
2. **Mouth width:** the model corners are drawn inward relative to pupil separation. Approximate crop inspection puts visible clay mouth width around 0.64–0.66 of interpupil distance; the existing broad source-derived sanity band is about 0.70–0.80. Those are uncertain image-space guides, not a recovered physical dimension. Original A also visibly supports more mouth spread than this model.
3. **Lip geometry:** the model's upper lip blends into the philtrum with little vermilion volume; its lower lip is a small narrow shelf. Original A has moderately full, naturally uneven lips with a visibly fuller lower lip and a soft Cupid's bow. Clay eliminates red-lip color, so the judgment rests on the visible seam, surface roll and silhouette in front/oblique/profile views. Do not inflate both lips indiscriminately.
4. **Lower cheek/chin:** the front render terminates in a comparatively broad, flat bottom chin; the three-quarter render carries a straighter lower-cheek/jaw plane into it. A shows softer cheek-to-jaw transitions and a rounded compact chin. Hair occlusion makes outer cheek width uncertain, so do not widen or slim the whole head as a shortcut. Preserve the broadly credible current eye-line-to-chin interval while refining local planes and chin curvature.
5. **Lids:** the visible openings are somewhat too compressed vertically compared with original A and B's supplemental front face, with weakly separated upper-lid folds and little soft lower-lid support. Restore the elongated opening and modest lid relief through eyelid shape. Do not enlarge eyeballs/irises or produce wide round eyes. The accepted generated front already had a slight over-open/round-eye caveat; it is not a mandate to copy that aperture exactly.

The two profiles are mutually coherent and the four renders describe the same intact head. Forehead, ears, neck and skull form are anatomically plausible for an editable adult reconstruction. Original A/B contain no true side view; generated left90 is a conservative hypothesis. Exact skull depth, full ears, sagittal nose/lip/chin projection and bilateral asymmetry are not recovered facts and are reserved below. Ear or skull changes should not outrank the supported frontal nose/mouth/lid correction.

## Original weighted rubric, with clay scope explicitly reserved

| Category | Original maximum | Assessable here | Earned | Deductions / reservation |
| --- | ---: | ---: | ---: | --- |
| Facial identity/proportions | 35 | 28 | 21.5 | −1.5 alar/tip footprint; −1 mouth spread; −1.5 upper/lower lip roll and volume; −1.5 flat chin/straight lower-cheek transition; −1 compressed lid opening/weak lid structure. Reserve 7 for unsupported exact sagittal depth, ears and hidden bilateral identity. |
| Body silhouette | 15 | 0 | — | All 15 reserved: a head/neck crop cannot establish dressed body proportions. |
| Hair identity/silhouette | 15 | 0 | — | All 15 reserved: no hair geometry is shown. No deduction for absence in clay. |
| Costume/accessories | 10 | 0 | — | All 10 reserved: sweater, jeans, boots and necklace are outside this stage. |
| Skin/eyes/materials | 10 | 0 | — | All 10 reserved: clay cannot certify albedo, freckles, iris color or PBR skin. No deduction for white clay. |
| Cross-view consistency | 10 | 6 | 6 | Front, both sides and oblique coherently show the same geometry. Reserve 4 for missing body/hair/costume correspondence. Coherence does not establish unseen original side depth. Facial deviations are deducted above, not counted twice here. |
| Technical visual usability | 5 | 5 | 4.5 | −0.5 low-contrast diffuse clay lighting partly washes out alar/lip/lid plane boundaries. Intact framing and genuine multi-angle evidence are otherwise useful. These images do not test topology, UVs, skinning or animation. |
| **Total** | **100** | **39** | **32** | **61 explicitly reserved; 82.1% of this limited scope only. No whole-character score.** |

Facial result is **21.5/28 eligible**, with 7 facial points reserved. Do not label this as passing the final ≥32/35 face criterion. A geometry refinement is required before detailed skin work, independently of later texture fidelity.

## Prioritized concrete next actions

1. Broaden the supported frontal alar wings and restore a softly rounded nose-tip/wing transition using original A, with B only as a frontal ratio check. Keep bridge/sagittal controls editable; avoid sharpening or upturning the nose.
2. Move mouth corners outward conservatively toward the source sanity band; rebuild a soft Cupid's bow and moderately full vermilion, particularly the lower lip. Maintain the relaxed closed seam, natural asymmetry and current broad mouth-to-chin interval.
3. Round the chin bottom and soften the local lower-cheek/jaw planes. Check both front and three-quarter silhouette without making the whole face narrower or wider. Preserve a natural, compact chin rather than a pointed apex.
4. Adjust eyelids to a modestly taller natural elongated opening, retain upper hooding and add soft upper-fold/lower-lid relief. Eyeball and iris scale should remain restrained.
5. Produce another actual front, left, right and three-quarter clay set under enough side light to separate lip, nose and lid planes. Keep original A and B attached to review. Only a successful independent geometry re-review may change the recommended false texture gate.

Nothing in this review approves generated body microtexture, inferred exact profile depth, a dressed model, or a playable/browser identity result. That later stage requires the real character rendered and controlled in Three.js.
