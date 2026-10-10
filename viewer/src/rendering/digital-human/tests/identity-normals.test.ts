// The identity-layer normal correction on a synthetic sphere (no GPU).
import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three/webgpu';
import { correctIdentityNormals, weldedNormals } from '../skin/identity-normals.ts';

function morphedSphere() {
  const geometry = new THREE.SphereGeometry(1, 48, 24);
  const position = geometry.getAttribute('position');
  const count = position.count;
  // Two large "identity" deformations: stretch in y, then shear z by x.
  const stretch = new Float32Array(count * 3), shear = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) { stretch[3 * i + 1] = position.getY(i) * 0.8; shear[3 * i + 2] = position.getX(i) * 0.6; }
  // Linear normal deltas, as an exporter writes them: n(single target) - n(base).
  const deltaFor = (offsets: Float32Array) => {
    const g = geometry.clone();
    const p = g.getAttribute('position');
    for (let i = 0; i < count; i++) p.setXYZ(i, p.getX(i) + offsets[3 * i], p.getY(i) + offsets[3 * i + 1], p.getZ(i) + offsets[3 * i + 2]);
    g.computeVertexNormals();
    const n = g.getAttribute('normal'), n0 = geometry.getAttribute('normal');
    const out = new Float32Array(count * 3);
    for (let i = 0; i < count; i++) out.set([n.getX(i) - n0.getX(i), n.getY(i) - n0.getY(i), n.getZ(i) - n0.getZ(i)], 3 * i);
    return out;
  };
  geometry.morphAttributes.position = [new THREE.Float32BufferAttribute(stretch, 3), new THREE.Float32BufferAttribute(shear, 3)];
  geometry.morphAttributes.normal = [new THREE.Float32BufferAttribute(deltaFor(stretch), 3), new THREE.Float32BufferAttribute(deltaFor(shear), 3)];
  geometry.morphTargetsRelative = true;
  const mesh = new THREE.Mesh(geometry);
  mesh.name = 'body';
  mesh.morphTargetDictionary = { Inez_HeadFit_v03: 0, Inez_FaceCorrect_v05: 1 };
  mesh.morphTargetInfluences = [1, 1];
  return mesh;
}

test('corrected normals match the identity-shaped surface; the linear sum does not', () => {
  const mesh = morphedSphere();
  const report = correctIdentityNormals([mesh]);
  assert.ok(report);
  assert.ok(report.beforeDeg.max > 5, `linear delta sum should be visibly wrong: ${JSON.stringify(report.beforeDeg)}`);
  assert.ok(report.afterDeg.max < 1e-3, `after: ${JSON.stringify(report.afterDeg)}`);
  assert.deepEqual(report.identityTargets.sort(), ['Inez_FaceCorrect_v05', 'Inez_HeadFit_v03']);
  assert.ok(report.tangentsRebuilt);
  // Identity NORMAL deltas are zeroed; positions are untouched.
  const zeroed = mesh.geometry.morphAttributes.normal[0].array as Float32Array;
  assert.ok(zeroed.every(v => v === 0));
  assert.ok((mesh.geometry.morphAttributes.position[0].array as Float32Array).some(v => v !== 0));
});

test('UV-seam duplicates get one shared normal', () => {
  const sphere = new THREE.SphereGeometry(1, 16, 8);
  const p = sphere.getAttribute('position');
  const positions = new Float64Array(p.count * 3);
  for (let i = 0; i < p.count; i++) positions.set([p.getX(i), p.getY(i), p.getZ(i)], 3 * i);
  const { normals } = weldedNormals([positions], [sphere.getIndex()!.array as ArrayLike<number>]);
  // Vertex 0 of each ring and the last one (u = 0 and u = 1) coincide on a sphere.
  for (let ring = 1; ring < 8; ring++) {
    const a = ring * 17, b = ring * 17 + 16;
    for (let c = 0; c < 3; c++) assert.ok(Math.abs(normals[0][3 * a + c] - normals[0][3 * b + c]) < 1e-9);
  }
});
