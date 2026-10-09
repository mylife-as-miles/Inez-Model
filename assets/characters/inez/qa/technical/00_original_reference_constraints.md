# Inez — independent technical review of the originals

Reviewer role: TECHNICAL CRITIC. Both original JPEG files were opened visually before this report. This report records evidence and uncertainty, not a generated-image acceptance score.

## Reference authority and coverage

- Reference A, `1-252164.jpg`, is a two-panel head-and-shoulders reference, 1280 × 956. The left panel is a three-quarter view; the right panel is a nearer frontal three-quarter view with a worried brow. Neither panel is a verified 90-degree profile or a neutral orthographic front.
- Reference B, `2-252175.jpg`, is a three-panel image, 1280 × 714. It shows a headless/cropped front body, a complete rear body, and a front/near-front portrait. Its front head absence is an image artifact. A completed front view must restore the head from A, using B's rear height and neck connection as consistency checks.
- No original provides a true side view, unoccluded ears, a complete scalp/hairline, bare body, palm/digit detail, sole underside, tongue, teeth, or a definitive pendant outline. Synthesized details in these areas must remain labeled inferred.
- Lighting differs across the originals; local color and apparent surface roughness cannot be treated as calibrated PBR measurements.

## Geometry constraints

The body is an ordinary adult silhouette with loose garments. The sweater has dropped/soft shoulders, relaxed sleeves, a cropped hem, and a short visible gap to the high jeans waistband. The jeans broaden through the hips and thighs, remain loose through the legs, and gather near the boot tops. A narrow hourglass mannequin, thin leggings, or long fitted sweater would contradict B.

The rear body extends from crown at approximately y=34 to sole bottom at y=699 within its panel. Relative positions are useful but not calibrated dimensions: sweater hem near y=286; jeans waistband near y=289; crotch area near y=390–405; gathered leg ends near y=593–609; boot sole bottom near y=699. Pixel locations are approximate visual readings, not anatomical landmarks or a claimed height. Front and rear camera pose/garment folds may differ. Do not force corresponding garment creases to identical y positions.

The original arms hang close to the sides. A modeling A-pose must move the arms only enough for rigging clearance without narrowing the torso or changing shoulder mass. Sleeves will deform and their stripe contours will change under that pose. Keep fingers and both soles within frame.

Face profile geometry is underconstrained. A gives oblique support for the nose projection, lips, chin, and jaw but not a historical sagittal silhouette. New profile views must be cross-checked against frontal and oblique projections and marked inferred, even if visually coherent. Dense skin detail cannot compensate for an inaccurate head mesh.

## Garment construction and stripe continuity

- Sweater base is mid/dark charcoal gray with broad very dark navy/charcoal bands. Crew neck, ribbed collar, cuffs, and ribbed cropped hem are gray.
- In B's front torso, three visible dark bands cross the upper chest, middle torso, and lower torso. The lower dark band ends above the gray ribbed hem. Approximate central-front stripe y ranges are 160–176, 195–209, and 230–244; folds and shoulder curvature alter local boundaries. These readings describe B at its current size, not texture UV coordinates.
- B's rear has corresponding upper, middle, and lower torso bands. The upper one is partially obscured by the ponytail. Do not add a fourth band at the hem or turn the gray collar/hem navy.
- Sleeves have alternating bands down to the wrist, with gray ribbed cuffs. Sleeve stripes arise from the actual sewn sleeve orientation, so their heights need not align perfectly with the torso stripes in an A-pose. Compare their phase and count to B; do not use a continuous world-space stripe projection over an incorrect sweater mesh.
- Sweater thickness, collar opening, ribbed borders, dropped shoulder shape, and loose sleeve folds need geometry or supported detail normal maps. A striped body surface is not an acceptable sweater model.
- Jeans show belt loops, front closure/button/fly area, front pockets, rear pockets/yoke, and seam/fold structure. No belt is visible. Maintain the original high waistband, loose leg volume, and gathered lower legs.
- Boots are black lace-up combat/platform boots with rounded toe boxes, substantial continuous sole volume, ankle shafts, eyelet/lace columns, and seams. The silhouette is chunky but not arbitrarily enlarged. Front/back evidence supports matching pair construction; unseen soles and exact tread remain inferred.
- Silver necklace is a fine chain forming a narrow V over the sweater with a small bright pendant. Exact pendant silhouette is not reliably legible; do not substitute a large icon, gem, or invented decorative motif.

## Hair constraints

The original rear silhouette shows a ponytail anchored high toward the upper back of the head, narrowing at the tie then spreading in irregular curls and ending over the upper back. It is not a spherical bun, uniformly straight sheet, or symmetric tubular braid. A shows loose side/temple curls reaching below the jaw/along the neck, and volume above the crown without a flattened hair cap.

Frontal hairline and face framing have to be preserved before ponytail detail is added. The upper ponytail tie/crown location, side projection, rear width, and tip height should be compared across views. Much of the actual scalp and tie hardware is hidden; neither is established enough to invent conspicuous accessories.

## Mesh, material, and rig requirements for later acceptance

- A coherent topology-suitable head/body mesh with UVs, actual eyelids, eyeballs/cornea separation, lips, mouth opening, and jaw relationship. No disconnected primitive approximation can pass likeness review.
- Eyelid and mouth deformation loops sufficient for blink, subtle emotion, jaw opening, and restrained dialogue shapes; eye rotations must preserve lid contact without exposed gaps.
- Clothing meshes with thickness/clearance and skin weights; test underarm, collar/neck, cropped hem, hips/crotch, boot/ankle, and sleeve cuff motion.
- Hair source/cards/strands built around the observed silhouette, with a weighted secondary-motion ponytail and collision allowance at shoulders/back.
- PBR albedo, roughness, and normal information with calibrated color-space handling. Skin pore detail and freckles must not be embossed uniformly; sweater knit and leather normals must respect plausible scale.
- Mesh hierarchy, metre-scale transforms, named skeleton/animations, texture resolution, GLB UV/material integrity, and real browser render tests.

## Generated-reference technical gate

A generated candidate is not technically accepted if the claimed angle is incorrect, required anatomy is cropped/absent, the head is duplicated or malformed, hands/feet are unresolvable, costume stripe construction changes, front/back scale is inconsistent, or new views contradict established head/body/hair geometry. Portrait-only images do not establish body proportional accuracy. Closeups cannot establish global viewing angles or scale.

The supplied 100-point rubric will be used only where a candidate contains evidence. Unseen categories will be marked unassessable instead of receiving invented full points. Any scored denominator and deductions will be explicit, and visual scores will not be represented as biometric percentages.
