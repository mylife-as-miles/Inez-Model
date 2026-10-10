// Per-vertex skin region masks, written as the vertex attribute `dhRegion`
// (vec4: x = T-zone (forehead + nose), y = lips, z = cheeks, w = eyelids).
//
// The skin shader uses them for spatially varying roughness (an oilier
// T-zone, moist lips), as Weyrich et al. 2006 measured across face regions
// (cited by GPU Gems 3 ch. 14). Nothing is painted:
// - lips, cheeks and eyelids come from the rig's own facial bone weights
//   (oris*, risorius*/levator*, orbicularis*), so they follow the authored
//   face regions and deform with them;
// - the T-zone is geometric: a soft band along the nose ridge from the
//   nasion to the tip, plus the forward-facing forehead above the brows,
//   measured on the identity-shaped mesh in the bind pose and scaled by the
//   inter-pupil distance (IPD).
// The masks are low-frequency by construction (vertex resolution), as
// roughness regions are.
import * as THREE from 'three/webgpu';

export interface RegionReport { mesh: string; vertices: number; coverage: { tzone: number; lips: number; cheeks: number; lids: number } }

const smooth = (a: number, b: number, x: number) => { const t = THREE.MathUtils.clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };

function boneWeightSums(mesh: THREE.SkinnedMesh, groups: Record<string, RegExp>): Record<string, Float32Array> {
  const index = mesh.geometry.getAttribute('skinIndex') as THREE.BufferAttribute;
  const weight = mesh.geometry.getAttribute('skinWeight') as THREE.BufferAttribute;
  const names = mesh.skeleton.bones.map(b => b.name);
  const out: Record<string, Float32Array> = {};
  for (const [group, pattern] of Object.entries(groups)) {
    const member = names.map(n => pattern.test(n));
    const sum = new Float32Array(index.count);
    for (let i = 0; i < index.count; i++) {
      for (let j = 0; j < 4; j++) if (member[index.getComponent(i, j)]) sum[i] += weight.getComponent(i, j);
    }
    out[group] = sum;
  }
  return out;
}

/**
 * Add `dhRegion` to each skinned skin mesh. `worldPositions(mesh)` must give
 * the bind-pose, identity-shaped world position of every vertex.
 */
export function addSkinRegions(meshes: THREE.SkinnedMesh[], eyeL: THREE.Vector3, eyeR: THREE.Vector3,
  forward = new THREE.Vector3(0, 0, 1), up = new THREE.Vector3(0, 1, 0)): RegionReport[] {
  const ipd = eyeL.distanceTo(eyeR);
  const mid = eyeL.clone().add(eyeR).multiplyScalar(.5);
  const side = new THREE.Vector3().crossVectors(up, forward).normalize();
  const local = (p: THREE.Vector3) => { const d = p.clone().sub(mid); return { x: d.dot(side) / ipd, y: d.dot(up) / ipd, z: d.dot(forward) / ipd }; };
  const world = meshes.map(mesh => {
    mesh.updateMatrixWorld(true);
    const count = mesh.geometry.getAttribute('position').count;
    const out: { x: number; y: number; z: number }[] = [];
    const v = new THREE.Vector3();
    for (let i = 0; i < count; i++) { mesh.getVertexPosition(i, v); out.push(local(v.applyMatrix4(mesh.matrixWorld))); }
    return out;
  });
  // Nose tip: the most forward vertex near the midline, between eye and mouth height.
  let tip = { x: 0, y: -.55, z: .45 };
  let nasion = { x: 0, y: 0, z: .2 };
  for (const vertices of world) for (const p of vertices) {
    if (Math.abs(p.x) < .12 && p.y < -.2 && p.y > -.9 && p.z > tip.z) tip = p;
    if (Math.abs(p.x) < .1 && Math.abs(p.y) < .12 && p.z > nasion.z) nasion = p;
  }
  return meshes.map((mesh, m) => {
    const weights = boneWeightSums(mesh, { lips: /^oris/, cheeks: /^(risorius|levator0[3-5])/, lids: /^orbicularis0[34]/ });
    const count = world[m].length;
    const data = new Float32Array(count * 4);
    const coverage = { tzone: 0, lips: 0, cheeks: 0, lids: 0 };
    const ridge = new THREE.Vector2(tip.x - nasion.x, tip.y - nasion.y);
    const ridgeLength = Math.max(ridge.length(), 1e-6);
    world[m].forEach((p, i) => {
      // Distance (in IPD) to the nasion-tip ridge in the frontal plane.
      const t = THREE.MathUtils.clamp(((p.x - nasion.x) * ridge.x + (p.y - nasion.y) * ridge.y) / (ridgeLength * ridgeLength), 0, 1.15);
      const dx = p.x - (nasion.x + ridge.x * t), dy = p.y - (nasion.y + ridge.y * t);
      const nose = (1 - smooth(.18, .42, Math.hypot(dx, dy))) * smooth(tip.z - .75, tip.z - .45, p.z);
      const forehead = smooth(.42, .62, p.y) * (1 - smooth(.85, 1.15, Math.abs(p.x))) * smooth(nasion.z - .55, nasion.z - .25, p.z);
      const tzone = Math.max(nose, forehead);
      const lips = THREE.MathUtils.clamp(weights.lips[i] * 1.4, 0, 1);
      const cheeks = THREE.MathUtils.clamp(weights.cheeks[i] * 1.2, 0, 1) * (1 - lips);
      const lids = THREE.MathUtils.clamp(weights.lids[i] * 1.3, 0, 1);
      data.set([tzone, lips, cheeks, lids], 4 * i);
      coverage.tzone += tzone; coverage.lips += lips; coverage.cheeks += cheeks; coverage.lids += lids;
    });
    mesh.geometry.setAttribute('dhRegion', new THREE.Float32BufferAttribute(data, 4));
    for (const key of Object.keys(coverage) as (keyof typeof coverage)[]) coverage[key] = +(coverage[key] / count).toFixed(4);
    return { mesh: mesh.name, vertices: count, coverage };
  });
}
