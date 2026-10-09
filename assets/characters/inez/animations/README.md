# Inez animation — staged clips

The requested delivery is a playable character with actual rig deformation.
This folder begins as preparation; it is not a completed animation delivery.
The gait planner has been numerically checked without creating or changing a
model. The actual dressed `.blend` and explicit root handoff are required next.

`Idle`, `Walk`, `Run` are looping skeletal clips. The foot path divides into a
stance phase and a lifting swing. Thigh/shin IK is baked into the real source
joint rotations, with preserved intermediate twist chains. Arms settle from
the source A-pose and swing opposite the legs. Pelvis, spine, neck, wrists,
fingers, gaze and weighted ponytail motion give the body coordinated movement.
The character's armature object stays in place. The browser translates and
turns the character at the clip's reported speed.

| Clip | Proposed cycle | Stance | Speed at provisional 1.68 m |
| --- | ---: | ---: | ---: |
| Idle | 4.00 s | planted | 0 m/s |
| Walk | 1.14 s | 62% | 0.95 m/s |
| Run | 0.76 s | 42% | 2.65 m/s |

The final periods are rounded to Blender frame boundaries; use the actual
`matching_viewer_speed_m_s` from `animation_manifest.json`. Boot support is
computed from rotated boot vertices rather than treating the ankle as the sole.
The planted stance moves backwards locally at the matching movement speed.
Root drop keeps the limbs within reach; foot-lift and pitch vary through swing.
The run has a short flight phase. A-pose to locomotion rest pose is a real pose
change, not a rigid whole-character bounce.

Optional `Blink` is a facial-only lid-bone clip. Use it once/additively or drive
the `Blink_L/R` morphs in the browser. Do not layer both blink methods at once.
Expressions and visemes are direct mesh controls, so they layer over the gait.

Prepared commands, only after root supplies and enables the actual source:

```bash
blender -b -t 4 --python tools/inez/animation_build.py -- \
  --root-enabled --source SOURCE.blend --output-blend ANIMATED.blend \
  --output-glb ANIMATED.glb \
  --report assets/characters/inez/rig/animation_manifest.json
python tools/inez/animation_validate_glb.py --glb ANIMATED.glb \
  --manifest assets/characters/inez/rig/animation_manifest.json \
  --report assets/characters/inez/animations/exported_deformation_audit.json
```

The Blender report samples evaluated vertices/boot soles and joint positions.
The independent glTF audit decodes the actual exported skin, applies animated
joint matrices and identity morphs, checks weights and loop endpoints, and
measures actual expression displacement. It samples four times per baked
frame, records actual left/right arm/leg vertex movement, checks every mesh's
loop endpoints, follows brows/lashes through exported morphs, and verifies
skin/UV/PBR preservation and each identity morph's exact source default.
Inactive older fit revisions stay inactive. Standard Three.js runtime weights are made
explicit in the separate animated copy before these checks (see rig README).
These numerical checks support a
technical claim only; visual/browser review remains necessary for natural gait,
costume intersections and character identity.

Known limitations before source review: reference images provide no motion
capture, true profile/hidden anatomy, teeth/tongue interior or calibrated height.
The procedural gait and subtle expressions therefore need manual artistic
refinement if the rendered results fail critique. No full-quality approval is
claimed from script presence, joint counts or a mathematical curve alone.

