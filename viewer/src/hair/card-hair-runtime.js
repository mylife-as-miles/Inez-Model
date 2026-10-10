// Binds the per-card XPBD solver to a skinned hair-card mesh in three.js.
//
// The GLB carries skinning (head + hair.01-04) and three custom attributes per
// vertex: _HAIR_CARD (card index), _HAIR_S (0 root .. 1 tip) and _HAIR_FREE
// (0 on the scalp .. 1 hanging free). From those this module builds one guide
// chain per card, samples the chain's animated (skinned) pose every frame on
// the CPU, lets the solver add inertia, gravity and collisions, and rebuilds
// every card vertex from the simulated chain. The original skinned mesh is
// hidden while the simulation drives a world-space copy; disabling the
// simulation shows the skinned mesh again (pure animation).
import * as THREE from 'three';
import { CardChainSolver } from './card-solver.js';

const _m = new THREE.Matrix4(), _v = new THREE.Vector3(), _q = new THREE.Quaternion();

export class CardHairRuntime {
  constructor(mesh, preset, { findBone }) {
    if (!mesh?.isSkinnedMesh) throw new Error('Hair cards must be a skinned mesh');
    const g = mesh.geometry, a = g.attributes;
    for (const name of ['_hair_card', '_hair_s', '_hair_free', 'position', 'normal', 'skinIndex', 'skinWeight'])
      if (!a[name]) throw new Error(`Hair mesh lacks attribute ${name}`);
    this.mesh = mesh; this.preset = preset; this.enabled = true;
    const K = preset.solver.particlesPerCard ?? 8;
    const count = a.position.count, card = a._hair_card.array, s = a._hair_s.array, free = a._hair_free.array;
    const pos = a.position.array, nor = a.normal.array;
    const cards = new Map();
    for (let i = 0; i < count; i++) { const c = Math.round(card[i]); if (!cards.has(c)) cards.set(c, []); cards.get(c).push(i); }
    const ids = [...cards.keys()].sort((x, y) => x - y);
    const nP = ids.length * K;
    this.K = K; this.cardCount = ids.length;
    const restP = new Float64Array(nP * 3), freeP = new Float32Array(nP), repVertex = new Int32Array(nP), restRef = new Float64Array(nP * 3);
    const chainStarts = new Int32Array(ids.length + 1);
    // ---- guide particles: weighted centre of the card's vertices around s_k
    ids.forEach((c, ci) => {
      const vs = cards.get(c); chainStarts[ci] = ci * K;
      for (let k = 0; k < K; k++) {
        const sk = k / (K - 1), band = .75 / (K - 1); let wsum = 0, fx = 0, px = 0, py = 0, pz = 0, nx = 0, ny = 0, nz = 0, best = -1, bestD = Infinity;
        for (const i of vs) {
          const d = Math.abs(s[i] - sk); if (d < bestD) { bestD = d; best = i; }
          if (d > band) continue;
          const w = 1 - d / band; wsum += w; fx += w * free[i];
          px += w * pos[i * 3]; py += w * pos[i * 3 + 1]; pz += w * pos[i * 3 + 2];
          nx += w * nor[i * 3]; ny += w * nor[i * 3 + 1]; nz += w * nor[i * 3 + 2];
        }
        const p = ci * K + k;
        if (wsum === 0) { px = pos[best * 3]; py = pos[best * 3 + 1]; pz = pos[best * 3 + 2]; nx = nor[best * 3]; ny = nor[best * 3 + 1]; nz = nor[best * 3 + 2]; fx = free[best]; wsum = 1; }
        restP[p * 3] = px / wsum; restP[p * 3 + 1] = py / wsum; restP[p * 3 + 2] = pz / wsum;
        const nl = Math.hypot(nx, ny, nz) || 1; restRef[p * 3] = nx / nl; restRef[p * 3 + 1] = ny / nl; restRef[p * 3 + 2] = nz / nl;
        freeP[p] = Math.min(1, Math.max(0, fx / wsum)); repVertex[p] = best;
      }
      // a chain is never freer toward the root than further out
      for (let k = 1; k < K; k++) freeP[ci * K + k] = Math.max(freeP[ci * K + k], freeP[ci * K + k - 1]);
    });
    chainStarts[ids.length] = nP;
    this.chainStarts = chainStarts; this.restP = restP; this.repVertex = repVertex; this.restRef = restRef; this.freeP = freeP;
    this.solver = new CardChainSolver({ chainStarts, freeFactor: freeP }, preset.solver);
    // ---- rest frames per particle and per-vertex binding (segment, t, local offset, local normal)
    const restFrames = this.#frames(restP, restRef, new Float64Array(nP * 4));
    this.vSeg = new Int32Array(count); this.vT = new Float32Array(count);
    this.vOff = new Float32Array(count * 3); this.vNor = new Float32Array(count * 3);
    const cardIndex = new Map(ids.map((c, ci) => [c, ci]));
    const qa = new THREE.Quaternion(), qb = new THREE.Quaternion(), base = new THREE.Vector3(), off = new THREE.Vector3(), nn = new THREE.Vector3();
    for (let i = 0; i < count; i++) {
      const ci = cardIndex.get(Math.round(card[i])), u = Math.min(.999999, Math.max(0, s[i])) * (K - 1), k = Math.floor(u), t = u - k;
      const p0 = ci * K + k, p1 = p0 + 1;
      this.vSeg[i] = p0; this.vT[i] = t;
      qa.fromArray(restFrames, p0 * 4); qb.fromArray(restFrames, p1 * 4); qa.slerp(qb, t).invert();
      base.set(restP[p0 * 3] + (restP[p1 * 3] - restP[p0 * 3]) * t, restP[p0 * 3 + 1] + (restP[p1 * 3 + 1] - restP[p0 * 3 + 1]) * t, restP[p0 * 3 + 2] + (restP[p1 * 3 + 2] - restP[p0 * 3 + 2]) * t);
      off.fromArray(pos, i * 3).sub(base).applyQuaternion(qa); off.toArray(this.vOff, i * 3);
      nn.fromArray(nor, i * 3).applyQuaternion(qa); nn.toArray(this.vNor, i * 3);
    }
    // ---- world-space render copy
    const rg = new THREE.BufferGeometry();
    rg.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3).setUsage(THREE.DynamicDrawUsage));
    rg.setAttribute('normal', new THREE.BufferAttribute(new Float32Array(count * 3), 3).setUsage(THREE.DynamicDrawUsage));
    for (const name of ['uv', 'color']) if (a[name]) rg.setAttribute(name, a[name]);
    rg.setIndex(g.index);
    this.renderMesh = new THREE.Mesh(rg, mesh.material);
    this.renderMesh.name = mesh.name + '_Simulated'; this.renderMesh.frustumCulled = false;
    this.renderMesh.castShadow = mesh.castShadow; this.renderMesh.receiveShadow = mesh.receiveShadow;
    this.renderMesh.matrixAutoUpdate = false;
    // ---- colliders on bones
    this.colliders = (preset.colliders ?? []).map(c => ({ ...c, node: findBone(c.bone) })).filter(c => c.node);
    this.colliderPrev = null; this.colliderNow = this.#colliderWorld();
    // ---- head-relative gravity: the authored rest shape already hangs under gravity
    this.headBone = findBone('head'); this.headRest = this.headBone.getWorldQuaternion(new THREE.Quaternion()).invert();
    this.kin = new Float64Array(nP * 3); this.kinRef = new Float64Array(nP * 3);
    this.sim = new Float64Array(nP * 3); this.frames = new Float64Array(nP * 4);
    this.timing = { skin_ms: 0, solve_ms: 0, rebuild_ms: 0 };
  }

  // Orthonormal frame per particle: tangent along the chain, reference normal from the card.
  #frames(P, ref, out) {
    const K = this.K, t = new THREE.Vector3(), n = new THREE.Vector3(), b = new THREE.Vector3(), m = new THREE.Matrix4(), q = new THREE.Quaternion();
    for (let c = 0; c < this.cardCount; c++) for (let k = 0; k < K; k++) {
      const p = c * K + k, i0 = c * K + Math.max(0, k - 1), i1 = c * K + Math.min(K - 1, k + 1);
      t.set(P[i1 * 3] - P[i0 * 3], P[i1 * 3 + 1] - P[i0 * 3 + 1], P[i1 * 3 + 2] - P[i0 * 3 + 2]);
      if (t.lengthSq() < 1e-16) t.set(0, -1, 0); t.normalize();
      n.set(ref[p * 3], ref[p * 3 + 1], ref[p * 3 + 2]); n.addScaledVector(t, -n.dot(t));
      if (n.lengthSq() < 1e-12) n.set(1, 0, 0).addScaledVector(t, -t.x); n.normalize();
      b.crossVectors(t, n);
      m.makeBasis(b, n, t); q.setFromRotationMatrix(m);
      if (k > 0) { // keep quaternion hemisphere continuous along the chain for slerp
        const pq = (p - 1) * 4; if (q.x * out[pq] + q.y * out[pq + 1] + q.z * out[pq + 2] + q.w * out[pq + 3] < 0) q.set(-q.x, -q.y, -q.z, -q.w);
      }
      q.toArray(out, p * 4);
    }
    return out;
  }

  #colliderWorld() {
    return this.colliders.map(c => {
      const M = c.node.matrixWorld;
      if (c.type === 'sphere') return { a: _v.fromArray(c.center).applyMatrix4(M).toArray(), radius: c.radius };
      return { a: _v.fromArray(c.a).applyMatrix4(M).toArray(), b: _v.fromArray(c.b).applyMatrix4(M).toArray(), radius: c.radius };
    });
  }

  // CPU skinning of the guide particles (same weights as their nearest card vertex).
  #skinParticles() {
    const mesh = this.mesh, sk = mesh.skeleton, bm = sk.boneMatrices, idx = mesh.geometry.attributes.skinIndex, wt = mesh.geometry.attributes.skinWeight;
    const toWorld = _m.multiplyMatrices(mesh.matrixWorld, mesh.bindMatrixInverse);
    const e = toWorld.elements, b = mesh.bindMatrix.elements;
    for (let p = 0; p < this.restP.length / 3; p++) {
      const vi = this.repVertex[p];
      // bind-space rest position and reference normal
      const rx = this.restP[p * 3], ry = this.restP[p * 3 + 1], rz = this.restP[p * 3 + 2];
      const bx = b[0] * rx + b[4] * ry + b[8] * rz + b[12], by = b[1] * rx + b[5] * ry + b[9] * rz + b[13], bz = b[2] * rx + b[6] * ry + b[10] * rz + b[14];
      const nx0 = this.restRef[p * 3], ny0 = this.restRef[p * 3 + 1], nz0 = this.restRef[p * 3 + 2];
      let sx = 0, sy = 0, sz = 0, nx = 0, ny = 0, nz = 0;
      for (let j = 0; j < 4; j++) {
        const w = wt.getComponent(vi, j); if (w === 0) continue;
        const o = idx.getComponent(vi, j) * 16;
        sx += w * (bm[o] * bx + bm[o + 4] * by + bm[o + 8] * bz + bm[o + 12]);
        sy += w * (bm[o + 1] * bx + bm[o + 5] * by + bm[o + 9] * bz + bm[o + 13]);
        sz += w * (bm[o + 2] * bx + bm[o + 6] * by + bm[o + 10] * bz + bm[o + 14]);
        nx += w * (bm[o] * nx0 + bm[o + 4] * ny0 + bm[o + 8] * nz0);
        ny += w * (bm[o + 1] * nx0 + bm[o + 5] * ny0 + bm[o + 9] * nz0);
        nz += w * (bm[o + 2] * nx0 + bm[o + 6] * ny0 + bm[o + 10] * nz0);
      }
      this.kin[p * 3] = e[0] * sx + e[4] * sy + e[8] * sz + e[12];
      this.kin[p * 3 + 1] = e[1] * sx + e[5] * sy + e[9] * sz + e[13];
      this.kin[p * 3 + 2] = e[2] * sx + e[6] * sy + e[10] * sz + e[14];
      const wx = e[0] * nx + e[4] * ny + e[8] * nz, wy = e[1] * nx + e[5] * ny + e[9] * nz, wz = e[2] * nx + e[6] * ny + e[10] * nz, l = Math.hypot(wx, wy, wz) || 1;
      this.kinRef[p * 3] = wx / l; this.kinRef[p * 3 + 1] = wy / l; this.kinRef[p * 3 + 2] = wz / l;
    }
  }

  setEnabled(on) {
    this.enabled = Boolean(on); this.mesh.visible = !this.enabled; this.renderMesh.visible = this.enabled;
    if (this.enabled) this.solver.initialized = false;  // restart from the current animated pose
    return this.enabled;
  }

  // Call after the animation (and character root) for this frame are final.
  update(delta) {
    if (!this.enabled) return;
    const t0 = performance.now();
    this.mesh.updateMatrixWorld(true); this.mesh.skeleton.update();
    this.#skinParticles();
    // gravity relative to the head: zero while the head keeps its rest orientation
    const g = this.preset.solver.gravity ?? [0, -9.81, 0];
    let acc = g;
    if ((this.preset.solver.gravityMode ?? 'head-relative') === 'head-relative') {
      _q.copy(this.headBone.getWorldQuaternion(new THREE.Quaternion())).multiply(this.headRest);
      const carried = _v.fromArray(g).applyQuaternion(_q);
      acc = [g[0] - carried.x, g[1] - carried.y, g[2] - carried.z];
    }
    const t1 = performance.now();
    this.solver.setTargets(this.kin, acc);
    const from = this.colliderNow; this.colliderNow = this.#colliderWorld();
    const to = this.colliderNow;
    this.solver.update(delta, t => from.map((c, i) => ({ a: c.a.map((v, k) => v + (to[i].a[k] - v) * t),
      b: c.b ? c.b.map((v, k) => v + (to[i].b[k] - v) * t) : undefined, radius: c.radius })));
    const t2 = performance.now();
    this.#rebuild();
    const t3 = performance.now();
    const k = .1; this.timing.skin_ms += (t1 - t0 - this.timing.skin_ms) * k; this.timing.solve_ms += (t2 - t1 - this.timing.solve_ms) * k; this.timing.rebuild_ms += (t3 - t2 - this.timing.rebuild_ms) * k;
  }

  #rebuild() {
    const sim = this.solver.interpolated(this.sim);
    const frames = this.#frames(sim, this.kinRef, this.frames);
    const P = this.renderMesh.geometry.attributes.position, N = this.renderMesh.geometry.attributes.normal, pa = P.array, na = N.array;
    const off = this.vOff, nor = this.vNor, seg = this.vSeg, tt = this.vT;
    for (let i = 0; i < seg.length; i++) {
      const p0 = seg[i], t = tt[i], a = p0 * 4, b = a + 4, u = 1 - t;
      // normalised lerp of adjacent particle frames (hemisphere-aligned in #frames)
      let qx = frames[a] * u + frames[b] * t, qy = frames[a + 1] * u + frames[b + 1] * t,
        qz = frames[a + 2] * u + frames[b + 2] * t, qw = frames[a + 3] * u + frames[b + 3] * t;
      const ql = 1 / Math.hypot(qx, qy, qz, qw); qx *= ql; qy *= ql; qz *= ql; qw *= ql;
      const k = i * 3, s0 = p0 * 3;
      for (let pass = 0; pass < 2; pass++) {
        const src = pass ? nor : off, vx = src[k], vy = src[k + 1], vz = src[k + 2];
        // v' = v + 2w(q x v) + 2 q x (q x v)
        const cx = qy * vz - qz * vy, cy = qz * vx - qx * vz, cz = qx * vy - qy * vx;
        const rx = vx + 2 * (qw * cx + qy * cz - qz * cy), ry = vy + 2 * (qw * cy + qz * cx - qx * cz), rz = vz + 2 * (qw * cz + qx * cy - qy * cx);
        if (pass) { na[k] = rx; na[k + 1] = ry; na[k + 2] = rz; }
        else {
          pa[k] = sim[s0] + (sim[s0 + 3] - sim[s0]) * t + rx;
          pa[k + 1] = sim[s0 + 1] + (sim[s0 + 4] - sim[s0 + 1]) * t + ry;
          pa[k + 2] = sim[s0 + 2] + (sim[s0 + 5] - sim[s0 + 2]) * t + rz;
        }
      }
    }
    P.needsUpdate = true; N.needsUpdate = true;
  }

  get diagnostics() {
    return { ...this.solver.diagnostics(this.colliderNow), cards: this.cardCount, particlesPerCard: this.K, vertices: this.vSeg.length,
      colliders: this.colliders.length, enabled: this.enabled, timing_ms: { ...this.timing } };
  }
}
