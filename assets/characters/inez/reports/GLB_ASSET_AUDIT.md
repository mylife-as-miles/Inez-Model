# GLB asset audit — the two existing Inez models

Audited 2026-10-09 from the user's Google Drive folder. Both files were
downloaded through Drive's public download endpoint (the Google Drive
connector is not connected in this session), stored untouched and made
read-only:

| | Asset A | Asset B |
|---|---|---|
| Drive name | `Inez.glb` | `Inez Facial Model.glb` |
| Drive file ID | `1prurZ-_3T0e-wnxkppRQN51YaiHXauQH` | `1nYEuqUYS6lRgunQ2czGgqAfXEA4kX0VT` |
| Stored at | `source/asset_a/Inez.glb` | `source/asset_b/Inez Facial Model.glb` |
| Bytes | 69,695,372 | 67,019,772 |
| SHA-256 | `bffc329efed868f02f72ec7479c526bd47f812cb8a119dd9cc1964308beb34c7` | `c3515428bde9d9ec34437135cc31caad872cf425e93c500731b8bbf81630c150` |

Paths are relative to `assets/characters/inez/`. Machine-readable results:
`reports/glb_asset_audit.json`, produced by `tools/inez/glb_audit.py`. Renders:
`renders/source_audit/asset_a|asset_b/`, produced by `tools/inez/glb_render.py`.
Both tools read the files without modifying them.

## Binary validity

Both files are genuine binary glTF 2.0 containers: magic `glTF`, version 2,
declared length equal to the file size, then a JSON chunk and a BIN chunk.
Drive reports Asset B as `text/plain`, but the download served
`application/octet-stream` with the `.glb` filename, and the header and
structure check out. It is not an HTML download page.

## Structure

| Property | Asset A | Asset B |
|---|---|---|
| Generator | Tripo (AI image-to-3D) | Tripo (AI image-to-3D) |
| Extensions declared | none | `KHR_materials_volume`, `FB_ngon_encoding` (declared, not used by the material) |
| Hierarchy | 1 scene → 1 node → 1 mesh → 1 primitive | same |
| Vertices / triangles | 1,081,995 / 1,955,177 | 987,311 / 1,865,603 |
| Welded vertices (seams merged) | 977,485 | 932,496 |
| Separate shells | 1: body, clothes, boots and hair fused into one surface | 1: head, hair, ponytail and sweater bust fused |
| Open boundary edges / non-manifold edges / degenerate triangles | 2 / 8 / 0 | 5 / 11 / 0 |
| Materials | 1 (`tripo_mat_…`) | 1 (`tripo_material_…`) |
| Textures | base colour (JPEG), metallic-roughness (JPEG), normal (PNG), all 4096×4096 | same, all 4096×4096 |
| UV sets | `TEXCOORD_0` only; AI-packed atlas of hundreds of small islands, about 63% of texture area used | `TEXCOORD_0`; same kind of atlas, about 52% used |
| Normal map content | nearly flat: 5th–95th percentile within ±0.015 of (0.5, 0.5, 1) | nearly flat: same range |
| Metallic-roughness | G (roughness) mean 0.77, 5th–95th percentile 0.42–0.91; B (metal) mean 0.06; R is 1.0 | roughness mean 0.76, 0.59–0.97; metal mean 0.04 |
| Skeleton / skin weights | none / none | none / none |
| Morph targets | none | none |
| Animations | none | none |

## Scale, units and orientation

Both models are normalised to about one unit tall. The units have no real-world
meaning.

- **Asset A:** extent 0.389 × 0.979 × 0.177. Full standing figure in an A-pose,
  feet at y = 0, facing glTF +Z (Blender −Y).
- **Asset B:** extent 0.493 × 0.980 × 0.826. A head-and-shoulders bust, rotated
  90° about the vertical axis, facing glTF −X (Blender −X). Its "front"
  renders need a −90° yaw.

Neither file encodes a physical height. Production scales them to Inez's
reference height of 1.70 m barefoot, plus the platform soles.

## Completeness (from the renders, not filenames)

### Asset A: full model

- Complete body in an A-pose.
- Cropped grey knit sweater with dark stripes, showing the midriff.
- Loose dark jeans with front and back pockets, gathered at the boots.
- Black lace-up platform combat boots.
- Thin necklace.
- Hair worn down: light-brown, stringy wavy strands, with a low loose tail at
  the back.
- The face is present but small relative to the full figure.

### Asset B: facial model

- Head, neck and upper chest in a navy-striped sweater; no arms or legs.
- Curly medium-brown hair pulled back into a high curly ponytail, with
  face-framing curls and baby hairs.
- Thin necklace.
- Eyes, lids, brows and lips are sculpted into the single surface.

### Both assets

- Hair is a solid sculpted mass fused to the scalp. There are no hair cards and
  no strands.
- Eyes are not separate objects: the eyeball surface is continuous with the
  lids.
- The mouth is closed into one surface. There is no mouth interior, teeth or
  tongue.
- The base colour contains baked lighting: highlights on the hair, and soft
  shading on the skin and folds.

## Can either be animated as delivered?

No. Neither file has a skeleton, skin weights or blendshapes. Their topology is
a uniform AI triangle soup of about 2 million triangles with no edge loops.
Fused lids, mouth and hair cannot deform for blinks, a jaw opening, visemes or
ponytail motion. Joints would also smear the dense triangulation.

Animation requires a retopology/transfer step. INEZ_MODEL_COMPARISON.md
describes that strategy.

## Renders

Rendered with Blender 4.3.2 Cycles from the imported GLB as delivered. Each
image has its asset and view label rendered into the frame.

| View | Asset A | Asset B |
|---|---|---|
| Face front / three-quarter / left / right | `face_front.png`, `face_three_quarter.png`, `face_left.png`, `face_right.png` | same names |
| Full body front / back / left / right / three-quarter | `body_*.png` | bust only (`body_*.png`) |
| Wireframe | `wire_face_front.png`, `wire_torso_front.png` | same names |
| Material inspection | `material_basecolor_face.png`, `material_basecolor_body.png`, `material_clay_normalmap_face.png`, `material_clay_geometry_face.png`, `material_clay_geometry_body.png` | same names |

`material_roughness_face.png` shows the metallic-roughness texture's green
channel (roughness) as unlit grey.

- **Asset A:** blotchy roughness. Atlas-island squares are visible around the
  eyes and cheeks, and the eye region is a dark, glossy smear.
- **Asset B:** clean roughness. Skin is mid-grey (about 0.55–0.65), lips and
  eyes are glossier, and hair and knit are near 0.9.
