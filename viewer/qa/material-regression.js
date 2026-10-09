import * as THREE from 'three';
import { MaterialInspector } from '../src/materials.js';

// Tiny detached geometry checks inspector rendering only. These are module
// regression fixtures, never a replacement character or asset approval.
export function runMaterialRegression() {
  const canvas = document.createElement('canvas');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, preserveDrawingBuffer: true });
  renderer.setSize(32, 16); renderer.setClearColor(0xff00ff, 1);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene(), root = new THREE.Group(); scene.add(root);
  const colorMap = new THREE.DataTexture(new Uint8Array([255, 255, 255, 0, 255, 255, 255, 255]), 2, 1);
  colorMap.magFilter = colorMap.minFilter = THREE.NearestFilter; colorMap.needsUpdate = true;
  const orm = new THREE.DataTexture(new Uint8Array([34, 128, 240, 255, 34, 128, 240, 255]), 2, 1);
  orm.magFilter = orm.minFilter = THREE.NearestFilter; orm.needsUpdate = true;
  const original = new THREE.MeshStandardMaterial({ map: colorMap, roughnessMap: orm, roughness: .5, alphaTest: .5 });
  const geometry = new THREE.PlaneGeometry(2, 2), mesh = new THREE.Mesh(geometry, original); root.add(mesh);
  const inspector = new MaterialInspector(root);
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, .1, 10); camera.position.z = 2;
  const gl = renderer.getContext(), checks = {};
  const read = x => { const pixel = new Uint8Array(4); gl.readPixels(x, 8, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel); return [...pixel]; };
  try {
    for (const mode of ['albedo', 'roughness', 'normal_map', 'normals']) {
      inspector.set(mode); renderer.render(scene, camera);
      const discarded = read(4), drawn = read(24);
      const isClear = p => p[0] === 255 && p[1] === 0 && p[2] === 255;
      checks[`${mode}_retains_base_color_alpha`] = isClear(discarded) && !isClear(drawn);
      if (mode === 'roughness') checks.roughness_uses_green_times_factor = mesh.material.map.image.data[0] === 64;
    }
    inspector.set('pbr'); checks.restores_original_material = mesh.material === original;
    checks.rejects_unknown_mode = inspector.set('invalid') === false;
    checks.rejects_unknown_material = inspector.set('albedo', 'invalid') === false;
    if (!Object.values(checks).every(Boolean)) throw new Error(`Material fixture regression: ${JSON.stringify(checks)}`);
    return { scope: 'Synthetic detached material fixtures only; no character GLB used.', checks };
  } finally {
    inspector.set('pbr'); for (const texture of inspector.textureCache.values()) texture.dispose();
    colorMap.dispose(); orm.dispose(); original.dispose(); geometry.dispose(); renderer.dispose();
  }
}
