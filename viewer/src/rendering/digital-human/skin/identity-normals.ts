// Correct shading normals of meshes that carry Inez's identity layers.
//
// The body exports seven identity morph targets that stay at fixed weights
// (HeadFit_v03 and the four _v05 layers at 1). glTF stores a NORMAL delta per
// target and renderers add them linearly: n = n0 + sum(w_i * dn_i). That
// approximation is fine for small deformations but not for these layers,
// which move vertices by up to 25 cm. Measured on inez_master.glb, the
// resulting normal differs from the true normal of the identity-shaped
// surface by 3 deg (median) / 19 deg (95th percentile) on the face and 8 / 17 deg
// on the torso, with some normals flipped. That shows as contour banding.
//
// At load, this module (1) evaluates the identity-shaped positions, (2)
// recomputes smooth, angle-weighted vertex normals, welding vertices that
// share a position across UV seams and across the body's two primitives,
// (3) stores them as the base normals and zeroes the identity targets'
// NORMAL deltas, so that at the identity weights the shader normal is the
// true one, and (4) rebuilds tangents on the identity-shaped surface (TSL
// would otherwise derive them from the un-morphed base shape). Positions and
// morph weights are untouched; expression and viseme normal deltas remain.
import * as THREE from 'three/webgpu';

export const IDENTITY_PREFIXES = ['Inez_HeadFit_', 'Inez_HeadRefine_', 'Inez_SourceBodyFit_', 'Inez_SourceHeadWrap_',
  'Inez_FaceCorrect_', 'Inez_ScanWrap_'];

export interface AngleStats { median: number; p95: number; max: number }
export interface NormalCorrectionReport {
  meshes: string[];
  vertices: number;
  identityTargets: string[];
  weldedPositions: number;
  /** Angle between the renderer's normal (linear delta sum) and the corrected normal, before the fix. */
  beforeDeg: AngleStats;
  /** The same after the fix (0 unless a mesh could not be corrected). */
  afterDeg: AngleStats;
  tangentsRebuilt: boolean;
}

type MorphMesh = THREE.Mesh & { morphTargetDictionary: Record<string, number>; morphTargetInfluences: number[] };

export function isIdentityTarget(name: string): boolean {
  return IDENTITY_PREFIXES.some(prefix => name.startsWith(prefix));
}

function identityTargets(mesh: MorphMesh): Array<[string, number, number]> {
  return Object.entries(mesh.morphTargetDictionary ?? {})
    .filter(([name]) => isIdentityTarget(name))
    .map(([name, index]) => [name, index, mesh.morphTargetInfluences[index] ?? 0]);
}

export function stats(values: Float64Array | number[]): AngleStats {
  const sorted = Array.from(values).sort((a, b) => a - b);
  if (!sorted.length) return { median: 0, p95: 0, max: 0 };
  const at = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * (sorted.length - 1)))];
  return { median: at(.5), p95: at(.95), max: sorted[sorted.length - 1] };
}

/** Identity-shaped positions (attribute space) of one mesh. */
export function identityPositions(mesh: MorphMesh): Float64Array {
  const geometry = mesh.geometry;
  const position = geometry.getAttribute('position') as THREE.BufferAttribute;
  const out = new Float64Array(position.count * 3);
  for (let i = 0; i < position.count; i++) out.set([position.getX(i), position.getY(i), position.getZ(i)], 3 * i);
  const relative = geometry.morphTargetsRelative;
  for (const [, index, weight] of identityTargets(mesh)) {
    if (!weight) continue;
    const target = geometry.morphAttributes.position?.[index] as THREE.BufferAttribute | undefined;
    if (!target) continue;
    for (let i = 0; i < position.count; i++) {
      const dx = target.getX(i), dy = target.getY(i), dz = target.getZ(i);
      if (relative) { out[3 * i] += weight * dx; out[3 * i + 1] += weight * dy; out[3 * i + 2] += weight * dz; }
      else { out[3 * i] += weight * (dx - position.getX(i)); out[3 * i + 1] += weight * (dy - position.getY(i)); out[3 * i + 2] += weight * (dz - position.getZ(i)); }
    }
  }
  return out;
}

/** The normal the renderer would use: base normal plus weighted NORMAL deltas of every active target. */
function rendererNormals(mesh: MorphMesh): Float64Array {
  const geometry = mesh.geometry;
  const normal = geometry.getAttribute('normal') as THREE.BufferAttribute;
  const out = new Float64Array(normal.count * 3);
  for (let i = 0; i < normal.count; i++) out.set([normal.getX(i), normal.getY(i), normal.getZ(i)], 3 * i);
  const targets = geometry.morphAttributes.normal ?? [];
  mesh.morphTargetInfluences?.forEach((weight, index) => {
    const target = targets[index] as THREE.BufferAttribute | undefined;
    if (!weight || !target) return;
    for (let i = 0; i < normal.count; i++) {
      out[3 * i] += weight * target.getX(i); out[3 * i + 1] += weight * target.getY(i); out[3 * i + 2] += weight * target.getZ(i);
    }
  });
  for (let i = 0; i < normal.count; i++) {
    const l = Math.hypot(out[3 * i], out[3 * i + 1], out[3 * i + 2]) || 1;
    out[3 * i] /= l; out[3 * i + 1] /= l; out[3 * i + 2] /= l;
  }
  return out;
}

function indexArray(geometry: THREE.BufferGeometry): ArrayLike<number> {
  const index = geometry.getIndex();
  if (index) return index.array as ArrayLike<number>;
  return Array.from({ length: geometry.getAttribute('position').count }, (_, i) => i);
}

/**
 * Angle-weighted smooth normals over several meshes that share one
 * attribute space (primitives of one glTF mesh). Vertices are welded when
 * their identity-shaped positions agree within `weldTolerance` (attribute units).
 */
export function weldedNormals(positions: Float64Array[], indices: ArrayLike<number>[], weldTolerance = 1e-6): { normals: Float64Array[]; welded: number } {
  const keys = new Map<string, number>();
  const ids = positions.map(p => {
    const id = new Int32Array(p.length / 3);
    for (let i = 0; i < id.length; i++) {
      const key = `${Math.round(p[3 * i] / weldTolerance)},${Math.round(p[3 * i + 1] / weldTolerance)},${Math.round(p[3 * i + 2] / weldTolerance)}`;
      let k = keys.get(key);
      if (k === undefined) { k = keys.size; keys.set(key, k); }
      id[i] = k;
    }
    return id;
  });
  const sum = new Float64Array(keys.size * 3);
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3(), n = new THREE.Vector3();
  const e1 = new THREE.Vector3(), e2 = new THREE.Vector3();
  positions.forEach((p, m) => {
    const idx = indices[m];
    for (let t = 0; t + 2 < idx.length; t += 3) {
      const v = [idx[t], idx[t + 1], idx[t + 2]];
      a.fromArray(p, 3 * v[0]); b.fromArray(p, 3 * v[1]); c.fromArray(p, 3 * v[2]);
      n.subVectors(b, a).cross(e1.subVectors(c, a));
      if (n.lengthSq() === 0) continue;
      n.normalize();
      const corners = [[a, b, c], [b, c, a], [c, a, b]];
      corners.forEach(([o, p1, p2], k) => {
        const angle = e1.subVectors(p1, o).angleTo(e2.subVectors(p2, o));
        const id = ids[m][v[k]];
        sum[3 * id] += n.x * angle; sum[3 * id + 1] += n.y * angle; sum[3 * id + 2] += n.z * angle;
      });
    }
  });
  const normals = ids.map(id => {
    const out = new Float64Array(id.length * 3);
    for (let i = 0; i < id.length; i++) {
      const x = sum[3 * id[i]], y = sum[3 * id[i] + 1], z = sum[3 * id[i] + 2];
      const l = Math.hypot(x, y, z) || 1;
      out[3 * i] = x / l; out[3 * i + 1] = y / l; out[3 * i + 2] = z / l;
    }
    return out;
  });
  return { normals, welded: keys.size };
}

function angles(a: Float64Array, b: Float64Array): Float64Array {
  const out = new Float64Array(a.length / 3);
  for (let i = 0; i < out.length; i++) {
    const d = a[3 * i] * b[3 * i] + a[3 * i + 1] * b[3 * i + 1] + a[3 * i + 2] * b[3 * i + 2];
    out[i] = THREE.MathUtils.radToDeg(Math.acos(THREE.MathUtils.clamp(d, -1, 1)));
  }
  return out;
}

/** Rebuild tangents on the identity-shaped surface with the corrected normals. */
function identityTangents(mesh: MorphMesh, positions: Float64Array, normals: Float64Array): THREE.BufferAttribute | null {
  const geometry = mesh.geometry;
  const uv = geometry.getAttribute('uv') as THREE.BufferAttribute | undefined;
  const index = geometry.getIndex();
  if (!uv || !index) return null;
  const temp = new THREE.BufferGeometry();
  temp.setAttribute('position', new THREE.Float32BufferAttribute(Float32Array.from(positions), 3));
  temp.setAttribute('normal', new THREE.Float32BufferAttribute(Float32Array.from(normals), 3));
  const uvs = new Float32Array(uv.count * 2);
  for (let i = 0; i < uv.count; i++) { uvs[2 * i] = uv.getX(i); uvs[2 * i + 1] = uv.getY(i); }
  temp.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  temp.setIndex(new THREE.BufferAttribute(Uint32Array.from(index.array as ArrayLike<number>), 1));
  temp.computeTangents();
  return temp.getAttribute('tangent') as THREE.BufferAttribute;
}

/**
 * Correct every mesh in `meshes` (all must share one attribute space, such
 * as the primitives of the body). Returns what was measured and changed.
 */
export function correctIdentityNormals(meshes: THREE.Mesh[]): NormalCorrectionReport | null {
  const morphMeshes = meshes.filter(m => (m as MorphMesh).morphTargetDictionary && identityTargets(m as MorphMesh).some(([, , w]) => w)) as MorphMesh[];
  if (!morphMeshes.length) return null;
  const positions = morphMeshes.map(identityPositions);
  const before = morphMeshes.map(rendererNormals);
  const { normals, welded } = weldedNormals(positions, morphMeshes.map(m => indexArray(m.geometry)));
  const beforeAngles: number[] = [];
  morphMeshes.forEach((mesh, m) => {
    beforeAngles.push(...angles(before[m], normals[m]));
    const geometry = mesh.geometry;
    geometry.setAttribute('normal', new THREE.Float32BufferAttribute(Float32Array.from(normals[m]), 3));
    const morphNormals = geometry.morphAttributes.normal;
    if (morphNormals) {
      const count = geometry.getAttribute('position').count;
      const zero = new THREE.Float32BufferAttribute(new Float32Array(count * 3), 3);
      for (const [, index] of identityTargets(mesh)) if (morphNormals[index]) morphNormals[index] = zero;
    }
    const tangent = identityTangents(mesh, positions[m], normals[m]);
    if (tangent) geometry.setAttribute('tangent', tangent);
    mesh.userData.digitalHumanNormalsCorrected = true;
  });
  const after = morphMeshes.map(rendererNormals);
  const afterAngles: number[] = [];
  morphMeshes.forEach((_, m) => afterAngles.push(...angles(after[m], normals[m])));
  return {
    meshes: morphMeshes.map(m => m.name),
    vertices: positions.reduce((n, p) => n + p.length / 3, 0),
    identityTargets: [...new Set(morphMeshes.flatMap(m => identityTargets(m).filter(([, , w]) => w).map(([name]) => name)))],
    weldedPositions: welded,
    beforeDeg: stats(beforeAngles),
    afterDeg: stats(afterAngles),
    tangentsRebuilt: morphMeshes.every(m => m.geometry.hasAttribute('tangent')),
  };
}
