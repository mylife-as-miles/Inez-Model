// Fixed-step XPBD for many short particle chains: one chain per hair card.
// Plain typed arrays, no rendering, skeleton or engine types. The caller
// supplies, every presentation frame, the kinematic (animated) position of
// every particle; pinned particles follow it exactly, free particles are
// pulled toward it by a compliant shape constraint and otherwise move with
// inertia, gravity, drag, inextensible segments, bending and collisions.

const finite = v => Number.isFinite(v);

export class CardChainSolver {
  // chains: Int32Array of chain start offsets (length chains+1, last = particle count)
  // freeFactor: Float32Array per particle, 0 = pinned to the animated pose, 1 = fully free
  constructor({ chainStarts, freeFactor }, settings = {}) {
    this.settings = { hz: 60, iterations: 6, mass: .001, particleRadius: .003,
      stretchCompliance: 0, bendCompliance: .0005, shapeComplianceRoot: .002, shapeComplianceTip: .25,
      drag: 2.5, friction: .3, maxSpeed: 12, maxDelta: .25, maxSubsteps: 6, teleportDistance: .5, teleportSpeed: 6, pinThreshold: .02, ...settings };
    const s = this.settings;
    if (!(s.hz > 0) || !Number.isInteger(s.iterations) || s.iterations < 1 || !Number.isInteger(s.maxSubsteps) || s.maxSubsteps < 1 ||
        ![s.mass, s.maxSpeed, s.maxDelta, s.teleportDistance, s.teleportSpeed, s.particleRadius].every(v => finite(v) && v > 0) ||
        ![s.stretchCompliance, s.bendCompliance, s.shapeComplianceRoot, s.shapeComplianceTip, s.drag].every(v => finite(v) && v >= 0) ||
        !(s.friction >= 0 && s.friction <= 1)) throw new Error('Invalid card solver settings');
    const n = chainStarts[chainStarts.length - 1];
    if (!(n > 0) || freeFactor.length !== n) throw new Error('Chain layout and free factors disagree');
    for (let c = 0; c + 1 < chainStarts.length; c++) if (chainStarts[c + 1] - chainStarts[c] < 2) throw new Error('Every chain needs >= 2 particles');
    this.n = n; this.starts = Int32Array.from(chainStarts); this.free = Float32Array.from(freeFactor);
    this.x = new Float64Array(n * 3); this.prev = new Float64Array(n * 3); this.v = new Float64Array(n * 3);
    this.kin = new Float64Array(n * 3); this.kinFrom = new Float64Array(n * 3); this.kinTo = new Float64Array(n * 3);
    this.before = new Float64Array(n * 3); this.offset = new Float64Array(n * 3);
    this.pinned = new Uint8Array(n); this.compliance = new Float64Array(n);
    for (let i = 0; i < n; i++) {
      this.pinned[i] = this.free[i] < s.pinThreshold ? 1 : 0;
      this.compliance[i] = s.shapeComplianceRoot + (s.shapeComplianceTip - s.shapeComplianceRoot) * Math.min(1, Math.max(0, this.free[i]));
    }
    this.contact = new Uint8Array(n); this.contactNormal = new Float64Array(n * 3);
    this.accumulator = 0; this.ticks = 0; this.resets = 0; this.recoveries = 0; this.initialized = false; this.paused = false;
    this.acceleration = [0, -9.81, 0]; this.lastSolveMs = 0;
  }

  // Kinematic targets for this presentation frame, and the external acceleration
  // (gravity, wind) acting on free particles in world space.
  setTargets(positions, acceleration = this.acceleration) {
    if (positions.length !== this.n * 3) throw new Error('Target count mismatch');
    for (let i = 0; i < positions.length; i++) if (!finite(positions[i])) throw new Error('Nonfinite target');
    if (!acceleration.every(finite)) throw new Error('Nonfinite acceleration');
    this.kinFrom.set(this.initialized ? this.kinTo : positions); this.kinTo.set(positions); this.acceleration = [...acceleration];
  }

  reset() {
    this.x.set(this.kinTo); this.prev.set(this.kinTo); this.v.fill(0); this.offset.fill(0);
    this.accumulator = 0; this.resets++; this.initialized = true;
  }

  pause(on = true) {
    on = Boolean(on);
    if (on && !this.paused) for (let i = 0; i < this.x.length; i++) this.offset[i] = this.x[i] - this.kinTo[i];
    this.paused = on;
  }

  // Advance by delta seconds of presentation time. colliders(t) returns the
  // proxies at fraction t of this frame: [{a:[x,y,z], b?:[x,y,z], radius}].
  update(delta, colliders = () => []) {
    if (!finite(delta) || delta < 0) throw new Error('Nonfinite delta');
    if (!this.initialized) { this.reset(); return 0; }
    const s = this.settings;
    // Teleport, animation snap or large hitch: restart from the animated pose
    // instead of whipping. A scalp point moving faster than teleportSpeed
    // (default 6 m/s, above any head speed in real motion) is a discontinuity.
    let jump = 0;
    for (let i = 0; i < this.n; i++) if (this.pinned[i]) {
      const k = i * 3; jump = Math.max(jump, Math.hypot(this.kinTo[k] - this.kinFrom[k], this.kinTo[k + 1] - this.kinFrom[k + 1], this.kinTo[k + 2] - this.kinFrom[k + 2]));
    }
    if (jump > s.teleportDistance || delta > s.maxDelta || (!this.paused && delta > 0 && jump / delta > s.teleportSpeed)) { this.reset(); return 0; }
    if (this.paused || delta === 0) {
      // Hold the current shape relative to the animated pose (no stepping).
      if (!this.paused) for (let i = 0; i < this.x.length; i++) this.offset[i] = this.x[i] - this.kinFrom[i];
      for (let i = 0; i < this.x.length; i++) { this.x[i] = this.kinTo[i] + this.offset[i]; this.prev[i] = this.x[i]; }
      for (let i = 0; i < this.n; i++) if (this.pinned[i]) { const k = i * 3; this.x[k] = this.prev[k] = this.kinTo[k]; this.x[k + 1] = this.prev[k + 1] = this.kinTo[k + 1]; this.x[k + 2] = this.prev[k + 2] = this.kinTo[k + 2]; }
      return 0;
    }
    const t0 = performance.now();
    const h = 1 / s.hz, start = this.accumulator; this.accumulator += delta;
    let count = 0;
    while (this.accumulator + 1e-12 >= h && count < s.maxSubsteps) {
      const t = Math.min(1, Math.max(0, (h - start + count * h) / delta));
      for (let i = 0; i < this.kin.length; i++) this.kin[i] = this.kinFrom[i] + (this.kinTo[i] - this.kinFrom[i]) * t;
      this.step(colliders(t));
      this.accumulator = Math.max(0, this.accumulator - h); count++;
    }
    if (this.accumulator >= h) { this.reset(); this.recoveries++; }
    this.lastSolveMs = performance.now() - t0;
    return count;
  }

  step(colliders) {
    const s = this.settings, h = 1 / s.hz, w = 1 / s.mass, x = this.x, v = this.v, kin = this.kin, n = this.n;
    const [ax, ay, az] = this.acceleration, damp = Math.exp(-s.drag * h);
    this.prev.set(x); this.before.set(x);
    for (let i = 0; i < n; i++) {
      const k = i * 3;
      if (this.pinned[i]) { x[k] = kin[k]; x[k + 1] = kin[k + 1]; x[k + 2] = kin[k + 2]; continue; }
      let vx = v[k] * damp, vy = v[k + 1] * damp, vz = v[k + 2] * damp;
      const sp = Math.hypot(vx, vy, vz); if (sp > s.maxSpeed) { const f = s.maxSpeed / sp; vx *= f; vy *= f; vz *= f; }
      x[k] += vx * h + ax * h * h; x[k + 1] += vy * h + ay * h * h; x[k + 2] += vz * h + az * h * h;
    }
    const proxies = colliders.map(c => {
      if (!c.a?.every?.(finite) || (c.b && !c.b.every(finite)) || !(c.radius > 0)) throw new Error('Invalid collision proxy');
      return c;
    });
    const lambdaShape = new Float64Array(n * 3), lambdaStretch = new Float64Array(n), lambdaBend = new Float64Array(n);
    this.contact.fill(0);
    const h2 = h * h, aStretch = s.stretchCompliance / h2, aBend = s.bendCompliance / h2;
    const distance = (i, j, rest, alpha, lambda, slot) => {
      const ki = i * 3, kj = j * 3, dx = x[kj] - x[ki], dy = x[kj + 1] - x[ki + 1], dz = x[kj + 2] - x[ki + 2];
      const len = Math.hypot(dx, dy, dz); if (len < 1e-12) return;
      const wi = this.pinned[i] ? 0 : w, wj = this.pinned[j] ? 0 : w; if (wi + wj === 0) return;
      const dl = (-(len - rest) - alpha * lambda[slot]) / (wi + wj + alpha); lambda[slot] += dl;
      const fx = dx / len * dl, fy = dy / len * dl, fz = dz / len * dl;
      x[ki] -= wi * fx; x[ki + 1] -= wi * fy; x[ki + 2] -= wi * fz; x[kj] += wj * fx; x[kj + 1] += wj * fy; x[kj + 2] += wj * fz;
    };
    const kd = (i, j) => Math.hypot(kin[j * 3] - kin[i * 3], kin[j * 3 + 1] - kin[i * 3 + 1], kin[j * 3 + 2] - kin[i * 3 + 2]);
    const pr = s.particleRadius;
    for (let it = 0; it < s.iterations; it++) {
      // compliant pull toward the animated shape (stiff near the root, soft at the tip)
      for (let i = 0; i < n; i++) {
        if (this.pinned[i]) continue;
        const k = i * 3, alpha = this.compliance[i] / h2;
        for (let a = 0; a < 3; a++) {  // one XPBD multiplier per axis
          const dl = (-(x[k + a] - kin[k + a]) - alpha * lambdaShape[k + a]) / (w + alpha);
          lambdaShape[k + a] += dl; x[k + a] += w * dl;
        }
      }
      for (let c = 0; c + 1 < this.starts.length; c++) {
        const a0 = this.starts[c], a1 = this.starts[c + 1];
        for (let i = a0; i + 2 < a1; i++) distance(i, i + 2, kd(i, i + 2), aBend, lambdaBend, i);
        for (let i = a0; i + 1 < a1; i++) distance(i, i + 1, kd(i, i + 1), aStretch, lambdaStretch, i);
      }
      for (let i = 0; i < n; i++) {
        if (this.pinned[i]) continue;
        const k = i * 3;
        for (const c of proxies) {
          let cx = c.a[0], cy = c.a[1], cz = c.a[2];
          if (c.b) {
            const ux = c.b[0] - cx, uy = c.b[1] - cy, uz = c.b[2] - cz, uu = ux * ux + uy * uy + uz * uz;
            const t = uu > 1e-12 ? Math.min(1, Math.max(0, ((x[k] - cx) * ux + (x[k + 1] - cy) * uy + (x[k + 2] - cz) * uz) / uu)) : 0;
            cx += ux * t; cy += uy * t; cz += uz * t;
          }
          const dx = x[k] - cx, dy = x[k + 1] - cy, dz = x[k + 2] - cz, d = Math.hypot(dx, dy, dz), r = c.radius + pr;
          if (d < r) {
            const nx = d > 1e-9 ? dx / d : 0, ny = d > 1e-9 ? dy / d : 1, nz = d > 1e-9 ? dz / d : 0;
            x[k] = cx + nx * r; x[k + 1] = cy + ny * r; x[k + 2] = cz + nz * r;
            this.contact[i] = 1; this.contactNormal[k] = nx; this.contactNormal[k + 1] = ny; this.contactNormal[k + 2] = nz;
          }
        }
      }
    }
    // Follow-the-leader (Mueller et al. 2012): walk each chain from the root and
    // restore every segment's length exactly, then one last collision push.
    if (s.inextensible !== false) for (let c = 0; c + 1 < this.starts.length; c++) {
      for (let i = this.starts[c] + 1; i < this.starts[c + 1]; i++) {
        if (this.pinned[i]) continue;
        const k = i * 3, p = k - 3, L = kd(i - 1, i);
        const dx = x[k] - x[p], dy = x[k + 1] - x[p + 1], dz = x[k + 2] - x[p + 2], d = Math.hypot(dx, dy, dz);
        if (d > 1e-12) { x[k] = x[p] + dx / d * L; x[k + 1] = x[p + 1] + dy / d * L; x[k + 2] = x[p + 2] + dz / d * L; }
        for (const cp of proxies) {
          let cx = cp.a[0], cy = cp.a[1], cz = cp.a[2];
          if (cp.b) { const ux = cp.b[0] - cx, uy = cp.b[1] - cy, uz = cp.b[2] - cz, uu = ux * ux + uy * uy + uz * uz;
            const t = uu > 1e-12 ? Math.min(1, Math.max(0, ((x[k] - cx) * ux + (x[k + 1] - cy) * uy + (x[k + 2] - cz) * uz) / uu)) : 0; cx += ux * t; cy += uy * t; cz += uz * t; }
          const ex = x[k] - cx, ey = x[k + 1] - cy, ez = x[k + 2] - cz, e = Math.hypot(ex, ey, ez), r = cp.radius + pr;
          if (e < r && e > 1e-9) { x[k] = cx + ex / e * r; x[k + 1] = cy + ey / e * r; x[k + 2] = cz + ez / e * r; this.contact[i] = 1;
            this.contactNormal[k] = ex / e; this.contactNormal[k + 1] = ey / e; this.contactNormal[k + 2] = ez / e; }
        }
      }
    }
    for (let i = 0; i < n; i++) {
      const k = i * 3;
      if (this.pinned[i]) { v[k] = v[k + 1] = v[k + 2] = 0; continue; }
      let vx = (x[k] - this.before[k]) / h, vy = (x[k + 1] - this.before[k + 1]) / h, vz = (x[k + 2] - this.before[k + 2]) / h;
      if (this.contact[i]) {
        const nx = this.contactNormal[k], ny = this.contactNormal[k + 1], nz = this.contactNormal[k + 2], vn = vx * nx + vy * ny + vz * nz;
        const tx = vx - vn * nx, ty = vy - vn * ny, tz = vz - vn * nz, keep = 1 - s.friction, out = Math.max(vn, 0);
        vx = nx * out + tx * keep; vy = ny * out + ty * keep; vz = nz * out + tz * keep;
      }
      const sp = Math.hypot(vx, vy, vz); if (sp > s.maxSpeed) { const f = s.maxSpeed / sp; vx *= f; vy *= f; vz *= f; }
      v[k] = vx; v[k + 1] = vy; v[k + 2] = vz;
    }
    this.ticks++;
    for (let i = 0; i < x.length; i++) if (!finite(x[i]) || Math.abs(x[i]) > 1e6) { this.reset(); this.recoveries++; break; }
  }

  // Particle positions blended between the last two fixed steps for smooth presentation.
  interpolated(out = new Float64Array(this.n * 3)) {
    const alpha = Math.min(1, this.accumulator * this.settings.hz);
    for (let i = 0; i < out.length; i++) out[i] = this.prev[i] + (this.x[i] - this.prev[i]) * alpha;
    for (let i = 0; i < this.n; i++) if (this.pinned[i]) { const k = i * 3; out[k] = this.kinTo[k]; out[k + 1] = this.kinTo[k + 1]; out[k + 2] = this.kinTo[k + 2]; }
    return out;
  }

  diagnostics(colliders = []) {
    let maxStretch = 0, maxOffset = 0, penetrations = 0;
    const x = this.x, kin = this.kinTo;
    for (let c = 0; c + 1 < this.starts.length; c++) for (let i = this.starts[c]; i + 1 < this.starts[c + 1]; i++) {
      const k = i * 3, j = k + 3;
      const rest = Math.hypot(kin[j] - kin[k], kin[j + 1] - kin[k + 1], kin[j + 2] - kin[k + 2]);
      const len = Math.hypot(x[j] - x[k], x[j + 1] - x[k + 1], x[j + 2] - x[k + 2]);
      if (rest > 1e-9) maxStretch = Math.max(maxStretch, Math.abs(len / rest - 1));
    }
    for (let i = 0; i < this.n; i++) {
      const k = i * 3; maxOffset = Math.max(maxOffset, Math.hypot(x[k] - kin[k], x[k + 1] - kin[k + 1], x[k + 2] - kin[k + 2]));
      if (this.pinned[i]) continue;
      for (const c of colliders) {
        let cx = c.a[0], cy = c.a[1], cz = c.a[2];
        if (c.b) { const ux = c.b[0] - cx, uy = c.b[1] - cy, uz = c.b[2] - cz, uu = ux * ux + uy * uy + uz * uz;
          const t = uu > 1e-12 ? Math.min(1, Math.max(0, ((x[k] - cx) * ux + (x[k + 1] - cy) * uy + (x[k + 2] - cz) * uz) / uu)) : 0; cx += ux * t; cy += uy * t; cz += uz * t; }
        if (Math.hypot(x[k] - cx, x[k + 1] - cy, x[k + 2] - cz) < c.radius - 1e-4) penetrations++;
      }
    }
    return { chains: this.starts.length - 1, particles: this.n, pinned: this.pinned.reduce((a, b) => a + b, 0), ticks: this.ticks,
      resets: this.resets, recoveries: this.recoveries, paused: this.paused, simulationHz: this.settings.hz, iterations: this.settings.iterations,
      maxRelativeStretch: maxStretch, maxOffsetFromAnimation: maxOffset, penetrations, lastSolveMs: this.lastSolveMs };
  }
}
