# Inez: human head scan source evaluation

This answers the earlier brief, "high-fidelity human scan reconstruction
pipeline". That brief asked us to rebuild Inez on a licensed 3D head scan used
as the anatomical base. The scan was never treated as Inez: identity had to
come from the original images.

The evaluation was done on 2026-10-09. The evidence is under
`assets/characters/inez/scans/`:

- `licenses/` holds verbatim licence text, with a SHA-256 of each retrieved
  page.
- `manifests/` holds the scan inventory.
- The raw scan data is git-ignored.

> **Status.** Scan work is paused. The later brief, "existing GLB
> reconstruction", replaced the anatomical source with the user's own models
> (Asset A body, Asset B face). The current master
> (`model/inez_master.blend` / `.glb`) contains **no scan-derived geometry,
> normals or textures**. Scan tools remain in `tools/inez/scan_*.py` in case
> the project returns to them.

## Candidates

| Source | Access | Licence (verbatim evidence) | Commercial game use | Decision |
|---|---|---|---|---|
| **Ten24 sample scan** (ten24.info) | Direct link on the publisher page; no account or form | "Feel free to use this scan as you wish for both commercial and personal projects. All we ask is that you provide us with a credit wherever it's used." | Yes, with credit | **Selected for evaluation**; downloaded and inspected |
| HumanScanRepository free samples | Free download | Free for commercial use with credit, but "we do not allow resale or free distribution on other websites, either of the original or any derivatives from the model" | Embedded use only | Not used: a browser GLB is downloadable, which conflicts with the no-distribution-of-derivatives clause |
| FaceScape (NJU / Baidu) | Licence agreement form | "The license granted is for internal, non-commercial research, evaluation or testing purposes only" | **No** | **Rejected**: licence incompatible regardless of quality |
| Headspace (York) | University academics only, via user agreement | "free for University-based non-commercial research" | **No** | **Rejected**: licence incompatible, and access is restricted to verified academics |

We bypassed no account, paywall or access agreement. Research-only scans were
not downloaded.

## The Ten24 sample: what it is

These facts are recorded in `manifests/ten24_sample/ten24_sample_2016.json`.

**Archive.** `OBJ+Package.zip`, 1,967,870,302 bytes, SHA-256
`1e7986dd…a138cde`. It contains a ZBrush 4.73 export dated 2016-03-25.

**Subject.** An adult **male**, full body, clothed. He has short hair and
stubble and a neutral closed mouth. He is not Inez and must never be
presented as her.

**Geometry.** Subdivision levels L1–L5, from 7.6k to about 1.94M vertices.
The units are metres, and the stature is 1.847 m in boots. The scan uses a
single 0–1 UV layout.

**Maps.**

- Normal maps `Level_01…06` are 8192² tangent-space.
- The 8K colour map was used only to build masks. Donor skin colour is never
  reused.

**Finding.** The forehead and cheeks show little pore-scale relief, so
pore-scale detail cannot be claimed as scanned. Mid-scale anatomy (lids,
nostrils, lips) is present.

## Licence flags

**Browser GLB distribution.** This is flagged for explicit legal
clarification.

- The Ten24 terms allow commercial use with credit.
- They do not address standalone, downloadable derivative meshes or textures.
  A web-delivered GLB is exactly that.

The question is moot for the current master, which carries no Ten24
derivative. It would apply again if scan-derived detail is reintroduced.

**Credit line,** if used: "Facial surface detail derived from the Ten24
sample scan (ten24.info), used under its published usage terms."

**Raw redistribution.** The raw scan is never committed or redistributed.
`.gitignore` excludes `scans/source/`, `scans/working/` and
`model/inez_scan_base.blend`.

## What was built before the pause

These tools exist as files and were run during the earlier brief. Their
outputs are scratch work, not part of the master.

- **`scan_import.py`.** Imports and crops L1/L4 above 1.48 m and applies the
  Level_04 normal map.
- **`scan_landmarks.py`.** Lifts MediaPipe face landmarks onto the scan surface
  with thick first-contact rays.
- **`scan_fit.py`.** Thin-plate fit of the scan to Inez's landmark proportions,
  followed by a frequency split.
- **Wrap, masks and bake.** `scan_wrap.py`, `scan_masks.py` and `scan_bake.py`
  wrap the production head and bake a masked detail normal. Hair, stubble,
  brows, a donor mole and under-eye age cues are masked out.

The paused output reached a wrapped head and baked detail maps. It never passed
an identity gate, so it was set aside when the brief changed.

## If scan work resumes

1. Get written clarification from Ten24 for browser-delivered GLB use, or
   deliver scan-derived detail only inside a compiled game build.
2. Use only mid-scale normal detail (Level_02–04) under the existing masks.
   Never use donor colour, and never use scan geometry where it would
   override the user's Asset B face.
3. Re-run the identity checks in
   `assets/characters/inez/reports/INEZ_IDENTITY_SPEC.md` §7, and fail the
   pass if any check worsens.
