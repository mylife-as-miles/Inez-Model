# V06 pause checkpoint — 2026-10-10

Current development progress and limitations are recorded in `docs/INEZ_V06_PRODUCTION_REPORT.md`; continuation instructions are in `docs/INEZ_NEXT_AGENT_PROMPT.md` (paths relative to repository root). Recovery color and contacts are saved; R02 likeness remains unapproved; selected Fab hair source is missing; target GPU profiling and native CORDEL integration remain pending. Prior content below is historical and must be checked against actual final V06 artifacts.

---

# Inez visual QA (final build of this run)

**Verdict.** The likeness is **not accepted**. The model is the user's own two GLBs transferred onto a rigged production body. It is recognisably built from them and matches the originals' face outline closely at matched angles. It still fails several of the identity spec's measured gates and reads as a younger, smoother face than the originals.

The three corrective passes per component that the brief allows for this run are used up. Further passes need a decision from the owner (§6).

**Subject.** `model/inez_master.blend` and the GLBs exported from it. Renders were made with the neutral studio rig in Cycles with the AgX view transform. The evidence is in:

- `renders/final_v05/`: full-body views, face views and an eye close-up;
- `renders/likeness_v05/`: matched-angle overlays and `report.json`;
- `renders/rig_review/`: expression and clip strips;
- `renders/browser_v02/`: frames from the browser, including `19_reference_comparison_page.png`.

**Score.** No number in this report is invented. My overall judgment is about **75/100** against the 90 target. It is an opinion summarising the measurements and side-by-side review below, not a measured score.

## 1. Measured gates (identity spec §7)

All measurements use MediaPipe landmarks on the final renders, compared with the originals.

- **Face renders:** `face_yaw_p5` (yaw −3.2°) against the B face panel (−2.9°).
- **Skin:** the same pairs, plus `face_yaw_p18` against the A right portrait.
- **Garments:** `tools/inez/garment_ratios.py`, with fixed boxes on `body_front` / `body_back` and on the turnaround panels, and the same two-tone split of the knit for both.

### 1.1 Frontal ratios (÷ IPD)

The limits are ±3% for full-weight ratios and ±6% for half-weight ratios.

| Ratio | Weight | Original B | Final | Δ | Gate | Asset B as delivered |
|---|---|---|---|---|---|---|
| eye line → chin | full | 1.681 | 1.745 | +3.8% | **fail** | 1.652 |
| eye line → subnasale | full | 0.732 | 0.767 | +4.8% | **fail** | 0.704 |
| lip seam → chin | full | 0.632 | 0.649 | +2.7% | pass | 0.630 |
| alar width | full | 0.584 | 0.624 | +6.8% | **fail** | 0.615 |
| eye width | full | 0.430 | 0.432 | +0.5% | pass | 0.415 |
| inner eye gap | full | 0.529 | 0.542 | +2.5% | pass | 0.552 |
| jaw width | full | 1.615 | 1.724 | +6.7% | **fail** | 1.687 |
| cheek width | half | 2.085 | 2.196 | +5.3% | pass | 2.116 |
| mouth width | half | 0.695 | 0.786 | +13.1% | **fail** | 0.773 |
| upper lip height | half | 0.121 | 0.141 | +16.5% | **fail** | 0.130 |
| lower lip height | half | 0.227 | 0.215 | −5.3% | pass | 0.198 |
| eye opening ÷ width | expression | 0.362 | 0.291 | −20% | (not gated) | 0.283 |
| brow → eye | expression | 0.335 | 0.319 | −4.8% | (not gated) | 0.312 |

**Result:**

- Full-weight ratios: 3 of 7 pass.
- Half-weight ratios: 2 of 4 pass.

**How the misses arose:**

- The wide mouth, nose and jaw come with the user's Asset B and were not narrowed enough.
- The landmark correction overshot the lower face, lengthening it past the original.

**Caveat.** The render's head pitch is 3.5° further down than the panel's, and vertical ratios are sensitive to pitch. The Asset B column was measured in an earlier report on a straight front view with a slightly different crop, so it is indicative only.

### 1.2 Outline error at matched angles

The outlines are aligned by similarity transform on stable points (eye corners, nose bridge, nose tip). This tolerates scale and pose; it is a different, looser measure than §1.1.

| Pair | Yaw gap | Jaw | Nose | Eyes | Brows | Lips | All |
|---|---|---|---|---|---|---|---|
| Final vs B face panel | 0.4° | 0.035 | 0.012 | 0.018 | 0.027 | 0.022 | **0.024** |
| Final vs A right portrait | 1.0° | 0.080 | 0.013 | 0.023 | 0.044 | 0.024 | **0.042** |
| Final vs A left portrait | 0.7° | 0.097 | 0.022 | 0.034 | 0.078 | 0.037 | **0.059** |
| Asset B as delivered vs B panel | 2.1° | 0.072 | 0.020 | 0.024 | 0.037 | 0.038 | 0.041 |
| Asset A as delivered vs B panel | 1.8° | 0.111 | 0.027 | 0.022 | 0.039 | 0.090 | 0.065 |
| Original A right vs original B (reference spread) | 9.8° | 0.254 | 0.037 | 0.052 | 0.062 | 0.050 | 0.118 |

**Results:**

- The final outline is closer to the B panel than either delivered asset.
- Its error is well inside the spread between the two original images. That spread is measured at a 9.8° yaw gap, so it is a loose bound.

**This does not establish likeness.** §1.1 and §3 show differences in proportion and appearance that the outline measure tolerates.

### 1.3 Skin colour

| Pair | R/G original | R/G final | G/B original | G/B final | Luminance original / final |
|---|---|---|---|---|---|
| B face panel | 1.97 | 1.65 (−16%) | 1.42 | 1.31 (−8%) | 0.15 / 0.28 |
| A right portrait | 2.01 | 1.64 (−19%) | 1.48 | 1.31 (−12%) | 0.15 / 0.28 |

**Fail** (±6%). The render is about 1.9× brighter than the photographs. AgX compresses chroma at higher exposure, so this measurement conflates three things: exposure, the view transform, and the albedo. Which one carries the error has not been established.

On screen the skin reads paler and less warm than the originals. Under-eye darkness and redness at the nose and cheeks are weaker.

### 1.4 Garments

The limit is ±25%.

| Ratio | Original front / back | Final front / back | Gate |
|---|---|---|---|
| stripe / grey knit luminance | 0.253 / 0.215 | 0.286 / 0.396 | front pass, **back fail (+84%)** |
| jeans / grey knit luminance | 0.218 / 0.212 | 0.189 / 0.221 | pass |
| stripe G/B (blue content) | 0.67 / 0.71 | 0.86 / 0.84 | **fail**: stripes read charcoal, not navy |

The back of the sweater was completed by mirroring Asset A's front. Its stripes are washed out and partly smeared (`renders/final_v05/body_back.png`).

## 2. Side-by-side review

These are the deductions behind the 75/100 judgment, worst first:

1. **Face reads younger and smoother.** The originals show a worried adult with under-eye shadows, forehead tension and skin texture. The render has an even, youthful surface. This is partly expression, since the originals are worried and the default is neutral. It is also partly the lower-detail transferred albedo and the brighter, paler skin of §1.3.
2. **Eyes narrower.** The opening is 0.29 of eye width against 0.36. The upper lash line is heavy and dark, which narrows them further.
3. **Mouth, nose and jaw slightly wide; lower face slightly long** (§1.1)
4. **Hair.**
   - The shell is stiff, with jagged strand tips and a grey streak on the crown.
   - The face-framing curls are shorter and darker than the originals' golden-brown curls.
   - The ponytail ends at the upper back, where the original reaches about the second stripe.
   - Measured: hair side R/G 1.68 and G/B 1.62, inside the originals' ranges (1.67–1.77 and 1.51–1.88). Top-of-head luminance relative to the cheek is 0.20 against 0.14–0.16, too light.
5. **Ears** are more prominent than in the originals, where curls cover them.
6. **Sweater stripes** are charcoal instead of navy, and washed out on the back (§1.4).

**What matches:**

- Head and face outline (§1.2), eye spacing and width.
- Hazel-green irises.
- Brow shape and density.
- Freckle distribution.
- The costume's cut: cropped knit, high-waisted wide jeans, platform combat boots, a fine V necklace.
- Body proportions.

## 3. Passes used this run

Reconstructed from the identity layers and the commit history (`f566bf3`, `d031955`, `d26211f`).

| Component | Pass 1 | Pass 2 | Pass 3 |
|---|---|---|---|
| Face geometry | Production head refined toward the originals (`Inez_HeadRefine_v05`) | Production head wrapped onto Asset B's face (`Inez_SourceHeadWrap_v05`) | Landmark correction toward the B face panel (`Inez_FaceCorrect_v05`) |
| Skin and face texture | Asset B colour baked onto the head UV | Chroma matched to both portraits; freckles, brows, under-eye | Skin gain re-fit; brows rebuilt (hair-only mask, darker); lid-margin tone; tearline strips removed |
| Eyes | Rigid 12 mm eyes behind B's pupils, B's lid contour | Iris colour from the originals' iris rings | Lid margins, tearlines removed |
| Hair | B's shell extracted, cleaned at ears, eyes and neck | Colour toward the turnaround | Colour re-targeted (sides now inside the measured range) |
| Garments | Asset A's sweater, jeans and boots transferred and skinned | Sweater hole completed by mirroring, collar spikes trimmed, boot soles rigid | (none) |
| Necklace | Rebuilt along Asset A's modelled V | (none) | (none) |

Face geometry has used its three passes. The open geometry items in §1.1 therefore wait for the next run (§6), as the brief requires. Lighting or texture is not used to hide them.

## 4. Technical checks (passed)

- **glTF validation.** The Khronos validator reports 0 errors on every GLB (`qa/technical/*_validation.json`).
- **Browser.** `qa/browser_browser_v02.json` shows `technical_passed: true`, with 14 of 14 checks, on the runtime GLB in Chromium. The checks cover:
  - geometry and UVs;
  - all 17 clips present and deforming the mesh;
  - turn and crouch chains;
  - cross-fades;
  - each of the six expressions and four facial clips moving the face. They move it 1.55–12.46 mm, matching Blender's per-target maxima within 0.05 mm;
  - blink, jaw, eye and head controls;
  - identity morphs held at their defaults;
  - keyboard locomotion;
  - no runtime errors.
- **Measurement fix.** An earlier run reported four expressions as not deforming. That was a fault in the measurement: it sampled the torso primitive. The body exports as two primitives, and the facial targets live on the face primitive. The morph data were correct throughout.

These are integration checks, not artistic approval.

## 5. Originals and sources

- **Originals.** `references/inez_portraits.jpg` (SHA-256 `ce76f4cc…6a764b`) and `references/inez_turnaround.jpg` (`9482e1a5…b2f64d39`) are unchanged.
- **The user's GLBs.** `source/asset_a/Inez.glb` and `source/asset_b/Inez Facial Model.glb` are stored byte-for-byte and read-only.
- **The segmented model.** `source/asset_c/Inez+segments.glb` is stored the same way; it was audited but not used in the build (see `GLB_ASSET_AUDIT.md`).

## 6. Recommended next run (needs the owner's go-ahead)

1. **Geometry first.**
   - Narrow the mouth by about 10%, the alae by about 6% and the jaw by about 6%.
   - Shorten eye-to-subnasale and eye-to-chin by 3–4%.
   - Open the default lid aperture toward 0.33–0.36 of eye width.
   - Each change is one landmark-driven layer, measured again at matched yaw and pitch.
2. **Skin.** Re-measure with the Standard view transform at matched exposure, to separate albedo from tone mapping. Only then change the albedo.
3. **Hair.**
   - Replace the stiff shell's crown and strand tips with hair cards (tools exist: `model_hair_cards.py`).
   - Lighten the curls toward the originals' golden brown.
   - Lengthen the ponytail.
4. **Sweater.**
   - Rebake the back from the front with stripe alignment instead of a mirror.
   - Shift the stripes toward navy (G/B ≈ 0.7).
