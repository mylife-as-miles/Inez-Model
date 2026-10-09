# Inez model comparison and reconstruction strategy

This compares the user's two existing models with the two original references:

- **A-face:** `references/original/inez_portraits.jpg`
- **B-body/costume:** `references/original/inez_turnaround.jpg`

The comparison uses real renders of the delivered GLBs (`renders/source_audit/`)
and the audit in `GLB_ASSET_AUDIT.md`. It was written before any modification of
the models.

## Evidence

- **Face sheets:** `face_front|three_quarter|left|right.png` of both assets,
  placed beside the original B face panel and the original A portraits.
- **Body sheets:** `body_front|back.png` of Asset A beside the turnaround's front
  and back panels.
- **Landmark proportions:** frontal ratios normalised by inter-pupil distance,
  measured on the same-camera front renders with MediaPipe Face Landmarker
  (`tools/inez/face_landmarks.py`). They are 2D proportion measurements, not a
  biometric likeness score. The references wear a worried expression, which
  widens the eyes and raises the brows.

| Ratio (÷ IPD) | Asset A | Asset B | Original B face panel | Original A right portrait (yaw −13°) |
|---|---|---|---|---|
| mouth width | 0.743 | 0.773 | 0.698 | 0.716 |
| alar width | 0.591 | 0.615 | 0.587 | 0.613 |
| inner eye gap | 0.533 | 0.552 | 0.545 | 0.532 |
| eye width | 0.420 | 0.415 | 0.424 | 0.434 |
| eye opening ÷ width | 0.277 | 0.283 | 0.374 | 0.369 |
| eyes → chin | 1.558 | **1.652** | 1.697 | 1.785 |
| eyes → subnasale | 0.683 | **0.704** | 0.735 | 0.747 |
| lip seam → chin | 0.590 | **0.630** | 0.634 | 0.708 |
| upper lip height | 0.084 | **0.130** | 0.129 | 0.129 |
| lower lip height | 0.165 | **0.198** | 0.230 | 0.263 |
| cheek width | 2.060 | 2.116 | 2.081 | 2.162 |
| jaw width | 1.628 | 1.687 | 1.627 | 1.694 |
| brow → eye | 0.304 | 0.312 | 0.341 | 0.361 |

Asset B is closer on lower-face length, mouth-to-chin length and lip
thickness. These vertical proportions are the ones that make Asset A read as a
different, rounder and younger face. Both assets have neutral, heavier lids
than the worried originals. Expression is not identity, but the eye-opening
difference is noted for the expression set. Asset B's mouth is about 10% wider
than the frontal original.

## The eight questions

1. **More accurate Inez face: Asset B.**
   - B matches: the oval face; the green-hazel eyes; strong straight brows with
     a restrained arch; the straight nose; full natural lips; the curly
     medium-brown hair pulled back with face-framing curls.
   - A's face is rounder with a short lower face, thin upper lip,
     darker-brown eyes and paler skin.
   - B's remaining differences:
     - mouth slightly wide;
     - freckles fainter than the originals;
     - skin a little pink;
     - brow-to-eye distance a little short.
2. **Better facial topology: neither.** Both are uniform AI triangle soups of
   about 2 million triangles, with fused eyes and a closed, fused mouth. For
   *sculpted shape*, B's lids, nostrils and lips are cleaner.
3. **Better skin textures: B.**
   - B's base colour is cleaner, with a believable warm skin tone, lips and
     eyes, and its roughness map is coherent.
   - A's roughness is blotchy around the eyes, with atlas-island squares.
   - Both have nearly flat normal maps and some lighting baked into the base
     colour.
4. **Better body proportions: A.** B is a bust and has no body. A's full figure
   is plausible and matches the turnaround's silhouette.
5. **More accurate clothing: A.**
   - Cut: cropped striped knit ending above the navel, loose dark jeans
     gathered over the boots, black lace-up platform boots. This matches the
     turnaround panel for panel, back pockets included.
   - Colours are lighter than the original. The knit is blue-grey with
     grey-navy stripes against charcoal with navy; the denim is washed
     charcoal against black.
6. **Better hair: B.**
   - B: a curly, high ponytail with face-framing curls and baby hairs, as in
     both originals.
   - A: light-brown stringy hair worn down into a low loose tail.
   - Both are solid sculpted shells, not cards.
7. **More suitable for rigging: neither as delivered.** There is no skeleton
   and no edge flow, and the lids, mouth and hair are fused. A's full body gives
   the proportions a rig needs; B gives the face and hair. Neither can blink,
   open the jaw or move the ponytail without retopology.
8. **Can they be combined? Yes, but not by joining meshes.** Each is a single
   fused shell, so there is no head or body object to cut and attach. They have
   to be combined through a shared production topology.

## Chosen strategy

Combine the user's models through a controlled retopology/transfer. The
geometry and textures come from the user's models; the topology, skeleton and
facial controls come from the existing animation-ready Inez production mesh.

### Production carrier

- MakeHuman CC0 body topology, with separate eyes, teeth and lashes.
- 163-bone rig plus the ponytail chain, with licensed skin weights.
- Clean eyelid, lip and joint loops.
- Separate sweater, jeans, boots and necklace meshes, plus the identity layers.
- It already exports to glTF and runs in the Three.js viewer.

### Steps

1. **Common frame.**
   - Scale Asset A to Inez's reference height: 1.70 m barefoot plus the 4.6 cm
     platform soles.
   - Rotate Asset B by +90° so it faces forward.
   - Register B to A with a similarity transform from face landmarks lifted
     onto each surface, so B's head sits exactly where A's head is.
2. **Body and costume from Asset A.**
   - Register the production figure (body, garments, boots and rig joints) to
     A: pose-landmark warp, then iterative closest-surface residual smoothing
     from coarse to fine.
   - Project the garment outer surfaces onto A's matching sweater, jeans and
     boot regions, and the exposed skin onto A's hands and midriff.
   - Rig joints move with the same field.
3. **Head and face from Asset B.**
   - Use the landmark-constrained wrap already built for scan work
     (`scan_landmarks.py`, `scan_fit.py`, `scan_wrap.py`), but adopt B's full
     resolvable shape, not only its fine detail.
   - Lid margins follow B's lid contours; B's fused eyeball surface is replaced
     by the separate eye meshes, fitted to B's eyeball spheres.
   - The closed mouth follows B's lip seam, so the mouth interior and jaw can
     still open.
   - Blend over the neck between the A-fitted body and the B-fitted head.
4. **Hair from Asset B.**
   - Segment B's hair shell using texture and geometry, then decimate it for
     the runtime.
   - Skin it to the head and ponytail chain. The production scalp sits inside
     it.
   - Add framing-curl and flyaway cards only where B's fused curls cannot move.
5. **Textures.**
   - Bake B's base colour and roughness onto the 4096×2048 head layout.
   - Bake A's onto the body and garment UVs.
   - Remove obvious baked lighting only where it reads as false shading.
   - Correct garment colours toward the turnaround: charcoal knit with navy
     stripes, black denim. Every correction is logged.
   - Recover skin micro-normals procedurally, plus the Ten24-derived anatomical
     detail where it agrees with B. The source normal maps are flat.
6. **Rig, animation, viewer and QA.** Reuse the existing pipeline, then run three
   corrective artist–critic passes per major component against the originals.

Generated reference images are not needed to start. Both identity anchors are
original images, and the user's models supply the 3D side views. The earlier
image-generation budget is exhausted (22 of 24 calls), and this session has no
access to that generator. Another generator would be a silent switch and would
spend paid credits, so none will be used without explicit approval.

### Explicitly rejected

- **Rigging the Tripo meshes directly**, decimated with automatic weights. The
  fused lids and mouth could not blink, open the jaw or carry visemes, and
  joint deformation would smear the triangulation.
- **Joining A's body to B's head as raw meshes.** Neither has a cuttable neck
  boundary; the scales and hair volumes differ; seams and texture-atlas
  mismatches would remain.
- **Replacing either face with a new or generic one.** A photoreal woman who is
  not Inez is a failed result.
