# Inez animation QA

Measured results for every clip that plays on Inez: the procedural clips embedded in the character GLBs, and the retargeted motion-capture clip loaded from `animation/clips/`. Nothing here is TERRA output; no TERRA motion exists yet ([`INEZ_TERRA_INTEGRATION.md`](INEZ_TERRA_INTEGRATION.md)).

## How it is measured

Three independent measurements, so a fault in one shows up in another:

| # | Where | What | Tool |
|---|---|---|---|
| 1 | Blender, during the bake | The retargeter's own bookkeeping: support points of each boot treated as rigid to the foot; stance slip of the point in contact; lowest sole; IK reach; rotation steps; frame count; the written GLB read back | `tools/inez/motion/retarget_to_inez.py` → `animation/qa/*_retarget.json` |
| 2 | Blender, the deformed mesh | Each boot's sole vertices on the evaluated (skinned) mesh. Planted means the lowest point is within 2 mm of the floor, below the 3 mm swing clearance. Slip is the travel of the vertex in contact, frame to frame. In-place clips are moved at their matching speed. | `tools/inez/boot_contact_audit.py` → `qa/technical/boot_contact_audit.json` |
| 3 | Chromium, Three.js | The real runtime GLB with the clip GLB bound by bone name, played by the viewer at its matching speed. Checks: source label, clip duration, travel speed, feet moving relative to the character, lowest sole, sole slip (same definition as 2), loop seam. | `tools/inez/browser_lab_qa.py` → `animation/qa/browser_lab_v01.json`; frames in `renders/lab_v01/` |

## Retargeted motion capture: `Mocap_Walk_CMU_02_01`

**Source.** CMU subject 02, trial 01: a straight walk, 2.85 s at 120 Hz. It is labelled `CMU mocap` in the viewer; the licence is in `INEZ_MOTION_LICENSES.md`.

| Measure | Corrected | Raw, no contact pass (comparison) |
|---|---|---|
| Frames / duration | 86 at 30 fps / 2.83 s (frame count preserved) | same |
| Matching speed (in place) | 1.128 m/s | same |
| (1) Stance slip per phase, support points | 0.004 mm L, 0.006 mm R | 43.9 mm L, 47.5 mm R |
| (1) Lowest sole, support points | −0.0006 mm | −41.7 mm |
| (2) Stance slip per phase, deformed mesh | **12.3 mm L**, 0.16 mm R | 117 mm L, 101 mm R |
| (2) Lowest sole, deformed mesh | **−3.05 mm L**, 0.0 mm R | −33.9 mm L, −41.7 mm R |
| (3) Lowest sole in the browser | −2.97 mm | −41.78 mm |
| (3) Stance slip in the browser, mesh, at the 30 fps keys | 13.0 mm L, 0.7 mm R | 95 mm L, 101 mm R |
| (3) Viewer lab counter, at 60 Hz display steps | 18.3 mm L, 11.2 mm R | 102 mm L, 127 mm R |
| (3) Duration and travel speed in the browser | 2.833 s, 1.128 m/s | same |
| IK reach error | 0.0 mm | 0.0 mm |
| Largest rotation step | 17.8° / frame (`lowerleg01.L`) | — |
| Knee flexion, stance mean L / R (source) | 26.4° / 26.9° (26.6° / 25.3°) | — |
| Knee flexion, swing max L / R (source) | 73.6° / 74.1° (73.5° / 73.0°) | — |
| Trunk lean, mean (source) | −1.7° (+1.2°) | — |

### Findings

- **The browser plays exactly what Blender baked.** At the keys, the lowest sole agrees within 0.1 mm and stance slip within 1 mm on both clips. The clip lasts 2.833 s and the character travels at 1.128 m/s. The browser check `corrected_clips_sole_slip_under_10mm` **fails** (13.0 mm, the left heel below).
- **Between keys the feet drift.** The clip is baked at 30 fps. Played at 60 Hz, the frames between keys interpolate each bone's rotation separately, and that does not hold the foot still. The viewer's 60 Hz counter therefore reads 5–11 mm more slip than the keys do. Baking at 60 fps (`--fps 60`) would halve that interval; not done yet.
- **The right foot is planted.** It slips 0.16 mm on the mesh and does not go below the floor.
- **The left foot is not fully planted.** On the deformed mesh its heel slides up to 12 mm per stance and dips 3 mm below the floor. The retargeter's bookkeeping reported about 0 here.
  - **Cause.** About 35% of each boot's lowest-3 cm vertices share weight with the shin bones, down to a foot weight of 0.03. So the back of the platform sole bends with the shin, while the retargeter models the sole as rigid to the foot. The weighting is the same on both boots: 861 and 881 shared vertices. Why the right foot stays within 0.2 mm in this take is not established.
  - **Fix.** Re-weight the boot soles (below the ankle) fully to `foot.L/R`. Platform soles are rigid. This is a change to the master, so every GLB must be re-exported. It is listed for the next run.
- **The contact pass works.** Compared with the raw clip, slip drops from 101–117 mm to 0.2–12 mm, and penetration from 42 mm to 3 mm.
- **The take is not a loop.** CMU 02_01 is a single straight walk, so looping it pops the feet by about 0.6 m at the seam. For looping locomotion, cut a cycle at matching foot phases or blend the seam. Not done yet.
- **Trunk lean.** Inez leans about 3° further back than the source. Not diagnosed.
- **Visual review** of the 16 Cycles frames in `animation/previews/mocap_walk_cmu_02_01/`:
  - The gait reads as a natural walk: heel strike, roll and toe-off, knees bending through swing, a counter-swinging arm, and a ponytail that follows.
  - **Clipping.** At mid-swing the left hand passes into the front of the jeans at the hip (`front_013.png`, `front_050.png`). The capture's arm swing runs closer to the body than Inez's wide jeans allow. The fix is an outward arm offset, or a hand-to-hip distance constraint, in the retargeter.
  - The palms turn forward at the back of the swing, which gives an open-hand look.
  - The source's narrow, nearly in-line foot placement brings the knees and jeans legs close together. No pass-through is visible in these frames.

### Correction rounds used: 3 of 3

1. **Contact pass.** Pelvis offset from the median stance sole height, rolling no-slip anchoring, and 3 mm swing clearance. Before it, the soles were 5 cm under the floor and slid 4–7 cm per stance.
2. **Phantom support points.** `boot_vectors` took both boots, which are one mesh, as each foot's support points. Under foot roll the other boot's phantom was planted and the real left sole floated about 1 cm. Fixing it also brought the left knee back to the source's flexion: it had been +5° in stance and +11° in swing.
3. **Clip export.** Inside the full character scene the exporter wrote a 0.2 s constant pose. Export now runs on the armature with one action, and the file is read back (`exported_clip_matches_bake`).

In the browser, three QA and viewer faults were also found and fixed. None of them changed the motion.

- **Shared key times.** Three.js tracks share one key-time array, so shifting each track to start at 0 moved the shared array many times over. The viewer now copies each array before shifting it.
- **Loop wrap.** The QA sampled one frame past the loop wrap.
- **Mesh selection.** The QA measured the torso primitive for facial expressions instead of the face primitive.

## Procedural clips (embedded in the character GLBs)

Deformed-mesh audit (2). In-place clips are moved at their matching speed: Walk 0.9205 m/s, Run 2.40 m/s.

| Clip | Lowest sole L / R (mm) | Largest stance slip per phase L / R (mm) |
|---|---|---|
| Idle | 0.0 / 0.0 | 0.01 / 0.01 |
| LookAround | 0.0 / 0.0 | 0.01 / 0.01 |
| Crouch (loop) | 0.0 / 0.0 | 0.0 / 0.0 |
| Walk | −7.9 / −8.7 | **45 / 49** |
| Run | −7.8 / −8.3 | **36 / 69** |
| TurnLeft | −0.1 / −3.2 | 5.8 / 5.2 |
| TurnRight | −5.1 / −1.6 | 10.6 / 18.8 |
| CrouchDown, CrouchUp | 0.0 / 0.0 | **45 / 42** |

**Findings:**

- The penetration figures (up to 8.7 mm in the walk) match the rig report.
- The slip is measured here for the first time, and it is real.
  - **Walk and Run.** The planted boots slide 4–7 cm per stance even at the matching speed. The procedural foot cycle and the travel speed do not agree exactly.
  - **CrouchDown and CrouchUp.** Each foot slides about 27 mm outward and turns out about 8°. `INEZ_RIG_QA.md`'s "feet stay planted" was a visual judgment; it is corrected there.
- The retargeted CMU walk has far less slip than the procedural walk. Fixing the procedural gait means rebuilding the animated master, which is for the next run.

## Browser checks of the character GLB

`qa/browser_browser_v02.json`: 14 of 14 checks pass on `inez_runtime.glb`.

- All 17 embedded clips are present and deform the mesh.
- Turns hand over their yaw; the crouch chain works; cross-fades blend.
- Six expressions and four facial clips deform the face primitive by 1.55–12.46 mm, matching Blender's per-target maxima within 0.05 mm.
- Blink, jaw, gaze and head controls work.
- The identity morphs keep their defaults throughout.
- Keyboard locomotion works.
- There are no runtime errors.

## Not covered yet

- An automated clipping check (hand–hip, leg–leg). Clipping is reviewed by eye only (above).
- Non-flat terrain. The contact pass is flat-ground only.
- Any TERRA clip.
