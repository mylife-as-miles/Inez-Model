# Inez rig — staged implementation

This folder records rig work separately from facial/body approval. The source
character must pass the head/model gates before `animation_build.py` is run.
No animated model exists merely because these scripts and plans exist.

The CC0 MakeHuman source contains 163 bones and 139 weighted groups. It includes
the pelvis/spine/neck chains, split upper/lower limb segments, wrists/fingers,
eye pivots, upper/lower lid bones, brow/lip chains, jaw and tongue. Some facial
parent bones have no direct weights; their descendants perform deformation.
Raw `.mhw` totals are not normalized. Body and clothing import must normalize
all retained weights, and the animation audit checks the actual meshes again.

The confirmed model handoff uses `Basis_FemaleYoung_Source` plus individually
preserved `Inez_HeadFit_*` source defaults, rest-fitted 18° arms, boots `Inez_Boot_L/R` and
`Inez_Boot_Sole_L/R` weighted to `foot.L/R`, and initially head-weighted
`Inez_Ponytail_Curls` / `Inez_Ponytail_WarmAccentCurls`. The model artist owns
the dressed source. Animation execution awaits explicit root enablement and
that artist's completed source handoff; a clay head is not the motion source.

The licensed source reaches nine skin influences per vertex. Standard
Three.js SkinnedMesh consumes four. The separate animated copy therefore
keeps the largest four influences deterministically and renormalizes them
before baking/auditing. The untouched dressed source retains its full skin.
`runtime_weight_adaptation` reports counts and discarded normalized mass per
mesh; the source body can discard up to 0.30 at a vertex. Rendered joint
deformation needs critique, particularly at shoulders, wrists and the face.

The staged Blender pipeline is [animation_build.py](/workspace/tools/inez/animation_build.py).
It discovers `InezRig_PROTOTYPE` and `Inez_ContinuousHumanMesh_UNAPPROVED`, retains
the licensed names and source-index data, and saves to a new editable `.blend`.
It adds `hair.01`, `hair.02`, `hair.03` to the real armature and gives the separate
ponytail geometry normalized longitudinal skin weights.

Facial control names are `Neutral`, `Confused`, `Suspicious`, `SubtleFear`,
`IntenseFear`, `Anger`, `Exhaustion`, `Blink_L`, `Blink_R`, `Viseme_AA`,
`Viseme_EE`, `Viseme_OH`, `Viseme_MM`, `Viseme_FV`. Neutral resets these controls.
Every pre-existing `Inez_HeadFit_*` shape must retain its own saved value. For
example, source v02 has inactive v01 at 0 and active v02 at 1. The latest fit
already includes cumulative fitting controls; activating older revisions
would apply those controls twice. The source-default map is captured before
animation changes and compared to the exported GLB exactly. Each fit carries
identity fitting and is not an expression slider.

Jaw and blink shapes use actual bind-space weighted jaw/lid rotations. Brows,
lid aperture and lip tension use restrained displacement of the licensed face
skin regions. Brow/lash/tearline overlays receive corresponding mesh deltas.
These are identity-preserving expression hypotheses, not observed original
expression captures. No extreme smile or cartoon distortion is introduced.

Blender coordinates: X lateral, -Y forward, Z up. glTF/Three.js: X lateral,
+Z forward, Y up. Bone local axes vary because the licensed roll planes are
anatomical. Compose gaze about head-relative world Y/X in Three.js, then
transform through the current eye parent; do not assume all eye local axes
equal world axes. `animation_manifest.json` will record actual exported bind
axes once an approved source is available.

Required verification after handoff:

- Every skinned visible mesh has known bone groups and normalized weights.
- Eye centers rotate as pivots; lids close through geometry; jaw/lip controls
  deform the mouth and any supplied lower teeth/tongue geometry.
- Dense samples of actual body/boot geometry loop and plant soles near ground.
- Exported glTF limb skinning and each named expression actually change
  vertices; clothing/hair/face loop endpoints and overlay morphs also match.
- Every visible mesh retains UVs, normals, PBR material and actual skin, and
  each fitted identity morph retains its individual source default exactly.
- Browser mixer, blending, gaze and facial controls work on the real GLB.
- Independent rendered/browser critique checks silhouette and garment clipping.

Prepared scripts cannot establish these passes before the actual source exists.

