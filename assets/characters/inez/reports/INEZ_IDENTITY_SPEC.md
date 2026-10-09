# Inez identity specification

This is the measurable identity target for the Inez reconstruction. It
quantifies the qualitative identity lock in
[`docs/INEZ_CHARACTER_IDENTITY.md`](../../../../docs/INEZ_CHARACTER_IDENTITY.md),
which stays in force. Where the two disagree, the original images decide.

## 1. Authority

| Reference | Path | SHA-256 | Governs |
|---|---|---|---|
| A, two portraits (1280×956) | `references/original/inez_portraits.jpg` | `ce76f4cc…6a764b` | face, eyes, skin, freckles, hairline |
| B, turnaround (1280×714) | `references/original/inez_turnaround.jpg` | `9482e1a5…b2f64d39` | body, costume, ponytail, necklace; its face panel is the only near-frontal face |

Both files are byte-identical to the originals; their hashes were re-checked
in this session.

The user's two GLBs (`source/asset_a/Inez.glb`, `source/asset_b/Inez Facial
Model.glb`) are approximations of these images. They are reused as 3D
evidence, but they are not the authority (see `INEZ_MODEL_COMPARISON.md`).

## 2. How the values were measured

- **Landmarks.** MediaPipe Face Landmarker on the originals. Values are 2D
  ratios normalised by inter-pupil distance (IPD) and taken with
  `tools/inez/face_landmarks.py`. They describe proportions in the image
  plane only. They are not a biometric likeness score.
- **Colour.** Linear-RGB medians, taken at the same anatomical patches on the
  originals and on renders with `tools/inez/skin_tone_compare.py`.
  - Patches are placed by landmarks and trimmed between the 15th and 85th
    luminance percentiles, so highlights and freckles do not dominate.
  - Both originals are lit neutrally: their grey knit reads R/G = 1.00 and
    G/B = 0.95–0.97. Their colour ratios therefore approximate albedo
    ratios. Absolute brightness does not, because exposure is unknown.
- **Expression.** Both originals show a worried, sad face: inner brows
  raised, mouth pouting or parted, wide eyes. Brow height, lid aperture and
  mouth shape are therefore expression, not identity. The neutral master is
  never fitted to them. Mouth width and lip heights count at half weight.

## 3. Face

### Frontal proportions (÷ IPD)

The B face panel is the frontal target. The A right portrait (yaw −12.7°) is a
cross-check, and its horizontal ratios are foreshortened.

| Ratio | B face panel (yaw −2.9°) | A right portrait | Identity use |
|---|---|---|---|
| eye line → chin | 1.681 | 1.784 | full |
| eye line → subnasale | 0.732 | 0.747 | full |
| lip seam → chin | 0.632 | 0.708* | full (*A has a parted mouth) |
| alar width | 0.584 | 0.613 | full |
| eye width | 0.430 | 0.434 | full |
| inner eye gap | 0.529 | 0.532 | full |
| cheek width | 2.085 | 2.162 | half (curls hide the contour) |
| jaw width | 1.615 | 1.694 | full |
| mouth width | 0.695 | 0.716 | half (pout) |
| upper lip height | 0.121 | 0.129 | half |
| lower lip height | 0.227 | 0.263 | half (pout) |
| eye opening ÷ eye width | 0.362 | 0.369 | expression only |
| brow → eye | 0.335 | 0.361 | expression only |

The face is an oval with distinct cheek volume. It tapers to a rounded,
moderately wide chin and is not pointed. The lower face is long:
eye-to-chin is about 1.7 IPD.

### Features

- **Eyes.** Horizontally elongated, with a soft upper-lid fold and natural
  under-eye shading.
  - The irises are hazel. They were measured on the iris rings of both
    originals with MediaPipe iris landmarks, in linear RGB:
    - outer field: R/G ≈ 1.3–1.6, G/B ≈ 1.5–2.0, an olive-khaki green;
    - centre: a warmer golden collarette;
    - edge: a darker limbal ring.
  - The irises are not emerald and not enlarged.
- **Brows.** Dense dark brown, with a largely straight inner section and a
  restrained outer arch. They are not thin or high.
- **Nose.** Moderate root, gradually widening to a softly rounded tip. The
  alae are visible. Profile projection is unknown.
- **Lips.** Moderately full, with the lower lip fuller than the upper.
  Visible Cupid's bow; muted rose-brown.
- **Skin.**
  - Light-to-medium warm beige.
  - Face patches on the originals read R/G = 1.86–2.01 and G/B = 1.48–1.54,
    the mean of forehead, both cheeks and chin.
  - Pinker nose and cheeks; soft darkness under the lower lids.
- **Freckles.** Clearly visible at portrait distance. Dense over the nose
  bridge and upper cheeks, sparse and smaller on the forehead and chin.
- **Ears.** Mostly covered by curls in both originals. Their shape is
  unresolved.

## 4. Hair

- **Colour and texture.** Medium-to-dark brown, wet-looking, curly, with
  golden highlights on the curls.
  - Sampled rendered hair reads R/G ≈ 1.5–1.9 and G/B ≈ 1.4–2.0.
  - Lit curls sit at 0.09–0.44 of cheek luminance; the crown is darker.
- **Style.** Pulled back into a high, dense, curly ponytail that falls to the
  upper or mid back (B back panel).
  - Loose curls frame both sides of the face and fall past the jaw.
  - Shorter strands cross the forehead.
- **Unresolved.** A light shape at the back of the head in A's left portrait
  may be a clip or a highlight. It is not established, so it is not modelled.

## 5. Body and costume (B)

- **Figure.** A natural, moderately proportioned adult figure.
  - Real height is not given. The build uses 1.70 m barefoot plus 4.6 cm
    platform soles; this is provisional and must be confirmed by the game
    team.
  - The total is 1.783 m to the crown of the hair.
- **Sweater.** Cropped charcoal-grey knit crew neck with broad, very dark
  navy horizontal bands.
  - On B's front and back panels the navy/grey luminance ratio is about
    0.18–0.22.
  - Dropped shoulders, long loose sleeves, ribbed neck, cuffs and hem.
  - A strip of midriff shows above the jeans.
- **Jeans.** Near-black washed denim; jeans/knit-grey luminance about 0.31–0.32.
  - High waist, belt loops, roomy legs gathered over the boots.
  - Rear patch pockets.
- **Boots.** Black lace-up combat boots: tall ankles, round toes, thick
  platform soles.
- **Necklace.** One fine silver chain that lies on the neck at the collar and
  falls in a V to a very small pendant.
  - The pendant sits about 6.5 cm below the front neckline.
  - The user's Asset A models the same V, with the pendant at 1.40 m and the
    arms reaching x = ±4.6 cm at the collar.
  - The pendant motif cannot be resolved, so it is built as a plain drop.

## 6. Unknowns (never presented as fact)

- True profile and nose projection
- Ear shape
- Pendant motif
- The possible hair clip
- Scalp boundary under the hair
- Teeth and tongue
- Skin under the clothes
- Hidden back of the sweater under A's long hair

These are reconstructed plausibly and labelled as estimates in the reports.

## 7. Acceptance checks used by the critic loop

Every check is measured against the originals.

1. **Frontal ratios.** Within ±3% of the B face panel for full-weight
   ratios, and within ±6% for half-weight ratios.
2. **Skin chroma.** R/G and G/B within ±6% of both originals at matched
   luminance.
3. **Garments.** Navy/grey and jeans/knit luminance ratios within ±25% of the
   turnaround.
4. **Visual review.** Face, three-quarter and profile renders reviewed side by
   side with the originals at the same framing.

A failing check is reported, never hidden. Passing the checks is necessary
but not sufficient for likeness.
