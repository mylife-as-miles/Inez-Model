# V06 pause checkpoint — 2026-10-10

Current development progress and limitations are recorded in `docs/INEZ_V06_PRODUCTION_REPORT.md`; continuation instructions are in `docs/INEZ_NEXT_AGENT_PROMPT.md` (paths relative to repository root). Recovery color and contacts are saved; R02 likeness remains unapproved; selected Fab hair source is missing; target GPU profiling and native CORDEL integration remain pending. Prior content below is historical and must be checked against actual final V06 artifacts.

---

# Inez performance

**No GPU has been measured.** Every frame rate below comes from this build machine: a 4-core Xeon VM with 15 GB of RAM and no GPU. Chromium there renders WebGL2 through SwiftShader, Google's CPU rasteriser. The numbers show relative cost between LODs and the CPU cost of animation. They say nothing about frame rate on real hardware.

To measure the hardware that matters, run this on that machine:

```bash
(cd viewer && npm ci && npx vite --host 127.0.0.1 --port 4173) &
python3 tools/inez/browser_perf.py --label <machine-name> --gpu        # add --headed if the GPU needs a visible window
```

It writes `qa/technical/performance_<machine-name>.json`, including the browser's WebGL renderer string, so the report names the GPU it measured.

## Asset budgets (measured from the files)

From `tools/inez/glb_stats.py`; the JSON is in `qa/technical/glb_stats.json`.

| File | MB | Triangles | Draw calls | Skinned meshes | Joints | Morph targets | Clips | Textures | Largest texture | GPU texture MB (compressed / RGBA8 est.) |
|---|---|---|---|---|---|---|---|---|---|---|
| `inez_master.glb` | 45.4 | 289,896 | 21 | 20 | 167 | 21 | 17 | 23 | 4096² (JPEG) | 220.9 / 883.7 |
| `inez_runtime.glb` | 29.0 | 144,450 | 21 | 20 | 167 | 21 | 17 | 23 | 2048² (KTX2) | 84.9 / 339.7 |
| `inez_runtime_lod1.glb` | 10.6 | 85,449 | 21 | 20 | 167 | 21 | 17 | 23 | 1024² (KTX2) | 22.9 / 91.7 |
| `inez_runtime_lod2.glb` | 5.0 | 57,450 | 21 | 20 | 167 | 21 | 17 | 23 | 512² (KTX2) | 6.4 / 25.7 |
| `inez_mocap_walk_cmu_02_01.glb` (clip) | 0.2 | — | — | — | (167 bound by name) | — | 1 | — | — | — |

**Texture memory is an estimate**, not a measurement: the texel count is multiplied by bytes per texel, plus a third for mipmaps.

- **"Compressed"** assumes 1 byte per texel. KTX2/Basis transcodes to BC7, ASTC 4×4 or ETC2 RGBA, which all cost that.
- **"RGBA8"** is 4 bytes per texel. That is the cost when no compressed format is available, and always the cost for the master's JPEG textures.

So the master's JPEGs cost about 880 MB of GPU memory once decoded. The master is for offline use and inspection, not the game.

**Runtime extensions:**

- `KHR_texture_basisu` (KTX2: ETC1S for colour, UASTC for normal, occlusion and metal/roughness maps);
- `EXT_meshopt_compression`;
- `KHR_mesh_quantization`;
- `KHR_materials_specular`.

The viewer registers the KTX2 and meshopt decoders. The Basis transcoder is served from three's own copy (`viewer/vite.config.js`).

**Draw calls.** There are 21: 20 skinned meshes, with the body split into two primitives for two materials. The viewer reports 22 because its ground plane adds one.

## Browser measurements (SwiftShader, not a GPU)

From `tools/inez/browser_perf.py --label container_swiftshader` at 1280×720; the JSON is `qa/technical/performance_container_swiftshader.json`. Each phase averages 6 s after a 1.5 s settle.

| Model | Load to ready (s) | FPS Idle (mean / min) | FPS Walk (mean / min) | Animation CPU (ms/frame) | Render submission (ms/frame) |
|---|---|---|---|---|---|
| `inez_runtime.glb` | 9.6 | 2.30 / 1.97 | 2.00 / 0.98 | 0.26 | 12.9–23.8 |
| `inez_runtime_lod1.glb` | 5.4 | 3.47 / 1.93 | 3.00 / 1.57 | 0.30–0.32 | 5.9–12.5 |
| `inez_runtime_lod2.glb` | 4.0 | 4.41 / 4.20 | 3.81 / 1.83 | 0.31–0.34 | 4.4–8.7 |

**Findings:**

- **Rasterisation dominates here.** Frame time follows triangle count and texture size, because SwiftShader rasterises on the CPU. That is the bottleneck of this machine, not of the asset.
- **Animation is cheap.** Mixer, skeleton, morphs and facial controls cost about 0.3 ms of CPU per frame for 167 joints, 21 morph targets and blended clips. Skinning itself runs in the vertex shader.
- **The animation lab adds about 0.25–0.35 ms per frame** with its overlays off. Its contact measurement runs only while the contact markers are on. It then samples the skinned sole vertices of both boots every frame: about 1,250 per foot on LOD0, whose boots have 10,214 vertices.
- **Earlier, at 1280×900** in the main QA run, LOD0 measured 0.51 FPS while the QA was also capturing frames (`qa/browser_browser_v02.json`).

## What is not measured

- Any GPU, desktop or mobile: frame time, GPU memory actually used, shader compile time.
- WebGPU. The viewer can request it but falls back to WebGL2, and it has not been validated.
- Several characters on screen, or Inez inside the game's own scenes and lighting.
- Network load time from a server. The load times above are from a local Vite server on the same machine.

## Recommendations (not yet acted on)

- **LOD switching.** LOD0 for close and dialogue cameras, then LOD1 and LOD2 with distance (`reports/INEZ_INTEGRATION.md`). Draw calls do not drop with LOD, since every level keeps 21 meshes. If draw calls turn out to matter on the target GPU, merging meshes and materials at LOD2 is the lever.
- **Measure on the slowest supported GPU first.** Then decide whether LOD0's 2048² textures are needed. LOD1's 1024² set cuts estimated texture memory from 85 MB to 23 MB.
