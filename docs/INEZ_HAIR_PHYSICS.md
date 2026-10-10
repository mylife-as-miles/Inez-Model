# Inez hair production — intake and simulation foundation

**Status: selected Fab hair is not integrated.** The local workspace contains no
Ponytail MessyWavy FBX, ABC, MHPKG or Additional Files ZIP. The public listing
was inspected on 2026-10-10; no authenticated Fab download was performed.
The complete asset-specific fitting, rigging, shading and motion acceptance
gate remains open. No selected-asset preview or production physics pass is claimed.

## Reference and source lock

[WhiteCap's selected listing](https://www.fab.com/listings/a3425afb-5801-455e-a6a1-e27632d493db)
advertises a MetaHuman MHPKG and a separate Additional Files ZIP containing
custom FBX hair cards, FBX scalp/reference head, PNG/TGA maps and ABC strands.
That is publisher metadata, not an inventory of downloaded files.
Its public Personal/Professional tiers are Fab Standard; the user's entitlement
and delivered package license have not been verified. Honor the user's NoAI
restriction: use local Blender transformations, never submit meshes/textures
to generative services or training. The Unreal physics setup is not portable.

Use `references/inez_portraits.jpg` and `references/inez_turnaround.jpg` as
identity authority. The user's supplied 254336/254275/253907 renders guide the
requested lighter skin and medium-brown hair appearance. Preserve the loose
high wavy ponytail, face-framing curls and natural volume. The new asset must
fit Inez's scalp; her face, body, outfit, UVs, facial layers and existing rig
must not be changed to accommodate it.

Existing editable source: `model/inez_master.blend`. Color/contact recovery:
`model/v06/inez_recovery_v06.blend` and its GLB. Both retain the 167-joint rig,
including `hair.01`–`hair.04`. Existing primary clips contain baked ponytail
motion; this is **not** a runtime physics integration.

## Local package intake

Place the legitimately downloaded Additional Files package in
`assets/characters/inez/hair/source/` or supply its local path. Keep source
bytes untouched. Run:

```sh
python3 tools/inez/hair/asset_intake.py --source /path/to/extracted-package \
  --report assets/characters/inez/hair/qa/intake_v01.json \
  --license-note /path/to/receipt-or-license-note
```

The tool records hashes, file formats, archive contents and actual image
dimensions; it does not extract archives, assert entitlement, guess texture
roles or fit a mesh. Then import the verified FBX in Blender into an untouched
source collection and create a working duplicate. Inspect units, axes, card
islands, alpha borders, UVs and map roles before fitting. Measure Inez's scalp
and the package reference scalp, align the gathering point and hairline,
fit temples and curls locally, preserve card spacing and strand direction,
and review front/profile/back/above renders against the originals. Save a new
working Blend and GLB; retain the current hairstyle for rollback.

## Executed solver foundation

`viewer/src/hair/guide-solver.js` implements world-space XPBD guide particles
with anchored roots, gravity, inertia, rigid length constraints, compliant
second-neighbor bend constraints, compliant rest-shape targets, drag, sphere/
capsule collision, contact friction and bounded velocity/acceleration.
Fixed 60 Hz stepping interpolates supplied attachment poses between presentation
frames. Roots follow the supplied position/quaternion; free particles retain
world inertia when the attachment translates or rotates. Wind is an optional
explicit acceleration vector, zero by default; there is no random idle motion.

Large deltas, excessive translation and explicit resets reinitialize the state.
Nonfinite particle state recovers; invalid inputs fail explicitly. Pause holds
the deformed shape in attachment space; single stepping is available. Particle
positions can be interpolated for rendering. Collision proxies must be supplied
in world metres at each fixed tick, with kinematic velocities when available.

The tests execute 30/60/120 FPS and irregular presentation timing, deterministic
replay, root attachment, settled idle, length error, sphere/capsule separation,
pause/resume/single step, teleport and nonfinite recovery. These are **solver
fixtures**, not demonstrations of the selected hair on Inez. Run:

```sh
cd viewer
node --test qa/hair-guide-solver.test.mjs
```

`hair/presets/guide-foundation.json` stores provisional tuning in physical units.
Guide count, regions, bone binding, actual anatomy proxies and quality-mode
transitions require the source topology. Do not describe these preset names
as measured production quality modes. Initial fixture tuning that held shape
too rigidly was corrected by softening compliant shape/bend forces; tests now
exercise actual inertial displacement and collision separation.

## Three.js and CORDEL integration boundary

The solver is **not enabled or bound to viewer meshes yet**. It takes plain
arrays for head attachment transforms, measured guide rest points and collision
proxies; it returns particle points. No Jolt or Unreal type enters this API.
The later Three.js adapter must sample the primary AnimationMixer and facial
pose first, then transform kinematic proxies, step guides, and apply secondary
bone rotations. Remove/override only overlapping baked hair tracks, retain the
bind pose, leave scalp attachment immediate, and preserve face morphs. Separate
curl guides must be derived from actual card topology; the current four-bone
chain alone cannot prove independent face-framing curl simulation.

CORDEL was freshly inspected at `057d304c5958e00913dae3d4d1383dff6dbf81fa`,
the current remote HEAD. `native/phase1_host/src/scene/scene.cpp` rejects skin,
hierarchy, rotation, scale and matrices in its static fixture loader. Character
motor and skeletal locomotion are still roadmap Phases 2.2 and 2.4. Physics
queries use engine-neutral `Vec3`, `Quaternion`, capsule casts and overlaps
under `native/physics/include/cordel/physics/`; simulation belongs on the
authoritative 60 Hz world update after animation. No CORDEL source was changed.
Native hair rendering/simulation integration requires its skinning and animation
prerequisites; no native execution is claimed.

GLB carries geometry, UVs, skin weights, bones and optional baked clips. It does
not automatically execute XPBD. Keep runtime solver, guide configuration and
proxy attachment data separate unless CORDEL adds an explicit supported format.

## Remaining acceptance work

Inspect the real licensed package; fit and rig scalp/main ponytail/curls/flyaways;
assign supplied color/alpha/normal and inspected auxiliary maps; implement and
measure bone/guide deformation and anatomy colliders; run actual Idle/Walk/Run/
Stop/Turn/LookDown/Crouch/Fear/Wind/Teleport sequences; capture real renders and
a demonstration. Verify reference brown color and silhouette under neutral,
warm/dim interior, backlight and flashlight, alpha stability, settling and
collision quality. Measure actual simulation/shading costs and quality transitions
on the target GPU. Until then, selected-hair production approval is **false**.
