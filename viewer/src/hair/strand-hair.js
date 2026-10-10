// Strand hair: thousands of ribbons deformed on the GPU by simulated guides.
//
// The GLB carries two LINES primitives (tools/inez/hair/build_strand_hair.py):
//   Inez_Hair_Guides   K points per guide, skinned (head, hair.01-04), with
//                      _HAIR_FREE (0 pinned to the scalp .. 1 free) and
//                      _HAIR_REF (the guide root's scalp normal)
//   Inez_Hair_Strands  every strand point with _HAIR_GUIDE, _HAIR_GS (guide
//                      parameter), _HAIR_U (root 0 .. tip 1), _HAIR_STRAND,
//                      _HAIR_OFFSET and _HAIR_TANGENT (in the guide's frame),
//                      _HAIR_AO and _HAIR_RADIUS.
// Each frame the guides are skinned on the CPU, the per-guide XPBD chains
// (card-solver.js) add inertia, gravity and collisions, and the guide
// positions and frames go to a float texture. The vertex shader rebuilds every
// strand point from its guide (the same frame construction the build tool
// used, so the rest pose is exact) and expands it into a camera-facing ribbon
// at least one pixel wide, with coverage = true width / drawn width for
// alpha-to-coverage. Shading is Kajiya-Kay with two shifted lobes under the
// scene's directional and hemisphere lights.
import * as THREE from 'three';
import { CardChainSolver } from './card-solver.js';

const VERT = /* glsl */`
uniform sampler2D guideTex;
uniform float K;
uniform vec2 resolution;
uniform float rootWidth;
uniform float tipWidth;
attribute vec4 aGuide;     // guide index, guide parameter, strand u, ribbon side (-1 / 1)
attribute vec3 aOffset;
attribute vec3 aTangent;
attribute vec3 aMisc;      // strand index, occlusion, radius taper
varying vec3 vTangent;
varying vec3 vViewPos;
varying float vAO;
varying float vU;
varying float vCoverage;
varying float vRand;
vec3 qrot(vec4 q, vec3 v) { vec3 c = cross(q.xyz, v); return v + 2.0 * (q.w * c + cross(q.xyz, c)); }
vec4 fetchTexel(int x, int y) { return texelFetch(guideTex, ivec2(x, y), 0); }
float hash(float n) { return fract(sin(n * 12.9898) * 43758.5453); }
void main() {
  int g = int(aGuide.x + 0.5);
  float s = clamp(aGuide.y, 0.0, 1.0) * (K - 1.0);
  int k0 = int(min(floor(s), K - 2.0));
  float t = s - float(k0);
  vec3 p0 = fetchTexel(2 * k0, g).xyz, p1 = fetchTexel(2 * k0 + 2, g).xyz;
  vec4 q0 = fetchTexel(2 * k0 + 1, g), q1 = fetchTexel(2 * k0 + 3, g);
  vec4 q = normalize(mix(q0, q1, t));
  vec3 world = mix(p0, p1, t) + qrot(q, aOffset);
  vec3 tangent = normalize(qrot(q, aTangent));
  vec4 view = viewMatrix * vec4(world, 1.0);
  vec3 tv = normalize((viewMatrix * vec4(tangent, 0.0)).xyz);
  vec3 toEye = projectionMatrix[2][3] == 0.0 ? vec3(0.0, 0.0, 1.0) : normalize(-view.xyz);
  vec3 side = cross(tv, toEye);
  side = length(side) > 1e-5 ? normalize(side) : vec3(1.0, 0.0, 0.0);
  // MainHair's thickness taper reaches zero at 70 % of the strand; at real-time
  // scale that erases the tips, so it only modulates the width mildly here.
  float width = mix(rootWidth, tipWidth, aGuide.z) * (0.65 + 0.35 * aMisc.z);
  float pixel = (projectionMatrix[2][3] == 0.0 ? 1.0 : -view.z) * 2.0 / (projectionMatrix[1][1] * resolution.y);
  float drawn = max(width, pixel);
  vCoverage = clamp(width / drawn, 0.0, 1.0);
  view.xyz += side * aGuide.w * 0.5 * drawn;
  vTangent = tv; vViewPos = view.xyz; vAO = aMisc.y; vU = aGuide.z; vRand = hash(aMisc.x);
  gl_Position = projectionMatrix * view;
}`;

const FRAG = /* glsl */`
#include <common>
#include <lights_pars_begin>
uniform vec3 rootColor;
uniform vec3 tipColor;
uniform vec3 specColor;
uniform float variation;
uniform float coverageGain;
uniform float specR;
uniform float specTRT;
uniform float expR;
uniform float expTRT;
varying vec3 vTangent;
varying vec3 vViewPos;
varying float vAO;
varying float vU;
varying float vCoverage;
varying float vRand;
float strandSpec(vec3 T, vec3 H, float e) { float th = dot(T, H); return pow(sqrt(max(0.0, 1.0 - th * th)), e); }
void main() {
  vec3 T = normalize(vTangent);
  vec3 V = isOrthographic ? vec3(0.0, 0.0, 1.0) : normalize(-vViewPos);
  vec3 N = normalize(V - T * dot(V, T));
  vec3 albedo = mix(rootColor, tipColor, smoothstep(0.0, 0.35, vU));
  albedo *= 1.0 + variation * (vRand - 0.5) * 2.0;
  albedo = mix(albedo, albedo * vec3(1.08, 0.97, 0.9), step(0.85, vRand) * 0.6);   // a few warmer strands
  vec3 color = vec3(0.0);
  #if NUM_DIR_LIGHTS > 0
  for (int i = 0; i < NUM_DIR_LIGHTS; i++) {
    vec3 L = directionalLights[i].direction;
    vec3 Lc = directionalLights[i].color;
    float tl = dot(T, L);
    float diffuse = mix(0.3, 1.0, sqrt(max(0.0, 1.0 - tl * tl))) * clamp(dot(N, L) * 0.5 + 0.5, 0.0, 1.0);
    vec3 H = normalize(L + V);
    float r = strandSpec(normalize(T + N * -0.06), H, expR);                          // primary (white) lobe
    float trt = strandSpec(normalize(T + N * 0.10), H, expTRT) * (0.5 + 0.5 * vRand);  // secondary (coloured) lobe
    color += Lc * (albedo * RECIPROCAL_PI * diffuse + specColor * r * specR + albedo * trt * specTRT);
  }
  #endif
  vec3 ambient = ambientLightColor;
  #if NUM_HEMI_LIGHTS > 0
  for (int i = 0; i < NUM_HEMI_LIGHTS; i++) ambient += getHemisphereLightIrradiance(hemisphereLights[i], N);
  #endif
  color += ambient * albedo * RECIPROCAL_PI;
  color *= vAO;
  gl_FragColor = vec4(color, clamp(vCoverage * coverageGain, 0.0, 1.0));
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
}`;

const _v = new THREE.Vector3(), _m = new THREE.Matrix4(), _q = new THREE.Quaternion();

export class StrandHairRuntime {
  constructor({ guides, strands, skinnedMesh, preset, findBone, renderer, appearance = {} }) {
    const ga = guides.geometry.attributes, sa = strands.geometry.attributes;
    for (const n of ['position', 'skinIndex', 'skinWeight', '_hair_free', '_hair_ref']) if (!ga[n]) throw new Error(`Guides lack ${n}`);
    for (const n of ['_hair_guide', '_hair_gs', '_hair_u', '_hair_strand', '_hair_offset', '_hair_tangent', '_hair_ao', '_hair_radius']) if (!sa[n]) throw new Error(`Strands lack ${n}`);
    this.guides = guides; this.strands = strands; this.skin = skinnedMesh; this.preset = preset; this.enabled = true;
    const K = guides.userData?.particles_per_guide ?? preset.solver.strandParticles ?? 12;
    const nP = ga.position.count, nG = nP / K;
    if (!Number.isInteger(nG)) throw new Error('Guide point count is not a multiple of the particles per guide');
    this.K = K; this.nG = nG; this.nP = nP;
    this.rest = ga.position.array; this.ref = ga._hair_ref.array; this.skinIndex = ga.skinIndex; this.skinWeight = ga.skinWeight;
    const chainStarts = Int32Array.from({ length: nG + 1 }, (_, g) => g * K);
    this.solver = new CardChainSolver({ chainStarts, freeFactor: Float32Array.from(ga._hair_free.array) }, preset.solver);
    this.kin = new Float64Array(nP * 3); this.kinRef = new Float64Array(nP * 3); this.sim = new Float64Array(nP * 3);
    // guide texture: per particle two RGBA texels (position, frame quaternion)
    this.texData = new Float32Array(K * 2 * nG * 4);
    this.texture = new THREE.DataTexture(this.texData, K * 2, nG, THREE.RGBAFormat, THREE.FloatType);
    this.texture.minFilter = this.texture.magFilter = THREE.NearestFilter; this.texture.generateMipmaps = false;
    // ribbons: two vertices per strand point, two triangles per segment
    const n = sa.position.count, idx = strands.geometry.index.array;
    const aGuide = new Float32Array(n * 8), aOffset = new Float32Array(n * 6), aTangent = new Float32Array(n * 6), aMisc = new Float32Array(n * 6);
    for (let i = 0; i < n; i++) for (let side = 0; side < 2; side++) {
      const v = i * 2 + side;
      aGuide.set([sa._hair_guide.array[i], sa._hair_gs.array[i], sa._hair_u.array[i], side ? 1 : -1], v * 4);
      aOffset.set(sa._hair_offset.array.subarray(i * 3, i * 3 + 3), v * 3);
      aTangent.set(sa._hair_tangent.array.subarray(i * 3, i * 3 + 3), v * 3);
      aMisc.set([sa._hair_strand.array[i], sa._hair_ao.array[i], sa._hair_radius.array[i]], v * 3);
    }
    const tris = new Uint32Array(idx.length / 2 * 6);
    for (let e = 0, o = 0; e < idx.length; e += 2) {
      const a = idx[e] * 2, b = idx[e + 1] * 2;
      tris.set([a, a + 1, b, b, a + 1, b + 1], o); o += 6;
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 6), 3));  // unused: the shader builds positions
    geo.setAttribute('aGuide', new THREE.BufferAttribute(aGuide, 4));
    geo.setAttribute('aOffset', new THREE.BufferAttribute(aOffset, 3));
    geo.setAttribute('aTangent', new THREE.BufferAttribute(aTangent, 3));
    geo.setAttribute('aMisc', new THREE.BufferAttribute(aMisc, 3));
    geo.setIndex(new THREE.BufferAttribute(tris, 1));
    const look = { rootColor: [.028, .017, .011], tipColor: [.105, .066, .043], specColor: [1, .93, .82], rootWidth: .0006, tipWidth: .00025,
      variation: .18, coverageGain: 1.0, specR: .04, specTRT: .18, expR: 260, expTRT: 60, ...preset.strandAppearance, ...appearance };
    this.material = new THREE.ShaderMaterial({
      vertexShader: VERT, fragmentShader: FRAG, lights: true, side: THREE.DoubleSide, alphaToCoverage: true,
      uniforms: THREE.UniformsUtils.merge([THREE.UniformsLib.lights, {
        guideTex: { value: null }, K: { value: K }, resolution: { value: new THREE.Vector2(1, 1) },
        rootWidth: { value: look.rootWidth }, tipWidth: { value: look.tipWidth },
        rootColor: { value: new THREE.Color(...look.rootColor) }, tipColor: { value: new THREE.Color(...look.tipColor) },
        specColor: { value: new THREE.Color(...look.specColor) }, variation: { value: look.variation }, coverageGain: { value: look.coverageGain },
        specR: { value: look.specR }, specTRT: { value: look.specTRT }, expR: { value: look.expR }, expTRT: { value: look.expTRT } }])
    });
    this.material.uniforms.guideTex.value = this.texture;
    this.renderer = renderer;
    this.mesh = new THREE.Mesh(geo, this.material);
    this.mesh.name = 'Inez_Hair_Strands_Ribbons'; this.mesh.frustumCulled = false; this.mesh.matrixAutoUpdate = false;
    this.mesh.onBeforeRender = r => r.getDrawingBufferSize(this.material.uniforms.resolution.value);
    guides.visible = false; strands.visible = false;
    this.colliders = (preset.colliders ?? []).map(c => ({ ...c, node: findBone(c.bone) })).filter(c => c.node);
    this.colliderNow = this.#colliderWorld();
    this.headBone = findBone('head'); this.headRest = this.headBone.getWorldQuaternion(new THREE.Quaternion()).invert();
    this.timing = { skin_ms: 0, solve_ms: 0, upload_ms: 0 };
    this.appearance = look;
  }

  #colliderWorld() {
    return this.colliders.map(c => {
      const M = c.node.matrixWorld;
      if (c.type === 'sphere') return { a: _v.fromArray(c.center).applyMatrix4(M).toArray(), radius: c.radius };
      return { a: _v.fromArray(c.a).applyMatrix4(M).toArray(), b: _v.fromArray(c.b).applyMatrix4(M).toArray(), radius: c.radius };
    });
  }

  // CPU skinning of the guide particles with the shared skeleton.
  #skinGuides() {
    const mesh = this.skin, bm = mesh.skeleton.boneMatrices, b = mesh.bindMatrix.elements;
    const e = _m.multiplyMatrices(mesh.matrixWorld, mesh.bindMatrixInverse).elements;
    const R = this.rest, F = this.ref, idx = this.skinIndex, wt = this.skinWeight;
    for (let p = 0; p < this.nP; p++) {
      const rx = R[p * 3], ry = R[p * 3 + 1], rz = R[p * 3 + 2];
      const bx = b[0] * rx + b[4] * ry + b[8] * rz + b[12], by = b[1] * rx + b[5] * ry + b[9] * rz + b[13], bz = b[2] * rx + b[6] * ry + b[10] * rz + b[14];
      const fx = F[p * 3], fy = F[p * 3 + 1], fz = F[p * 3 + 2];
      let sx = 0, sy = 0, sz = 0, nx = 0, ny = 0, nz = 0;
      for (let j = 0; j < 4; j++) {
        const w = wt.getComponent(p, j); if (w === 0) continue;
        const o = idx.getComponent(p, j) * 16;
        sx += w * (bm[o] * bx + bm[o + 4] * by + bm[o + 8] * bz + bm[o + 12]);
        sy += w * (bm[o + 1] * bx + bm[o + 5] * by + bm[o + 9] * bz + bm[o + 13]);
        sz += w * (bm[o + 2] * bx + bm[o + 6] * by + bm[o + 10] * bz + bm[o + 14]);
        nx += w * (bm[o] * fx + bm[o + 4] * fy + bm[o + 8] * fz); ny += w * (bm[o + 1] * fx + bm[o + 5] * fy + bm[o + 9] * fz); nz += w * (bm[o + 2] * fx + bm[o + 6] * fy + bm[o + 10] * fz);
      }
      this.kin[p * 3] = e[0] * sx + e[4] * sy + e[8] * sz + e[12]; this.kin[p * 3 + 1] = e[1] * sx + e[5] * sy + e[9] * sz + e[13]; this.kin[p * 3 + 2] = e[2] * sx + e[6] * sy + e[10] * sz + e[14];
      const wx = e[0] * nx + e[4] * ny + e[8] * nz, wy = e[1] * nx + e[5] * ny + e[9] * nz, wz = e[2] * nx + e[6] * ny + e[10] * nz, l = Math.hypot(wx, wy, wz) || 1;
      this.kinRef[p * 3] = wx / l; this.kinRef[p * 3 + 1] = wy / l; this.kinRef[p * 3 + 2] = wz / l;
    }
  }

  // Positions and frames into the texture; frames as in build_strand_hair.py guide_frames().
  #upload(P) {
    const K = this.K, d = this.texData, t = new THREE.Vector3(), n = new THREE.Vector3(), bvec = new THREE.Vector3(), m = new THREE.Matrix4(), q = new THREE.Quaternion();
    for (let g = 0; g < this.nG; g++) {
      let px = 0, py = 0, pz = 0, pw = 1;
      for (let k = 0; k < K; k++) {
        const p = g * K + k, i0 = g * K + Math.max(0, k - 1), i1 = g * K + Math.min(K - 1, k + 1);
        t.set(P[i1 * 3] - P[i0 * 3], P[i1 * 3 + 1] - P[i0 * 3 + 1], P[i1 * 3 + 2] - P[i0 * 3 + 2]);
        if (t.lengthSq() < 1e-16) t.set(0, -1, 0); t.normalize();
        n.set(this.kinRef[p * 3], this.kinRef[p * 3 + 1], this.kinRef[p * 3 + 2]).addScaledVector(t, -n.dot(t));
        if (n.lengthSq() < 1e-12) n.set(1, 0, 0).addScaledVector(t, -t.x); n.normalize();
        bvec.crossVectors(t, n); m.makeBasis(bvec, n, t); q.setFromRotationMatrix(m);
        if (k > 0 && q.x * px + q.y * py + q.z * pz + q.w * pw < 0) q.set(-q.x, -q.y, -q.z, -q.w);
        px = q.x; py = q.y; pz = q.z; pw = q.w;
        const o = (g * K * 2 + k * 2) * 4;
        d[o] = P[p * 3]; d[o + 1] = P[p * 3 + 1]; d[o + 2] = P[p * 3 + 2]; d[o + 3] = 1;
        d[o + 4] = q.x; d[o + 5] = q.y; d[o + 6] = q.z; d[o + 7] = q.w;
      }
    }
    this.texture.needsUpdate = true;
  }

  setEnabled(on) { this.enabled = Boolean(on); this.solver.initialized = false; return this.enabled; }

  update(delta) {
    const t0 = performance.now();
    this.skin.updateMatrixWorld(true); this.skin.skeleton.update();
    this.#skinGuides();
    const t1 = performance.now();
    let positions = this.kin;
    if (this.enabled) {
      const g = this.preset.solver.gravity ?? [0, -9.81, 0];
      _q.copy(this.headBone.getWorldQuaternion(new THREE.Quaternion())).multiply(this.headRest);
      const carried = _v.fromArray(g).applyQuaternion(_q);
      this.solver.setTargets(this.kin, [g[0] - carried.x, g[1] - carried.y, g[2] - carried.z]);
      const from = this.colliderNow; this.colliderNow = this.#colliderWorld(); const to = this.colliderNow;
      this.solver.update(delta, t => from.map((c, i) => ({ a: c.a.map((v, k) => v + (to[i].a[k] - v) * t),
        b: c.b ? c.b.map((v, k) => v + (to[i].b[k] - v) * t) : undefined, radius: c.radius })));
      positions = this.solver.interpolated(this.sim);
    }
    const t2 = performance.now();
    this.#upload(positions);
    const t3 = performance.now(), k = .1;
    this.timing.skin_ms += (t1 - t0 - this.timing.skin_ms) * k; this.timing.solve_ms += (t2 - t1 - this.timing.solve_ms) * k; this.timing.upload_ms += (t3 - t2 - this.timing.upload_ms) * k;
  }

  get diagnostics() {
    return { ...this.solver.diagnostics(this.colliderNow), guides: this.nG, particlesPerGuide: this.K, strands: Math.round(this.strands.geometry.attributes._hair_strand.array.at(-1) + 1),
      strandPoints: this.strands.geometry.attributes.position.count, colliders: this.colliders.length, enabled: this.enabled, kind: 'strands', timing_ms: { ...this.timing } };
  }
}
