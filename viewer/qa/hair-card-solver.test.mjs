// Fixture tests for the per-card XPBD solver (viewer/src/hair/card-solver.js).
// Synthetic chains only: these exercise the solver, not the fitted Inez hair.
import test from 'node:test';
import assert from 'node:assert/strict';
import { CardChainSolver } from '../src/hair/card-solver.js';

// Two hanging chains of 6 particles, 2 cm apart, root pinned (free 0), tips free.
function makeChains() {
  const chainStarts = Int32Array.from([0, 6, 12]);
  const free = new Float32Array(12).map((_, i) => Math.min(1, (i % 6) / 3));
  return { chainStarts, freeFactor: free };
}
function rest(offset = [0, 0, 0]) {
  const p = new Float64Array(36);
  for (let c = 0; c < 2; c++) for (let i = 0; i < 6; i++) {
    const k = (c * 6 + i) * 3; p[k] = c * .05 + offset[0]; p[k + 1] = 1.7 - i * .02 + offset[1]; p[k + 2] = offset[2];
  }
  return p;
}
const dist = (a, b, i) => Math.hypot(a[i * 3] - b[i * 3], a[i * 3 + 1] - b[i * 3 + 1], a[i * 3 + 2] - b[i * 3 + 2]);

test('pinned particles follow the animation exactly and free ones do not drift at rest', () => {
  const s = new CardChainSolver(makeChains());
  const target = rest();
  s.setTargets(target, [0, 0, 0]); s.update(0);
  for (let f = 0; f < 120; f++) { s.setTargets(target, [0, 0, 0]); s.update(1 / 60); }
  const x = s.interpolated();
  for (let i = 0; i < 12; i++) assert.ok(dist(x, target, i) < 1e-9, `particle ${i} drifted`);
});

test('gravity sag is bounded by the shape compliance', () => {
  // horizontal chains, so gravity acts across them (vertical chains cannot sag: they are inextensible)
  const s = new CardChainSolver(makeChains());
  const target = rest();
  for (let c = 0; c < 2; c++) for (let i = 0; i < 6; i++) { const k = (c * 6 + i) * 3; target[k + 1] = 1.7; target[k + 2] = i * .02; }
  s.setTargets(target); s.update(0);
  for (let f = 0; f < 300; f++) { s.setTargets(target, [0, -9.81, 0]); s.update(1 / 60); }
  const x = s.interpolated();
  const sag = Math.max(...[...Array(12).keys()].map(i => dist(x, target, i)));
  assert.ok(sag > 1e-4 && sag < .005, `sag ${sag}`);
});

test('free tips lag behind a moving head and settle back afterwards', () => {
  const s = new CardChainSolver(makeChains());
  s.setTargets(rest(), [0, 0, 0]); s.update(0);
  let maxLag = 0, maxStretch = 0;
  for (let f = 0; f < 60; f++) {           // 1 s sideways at 1 m/s
    const t = rest([(f + 1) / 60, 0, 0]); s.setTargets(t, [0, 0, 0]); s.update(1 / 60);
    maxLag = Math.max(maxLag, dist(s.interpolated(), t, 5)); maxStretch = Math.max(maxStretch, s.diagnostics().maxRelativeStretch);
  }
  for (let f = 0; f < 60; f++) {            // sudden stop
    const t = rest([1, 0, 0]); s.setTargets(t, [0, 0, 0]); s.update(1 / 60);
    maxStretch = Math.max(maxStretch, s.diagnostics().maxRelativeStretch);
  }
  const settled = rest([1, 0, 0]);
  for (let f = 0; f < 180; f++) { s.setTargets(settled, [0, 0, 0]); s.update(1 / 60); }
  assert.ok(maxLag > .002, `tip should lag, lag ${maxLag}`);
  assert.ok(dist(s.interpolated(), settled, 5) < .001, 'tip should settle');
  assert.ok(maxStretch < .02, `segments must stay near inextensible, stretch ${maxStretch}`);
});

test('collision proxies keep free particles outside', () => {
  const s = new CardChainSolver(makeChains());
  const t = rest(); s.setTargets(t, [0, 0, 0]); s.update(0);
  const sphere = { a: [0, 1.62, -.012], radius: .02 };   // overlaps the first chain's tip targets
  for (let f = 0; f < 120; f++) { s.setTargets(t, [0, 0, 0]); s.update(1 / 60, () => [sphere]); }
  assert.equal(s.diagnostics([sphere]).penetrations, 0);
  const x = s.interpolated();
  for (const i of [3, 4, 5]) assert.ok(Math.hypot(x[i * 3] - sphere.a[0], x[i * 3 + 1] - sphere.a[1], x[i * 3 + 2] - sphere.a[2]) >= sphere.radius - 1e-6);
});

test('fixed stepping gives the same result at 30, 60 and 120 FPS', () => {
  const run = fps => {
    const s = new CardChainSolver(makeChains());
    s.setTargets(rest(), [0, 0, 0]); s.update(0);
    const frames = Math.round(2 * fps);
    for (let f = 1; f <= frames; f++) { const time = f / fps; s.setTargets(rest([.5 * time, 0, 0]), [0, -9.81, 0]); s.update(1 / fps); }
    return s.x.slice();
  };
  const a = run(30), b = run(60), c = run(120);
  for (let i = 0; i < a.length; i++) { assert.ok(Math.abs(a[i] - b[i]) < 1e-9); assert.ok(Math.abs(b[i] - c[i]) < 1e-9); }
});

test('teleport resets to the animated pose; pause holds shape relative to it', () => {
  const s = new CardChainSolver(makeChains());
  s.setTargets(rest(), [0, 0, 0]); s.update(0);
  for (let f = 0; f < 30; f++) { s.setTargets(rest([f * .01, 0, 0]), [0, 0, 0]); s.update(1 / 60); }
  const resets = s.resets;
  const far = rest([5, 0, 0]); s.setTargets(far, [0, 0, 0]); s.update(1 / 60);
  assert.equal(s.resets, resets + 1);
  for (let i = 0; i < 12; i++) assert.ok(dist(s.interpolated(), far, i) < 1e-9);
  // pause: move the animation, the hair keeps its offsets from it
  for (let f = 0; f < 10; f++) { s.setTargets(rest([5 + f * .02, 0, 0]), [0, 0, 0]); s.update(1 / 60); }
  const before = s.x.slice(), kinBefore = rest([5.18, 0, 0]);
  s.pause(true); const moved = rest([5.3, .1, 0]); s.setTargets(moved, [0, 0, 0]); s.update(1 / 60);
  const after = s.x;
  for (let i = 0; i < 12; i++) if (i % 6) for (let a = 0; a < 3; a++)   // free particles keep their offsets
    assert.ok(Math.abs((after[i * 3 + a] - moved[i * 3 + a]) - (before[i * 3 + a] - kinBefore[i * 3 + a])) < 1e-9);
});

test('invalid input is rejected and nonfinite state recovers', () => {
  assert.throws(() => new CardChainSolver({ chainStarts: Int32Array.from([0, 1]), freeFactor: new Float32Array(1) }));
  const s = new CardChainSolver(makeChains());
  assert.throws(() => s.setTargets(new Float64Array(36).fill(NaN)));
  s.setTargets(rest(), [0, 0, 0]); s.update(0);
  s.x[5 * 3] = NaN; s.setTargets(rest(), [0, 0, 0]); s.update(1 / 60);
  assert.ok(s.recoveries >= 1 && s.interpolated().every(Number.isFinite));
});

test('an animation snap faster than teleportSpeed restarts from the animated pose', () => {
  const s = new CardChainSolver(makeChains(), { teleportSpeed: 6 });
  s.setTargets(rest(), [0, 0, 0]); s.update(0);
  for (let f = 0; f < 20; f++) { s.setTargets(rest([f * .02, 0, 0]), [0, 0, 0]); s.update(1 / 60); }  // 1.2 m/s: simulated
  const resets = s.resets;
  const snapped = rest([.38 + .2, 0, 0]);                        // 20 cm in one 60 Hz frame = 12 m/s
  s.setTargets(snapped, [0, 0, 0]); s.update(1 / 60);
  assert.equal(s.resets, resets + 1);
  for (let i = 0; i < 12; i++) assert.ok(dist(s.interpolated(), snapped, i) < 1e-9);
});
