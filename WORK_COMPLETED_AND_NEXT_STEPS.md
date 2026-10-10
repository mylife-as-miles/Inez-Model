# V06 continuation checkpoint — 2026-10-10

The fetched development head is `7c430b5a`. Contact interpolation in four clips
has been corrected and applied to the default recovery GLB after actual browser,
skin, exported deformation and matched-render QA. The original face, color,
materials, rig and identity defaults remain intact. See
[current contact report](docs/INEZ_V06_CONTACT_REFINEMENT.md) and
[production report](docs/INEZ_V06_PRODUCTION_REPORT.md). The user explicitly
requested a commit and push of this development checkpoint, including completed
work, remaining implementation and the [next-agent prompt](docs/INEZ_NEXT_AGENT_PROMPT.md).
No main merge is authorized. Production/likeness approval is still false. Next:
controlled baked shading/scalp/costume fixes and original-reference review;
licensed hair ZIP and target hardware remain missing. R02 stays held.

## Previous pause checkpoint

Current development progress and limitations are recorded in `docs/INEZ_V06_PRODUCTION_REPORT.md`; continuation instructions are in `docs/INEZ_NEXT_AGENT_PROMPT.md` (paths relative to repository root). Recovery color and contacts are saved; R02 likeness remains unapproved; selected Fab hair source is missing; target GPU profiling and native CORDEL integration remain pending. Prior content below is historical and must be checked against actual final V06 artifacts.

---

# Inez — work completed and what's left (2026-10-10)

## Where things stand

| Area | State |
|---|---|
| Character model | **Built and rigged; the likeness is not accepted.** Inez is the user's Asset A (body, costume) and Asset B (face, hair) transferred onto a rigged production body, with three corrective passes per component. Measured gaps: mouth, nose and jaw wide; lower face long; skin chroma off; stripes charcoal instead of navy; stiff hair shell. My judgment is about 75/100 against a 90 target. ([visual QA](assets/characters/inez/reports/INEZ_VISUAL_QA.md)) |
| Rig and face | 167 joints, including eyes, lids, jaw, tongue and a 4-bone ponytail. 21 morph targets: 7 identity layers held at their defaults, 7 expressions, 5 visemes, 2 blinks. Blink, talk and hair motion all work on the user's geometry. ([rig QA](assets/characters/inez/reports/INEZ_RIG_QA.md)) |
| Exports | Master GLB, runtime GLB with KTX2 and meshopt, and two LODs. Every file is under 100 MB with 0 validator errors. |
| Browser | 14 of 14 checks pass on the real runtime GLB in Chromium: clips, expressions, controls, identity morphs, locomotion, no errors. |
| Motion pipeline | Intermediate-skeleton bridge with CMU and TERRA adapters, Blender retargeter, clip export and viewer lab. One CMU walk is retargeted and plays on Inez in Three.js, labelled `CMU mocap`. ([pipeline](docs/INEZ_ANIMATION_PIPELINE.md), [QA](docs/INEZ_ANIMATION_QA.md)) |
| TERRA | **No TERRA motion yet.** Every retarget path needs the SMPL-H model, which requires registration, and the licences do not cover a commercial game. The Inez side is ready. ([status](docs/INEZ_TERRA_INTEGRATION.md), [feasibility](docs/INEZ_TERRA_FEASIBILITY.md)) |
| Performance | Measured only on a CPU software renderer (2.3 / 3.5 / 4.4 FPS for LOD0 / 1 / 2). **No GPU measured.** ([performance](assets/characters/inez/reports/INEZ_PERFORMANCE.md)) |

## Done in this session

1. **Facial expressions in the browser.** QA had reported four expressions as not deforming. The morph data were correct: the QA sampled the torso primitive, and the face is the body's second primitive. Browser values now match Blender's per-target maxima within 0.05 mm.
2. **Retargeted clip export.** Inside the full character scene, the clip GLB had been written as a 0.2 s constant pose. The export now runs on the armature and that one action, and the written file is read back and checked.
3. **Foot support points.** The foot code used both boots, which are one mesh, as each foot's support points. Under foot roll this planted a phantom copy of the other boot. Fixing it brought the CMU walk's left knee back to the source's flexion.
4. **New measurement tools:**
   - `boot_contact_audit.py`: per-boot ground contact and slip on the deformed mesh in Blender.
   - `browser_lab_qa.py`: external clips in Chromium, with the same contact measure.
   - `browser_perf.py`: per-LOD frame rate, with a `--gpu` mode for real hardware.
   - `garment_ratios.py`: costume colour ratios against the turnaround.
   The browser and Blender agree within 1 mm on contact.
5. **Reports:**
   - visual QA, performance, animation QA, TERRA integration status, animation pipeline runbook;
   - rig QA tables;
   - Asset C (segmented model) audit;
   - corrected integration docs.
6. **The segmented model (Asset C).** It is stored and audited. Its face, eyes, mouth and hair are one fused surface with the eyes sculpted closed, so it cannot blink, talk or move its hair without rebuilding the face. The master already does all three on the user's geometry, so Asset C is not used ([audit](assets/characters/inez/reports/GLB_ASSET_AUDIT.md)).

## What's left, in priority order

1. **Likeness (needs your go-ahead for a fourth round of passes):**
   - narrow the mouth by about 10%, the alae by about 6% and the jaw by about 6%;
   - shorten the lower face by 3–4%;
   - open the lids toward the originals;
   - re-measure skin colour with a neutral view transform, then fix the albedo;
   - hair cards for the crown and tips, lighter curls, a longer ponytail;
   - navy stripes and a clean sweater back.

   Each change is geometry-first and measured at matched angles.
2. **Boot soles:**
   - re-weight the platform soles rigid to the feet. About 35% of the sole vertices bend with the shin, which leaves the CMU walk's left heel sliding 12 mm and dipping 3 mm;
   - then re-export all GLBs.
3. **Procedural gait.** The walk and run slide 4–7 cm per stance at the matching speed. The crouch slides each foot 27 mm outward. Either fix the gait or replace it with retargeted capture.
4. **Locomotion library (TERRA milestone 5) from CMU capture:**
   - cut looping cycles (the current take is a single walk with a 0.6 m seam);
   - bake at 60 fps;
   - fix the hand passing into the jeans at mid-swing;
   - add run, turns and stairs.
5. **TERRA.** Decide the licensing path:
   - commercial SMPL/AMASS licences;
   - research use only;
   - no TERRA.

   If you go ahead, supply SMPL-H and a permitted motion; the runbook does the rest.
6. **GPU performance.** Run `tools/inez/browser_perf.py --gpu` on the target machines.
7. **Game integration (milestone 7).** It needs the THREE BEDROOM / CORDEL character motor, which does not exist yet.

## Never changed

- The original images: `references/inez_portraits.jpg` (SHA-256 `ce76f4cc…6a764b`) and `references/inez_turnaround.jpg` (`9482e1a5…b2f64d39`).
- The user's GLBs in `assets/characters/inez/source/`.
- The identity morph defaults: HeadFit v01 = 0, v02 = 0, v03 = 1, and the four `_v05` layers = 1.
