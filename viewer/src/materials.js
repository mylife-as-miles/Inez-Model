import * as THREE from 'three';

const materialList = material => Array.isArray(material) ? material : [material];
const textureSlots = ['map', 'normalMap', 'roughnessMap', 'metalnessMap', 'aoMap', 'emissiveMap', 'alphaMap'];
function imageSize(texture) {
  const image = texture?.image;
  return image ? [image.width || image.videoWidth || 0, image.height || image.videoHeight || 0] : null;
}
function rgbaPixels(texture) {
  const [width, height] = imageSize(texture);
  if (!width || !height) throw new Error(`Texture is unreadable: ${texture.name || texture.uuid}`);
  const image = texture.image;
  if (image.data && image.data.length === width * height * 4) return image.data;
  const canvas = document.createElement('canvas'); canvas.width = width; canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  context.drawImage(image, 0, 0, width, height);
  return context.getImageData(0, 0, width, height).data;
}
function copyTextureSampling(target, source) {
  for (const key of ['wrapS', 'wrapT', 'magFilter', 'minFilter', 'anisotropy', 'channel', 'flipY']) target[key] = source[key];
  target.offset.copy(source.offset); target.repeat.copy(source.repeat); target.center.copy(source.center);
  target.rotation = source.rotation; target.matrix.copy(source.matrix); target.matrixAutoUpdate = source.matrixAutoUpdate;
  target.colorSpace = THREE.NoColorSpace; target.generateMipmaps = true; target.needsUpdate = true;
  return target;
}
export function describeMaterial(material) {
  return { name: material.name || '(unnamed)', type: material.type, uuid: material.uuid,
    albedoFactor: material.color?.toArray(), roughness: material.roughness, metalness: material.metalness,
    transparent: material.transparent, alphaTest: material.alphaTest, doubleSided: material.side === THREE.DoubleSide,
    normalScale: material.normalScale?.toArray(), textures: Object.fromEntries(textureSlots.filter(slot => material[slot]).map(slot => [slot, {
      uuid: material[slot].uuid, size: imageSize(material[slot]), uvChannel: material[slot].channel,
      colorSpace: material[slot].colorSpace, roughnessChannel: slot === 'roughnessMap' ? 'G' : undefined
    }])) };
}

export class MaterialInspector {
  constructor(root) {
    this.root = root;
    this.originals = new Map();
    this.materials = new Map();
    this.initialWireframes = new Map();
    this.replacements = [];
    this.textureCache = new Map();
    this.mode = 'pbr'; this.selected = 'all'; this.wireframe = false;
    root.traverse(mesh => {
      if (!mesh.isMesh) return;
      this.originals.set(mesh, mesh.material);
      for (const material of materialList(mesh.material)) {
        this.materials.set(material.uuid, material);
        this.initialWireframes.set(material.uuid, material.wireframe);
      }
    });
  }

  roughnessTexture(material) {
    const texture = material.roughnessMap;
    if (!texture) return null;
    const cacheKey = `${texture.uuid}:${material.roughness ?? 1}`;
    if (this.textureCache.has(cacheKey)) return this.textureCache.get(cacheKey);
    const [width, height] = imageSize(texture);
    const pixels = rgbaPixels(texture);
    const output = new Uint8Array(width * height * 4);
    for (let i = 0; i < output.length; i += 4) {
      const green = Math.round(pixels[i + 1] * (material.roughness ?? 1));
      output[i] = output[i + 1] = output[i + 2] = green; output[i + 3] = 255;
    }
    const result = copyTextureSampling(new THREE.DataTexture(output, width, height, THREE.RGBAFormat), texture);
    this.textureCache.set(cacheKey, result);
    return result;
  }

  // glTF MASK/BLEND coverage lives in base-color alpha. Inspection replaces
  // RGB maps, so retain that alpha independently in Three.js' green channel.
  alphaTexture(material) {
    if (material.alphaMap) return material.alphaMap;
    const texture = material.map;
    if (!texture || (!material.transparent && !material.alphaTest)) return null;
    const key = `alpha:${texture.uuid}`;
    if (this.textureCache.has(key)) return this.textureCache.get(key);
    const [width, height] = imageSize(texture), pixels = rgbaPixels(texture);
    const output = new Uint8Array(width * height * 4);
    for (let i = 0; i < output.length; i += 4) {
      output[i] = output[i + 1] = output[i + 2] = pixels[i + 3]; output[i + 3] = 255;
    }
    const result = copyTextureSampling(new THREE.DataTexture(output, width, height, THREE.RGBAFormat), texture);
    this.textureCache.set(key, result); return result;
  }

  replacement(material) {
    const common = { side: material.side, transparent: material.transparent, opacity: material.opacity,
      alphaTest: material.alphaTest, depthWrite: material.depthWrite,
      wireframe: this.wireframe, toneMapped: false };
    let result;
    if (this.mode === 'normals') {
      result = new THREE.MeshNormalMaterial(common);
      // MeshNormalMaterial omits alpha support in its default fragment shader.
      // Use the real source coverage with the normal/skinning vertex pipeline.
      result.alphaMap = this.alphaTexture(material);
      result.onBeforeCompile = shader => {
        shader.fragmentShader = shader.fragmentShader.replace('#include <uv_pars_fragment>',
          '#include <uv_pars_fragment>\n#include <alphamap_pars_fragment>\n#include <alphatest_pars_fragment>')
          .replace('#include <clipping_planes_fragment>',
            '#include <clipping_planes_fragment>\n#include <alphamap_fragment>\n#include <alphatest_fragment>');
      };
      result.customProgramCacheKey = () => 'inez-normal-alpha-v1';
    }
    else if (this.mode === 'albedo') result = new THREE.MeshBasicMaterial({ ...common, alphaMap: material.alphaMap, color: material.color ?? 0xffffff, map: material.map });
    else if (this.mode === 'roughness') result = new THREE.MeshBasicMaterial({ ...common, alphaMap: this.alphaTexture(material), map: this.roughnessTexture(material),
      color: material.roughnessMap ? 0xffffff : new THREE.Color().setScalar(material.roughness ?? 1) });
    else if (this.mode === 'normal_map') {
      let texture;
      if (material.normalMap) {
        const key = `normal:${material.normalMap.uuid}`;
        if (!this.textureCache.has(key)) {
          const copy = material.normalMap.clone(); copy.colorSpace = THREE.SRGBColorSpace; copy.needsUpdate = true;
          this.textureCache.set(key, copy);
        }
        texture = this.textureCache.get(key);
      }
      result = new THREE.MeshBasicMaterial({ ...common, alphaMap: this.alphaTexture(material), map: texture ?? null, color: texture ? 0xffffff : new THREE.Color(.5, .5, 1) });
    }
    this.replacements.push(result);
    return result;
  }

  set(mode = this.mode, selected = this.selected, wireframe = this.wireframe) {
    if (!['pbr', 'albedo', 'roughness', 'normal_map', 'normals'].includes(mode) || (selected !== 'all' && !this.materials.has(selected))) return false;
    this.mode = mode; this.selected = selected; this.wireframe = Boolean(wireframe);
    for (const replacement of this.replacements) replacement.dispose();
    this.replacements = [];
    const cache = new Map();
    for (const material of this.materials.values()) material.wireframe = this.wireframe || this.initialWireframes.get(material.uuid);
    for (const [mesh, originals] of this.originals) {
      const inspect = material => {
        if (mode === 'pbr' || (selected !== 'all' && selected !== material.uuid)) return material;
        if (!cache.has(material.uuid)) cache.set(material.uuid, this.replacement(material));
        return cache.get(material.uuid);
      };
      mesh.material = Array.isArray(originals) ? originals.map(inspect) : inspect(originals);
    }
    return true;
  }

  get information() {
    const selected = this.selected === 'all' ? [...this.materials.values()] : [this.materials.get(this.selected)].filter(Boolean);
    return selected.map(describeMaterial);
  }
}
