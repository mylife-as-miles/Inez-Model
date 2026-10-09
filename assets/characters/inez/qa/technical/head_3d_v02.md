# Inez actual clay head v02 — independent technical review

Reviewer `/root/technical_review3` opened all four actual `renders/head_v02/{front,left_profile,right_profile,three_quarter}.png`, compared them with v01, both untouched originals, approved front and scoped left-profile hypothesis, and opened `model/work/inez_head_v02.blend` in Blender 4.3.2 for a read-only audit. Manifest: `qa/model/model_head_v02_manifest.json`. A remains facial authority; B remains body/costume and ponytail authority. No model/status/ledger was changed by this reviewer.

## Decision

**`credible_head_geometry_passed: false` — retain the geometry hold.**

V02 improves mouth width/resting closure, nasal base breadth and chin compactness. The changes are visible actual mesh work, not a material disguise. The remaining primary blocker is weak upper-lid mass/hood/fold construction, particularly in three-quarter view; facial feature transitions also remain generalized. The revision is a better fitting basis, but it does not yet meet the face working target or clear detailed facial textures/dressed execution.

**The exposed-sphere visual impression does not prove an intersection.** No blanket inward eye movement or lid translation is recommended. Reported mathematical globe/rim clearance is compatible with a technically separated eye and an aesthetically insufficient hood. The next work should target the actual exterior lid rows and local fold/roll shape, preserving iris/globe size and measuring any proposed contact changes.

## Original-weight, scoped assessment

Original weights remain face 35, body 15, hair 15, costume 10, skin/eyes/materials 10, cross-view 10, usability 5. Static clay-head evidence permits 44 points; **56 are reserved**. Scores are subjective visual judgments, not biometric metrics.

| Category | Weight | Assessable | Award | Every deduction / reservation |
| --- | ---: | ---: | ---: | --- |
| Facial geometry/identity | 35 | 35 | 27 | −3: upper lids remain thin rims around a largely smooth orbit; source hood/fold and fleshy roll are insufficiently legible, and oblique eye openings retain a generic spherical appearance. −1.5: nasal base is broader than v01, but wing/tip transitions remain generalized and the lateral tip reads more wedge-like than the source's substantial rounded form; remaining width uncertainty is not a calibrated failed-ratio claim. −2: mouth closure/spread improve, but upper-lip body, corner turning and the seam still have an angular/pinched contour rather than A's natural soft irregularity. −1.5: more compact chin improves v01, but the lower cheek/chin surface remains a broad smooth shelf with weak source-like local transitions. Absence of hair/brows/texture is not a deduction in this geometry category. |
| Body | 15 | 0 | Reserved | No actual dressed-body render assessed. |
| Hair | 15 | 0 | Reserved | No actual hair. Bald skull silhouette is not scored as hairstyle failure. |
| Costume | 10 | 0 | Reserved | No clothing/accessories rendered; body-reference material hold remains in force. |
| Skin/eyes/materials | 10 | 0 | Reserved | Deliberate clay plus temporary gray iris/pupil disks; no PBR/skin/eye appearance score invented. |
| Cross-view | 10 | 6 | 6 | No deduction in static scope: rotations are coherent, profiles expose only the near eye, and nose/lips/chin remain one plausible head rather than changing features. Four points reserved for source-undetermined depth/bilateral anatomy and deformed-view consistency. |
| Technical usability | 5 | 3 | 3 | No deduction in static scope: complete framing, readable orthographic views, editable quad mesh/keys, UVs and weighted eye/body objects. Two points reserved for tested deformation and exported/browser behavior. |

**36/44 assessable (81.8%); 56 reserved. Face 27/35 versus v01's 25/35.** This is not a 100-point character score, completed likeness, production approval or playable result. The face remains below the ≥32/35 working target.

## Focused priorities for v03

1. **Shape the actual exterior superior-lid rows.** Use the diagnosed upper exterior rows around source Z≈1.34–1.35 rather than the old crease field centered near Z≈1.26. This location is a model-space implementation diagnostic supplied by the model artist, not a measurement of original anatomy. Build a restrained fleshy lid roll/canopy and a fold above it, with continuous canthus transitions. Preserve the horizontally elongated aperture and globe/iris dimensions; do not enlarge the eyes to manufacture likeness. A controls hooding, with generated08 useful only as a qualitative detail guide.
2. **Keep nasal improvement and refine the fleshy wings/rounded tip.** Judge the full alar outline, bridge-to-tip widening and rounding in front/three-quarter. Do not equate nostril center separation with alar width. Broadening is now visibly better; no new exact ratio is asserted because soft clay illumination obscures the boundary. Make only original-supported shape changes; profile projection remains a conservative hypothesis.
3. **Refine lip/corner geometry locally.** Keep the improved narrower resting gap and slightly wider mouth. Soften the pinched corners and angular seam, restore the modest upper-lip volume/Cupid's-bow transition and retain a fuller lower lip without inflation. A dark natural seam is expected; darkness alone is not a failure. The issue is its shape and surrounding volumes.
4. **Retain compact chin; improve local lower-cheek/chin transitions conservatively.** Do not introduce a point, hollow cheeks or exaggerated chin projection. A/B show soft fullness and a rounded substantial chin. Hidden posterior skull and exact ear anatomy remain inferred and do not require speculative redesign.

Supply the same actual four-camera clay evidence and close front/oblique eyelid views. Once static construction improves, verify an actual closed blink and gaze rotations; skeleton names or plausible rest clearance do not demonstrate those behaviors.

## Read-only technical findings

- Continuous body remains **13,380 vertices / 13,378 quads**, with `MakeHuman_CC0_UV`, 139 weighted groups and no unweighted vertices. Polygon-edge incidence reports no one-face boundaries and no edge used by more than two polygons. This supports editability/continuity, not a guarantee against all self-intersections or a full loop/deformation approval.
- Editable fitting revisions are retained; the current fitted revision is active. Separate `EyeGeometry_L/R` remain 72 vertices / 70 quads with eye-bone attachments. Gray iris/pupil markers remain temporary disks, not production corneas/eye textures.
- Prototype armature has **163 bones**. No animation actions are present. The supplied stage has no authored hair, dressed mesh, production textures or tested expression set. UV presence does not prove production atlas/texel density/seam quality.
- All four cameras maintain usable scale, complete crown/chin/ears and coherent silhouette. No extra far eye is visible in either actual profile. The saved camera/build setup uses orthographic front, ±90° profiles and +45° oblique; generated03's far-lash defect is separate and does not describe these Blender cameras.
- No actual GLB or browser character was inspected in this pass. Idle/Walk/Run, clip blending, playable movement, blink/eye/jaw deformation, hair dynamics and real browser material screenshots remain required independent gates.

Root owns gate/status updates. **Recommend a focused actual-geometry v03; do not clear the head gate or substitute material detail for eyelid construction.**
