// Runtime material attachment for Inez's digital-human rendering.
//
// A GLB carries standard glTF PBR materials only; custom TSL shaders do not
// survive export. This module rebuilds the special materials after the GLB
// loads, keyed by the glTF material names, and leaves geometry, skinning,
// morph targets and animation untouched (apart from the load-time normal
// correction for the identity layers, see skin/identity-normals.ts).
//
//   const dh = await attachDigitalHuman(gltf.scene, { assetRoot, findBone });
//   dh.setMode('digital' | 'glb'); dh.setDebug('roughness'); dh.setSkin({ microNormal: .3 });
import * as THREE from 'three/webgpu';
import { correctIdentityNormals, type NormalCorrectionReport } from './skin/identity-normals.ts';
import { addSkinRegions, type RegionReport } from './skin/regions.ts';
import { applySkinParams, createSkinMaterial, createSkinUniforms, SKIN_DEFAULTS, type SkinDebugView, type SkinMaterialSet,
  type SkinParams } from './skin/skin-material.ts';

/** glTF material names treated as skin. */
export const SKIN_MATERIALS = ['Inez_Head_Skin_PBR', 'Inez_Skin_Freckles_Pores_Lips_PBR'];

export interface SkinCalibration {
  materials: Record<string, { albedo_gain_linear_rgb: [number, number, number] }>;
  target_skin_albedo_linear_rgb: [number, number, number];
}

export interface AttachOptions {
  assetRoot: string;
  findBone: (root: THREE.Object3D, name: string) => THREE.Object3D | null | undefined;
  /** Recompute identity-layer normals at load (default true). */
  fixNormals?: boolean;
  /** Use the calibrated albedo gain (default true). */
  calibrated?: boolean;
  skin?: Partial<SkinParams>;
}

export interface DigitalHumanAttachment {
  mode: 'digital' | 'glb';
  debug: SkinDebugView;
  skinMeshes: THREE.Mesh[];
  skinSets: Map<string, SkinMaterialSet>;
  params: SkinParams;
  calibration: SkinCalibration | null;
  normalReport: NormalCorrectionReport | null;
  regionReports: RegionReport[];
  tangentsPrecomputed: string[];
  setMode(mode: 'digital' | 'glb'): void;
  setDebug(view: SkinDebugView): void;
  setSkin(params: Partial<SkinParams>): void;
  describe(): Record<string, unknown>;
}

/**
 * Give every normal-mapped mesh a tangent attribute before the first render.
 * Without it, TSL calls geometry.computeTangents() while building the shader,
 * i.e. it adds an attribute to the geometry mid-build. With Inez's quantized,
 * meshopt-decoded (interleaved) runtime GLB on the WebGL2 backend, that
 * corrupted the body's rendering (exploded faces) whenever the GLB's own
 * materials were used. Doing it up front avoids that path. Meshes whose
 * tangents were rebuilt by the identity-normal correction already have them.
 */
export function precomputeTangents(root: THREE.Object3D): string[] {
  const done: string[] = [];
  root.traverse(node => {
    const mesh = node as THREE.Mesh;
    if (!mesh.isMesh) return;
    const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    const geometry = mesh.geometry;
    if (!materials.some(m => (m as THREE.MeshStandardMaterial).normalMap) || geometry.hasAttribute('tangent')) return;
    if (!geometry.index || !geometry.hasAttribute('uv') || !geometry.hasAttribute('normal')) return;
    geometry.computeTangents();
    done.push(mesh.name);
  });
  return done;
}

async function loadJSON<T>(url: string): Promise<T | null> {
  try { const r = await fetch(url, { cache: 'no-store' }); return r.ok ? await r.json() as T : null; } catch { return null; }
}

function loadTexture(url: string): Promise<THREE.Texture> {
  return new Promise((resolve, reject) => new THREE.TextureLoader().load(url, resolve, undefined, reject));
}

export async function attachDigitalHuman(root: THREE.Object3D, options: AttachOptions): Promise<DigitalHumanAttachment> {
  const base = `${options.assetRoot}characters/inez/textures/digital_human/`;
  const [calibration, micro] = await Promise.all([
    loadJSON<SkinCalibration>(`${base}skin_calibration.json`),
    loadTexture(`${base}skin_micro_normal.png`),
  ]);
  micro.colorSpace = THREE.NoColorSpace;
  micro.wrapS = micro.wrapT = THREE.RepeatWrapping;
  micro.anisotropy = 8;
  micro.generateMipmaps = true;
  micro.minFilter = THREE.LinearMipmapLinearFilter;

  const skinMeshes: THREE.Mesh[] = [];
  root.traverse(node => {
    const mesh = node as THREE.Mesh;
    if (mesh.isMesh && !Array.isArray(mesh.material) && SKIN_MATERIALS.includes(mesh.material.name)) skinMeshes.push(mesh);
  });

  // Geometry fixes, once, before the first render.
  const normalReport = options.fixNormals === false ? null : correctIdentityNormals(skinMeshes);
  const tangentsPrecomputed = precomputeTangents(root);
  const eyeL = options.findBone(root, 'eye.L'), eyeR = options.findBone(root, 'eye.R');
  root.updateMatrixWorld(true);
  const regionReports = eyeL && eyeR
    ? addSkinRegions(skinMeshes.filter(m => (m as THREE.SkinnedMesh).isSkinnedMesh) as THREE.SkinnedMesh[],
      eyeL.getWorldPosition(new THREE.Vector3()), eyeR.getWorldPosition(new THREE.Vector3()))
    : [];

  const params: SkinParams = { ...SKIN_DEFAULTS, ...options.skin };
  const originals = new Map<THREE.Mesh, THREE.Material>();
  const skinSets = new Map<string, SkinMaterialSet>();
  for (const mesh of skinMeshes) {
    const source = mesh.material as THREE.MeshStandardMaterial;
    originals.set(mesh, source);
    if (!skinSets.has(source.name)) {
      const gain = options.calibrated === false ? [1, 1, 1] as [number, number, number]
        : calibration?.materials[source.name]?.albedo_gain_linear_rgb ?? [1, 1, 1];
      const materialParams = { ...params, albedoGain: options.skin?.albedoGain ?? gain };
      const uniforms = createSkinUniforms(materialParams);
      skinSets.set(source.name, createSkinMaterial(source, micro, uniforms, materialParams, mesh.geometry.hasAttribute('dhRegion')));
    }
  }

  const attachment: DigitalHumanAttachment = {
    mode: 'digital', debug: 'off', skinMeshes, skinSets, params, calibration, normalReport, regionReports, tangentsPrecomputed,
    setMode(mode) { this.mode = mode; refresh(); },
    setDebug(view) { this.debug = view; refresh(); },
    setSkin(update) {
      Object.assign(this.params, update);
      for (const set of skinSets.values()) {
        const perMaterial = { ...update };
        if (update.albedoGain === undefined) delete perMaterial.albedoGain;
        applySkinParams(set.uniforms, perMaterial, set.material);
      }
    },
    describe() {
      return {
        mode: this.mode, debug: this.debug, skinMeshes: skinMeshes.map(m => m.name),
        materials: [...skinSets.entries()].map(([name, set]) => ({ name, albedoGain: set.uniforms.albedoGain.value.toArray(),
          ior: set.material.ior, specularIntensity: set.material.specularIntensity })),
        normalReport, regionReports, tangentsPrecomputed, calibrationTarget: calibration?.target_skin_albedo_linear_rgb ?? null,
      };
    },
  };
  function refresh() {
    for (const mesh of skinMeshes) {
      const source = originals.get(mesh)!;
      const set = skinSets.get(source.name)!;
      mesh.material = attachment.mode === 'glb' ? source : attachment.debug === 'off' ? set.material : set.debug[attachment.debug];
    }
  }
  refresh();
  return attachment;
}
