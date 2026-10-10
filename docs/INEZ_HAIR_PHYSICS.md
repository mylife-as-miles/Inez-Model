# Inez hair: Ponytail MessyWavy cards, fit and per-card simulation

**Update (2026-10-10, later): the card build (r04) below was rejected by the
user ("looks so bad": thin, straw-like, short high ponytail). The previous hair
is the default again. The current candidate is strand hair (r09) grown with the
user's MainHair node group from guides restyled to the reference ponytail; see
[Strand hair](#strand-hair-from-the-users-mainhair-node-group-r09) at the end.**

**Status of the card build (r04): integrated in a local build; not in this public repository.**
The WhiteCap *Ponytail MessyWavy* package (Fab) replaces Inez's Asset B hair in
`model/v06/inez_recovery_v06_hair_r04.glb` (33,234,004 bytes, SHA-256
`c50d6a64…68a06ba`). Every one of the 665 LOD0 hair cards is skinned to her
existing rig and simulated individually in the viewer. Production/likeness
approval remains **false**.

## Source and licence handling

The repository owner supplied the package on 2026-10-10 through their own
Google Drive: `hair_f_ponytail_messy_wavy_01.zip` (Additional Files: 8 card
LODs as FBX, scalp/head FBX, `fiber_Attribue.png`, `fiber_Tangent.tga`,
`Highlights_001.jpg`, 136 MB Alembic groom) and
`hair_f_ponytail_messywavy_01.mhpkg` (Unreal assets, used only for its
manifest: 68,005 strands, 3,115,191 points). Hashes are in
`assets/characters/inez/hair/qa/intake_v01.json`. Entitlement was not
independently verified. NoAI: only local tools (Blender, Python, three.js)
touched the files.

**This repository is public**, so the package, the fitted hair and any GLB
containing it are git-ignored (`.gitignore`): tools, presets, QA reports and
renders are committed; licensed geometry and textures are not. The viewer's
default is the hair build; when it is absent it falls back to
`v06/inez_recovery_v06.glb` with a warning (`production_status.json`
`default_model` / `fallback_model`).

## Build it locally

From the repository root, with the extracted ZIP in `PKG` and a scratch dir `W`:

```sh
blender -b --factory-startup -P tools/inez/hair/export_package_meshes.py -- $PKG $W/pkg
python3 -I tools/inez/hair/fit_hair_cards.py --glb assets/characters/inez/model/v06/inez_recovery_v06.glb \
  --package-npz $W/pkg --lod 0 --rotation pitch --out $W/fit_lod0.npz --report $W/fit_lod0.json
python3 -I tools/inez/hair/make_card_textures.py --package $PKG \
  --reference-hair assets/characters/inez/model/v06/textures/Inez_Hair_FromAssetB_basecolor_restored_v06.png \
  --out $W/cards_basecolor.png --report $W/texture.json
python3 -I tools/inez/hair/inject_hair_glb.py --input assets/characters/inez/model/v06/inez_recovery_v06.glb \
  --fit $W/fit_lod0.npz --texture $W/cards_basecolor.png --scalp-cap --scalp-color .0267 .0169 .0106 \
  --output assets/characters/inez/model/v06/inez_recovery_v06_hair_r04.glb --report $W/inject.json
python3 -I tools/inez/hair/measure_hair_colliders.py --glb assets/characters/inez/model/v06/inez_recovery_v06.glb \
  --out assets/characters/inez/hair/presets/inez_messywavy_cards_r01.json   # already committed
```

Restart Vite after adding the GLB (its public-file list is built at start-up).

## Fit (`fit_hair_cards.py`, report `hair/qa/fit_lod0_r04.json`)

The target is the surface the viewer actually renders at rest: base positions
plus every morph target at its default weight (the identity layers). Her face
is never moved.

- **Similarity ICP** from the package scalp to Inez's cranium, pitch-only
  rotation: scale 1.104, rotation 0.76°, mean trimmed distance 2.19 mm. A free
  rotation fitted marginally closer (2.08 mm) but rolled the style 3.2°
  sideways toward ear asymmetry, so it was rejected.
- **Local wrap**: scalp residuals (max 11 mm) smoothed over the scalp and
  carried onto the cards with a 2.5 cm Gaussian, so cards keep their height
  above the scalp.
- **Collisions** with her skin (ears included), sweater and necklace: every
  vertex beyond the first 6 % of a card is pushed at least 1.5 mm out of the
  skin and 3 mm out of the cloth, spread along the card to avoid kinks. 92
  cards (512 vertices) moved > 5 mm, mostly face-framing strands passing
  through her right ear/jaw (max 39 mm). One vertex remains 0.4 mm inside an
  ear fold.
- **Skin weights** on existing joints only (`head`, `hair.01`–`hair.04`;
  167 joints, 17 clips, all identity defaults unchanged). The ponytail
  (15,365 vertices) blends from the head into the old ponytail chain.
- Per-vertex data for the runtime: `_HAIR_CARD`, `_HAIR_S` (root 0 → tip 1,
  from the card UVs; root = end nearest the package scalp) and `_HAIR_FREE`
  (0 on the scalp → 1 hanging, non-decreasing toward the tip; 9,009 pinned,
  17,160 free vertices, 509 cards with a free part).

## Crown "scalp ridge"

Diagnosis with the hair or the head hidden at the same camera
(`renders/hair_iterations/`): the pale, glossy crown streak was Inez's own
skull, which carries painted hair, poking out through the old hair shell
and shaded as glossy skin. Fix in r04: the new cards sit outside the skull,
and a scalp cap (the package scalp, shrink-wrapped 0.8 mm above her head)
covers only the top of the head in the hair's root colour, matte, with alpha
fading to zero over 2.5 cm toward the hairline, the nape and the ears. A
hard-edged cap (r03) made a visible forehead line and flat dark patches and
was rejected. Matched evidence: `renders/hair_r04_matched/compare_crown_*.png`.

## Material

`make_card_textures.py` builds one 4096² RGBA texture: alpha is the package's
fine strand coverage (×2.2), RGB is the medium brown measured from Inez's
restored, user-approved hair albedo (linear median → 95th percentile), varied
per strand by the package's random channels and lightened toward the tips.
COLOR_0 darkens the first 6 % of each card (roots) with a small per-card
tint. Alpha mask 0.3, double-sided, roughness 0.42, the old hair's warm
specular; the viewer turns on alpha-to-coverage for it.

## Per-card simulation (viewer)

- `viewer/src/hair/card-solver.js`: fixed 60 Hz XPBD for many short chains
  in typed arrays. Pinned particles follow the animation exactly; free
  particles are pulled toward their animated position by a compliant shape
  constraint (stiff near the root, soft at the tip), with inertia, gravity,
  drag, bending, sphere/capsule collision and friction. A follow-the-leader
  pass keeps segments inextensible. Teleports, animation snaps (scalp moving
  faster than 6 m/s) and hitches restart from the animated pose; pause holds
  the shape relative to it; nonfinite state recovers.
- `viewer/src/hair/card-hair-runtime.js`: one 8-particle guide per card
  (5,320 particles, 2,121 pinned) from the custom attributes; particle targets
  are skinned on the CPU with the hair's own weights every frame, so the baked
  ponytail motion still drives the hair; every one of the 35,618 vertices is
  rebuilt from its simulated segment frame. Gravity is head-relative (the
  authored shape already hangs under gravity). The skinned mesh is hidden
  while a world-space copy is simulated; the "Hair physics" checkbox (or
  `inezViewer.setHairPhysics(false)`) returns to pure animation.
- `hair/presets/inez_messywavy_cards_r01.json`: 11 collision proxies measured
  from her skin and sweater (5 cranium spheres, 2 temple spheres, 2 jaw
  spheres, neck and upper-spine capsules, each inscribed with 2 mm margin) and
  provisional tuning (tip compliance 5 m/N ≈ 2.2 Hz sway, drag 4/s).

The 68,005-strand Alembic groom is not used: millions of points are not a
real-time browser asset. Each card stands for a clump of strands; "every
strand" is realised as every card moving on its own.

## Evidence (SwiftShader WebGL2 in a container: CPU evidence, not GPU)

| Clip | Max offset from animation | Max segment stretch | Proxy penetrations |
|---|---:|---:|---:|
| Idle | 0.4 cm | 0.00 % | 0 |
| Walk | 3.8 cm | 0.07 % | 0 |
| Run | 8.0 cm | 0.24 % | 0 |
| TurnLeft | 1.2 cm | 0.00 % | 0 |
| CrouchDown | 3.8 cm | 0.27 % | 0 |
| LookAround | 1.0 cm | 0.00 % | 0 |

`hair/qa/hair_r04_motion.json` (7/7 checks): teleport after 3.37 m of travel
resets with no recovery; side/back renders with physics on and off at the
same pose in `renders/hair_r04_motion/`. Browser QA 14/14
(`qa/browser_v06_hair_r04_browser.json`), skin QA 17/17
(`qa/v06/v06_hair_r04_skin.json`), Khronos validation 0 errors / 21 warnings
(20 existing + one more of the same kind for the scalp node), the original
binary chunk preserved byte-exact as a prefix. Viewer build passes; 20 unit
tests pass (12 existing, 8 for the card solver). Live loop on this CPU-only
renderer: whole scene 1.85 FPS; hair skinning 0.7 ms, rebuild 4.1 ms, solve
33 ms per frame for up to 3 fixed ticks at that frame rate. No target-GPU
measurement.

## Known limits and next steps

- The package is a short, high crown ponytail; the original references show
  a lower ponytail reaching the shoulders. The style is the user's choice and
  was fitted as designed, not restyled.
- Inez's painted hair shows as a dark patch behind the ears and at the nape,
  where the old shell covered it; strands are thin at close range.
- TurnLeft/TurnRight end with a whole-body snap in the viewer (the head jumps
  19 cm then 16 cm across two frames when the clip's turn is baked into the
  root): an existing animation issue, not hair. The hair restarts with it.
- Only LOD0 is integrated; LOD1–LOD4 could feed a quality setting. No runtime
  LOD switching yet.
- Profile on the target hardware before any frame-rate claims.
- CORDEL: no integration is claimed; the solver API takes plain arrays only.

## Strand hair from the user's MainHair node group (r09)

The user rejected the card look and asked to restyle it toward the
references, then supplied `HairNodes.blend` (one Blender 3.4 geometry-nodes
group, *MainHair*: Hair Amount, Spread/Clumping, Points Count, Random Length,
Stick To Mesh, Noise, Delete Hair, Hair Thickness, Curl, Roughness). The file
is only read; it is not committed (user-supplied).

Pipeline (local; inputs and outputs with licensed content are git-ignored):

```sh
python3 -I tools/inez/hair/restyle_ponytail.py --glb assets/characters/inez/model/v06/inez_recovery_v06.glb \
  --fit $W/fit_lod0.npz --out $W/restyled.npz --guides $W/guides.npz --report $W/restyle.json
blender -b --factory-startup --disable-autoexec -P tools/inez/hair/groom_with_mainhair.py -- \
  HairNodes.blend $W/guides.npz $W/head_surface.npz $W/strands.npz $W/groom.blend $W/groom.json
python3 -I tools/inez/hair/build_strand_hair.py --glb assets/characters/inez/model/v06/inez_recovery_v06.glb \
  --strands $W/strands.npz --guides $W/guides.npz --cards $W/restyled.npz --fit $W/fit_lod0.npz \
  --scalp $W/pkg/scalp.npz --output assets/characters/inez/model/v06/inez_recovery_v06_hair_strands_r09.glb --report $W/build.json
```

1. **Restyle** (`restyle_ponytail.py`): every card that passes within 4 cm
   of the package's high tie is part of the ponytail (373 of 665). The tie
   moves 3.7 cm down and back onto Inez's own ponytail root (hair.01); the
   scalp part follows with a 6 cm falloff at its original height above the
   scalp. Each tail is re-laid by arc length along the hair.01-04 chain (the
   reference path, down to the upper back), lengthened per card so the longest
   tails end at the chain end (tips at y 1.34-1.45 m), keeping each card's
   offset, width and waves through parallel-transported frames. 665 guide
   curves (card centrelines) result.
2. **Groom** (`groom_with_mainhair.py`): a copy of MainHair runs on the
   guides with Inez's head as the Stick To Mesh object. Parameters were
   authored for a much larger scene, so the copy changes values only (plus a
   stored `guide_id` and the curl's random seed): Hair Amount 2 -> 20
   (13,300 strands), Spread 0.8 x 0.02 -> 0.8 x 0.004, Clumping x5..x1.5 ->
   x4..x0.5, Points 8 -> 16, Random Length absolute 1-2.7 -> 75-100 % of the
   guide, Noise 0.1 -> 0.003, Roughness 41 % x 0.2 -> 4 % x 0.006, Curl 6 ->
   40 points, Curl Scale 0.01 -> 8 turns, Curl Shape 0.2 -> 0.005 m, curl
   random factor 0.6-1 seeded per guide (ringlets per clump instead of
   frizz), curl circle perpendicular to the strand (helix). Deform Curves on
   Surface is bypassed (static rest groom).
3. **Build** (`build_strand_hair.py`): strand points over the scalp part of
   their guide are put back at the guide's height above the scalp (one offset
   per strand), every point is kept >= 1 mm out of the skin and 2 mm out of
   the sweater, and each point is bound to its guide (parameter, offset and
   tangent in the guide frame; rest reconstruction error 6e-17 m). Guides are
   skinned to head and hair.01-04 (no joints added). An angular depth map
   darkens inner hair. A soft-edged matte scalp patch covers the whole hair
   area: Inez's head texture has a bare-skin patch at the back of the head
   where the old ponytail shell attached. 532,000 points; 63 MB GLB.
4. **Viewer** (`viewer/src/hair/strand-hair.js`): the 665 guides (12
   particles each, 3,136 pinned) run in the card solver; their positions and
   frames go to a float texture and the vertex shader rebuilds every strand
   point and expands it into a ribbon at least one pixel wide (coverage =
   true width / drawn width, alpha-to-coverage). Kajiya-Kay shading with a
   white primary and a coloured secondary lobe, darker roots, per-strand
   variation, damp-look tuning in `inez_messywavy_cards_r01.json`
   (`strandAppearance`). The solver's follow-the-leader pass now restores
   segment length after each collision push (stretch was 6.2 % on Run).

Evidence: `renders/hair_strands_r09_matched/` (before/after, same camera and
light; reference comparison), `hair/qa/hair_strands_r09_motion.json`.

Known limits: the references' ponytail is curlier and they show more loose
tendrils at the temples; side ringlets sit below the ears. Hair neither casts
nor receives shadow-map shadows yet. About 1.06 M ribbon vertices: the whole
scene ran at 0.1 FPS on this container's software renderer (CPU evidence
only); profile on the target GPU before any frame-rate claim, and add a
strand LOD if needed. The GLB (63 MB) uses float32 attributes throughout.
