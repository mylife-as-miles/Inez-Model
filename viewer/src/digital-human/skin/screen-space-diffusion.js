import * as THREE from 'three';
import { SKIN_PROFILE } from './diffusion-profile.js';
import { QUALITY_PRESETS } from '../quality/quality-presets.js';
import { debugModeIndex } from './skin-debug.js';
import { FullScreenQuad } from 'three/addons/postprocessing/Pass.js';

const fragment = /* glsl */`
uniform sampler2D beautyMap, diffuseMap, normalMap, depthMap;
uniform vec2 projectionScale;
uniform float cameraNear, cameraFar, perspectiveCamera, diffusionRadius, diffusionStrength, debugMode;
uniform float variances[6]; uniform vec3 profileWeights[6];
varying vec2 vUv;
#include <common>
#include <packing>
float distanceAt(vec2 uv) {
  float d=texture2D(depthMap,uv).x;
  return perspectiveCamera>.5 ? -perspectiveDepthToViewZ(d,cameraNear,cameraFar) : -orthographicDepthToViewZ(d,cameraNear,cameraFar);
}
void main() {
  vec4 original=texture2D(beautyMap,vUv), center=texture2D(diffuseMap,vUv);
  if(center.a<.99 || (diffusionStrength<.000001 && debugMode<.5)) {gl_FragColor=original;}
  else {
    vec4 nData=texture2D(normalMap,vUv);
    vec3 n=normalize(nData.xyz*2.0-1.0);
    float z=distanceAt(vUv), projectionDistance=perspectiveCamera>.5 ? max(z,.01) : 1.0;
    vec3 scattered=vec3(0.0);
    // Each normalized Gaussian is integrated with center + a symmetric
    // radial cubature ring (second moment = 2*sigma²). Sum the six results
    // per RGB channel. This is intentionally a compact diffusion prototype,
    // not the chapter's complete texture-space/translucent-shadow-map system.
    for(int l=0;l<6;l++) {
      float sigma=sqrt(variances[l])*diffusionRadius*.001;
      float ringRadius=sqrt(3.0)*sigma;
      vec3 sum=center.rgb/3.0; float norm=1.0/3.0;
      for(int k=0;k<DH_DIRECTIONS;k++) {
        float angle=6.28318530718*(float(k)+float(l)*.37)/float(DH_DIRECTIONS);
        vec2 worldOffset=vec2(cos(angle),sin(angle))*ringRadius;
        vec2 uv=vUv+worldOffset*projectionScale/projectionDistance;
        vec4 sampleDiffuse=texture2D(diffuseMap,uv);
        vec3 sn=normalize(texture2D(normalMap,uv).xyz*2.0-1.0);
        float planeDepth=z+dot(n.xy,worldOffset)/max(abs(n.z),.15)*sign(n.z);
        float depthGate=exp(-abs(distanceAt(uv)-planeDepth)/max(.0008,ringRadius*.4));
        float normalGate=smoothstep(.55,.98,dot(n,sn));
        float bounds=step(0.0,uv.x)*step(uv.x,1.0)*step(0.0,uv.y)*step(uv.y,1.0);
        float w=(2.0/3.0)/float(DH_DIRECTIONS)*step(.99,sampleDiffuse.a)*depthGate*normalGate*bounds;
        sum+=sampleDiffuse.rgb*w;norm+=w;
      }
      scattered+=sum/max(norm,.0001)*profileWeights[l];
    }
    // Only diffuse is replaced. The beauty residual includes sharp GGX
    // specular, corneas, eyes, hair and clothing unchanged.
    vec3 color=original.rgb-center.rgb+mix(center.rgb,scattered,diffusionStrength);
    if(debugMode>.5 && debugMode<1.5) color=center.rgb;
    if(debugMode>1.5 && debugMode<2.5) color=scattered;
    if(debugMode>2.5 && debugMode<3.5) color=nData.rgb;
    if(debugMode>3.5) color=mix(vec3(.1,.35,.9),vec3(1.0,.25,.05),nData.a);
    gl_FragColor=vec4(max(color,vec3(0)),original.a);
  }
  // Three's Color background clears are encoded but not tone mapped.
  // Keep the backdrop identical to the direct PBR path.
  if(texture2D(depthMap,vUv).x<.999999) {
    #include <tonemapping_fragment>
  }
  #include <colorspace_fragment>
}
`;

export class ScreenSpaceDiffusion {
  constructor(renderer, registry) {
    this.renderer = renderer; this.registry = registry; this.size = new THREE.Vector2();
    this.beauty = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType, depthBuffer: true });
    this.beauty.samples = Math.min(4, renderer.capabilities.maxSamples);
    this.beauty.resolveDepthBuffer = true;
    this.beauty.depthTexture = new THREE.DepthTexture(1, 1, THREE.UnsignedIntType);
    // Match g-buffer fragment centers without MSAA depth subsample bias.
    this.visibility = new THREE.WebGLRenderTarget(1,1,{type:THREE.UnsignedByteType});
    this.visibility.depthTexture = new THREE.DepthTexture(1,1,THREE.UnsignedIntType);
    this.diffuse = new THREE.WebGLRenderTarget(1, 1, { type: THREE.HalfFloatType });
    this.normal = new THREE.WebGLRenderTarget(1, 1, { type: THREE.UnsignedByteType });
    for (const target of [this.beauty, this.visibility, this.diffuse, this.normal]) {
      target.texture.colorSpace = THREE.NoColorSpace; target.texture.minFilter = target.texture.magFilter = THREE.LinearFilter;
      target.texture.generateMipmaps = false;
    }
    this.beauty.depthTexture.minFilter = this.beauty.depthTexture.magFilter = THREE.NearestFilter;
    this.visibility.depthTexture.minFilter = this.visibility.depthTexture.magFilter = THREE.NearestFilter;
    this.uniforms = { beautyMap: { value: this.beauty.texture }, diffuseMap: { value: this.diffuse.texture },
      normalMap: { value: this.normal.texture }, depthMap: { value: this.beauty.depthTexture },
      projectionScale: { value: new THREE.Vector2() }, cameraNear: { value: .005 }, cameraFar: { value: 100 },
      perspectiveCamera: { value: 0 }, diffusionRadius: { value: 1 }, diffusionStrength: { value: .55 }, debugMode: { value: 0 },
      variances: { value: SKIN_PROFILE.map(p => p.variance) }, profileWeights: { value: SKIN_PROFILE.map(p => new THREE.Vector3(...p.rgb)) } };
    this.material = new THREE.ShaderMaterial({ uniforms: this.uniforms, defines: { DH_DIRECTIONS: 4 }, depthTest: false, depthWrite: false,
      vertexShader: 'varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.0,1.0);}', fragmentShader: fragment });
    this.quad = new FullScreenQuad(this.material); this.occluders = new Map(); this.lastTimings = {};
  }

  configure(settings) {
    const preset = QUALITY_PRESETS[settings.quality];
    if (this.material.defines.DH_DIRECTIONS !== preset.directions) {
      this.material.defines.DH_DIRECTIONS = preset.directions; this.material.needsUpdate = true;
    }
    this.uniforms.diffusionRadius.value = settings.radius;
    this.uniforms.diffusionStrength.value = settings.sss && preset.diffusion ? settings.strength : 0;
    this.uniforms.debugMode.value = debugModeIndex(settings.debug);
  }

  occluder(material) {
    if (!this.occluders.has(material)) {
      const copy = material.clone(); copy.colorWrite = false;
      // Preserve the source depth/alpha behavior, including corneal BLEND.
      this.occluders.set(material, copy);
    }
    return this.occluders.get(material);
  }

  render(scene, camera, layers = true) {
    const r = this.renderer, backup = { target: r.getRenderTarget(), autoReset: r.info.autoReset,
      background: scene.background, color: r.getClearColor(new THREE.Color()), alpha: r.getClearAlpha(),
      shadows: r.shadowMap.autoUpdate, autoClear: r.autoClear };
    const size = r.getDrawingBufferSize(new THREE.Vector2());
    for (const record of this.registry.records.values()) record.uniforms.dhBufferSize.value.copy(size);
    if (!this.size.equals(size)) {
      this.size.copy(size); for (const t of [this.beauty, this.visibility, this.diffuse, this.normal]) t.setSize(size.x, size.y);
    }
    this.uniforms.projectionScale.value.set(Math.abs(camera.projectionMatrix.elements[0]) * .5, Math.abs(camera.projectionMatrix.elements[5]) * .5);
    this.uniforms.cameraNear.value = camera.near; this.uniforms.cameraFar.value = camera.far;
    this.uniforms.perspectiveCamera.value = camera.isPerspectiveCamera ? 1 : 0;
    const originals = new Map(), visibility = new Map();
    try {
      r.info.autoReset = false; r.info.reset(); r.autoClear = true;
      this.registry.setPass(0);
      const start = performance.now(); r.setRenderTarget(this.beauty); r.render(scene, camera); const beautyEnd = performance.now();
      if (!layers) {
        r.setRenderTarget(backup.target); this.quad.render(r);
        this.lastTimings = { beauty_submit_ms: beautyEnd-start, total_submit_ms: performance.now()-start,
          gpu_ms: null, scene_passes: 1, diffusion_submit_ms: 0, timer_label: 'CPU command submission; not GPU execution time' };
        return;
      }
      r.shadowMap.autoUpdate = false; scene.background = null; r.setClearColor(0, 0);
      scene.traverse(mesh => {
        // Lab skeleton/contact lines, sprites and point gizmos are display
        // overlays, not scattering surfaces. They remain in the beauty pass.
        if (mesh.isLine || mesh.isPoints || mesh.isSprite) { visibility.set(mesh, mesh.visible); mesh.visible = false; }
        if (!mesh.isMesh) return;
        originals.set(mesh, mesh.material);
        mesh.material = Array.isArray(mesh.material) ? mesh.material.map(m=>this.occluder(m)) : this.occluder(mesh.material);
      });
      r.setRenderTarget(this.visibility);r.clear();r.render(scene,camera);const visibilityEnd=performance.now();
      for(const [mesh,material] of originals) {
        const select = material => this.registry.isSkinMaterial(material) ? material : this.occluder(material);
        mesh.material = Array.isArray(material) ? material.map(select) : select(material);
      }
      this.registry.setPass(1); r.setRenderTarget(this.diffuse); r.clear(); r.render(scene, camera); const diffuseEnd = performance.now();
      this.registry.setPass(2); r.setRenderTarget(this.normal); r.clear(); r.render(scene, camera); const normalEnd = performance.now();
      r.setRenderTarget(backup.target); this.quad.render(r); const end = performance.now();
      this.lastTimings = { beauty_submit_ms: beautyEnd - start, visibility_submit_ms: visibilityEnd-beautyEnd, diffuse_submit_ms: diffuseEnd - visibilityEnd,
        normals_submit_ms: normalEnd - diffuseEnd, diffusion_submit_ms: end - normalEnd, total_submit_ms: end - start,
        gpu_ms: null, scene_passes: 4, timer_label: 'CPU command submission; not GPU execution time' };
    } finally {
      for (const [mesh, material] of originals) mesh.material = material;
      for (const [object, visible] of visibility) object.visible = visible;
      this.registry.setPass(0); scene.background = backup.background;
      r.setRenderTarget(backup.target); r.setClearColor(backup.color, backup.alpha);
      r.shadowMap.autoUpdate = backup.shadows; r.autoClear = backup.autoClear; r.info.autoReset = backup.autoReset;
    }
  }

  get diagnostics() {
    return { size: this.size.toArray(), scenePasses: this.lastTimings.scene_passes ?? 0, diffusionPasses: 1,
      neighborSamples: 6 * this.material.defines.DH_DIRECTIONS,
      beautySamples: this.beauty.samples,
      estimated_target_bytes: this.size.x * this.size.y * (40 + 12 * this.beauty.samples),
      memory_note: 'texture/depth allocation estimate, excludes driver overhead and asset textures', timings: this.lastTimings };
  }
  dispose() {
    for (const t of [this.beauty, this.visibility, this.diffuse, this.normal]) t.dispose();
    for (const m of this.occluders.values()) m.dispose(); this.material.dispose(); this.quad.dispose();
  }
}
