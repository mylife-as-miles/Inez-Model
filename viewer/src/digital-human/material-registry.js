import * as THREE from 'three';
import { SKIN_DEFAULTS, sanitizeSkinSettings } from './skin/diffusion-profile.js';
import { createSkinMaterial } from './skin/skin-material.js';
import { ScreenSpaceDiffusion } from './skin/screen-space-diffusion.js';
import { thicknessInfo } from './skin/thickness.js';
import { QUALITY_PRESETS, TARGET_LAPTOP } from './quality/quality-presets.js';

const SKIN_NAMES = new Set(['Inez_Head_Skin_PBR', 'Inez_Skin_Freckles_Pores_Lips_PBR']);

export class DigitalHumanRegistry {
  constructor(root, renderer, backend) {
    this.root = root; this.renderer = renderer; this.backend = backend;
    this.settings = { ...SKIN_DEFAULTS }; this.originals = new Map(); this.records = new Map(); this.skinMeshes = [];
    // WebGPURenderer uses nodes even with its WebGL backend; GLSL hooks do not
    // work there. Explicitly keep the original PBR path on either node backend.
    this.supported = Boolean(renderer.isWebGLRenderer && renderer.extensions.has('EXT_color_buffer_float'));
    root.traverse(mesh => {
      if (!mesh.isMesh) return;
      this.originals.set(mesh, mesh.material);
      for (const material of [mesh.material].flat()) {
        if (!mesh.name.includes('ContinuousHumanMesh') || !SKIN_NAMES.has(material.name)) continue;
        this.skinMeshes.push(mesh);
        if (this.supported && !this.records.has(material)) {
          const first = this.records.values().next().value;
          this.records.set(material, createSkinMaterial(material, first?.microMap));
        }
      }
    });
    if (this.supported) {
      this.pipeline = new ScreenSpaceDiffusion(renderer, this);
      for (const record of this.records.values()) record.uniforms.dhVisibleDepth.value = this.pipeline.visibility.depthTexture;
    }
  }
  configure(values = {}) {
    this.settings = sanitizeSkinSettings(this.settings, values);
    for (const record of this.records.values()) {
      record.uniforms.dhRoughnessVariation.value = this.settings.roughnessVariation;
      record.uniforms.dhMicroIntensity.value = this.settings.microNormal;
      record.uniforms.dhThinEnabled.value = this.settings.thinTransmission ? 1 : 0;
    }
    this.pipeline?.configure(this.settings); return { ...this.settings };
  }
  apply(inspection = 'pbr') {
    if (inspection !== 'pbr') return;
    const enhanced = this.supported && this.settings.mode === 'enhanced';
    for (const [mesh, material] of this.originals) {
      const select = source => {
        if (!enhanced || !this.records.has(source)) return source;
        const skin = this.records.get(source).material;
        if (skin.wireframe !== source.wireframe) { skin.wireframe = source.wireframe; skin.needsUpdate = true; }
        return skin;
      };
      mesh.material = Array.isArray(material) ? material.map(select) : select(material);
    }
  }
  setPass(pass) { for (const record of this.records.values()) record.uniforms.dhPass.value = pass; }
  isSkinMaterial(material) { return [...this.records.values()].some(r => r.material === material); }
  updateLight(camera, light) {
    camera.updateMatrixWorld();
    const direction = light.getWorldPosition(new THREE.Vector3()).sub(light.target.getWorldPosition(new THREE.Vector3())).normalize();
    direction.transformDirection(camera.matrixWorldInverse);
    for (const r of this.records.values()) {
      r.uniforms.dhLightDirection.value.copy(direction);
      r.uniforms.dhLightRadiance.value.copy(light.color).multiplyScalar(light.intensity / Math.PI);
    }
  }
  render(scene, camera, inspection) {
    const s = this.settings, active = this.supported && s.mode === 'enhanced' && inspection === 'pbr' && !this.renderer.xr.isPresenting;
    if (active && (QUALITY_PRESETS[s.quality].diffusion || s.debug !== 'off')) {
      this.pipeline.render(scene, camera, (s.sss && s.strength > 0 && QUALITY_PRESETS[s.quality].diffusion) || s.debug !== 'off'); return true;
    }
    return false;
  }
  get diagnostics() {
    const gl = this.renderer.getContext?.(); const debug = gl?.getExtension('WEBGL_debug_renderer_info');
    return { threeRevision: THREE.REVISION, requestedMaterialMode: this.settings.mode, actualBackend: this.backend,
      skinDiffusionSupported: this.supported, activeSkinMeshes: this.skinMeshes.map(m => m.name),
      fallback: this.supported ? null : 'Original PBR: WebGL2 float targets required; no WebGPU diffusion implementation yet',
      renderer: debug ? gl.getParameter(debug.UNMASKED_RENDERER_WEBGL) : null,
      thickness: this.skinMeshes.map(thicknessInfo), settings: { ...this.settings },
      pipeline: this.pipeline?.diagnostics ?? null, targetHardware: TARGET_LAPTOP,
      shaderFailures: (this.renderer.info.programs ?? []).filter(p => p.diagnostics?.runnable === false).map(p => p.diagnostics),
      limitations: ['Visible-surface screen-space diffusion; offscreen/backside irradiance unavailable',
        'Compact radial Gaussian cubature; not a full multilayer skin simulation',
        'Rest-pose geometric thickness follows vertices; no animated thickness recomputation',
        'WebGPU keeps original PBR; its SSS is unavailable', 'No target GPU performance measured here'] };
  }
}
