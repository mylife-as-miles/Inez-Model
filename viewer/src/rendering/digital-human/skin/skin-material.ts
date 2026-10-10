// Physically based skin material for Inez (milestone 2: the baseline before
// subsurface scattering), built as a TSL node material so the same graph runs
// on WebGPURenderer's WebGPU and WebGL2 backends.
//
// Surface reflection: MeshPhysicalNodeMaterial's GGX microfacet specular with
// a dielectric Fresnel from IOR 1.4, i.e. F0 = ((1.4-1)/(1.4+1))^2 = 0.0278,
// the skin value in GPU Gems 3 ch. 14. Specular colour is white (skin's
// outer layer is a dielectric). Image-based lighting supplies environment
// reflections; the renderer's split-sum keeps the specular energy bounded.
//
// Albedo: the GLB's skin texture times a calibrated per-channel gain
// (tools/inez/dh_skin_calibration.py). A "freckle detail" control scales the
// texture's high frequencies against a low-pass copy (a higher mip level),
// without a separate mask. 1 = exactly as authored.
//
// Roughness: the GLB's roughness map (G channel) with per-region offsets from
// the `dhRegion` vertex masks (T-zone, lips, cheeks, eyelids), clamped to a
// plausible skin range.
//
// Normals: the GLB's normal map blended with a tileable micro-normal
// (pores and furrows, tools/inez/dh_skin_detail.py) by reoriented normal
// mapping. The micro layer fades out with view distance; mipmaps average it
// before that, so it does not shimmer. Its height channel adds a slight
// cavity darkening to the albedo, which fades with it.
import * as THREE from 'three/webgpu';
import { attribute, float, mix, normalMap, positionView, smoothstep, texture, uniform, uv, vec2, vec3, vec4 } from 'three/tsl';
import type { ShaderNodeObject } from 'three/tsl';

type Uniform<T> = ShaderNodeObject<THREE.UniformNode<T>>;
type AnyNode = ShaderNodeObject<THREE.Node>;

export interface SkinParams {
  albedoGain: [number, number, number];
  freckleDetail: number;
  roughnessScale: number;
  roughnessOffset: number;
  tzoneRoughness: number;
  lipsRoughness: number;
  cheeksRoughness: number;
  lidsRoughness: number;
  specularIntensity: number;
  ior: number;
  primaryNormal: number;
  microNormal: number;
  microTiling: [number, number];
  microFadeStart: number;
  microFadeEnd: number;
  cavity: number;
}

// Starting values. Region offsets follow the qualitative finding that the
// nose, forehead and lips are shinier than the cheeks (Weyrich et al. 2006,
// via GPU Gems 3 ch. 14); the exact values are calibration choices, checked
// on renders, not measured data.
export const SKIN_DEFAULTS: SkinParams = {
  albedoGain: [1, 1, 1],
  freckleDetail: 1,
  roughnessScale: 1,
  roughnessOffset: 0,
  tzoneRoughness: -0.12,
  lipsRoughness: -0.16,
  cheeksRoughness: 0.03,
  lidsRoughness: -0.06,
  specularIntensity: 1,
  ior: 1.4,
  primaryNormal: 1,
  microNormal: 0.45,
  // One micro tile is 24 mm of skin; the head UVs span ~0.95 m (U) x 0.48 m (V).
  microTiling: [40, 20],
  microFadeStart: 0.6,
  microFadeEnd: 3.0,
  cavity: 0.18,
};

export type SkinDebugView = 'off' | 'albedo' | 'roughness' | 'normal' | 'regions' | 'micro';

/** Uniforms the lab and quality presets change at runtime. */
export interface SkinUniforms {
  albedoGain: Uniform<THREE.Vector3>;
  freckleDetail: Uniform<number>;
  roughnessScale: Uniform<number>;
  roughnessOffset: Uniform<number>;
  regionRoughness: Uniform<THREE.Vector4>;
  primaryNormal: Uniform<number>;
  microNormal: Uniform<number>;
  microTiling: Uniform<THREE.Vector2>;
  microFade: Uniform<THREE.Vector2>;
  cavity: Uniform<number>;
}

export interface SkinMaterialSet {
  material: THREE.MeshPhysicalNodeMaterial;
  debug: Record<Exclude<SkinDebugView, 'off'>, THREE.MeshBasicNodeMaterial>;
  uniforms: SkinUniforms;
  source: THREE.MeshStandardMaterial;
}

export function createSkinUniforms(params: SkinParams): SkinUniforms {
  return {
    albedoGain: uniform(new THREE.Vector3(...params.albedoGain)),
    freckleDetail: uniform(params.freckleDetail),
    roughnessScale: uniform(params.roughnessScale),
    roughnessOffset: uniform(params.roughnessOffset),
    regionRoughness: uniform(new THREE.Vector4(params.tzoneRoughness, params.lipsRoughness, params.cheeksRoughness, params.lidsRoughness)),
    primaryNormal: uniform(params.primaryNormal),
    microNormal: uniform(params.microNormal),
    microTiling: uniform(new THREE.Vector2(...params.microTiling)),
    microFade: uniform(new THREE.Vector2(params.microFadeStart, params.microFadeEnd)),
    cavity: uniform(params.cavity),
  };
}

export function applySkinParams(uniforms: SkinUniforms, params: Partial<SkinParams>, material?: THREE.MeshPhysicalNodeMaterial): void {
  if (params.albedoGain) uniforms.albedoGain.value.set(...params.albedoGain);
  if (params.freckleDetail !== undefined) uniforms.freckleDetail.value = params.freckleDetail;
  if (params.roughnessScale !== undefined) uniforms.roughnessScale.value = params.roughnessScale;
  if (params.roughnessOffset !== undefined) uniforms.roughnessOffset.value = params.roughnessOffset;
  const r = uniforms.regionRoughness.value;
  if (params.tzoneRoughness !== undefined) r.x = params.tzoneRoughness;
  if (params.lipsRoughness !== undefined) r.y = params.lipsRoughness;
  if (params.cheeksRoughness !== undefined) r.z = params.cheeksRoughness;
  if (params.lidsRoughness !== undefined) r.w = params.lidsRoughness;
  if (params.primaryNormal !== undefined) uniforms.primaryNormal.value = params.primaryNormal;
  if (params.microNormal !== undefined) uniforms.microNormal.value = params.microNormal;
  if (params.microTiling) uniforms.microTiling.value.set(...params.microTiling);
  if (params.microFadeStart !== undefined) uniforms.microFade.value.x = params.microFadeStart;
  if (params.microFadeEnd !== undefined) uniforms.microFade.value.y = params.microFadeEnd;
  if (params.cavity !== undefined) uniforms.cavity.value = params.cavity;
  if (material) {
    if (params.specularIntensity !== undefined) material.specularIntensity = params.specularIntensity;
    if (params.ior !== undefined) material.ior = params.ior;
  }
}

/**
 * Build the skin material set for one GLB skin material. `micro` is the
 * micro-normal texture (RGB normal, A height); `regions` says whether the
 * meshes using it carry the `dhRegion` attribute.
 */
export function createSkinMaterial(source: THREE.MeshStandardMaterial, micro: THREE.Texture, uniforms: SkinUniforms,
  params: SkinParams, regions: boolean): SkinMaterialSet {
  const u = uv();
  const map = source.map;
  // Albedo with freckle-detail control: low-pass = a coarser mip of the same texture.
  const authored: AnyNode = map ? texture(map, u).rgb : vec3(source.color.r, source.color.g, source.color.b);
  const lowPass: AnyNode = map ? texture(map, u).level(float(5)).rgb : authored;
  const detailAlbedo = mix(lowPass, authored, uniforms.freckleDetail);
  // Micro layer, faded with view distance (metres).
  const distance = positionView.z.negate();
  const fade = float(1).sub(smoothstep(uniforms.microFade.x, uniforms.microFade.y, distance));
  const microSample = texture(micro, u.mul(uniforms.microTiling));
  const microHeight = microSample.a;
  const cavityShade = float(1).sub(uniforms.cavity.mul(fade).mul(float(0.5).sub(microHeight).max(0).mul(2)));
  const albedo = detailAlbedo.mul(uniforms.albedoGain).mul(cavityShade);
  // Roughness with region offsets.
  const baseRoughness: AnyNode = source.roughnessMap ? texture(source.roughnessMap, u).g.mul(source.roughness) : float(source.roughness);
  const region: AnyNode = regions ? attribute('dhRegion', 'vec4') : vec4(0, 0, 0, 0);
  const regionOffset = region.dot(uniforms.regionRoughness);
  const roughness = baseRoughness.mul(uniforms.roughnessScale).add(uniforms.roughnessOffset).add(regionOffset).clamp(0.22, 0.9);
  // Normals: primary map (GLB) + micro detail, reoriented normal mapping
  // (Barre-Brisebois & Hill): t = n1 + (0,0,1), u = n2 * (-1,-1,1),
  // r = t * dot(t, u) / t.z - u.
  const primaryTS: AnyNode = source.normalMap ? texture(source.normalMap, u).xyz.mul(2).sub(1) : vec3(0, 0, 1);
  const primaryScale: AnyNode = source.normalScale ? vec2(source.normalScale.x, source.normalScale.y).mul(uniforms.primaryNormal) : vec2(1, 1);
  const n1 = vec3(primaryTS.xy.mul(primaryScale), primaryTS.z).normalize();
  const microTS = microSample.xyz.mul(2).sub(1);
  const n2 = vec3(microTS.xy.mul(uniforms.microNormal.mul(fade)), microTS.z).normalize();
  const t = n1.add(vec3(0, 0, 1));
  const v = n2.mul(vec3(-1, -1, 1));
  const blended = t.mul(t.dot(v)).div(t.z).sub(v).normalize();
  const normalNode = normalMap(blended.mul(0.5).add(0.5));

  const material = new THREE.MeshPhysicalNodeMaterial();
  material.name = `${source.name} (digital human skin)`;
  material.colorNode = albedo;
  material.roughnessNode = roughness;
  material.metalnessNode = float(0);
  material.normalNode = normalNode;
  material.ior = params.ior;
  material.specularIntensity = params.specularIntensity;
  material.specularColor = new THREE.Color(1, 1, 1);
  material.side = source.side;
  material.userData.digitalHuman = 'skin';

  const basic = (colorNode: AnyNode) => {
    const debug = new THREE.MeshBasicNodeMaterial();
    debug.colorNode = colorNode;
    debug.side = source.side;
    debug.userData.digitalHuman = 'skin-debug';
    return debug;
  };
  // Debug views show linear data as stored (the renderer still applies the
  // output transform): albedo, roughness, the view-space shading normal,
  // region masks (R = T-zone, G = lips, B = cheeks + eyelids), micro height.
  const debug = {
    albedo: basic(albedo),
    roughness: basic(vec3(roughness)),
    normal: basic(normalNode.mul(0.5).add(0.5)),
    regions: basic(vec3(region.x, region.y, region.z.add(region.w).min(1))),
    micro: basic(vec3(microHeight.mul(fade).add(float(0.5).mul(float(1).sub(fade))))),
  };
  return { material, debug, uniforms, source };
}
