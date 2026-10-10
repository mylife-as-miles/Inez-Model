# Inez digital-human rendering: research notes

What was studied, what it says, and how each technique maps onto the installed renderer: three.js **0.180.0**, `WebGPURenderer` with TSL node materials.

## Sources actually read in this work

| Source | How it was read | Used for |
|---|---|---|
| d'Eon & Luebke, *Advanced Techniques for Realistic Real-Time Skin Rendering*, GPU Gems 3 ch. 14 (NVIDIA) | Chapter text, first ~100k characters, via fetch | Specular model, skin F0, diffusion profiles, texture-space diffusion, translucent shadow maps, pre/post-scatter texturing |
| Epic Games, *Digital Humans* (Unreal Engine 4.27 docs) | Page text via fetch | Eye structure and parameters, dual-lobe skin specular, cavity, edge roughness for fuzz, hair shading paths |
| three.js 0.180.0 source in `viewer/node_modules/three` | Read directly | Every API used: `NormalMapNode`, tangent frames, `PMREMGenerator.fromSceneAsync`, tone-mapping constants, `MeshSSSNodeMaterial`, `PostProcessing`, `DepthOfFieldNode` |

The three.js documentation pages and the Pixar RenderMan head page listed in the brief were **not** fetched; the installed source is the authority for API behaviour. The Pixar page is still to be read before the micro-detail and fuzz passes.

## What the sources establish

### Skin (GPU Gems 3 ch. 14)

**Specular.**

- Physically based: Kelemen/Szirmay-Kalos BRDF with a Beckmann distribution and Schlick Fresnel evaluated with the half vector.
- **F0 = 0.028**, from an index of refraction of 1.4.
- The specular colour is white, because skin's outer layer is a dielectric.
- Roughness m and intensity ρs vary over the face. The chapter cites Weyrich et al. 2006 (ten regions, 149 faces); lips and nose are shinier. The numbers are in figures, not the text.

**Diffusion.**

- Skin is modelled with a sum of **six Gaussians**. All three colour channels share the same variances, with per-channel weights that sum to 1 in each channel, so the albedo map alone sets the colour.
- The fit itself is printed in Figure 14-13. `viewer/src/rendering/digital-human/skin/profiles.ts` carries the published values, and a unit test checks that each channel sums to 1.000.
- The chapter says fewer Gaussians "will likely suffice" for most real-time characters, and that SSS can be scaled down with distance.

**Texture-space diffusion.** Per frame:

1. Shadow maps.
2. A stretch map, either precomputed or from screen-space derivatives (1/length per U and V).
3. Irradiance rendered into UV space.
4. Five separable U/V blurs, using a 7-tap kernel {0.006, 0.061, 0.242, 0.383, 0.242, 0.061, 0.006} whose spacing is scaled by each Gaussian's width and by the stretch.
5. A final pass that combines the irradiance textures with the profile weights and adds specular.

That is 84 texture reads per texel, instead of 4,096 for a direct 64×64 blur.

**Albedo placement.**

- Pre-scatter: albedo applied before blurring, which softens detail.
- Post-scatter: profiles normalised to white, albedo applied after, which keeps detail but gives no colour bleeding.
- Mixed: `pow(albedo, mix)` before and `pow(albedo, 1 − mix)` after, with **mix = 0.5** as the most plausible.

**Thin regions (ears).** Translucent shadow maps:

- They store depth plus the light-facing surface's UV.
- Thickness is kept as exp(−20·d) and blurred along with the irradiance.
- Normal-aware correction prevents double counting.

**Energy conservation.** Diffuse light is scaled by the energy the specular lobe leaves, a precomputed ρdt(N·L, m) table. Silhouettes otherwise look too bright.

### Eyes (Epic)

- **Structure:**
  - a wet sclera;
  - a dark limbus ring between iris and sclera;
  - the iris under a clear, fluid-filled cornea, with **refraction done in the shader** rather than with a separate shell;
  - pupil scale for dilation;
  - lacrimal-fluid geometry under the lower lid;
  - eyelid contact shadow (a thin occlusion mesh or contact shadows).
- **Parameters:** depth scale (iris depth under the cornea), the IOR of the fluid under the cornea, iris concavity (caustics), limbus width and darkness. **The page gives no numeric values** for IOR, depth or limbus. The brief's corneal IOR of 1.376 is the physiological value and the starting point.

### Skin details (Epic)

- **Two specular lobes**, a soft one and a tight one, mixed.
- **Cavity** acts as specular occlusion and is reduced at Fresnel edges.
- **Micro normals** carry pores; meso normals carry wrinkles and are pose-driven.
- **Edge roughness** of 0.25, applied through a Fresnel term, approximates peach fuzz.
- **Transmission** uses shadow-map depth, exponential falloff and a Henyey-Greenstein phase function.

### Hair (Epic)

- **Model:** d'Eon/Marschner/Hanika-based, with R (primary highlight), TT (transmission) and TRT (secondary, coloured highlight).
- **Strand variation:** per-strand variation of colour, roughness and tangent ("scraggle").
- **Geometry:** cards or strips with depth offset at the hairline.
- **Fuzz:** shaded as translucent emissive, not with the hair model.

## Mapping onto three.js 0.180 (WebGPURenderer + TSL)

| Technique | Status in this renderer | Plan |
|---|---|---|
| Microfacet specular, Fresnel, IOR-derived F0 | **Supported.** `MeshPhysicalNodeMaterial`: GGX distribution (not Beckmann), Schlick Fresnel, `ior` sets F0, split-sum IBL from a PMREM | Used in milestone 2, with IOR 1.4 (F0 0.0278) and white specular |
| Spatially varying roughness | **Supported** (`roughnessNode`) | Regions from the rig's facial bone weights plus a geometric T-zone (milestone 2) |
| Dual specular lobes | **Custom** (second lobe added in a custom lighting model) | Evaluate in milestone 3 |
| Diffuse energy conservation (ρdt) | Partial. three's physical material has specular multi-scattering compensation. Diffuse attenuation by the specular albedo is not verified here. | Check on grazing-angle renders before adding a ρdt term |
| Texture-space diffusion | **Custom.** It needs the skinned, morphed mesh lit and rasterised in UV space, plus 2 × N blur passes in render targets per character. TSL can express each pass, but there is no built-in path. | Prototype and benchmark against screen-space diffusion (milestone 3) |
| Screen-space diffusion (skin-masked, depth- and normal-aware) | **Custom.** It needs a diffuse-only skin buffer (MRT), a skin mask, and separable blurs whose width scales with depth. The `PostProcessing` and `pass`/`mrt` nodes exist. | Prototype and benchmark (milestone 3) |
| Thin-region transmission | **Partly supported.** `MeshSSSNodeMaterial` implements the fast thickness-map translucency approximation (Barré-Brisebois/Bouchard), which is not shadow-aware. Shadow-aware transmission (translucent shadow maps) is custom. | Thickness-map transmission for the ears first, then judge whether shadow-awareness is needed |
| Micro and meso detail | **Supported** through node texture sampling and `normalMap`. Blending the two layers is custom TSL (reoriented normal mapping). | Done in milestone 2: procedural tileable micro-normal, distance fade, mipmaps |
| Eye refraction | **Custom** integrated eye shader (view ray refracted at the cornea, iris parallax). A transmissive cornea (`transmission` on the physical material) is supported but costs a screen-space transmission pass and sorting. | Compare both (milestone 4) |
| Hair: anisotropic, R/TT/TRT | **Custom** lighting model in TSL. It needs per-strand tangents: Inez's hair is a sculpted shell with **no strand directions**, so a direction map or new cards are a prerequisite. | Milestone 5: an honest prerequisite first |
| Peach fuzz | **Supported as a BRDF approximation.** `sheen` (Charlie sheen) or an edge-roughness Fresnel term. Fibre geometry is custom. | Milestone 6: BRDF first, geometry only if close-ups need the silhouette |
| Physical depth of field | `dof()` TSL node (`examples/jsm/tsl/display/DepthOfFieldNode.js`) with `focusDistance`, `focalLength`, `bokehScale`. Its parameters are not physical lens units, so a thin-lens circle of confusion must be mapped onto them. | Milestone 7 |
| Colour management | **Supported.** Linear working space, sRGB output, per-texture colour spaces, Neutral/AgX/ACES tone mapping, one output transform | Done in milestone 2 (Khronos PBR Neutral by default) |
| WebGPU | Available in this Chromium through SwiftShader, but **the device is lost on first use, even for a single sphere**, headless or headed. The WebGL2 backend of the same renderer works. | All verification here is on the WebGL2 backend. WebGPU must be tested on real hardware before it is claimed. |

## Unsuitable for real-time gameplay (as described in the sources)

- **Full six-Gaussian texture-space diffusion at high resolution per character per frame.** The chapter's demo used most of a GeForce 8800 Ultra. It is acceptable for close-up cinematic shots with one character. Gameplay and VR need reduced profiles (3–4 Gaussians) or screen-space diffusion with distance LOD.
- **Translucent shadow maps per light.** These need an extra depth-plus-UV map per light. Reserve them for the cinematic preset, if at all.
- **Strand hair** with tens of thousands of strands. Cards with good direction data are the gameplay path.
- **Geometric peach fuzz beyond close-up distance.** Fade it to the BRDF approximation.

## What this project adds that the sources do not cover

- **Load-time normal correction for Inez's identity layers.** glTF sums morph-normal deltas linearly, which is wrong for her large identity layers (up to 156° on some vertices). This is specific to this asset and is fixed in `skin/identity-normals.ts`.
- **Albedo calibration from the original images.** The skin colour target comes from skin chroma and the skin-to-knit luminance ratio measured in the originals (`tools/inez/dh_skin_calibration.py`), not from a generic skin chart. Inez's identity is defined by those images.
