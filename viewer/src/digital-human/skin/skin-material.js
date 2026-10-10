import * as THREE from 'three';
import { THICKNESS_ATTRIBUTE, THIN_REGION_ATTRIBUTE } from './thickness.js';

function microNormalTexture() {
  const size = 128, height = new Float32Array(size * size), data = new Uint8Array(size * size * 4);
  let seed = 107;
  for (let i = 0; i < height.length; i++) { seed = (1664525 * seed + 1013904223) >>> 0; height[i] = seed / 4294967296; }
  const sample = (x, y) => height[((y + size) % size) * size + (x + size) % size];
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const v = new THREE.Vector3((sample(x - 1, y) - sample(x + 1, y)) * .12,
      (sample(x, y - 1) - sample(x, y + 1)) * .12, 1).normalize();
    const i = 4 * (y * size + x); data[i] = (v.x * .5 + .5) * 255; data[i + 1] = (v.y * .5 + .5) * 255;
    data[i + 2] = (v.z * .5 + .5) * 255; data[i + 3] = 255;
  }
  const t = new THREE.DataTexture(data, size, size); t.colorSpace = THREE.NoColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping; t.magFilter = THREE.LinearFilter;
  t.minFilter = THREE.LinearMipmapLinearFilter; t.generateMipmaps = true; t.needsUpdate = true;
  return t;
}

const declarations = /* glsl */`
uniform float dhPass;
uniform float dhRoughnessVariation;
uniform float dhMicroIntensity;
uniform float dhThinEnabled;
uniform sampler2D dhMicroMap;
uniform sampler2D dhVisibleDepth;
uniform vec2 dhBufferSize;
uniform vec3 dhLightDirection;
uniform vec3 dhLightRadiance;
varying vec2 vDhUv;
varying float vDhThickness;
varying float vDhThinRegion;
`;

// r180 WebGL2 only. MeshStandardMaterial retains its GGX specular, real maps,
// vertex skinning, morph pipeline and shadows. WebGPU never receives this hook.
export function createSkinMaterial(original, sharedMicroMap = microNormalTexture()) {
  const material = original.clone(); material.name = original.name + '_DigitalHuman_v06';
  material.defaultAttributeValues = { [THICKNESS_ATTRIBUTE]: [.04], [THIN_REGION_ATTRIBUTE]: [0] };
  const uniforms = { dhPass: { value: 0 }, dhRoughnessVariation: { value: 1 }, dhMicroIntensity: { value: .15 },
    dhThinEnabled: { value: 0 }, dhMicroMap: { value: sharedMicroMap },
    dhVisibleDepth: { value: null }, dhBufferSize: { value: new THREE.Vector2(1,1) },
    dhLightDirection: { value: new THREE.Vector3(0, 0, 1) }, dhLightRadiance: { value: new THREE.Color() } };
  material.onBeforeCompile = shader => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader.replace('#include <common>', `#include <common>
attribute float ${THICKNESS_ATTRIBUTE}; attribute float ${THIN_REGION_ATTRIBUTE};
varying vec2 vDhUv; varying float vDhThickness; varying float vDhThinRegion;`)
      .replace('#include <uv_vertex>', `#include <uv_vertex>
vDhUv = uv; vDhThickness = ${THICKNESS_ATTRIBUTE}; vDhThinRegion = ${THIN_REGION_ATTRIBUTE};`);
    shader.fragmentShader = shader.fragmentShader.replace('#include <common>', '#include <common>\n' + declarations)
      .replace('#include <roughnessmap_fragment>', `#include <roughnessmap_fragment>
roughnessFactor = clamp(mix(0.52, roughnessFactor, dhRoughnessVariation), 0.18, 0.95);`)
      .replace('#include <normal_fragment_maps>', /* glsl */`#include <normal_fragment_maps>
vec2 dhDetailUv = vDhUv * 96.0;
vec3 dhMicro = texture2D(dhMicroMap, dhDetailUv).xyz * 2.0 - 1.0;
float dhFootprint = max(length(dFdx(dhDetailUv)), length(dFdy(dhDetailUv)));
float dhDetailWeight = dhMicroIntensity * (1.0 - smoothstep(0.3, 0.8, dhFootprint));
vec3 dhDp1 = dFdx(-vViewPosition), dhDp2 = dFdy(-vViewPosition);
vec2 dhDu1 = dFdx(vDhUv), dhDu2 = dFdy(vDhUv);
vec3 dhT = cross(dhDp2, normal) * dhDu1.x + cross(normal, dhDp1) * dhDu2.x;
vec3 dhB = cross(dhDp2, normal) * dhDu1.y + cross(normal, dhDp1) * dhDu2.y;
float dhInvScale = inversesqrt(max(max(dot(dhT,dhT),dot(dhB,dhB)),1e-12));
normal = normalize(normal + (dhT*dhMicro.x + dhB*dhMicro.y)*dhInvScale*dhDetailWeight);`)
      .replace('#include <opaque_fragment>', /* glsl */`
// Depth-only occluders drawn after skin cannot erase an earlier color write.
// Reject hidden skin against a single-sample scene depth at matching
// fragment centers. Beauty retains MSAA, without biasing this visibility.
if (dhPass > .5 && gl_FragCoord.z > texture2D(dhVisibleDepth,gl_FragCoord.xy/dhBufferSize).r + .0000002) discard;
// Beer-Lambert attenuation of back lighting, gated by a measured thin-region
// attribute. No ambient term and no emission: it goes dark when the light does.
float dhBack = max(dot(-nonPerturbedNormal, dhLightDirection), 0.0);
vec3 dhAttenuation = exp(-max(vDhThickness,0.0)*1000.0*vec3(0.45,1.2,2.1));
vec3 dhThin = dhThinEnabled*vDhThinRegion*dhBack*dhAttenuation*dhLightRadiance*diffuseColor.rgb*0.12;
totalDiffuse += dhThin; outgoingLight += dhThin;
if (dhPass > 1.5) { gl_FragColor = vec4(nonPerturbedNormal * .5 + .5, clamp(vDhThickness*50.0,0.001,1.0)); return; }
if (dhPass > .5) { gl_FragColor = vec4(totalDiffuse, 1.0); return; }
#include <opaque_fragment>`);
  };
  material.customProgramCacheKey = () => 'inez-skin-webgl-r180-v06-1';
  material.userData.digitalHuman = { backend: 'WebGL2', originalUUID: original.uuid };
  return { original, material, uniforms, microMap: sharedMicroMap };
}
