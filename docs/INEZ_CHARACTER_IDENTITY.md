# Inez — character identity lock

Project: THREE BEDROOM / PALINDROME. Created 2026-10-08.

Status: original-reference inspection complete; no generated reference or 3D model is approved by this document. Identity accuracy takes precedence over attractive rendering.

## Authority and preserved sources

Both attachments have been opened and visually inspected. Original bytes are preserved in `assets/characters/inez/references/original/`, with SHA-256 hashes and attachment paths in `manifest.json`. Convenience copies exist at the requested `references/inez_portraits.jpg` and `references/inez_turnaround.jpg` paths. Never overwrite any of these JPEGs.

- **A — `inez_portraits.jpg`, 1280 × 956:** two close portraits. Final authority for facial identity, feature proportions, eyes, nose, lips, jaw, brows, freckles, skin response, hairline and framing curls. The expressions are slightly tense, and neither portrait provides a true 90-degree profile.
- **B — `inez_turnaround.jpg`, 1280 × 714:** front body, rear body, and a near-frontal face. Final authority for dressed body silhouette, ponytail, sweater stripes, jeans, boots, and necklace placement. B's face offers supplemental frontal landmark evidence; A retains facial authority. The missing head in B's first panel is an image artifact, not anatomy.

Approximate age 29 and adult status are supplied character metadata, not measurements derived from the images. No ethnicity, exact height, weight, hidden anatomy, or personality is inferred.

## Invariants

- Medium-brown hair with restrained warm highlights, wavy/curly texture, gathered in a loose high ponytail. Preserve raised, irregular crown volume, off-center irregular part, and uneven fine flyaways.
- Prominent loose curls frame both sides of the face. Shorter curling strands cross the forehead; longer temple tendrils extend past the jaw toward the neck. Do not replace them with a smooth fringe or symmetrical decorative ringlets.
- Muted green-hazel irises with olive/gray-green outer color and warmer central variation. Preserve natural pupil, limbal edge, subtle tearline and modest corneal reflections. No emerald saturation or enlarged eyes.
- Light-to-medium warm neutral skin as rendered in the sources; peach/brown and red tonal variation is visible. Freckles concentrate across the bridge/upper nose and cheeks, with smaller scattered forehead marks. Lighting-dependent rendered colors are not calibrated albedo measurements.
- Soft facial contours with distinct cheek volumes, tapering jaw, and rounded compact chin. The face must not become a generic pointed heart shape or a hollow-cheeked beauty face.
- Natural moderately full lips, the lower lip visibly fuller than the upper, a visible Cupid's bow, and a narrow natural lip seam. Preserve warm muted rose/brown coloration and vertical surface detail.
- Dense medium/dark brown brows with irregular individual hairs, a largely straight inner section and restrained outer arch. Do not sculpt them into thin, raised, high-arched brows.
- Cropped charcoal-gray knit crew-neck sweater, broad very dark navy/charcoal horizontal bands, roomy torso, dropped shoulder, long loose sleeves, ribbed neck/cuffs/hem.
- Dark nearly black washed jeans: high waistband, belt loops, central fly, front pocket openings and small rivets, roomy thighs and lower legs, fabric gathering at boot tops. Rear patch pockets are visible. No leggings, skinny jeans, belt, decorative distressing or added hardware.
- Black lace-up combat boots with tall ankles, round toes, thick platform soles, visible eyelets/laces and stitched panel construction. Avoid heels, sneaker shapes or invented buckles.
- One fine silver chain and a very small bright pendant centered on the upper chest. No earrings or additional jewelry are visible.

## Face construction observations

The forehead is moderately tall where the hair permits inspection. The hairline is partly occluded; its exact scalp boundary cannot be recovered. Eye sockets have visible upper-lid folds, soft upper-lid hooding, natural under-eye shading and small asymmetries. Eyes are horizontally elongated rather than round, with a restrained outer lift; lashes are natural, not extensions. The apparent inner-brow rise in A's second portrait is expression, not an invariant brow pose.

The nose has a narrow-to-moderate root/bridge, gradual widening toward a softly rounded tip, and visible alar width. Preserve the bridge-to-tip transition and visible nostril wings. Do not narrow the nose or sharpen/upturn the tip. The exact sagittal bridge curve, projection, columella angle and nostril depth are unresolved without a profile.

Cheeks carry soft fullness around the midface; the jaw narrows gradually below them. The mouth is moderately wide with full but not inflated lips. The chin is rounded and has appreciable width rather than a pointed apex. Visible ears are partly covered; their complete contours and rear attachment remain uncertain. Preserve a natural neck and shoulder transition.

Expression lock for the canonical reconstruction: relaxed brow, level gaze and a gently closed/resting mouth. Relax the tension visible in some originals without changing eye aperture, lip volume or jaw size. Neutralization is a reconstruction operation and must be reviewed.

## Approximate landmarks — visible image measurements only

These are manually estimated image-space landmarks, not automated landmark detection or recovered 3D dimensions. Use roughly ±5–10 px uncertainty for clear frontal landmarks and larger uncertainty for hair-covered contours. Coordinates refer to **the complete original B image**, origin at upper left. Its facial panel starts at x ≈ 853. Perspective and expression prevent exact equality with A.

| Landmark | Approximate original-B position / interval | Confidence and use |
| --- | --- | --- |
| Pupil centers | (990, 268), (1112, 268) | Medium; inter-pupil distance ≈122 px, use a 118–128 px band |
| Inner canthi | (1014, 269), (1085, 269) | Medium; inner-eye gap ≈71 px, not iris spacing |
| Outer canthi | (967, 269), (1138, 268) | Medium; each visible eye opening ≈47–53 px |
| Brow band | y ≈232–248 | Medium; do not bake worried expression into brow geometry |
| Nose alar extent | x ≈1013–1092, y ≈332–348 | Medium-low; shading obscures exact alar boundary |
| Nose base / subnasale | y ≈345–352 | Medium; profile projection is not recoverable |
| Mouth corners | x ≈1007–1099, y ≈387–397 | Medium; parted-mouth expression alters seam |
| Upper lip apex / seam / lower border | y ≈372 / 390 / 410 | Medium; evaluate against A rather than tracing B alone |
| Bottom of chin | y ≈457–465 | Medium; preserves lower-face length |
| Visible central hairline | y ≈115–135 | Low; curls overlap the forehead |
| Visible cheek width | x ≈941–1163 at y ≈306–331 | Low; loose hair conceals edges |

Useful sanity bands: mouth width ≈0.70–0.80 of inter-pupil distance; alar width ≈0.58–0.68; inner-eye gap ≈0.53–0.62; eye line to chin ≈1.5–1.65 inter-pupil distances. These broad ratios constrain a frontal fit, not a metric head sculpt. Never turn the uncertain cheek boundary or occluded hairline into a precise dimension. Inspect A before accepting any numeric fit.

## Body and costume construction observations

The dressed silhouette is natural and moderately proportioned. The sweater hangs loosely without an exaggerated bust or pinched waist. A narrow band of abdomen separates its front hem and the jean waistband; the rear hem reaches nearer the waistband. Hands are relaxed at the sides in the original; generated modeling views may use a modest A-pose while preserving limb length and garment volume.

In B's front panel, shoulders begin near y ≈143–163, the sweater hem near y ≈277–284, waistband near y ≈292–310, apparent crotch near y ≈397–409, jean-to-boot transition near y ≈590–608, and sole bottoms near y ≈698–701. The knit body's side-to-side width is about x ≈140–294, while the full sleeve silhouette is wider. These are garment/image-space measurements. The front head is absent and must be reconstructed using A; do not infer total stature from the truncated front panel.

The rear head begins near y ≈33; rear soles end near y ≈699. If the independently arranged panels share scale, this suggests a roughly 7–7.5-head clothed figure. That assumption is unverified. World scale will be explicitly provisional until the game team supplies height.

The visible front sweater has three broad dark torso bands separated by wider charcoal-gray knit bands. A gray crew neck/upper shoulder section sits above the first dark chest band; the lowest visible torso band sits above the gray ribbed hem. Sleeves carry additional alternating bands and gray ribbed cuffs. Copy band order and relative phase from B, not a generic equal-width striped texture. A's closer crop confirms coarse knit and the same dark chest stripe beneath the neckline.

The ponytail is curly and dense with uneven taper, falling to the upper/mid-back in B. Its side projection, tie position, hidden scalp hair and interior curl arrangement require reconstruction. Rear volume from B takes precedence over any generated side proposal.

The fine necklace forms a shallow V to the upper chest. The pendant is tiny, with a bright irregular branched/pointed silhouette at the source resolution. **Its exact motif, thickness and back face cannot be established.** Do not label it a cross, star, bird or flower as fact; do not enlarge it to improve legibility. Extract the visible silhouette when possible and retain uncertainty.

## Skin and material constraints

Preserve forehead pore response, cheek freckles, slightly pinker nose/cheeks, subtle under-eye discoloration, fine lip texture, and restrained specular variation. A permits qualitative texture and cluster evaluation, but not an exact UV-space freckle map for unseen skin. Mark invented microdetail and hidden-surface texture as extrapolation.

Sweater: coarse, soft knit with visible directional stitches, matte fibers, ribbed trim and real cloth thickness. Jeans: matte washed dark denim, lighter seam/wrinkle wear, stitched rear pocket shapes. Boots: black leather-like uppers with restrained broad highlights and rough rubber-like thick soles. Chain: fine silver metallic response. Skin albedo, normal and roughness must be distinct maps in a later model; these images are not ready-made PBR textures.

## Unknowns and forbidden substitutions

Unknown: exact true left/right profile, head/back-of-skull depth beneath hair, complete ears, nostril interior, teeth/tongue, unseen skin and costume surfaces, body dimensions under clothing, boot sole tread, pendant motif, calibrated material colors and real-world height. New views are hypotheses checked for consistency, not historical facts.

Forbidden: face/body redesign, enlarged or differently colored eyes, narrower nose, inflated lips, slimmed body, alternative hairstyle/costume, unseen makeup, added jewelry, smoothing away skin variation, anime/cartoon proportions, or reproducing B's cropped-head artifact.

## Production gates

Root acts as artist; separate identity and technical agents review candidates against originals. Original images remain attached to every identity-sensitive generation or edit. The initial run is capped at 24 calls, including retries. Each problematic view permits up to three initial refinement passes. Every candidate and its critiques are retained.

Target for assessable whole-character evidence: ≥90/100, facial identity ≥32/35, no critical anatomy/cropping/redesign failures. Scores are subjective visual assessments, not biometric percentages. Partial views use scoped scores and clearly reserve unassessable categories. No fabricated full-score approval from a crop.

Only after front, profile and body references pass initial review may a real character sculpt advance. Blender models and their actual renders need a second independent critique. A licensed base mesh must have recorded provenance and suitable topology. No procedural mannequin or unrelated stock character can be delivered as completed Inez. If likeness cannot be attained automatically, preserve editable work and explicitly record the need for manual sculpting.
