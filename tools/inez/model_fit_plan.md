# Inez editable geometry reconstruction

The user authorized an actual reconstructive character, not a new design.
Original A and original B have both been inspected. Original A controls face;
original B controls dressed proportions. The approved generated front is a
secondary modeling aid. Its face appears somewhat longer below the eyes than
the near-frontal original B panel, so it must not replace the source authority.

The explicit initial front/profile/body geometry gate now permits actual clay
head reconstruction. Versioned continuous meshes, editable fitted shape keys
and actual clay renders exist under `model/work/` and `renders/head_v*/`.
Each remains a review candidate. Detailed skin maps and dressed execution are
withheld until the root records a separate credible-head geometry gate.

## Source substrate

The MakeHuman hm08 CC0 body is a continuous quad surface with eyelid, lip,
nostril, finger, toe, neck and ear topology, existing UV coordinates and indexed
source joint/weight data. It is a fitting substrate only. It is not Inez before
fitting and is never labeled a matched stock character. Source filenames that
name population presets refer only to vendor asset names, never an inference
of Inez's ethnicity. All source bytes/provenance/licenses remain preserved.

## First clay fitting checks

1. Align the original B frontal pupil distance and eye line to actual front
   render; maintain the originals' eye-to-chin ratio about 1.5–1.65 IPD.
2. Check restrained, horizontally elongated eye aperture. Match inner-canthal
   gap about 0.53–0.62 IPD and opening widths about 0.39–0.45 IPD.
3. Check original A's rounded tip and appreciable alar volume. Keep alar width
   about 0.58–0.68 IPD; assess width independently of lighting and nostril shadow.
4. Preserve full but natural lips, visible Cupid's bow, fuller lower lip and
   compact lip seam. Original mouth width is about 0.70–0.80 IPD. Do not copy
   a worried parted mouth as neutral geometry.
5. Check soft cheek transition, gradual jaw taper and rounded chin width. Avoid
   a pointed generic chin or a narrow elongated beauty face.
6. Inspect profile nose bridge, tip projection, philtrum, lip projection, chin
   depth and forehead. Generated profiles are proposals for missing evidence,
   not proven historical anatomy. Original A three-quarter face remains final
   authority when a plausible side proposal conflicts with it.
7. Keep head, eyes, mouth and ears coherent in three-quarter clay rendering;
   no texture projection can mask contradictory underlying geometry.

## Editable source and tests

The build retains source vertex IDs, existing UVs, an explicit fitted shape
key, the licensed humanoid/facial skeleton, normalized indexed source weights,
rigged eye geometry and clay pupil/iris landmarks. Original images and approved
modeling hypotheses are packed as non-rendering image references. Every smooth
local fitting control is recorded in a JSON config and can be replaced by
manual sculpted shape keys. Provisional scale is 1.70 m until specified by the
game team; this is not an observed height.

The first four actual renders are front, anatomical left profile, anatomical
right profile and left three-quarter. Blender .L source joints are positive X;
a positive-X side camera therefore sees the character's left side. All clay
materials are temporary. No production skin/hair/costume likeness is claimed.

If automatic fitting leaves identity errors, the best continuous, UV-mapped,
rigged editable source is retained as an unapproved geometry prototype. Manual
sculpting is reported as the next requirement; it is not bypassed with a
procedural mannequin or presented as a finished photorealistic asset.

## Actual clay iterations

v01 preserved the source Basis and 16 recorded local fitting controls. Independent
review held alar/tip form, upper/lower lip volume, eye hooding and chin contours.
v02 retains those exact controls and adds 25 original/render-based geometry
corrections. Independent review retained improved mouth width, lower lip and
compact chin, but held superior lid form and upper lip/seam readability.

v03 preserves inactive exact v01/v02 keys and authors localized indexed exterior
lid rows, their actual topology mirrors, superior fleshy hood/crease and lower
roll. Actual upper vermilion receives a restrained soft roll; matched lip seam
topology pairs form a gently closed neutral seam. Body UVs, source vertex IDs,
licensed weights and unchanged eyeball/iris dimensions remain intact. The
topology inspection records source coordinates and explicit displacements in
`qa/model/model_head_v03_topology_inspection.json`. This version requires its
own four-angle independent review before detailed PBR or dressed execution.
