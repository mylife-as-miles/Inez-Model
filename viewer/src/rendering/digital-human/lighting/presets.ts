// Calibrated lighting environments for evaluating Inez's materials.
//
// All lighting is linear; the renderer applies one output transform (tone
// mapping, then sRGB encoding). Image-based lighting comes from three's
// RoomEnvironment (a neutral grey room with area-light panels, MIT, shipped
// with three) prefiltered into a PMREM. Each preset scales that environment
// and adds direct lights with shadows. Colours come from black-body
// temperatures, so "warm" and "cool" are physical rather than arbitrary.
//
// A  studio      soft key, controlled fill, subtle rim, neutral environment
// B  daylight    window light: large soft source from one side, sky fill
// C  apartment   dark room, one practical lamp (2700 K), high contrast
// D  flashlight  dim room, a small spot light at the camera (moves with it)
// E  backlight   strong light behind the head, weak fill: ears, fine hair
// F  practical   mixed warm (2700 K) and cool (6500 K / LED blue) sources
import * as THREE from 'three/webgpu';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export type LightingPresetName = 'studio' | 'daylight' | 'apartment' | 'flashlight' | 'backlight' | 'practical';

export interface LightingPreset {
  name: LightingPresetName;
  label: string;
  environmentIntensity: number;
  exposure: number;
  background: string;
  lights: LightSpec[];
}

interface LightSpec {
  type: 'directional' | 'spot' | 'point';
  kelvin: number;
  intensity: number;
  /** Position relative to the head (metres): x = character's left, y = up, z = in front. */
  offset: [number, number, number];
  shadow?: boolean;
  angleDeg?: number;
  penumbra?: number;
  distance?: number;
  /** Attach to the camera instead of the head (flashlight). */
  camera?: boolean;
  tint?: string;
}

/** Linear-sRGB colour of a black body (Tanner Helland's fit, then decoded to linear). */
export function kelvinToLinear(kelvin: number): THREE.Color {
  const t = kelvin / 100;
  const r = t <= 66 ? 255 : 329.698727446 * Math.pow(t - 60, -0.1332047592);
  const g = t <= 66 ? 99.4708025861 * Math.log(t) - 161.1195681661 : 288.1221695283 * Math.pow(t - 60, -0.0755148492);
  const b = t >= 66 ? 255 : t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  const c = (v: number) => THREE.MathUtils.clamp(v, 0, 255) / 255;
  const color = new THREE.Color().setRGB(c(r), c(g), c(b), THREE.SRGBColorSpace);
  // Normalise luminance so intensity alone sets brightness.
  const lum = 0.2126 * color.r + 0.7152 * color.g + 0.0722 * color.b;
  return color.multiplyScalar(1 / Math.max(lum, 1e-6));
}

export const PRESETS: Record<LightingPresetName, LightingPreset> = {
  studio: { name: 'studio', label: 'A · Neutral studio', environmentIntensity: 0.55, exposure: 1.0, background: '#7d8287',
    lights: [
      { type: 'directional', kelvin: 5600, intensity: 2.2, offset: [0.9, 0.7, 1.4], shadow: true },
      { type: 'directional', kelvin: 5600, intensity: 0.55, offset: [-1.2, 0.2, 1.0] },
      { type: 'directional', kelvin: 5600, intensity: 0.7, offset: [-0.6, 0.8, -1.4] },
    ] },
  daylight: { name: 'daylight', label: 'B · Daylight window', environmentIntensity: 0.7, exposure: 0.9, background: '#a9b4bf',
    lights: [
      { type: 'directional', kelvin: 6500, intensity: 3.0, offset: [1.6, 0.6, 0.6], shadow: true },
      { type: 'directional', kelvin: 9000, intensity: 0.35, offset: [-0.5, 1.4, 1.0] },
    ] },
  apartment: { name: 'apartment', label: 'C · Dark apartment', environmentIntensity: 0.04, exposure: 1.6, background: '#141414',
    lights: [
      { type: 'point', kelvin: 2700, intensity: 2.2, offset: [0.75, 0.15, 0.7], shadow: true, distance: 6 },
    ] },
  flashlight: { name: 'flashlight', label: 'D · Phone flashlight', environmentIntensity: 0.02, exposure: 1.4, background: '#0b0b0c',
    lights: [
      { type: 'spot', kelvin: 5500, intensity: 6.0, offset: [0.05, -0.05, 0], shadow: true, angleDeg: 22, penumbra: 0.6, distance: 8, camera: true },
    ] },
  backlight: { name: 'backlight', label: 'E · Strong backlight', environmentIntensity: 0.12, exposure: 1.2, background: '#1b1d20',
    lights: [
      { type: 'directional', kelvin: 5200, intensity: 6.0, offset: [0.35, 0.45, -1.6], shadow: true },
      { type: 'directional', kelvin: 6000, intensity: 0.25, offset: [-0.4, 0.2, 1.4] },
    ] },
  practical: { name: 'practical', label: 'F · Mixed practical lights', environmentIntensity: 0.06, exposure: 1.4, background: '#16171a',
    lights: [
      { type: 'point', kelvin: 2700, intensity: 1.6, offset: [0.8, 0.1, 0.6], shadow: true, distance: 6 },
      { type: 'point', kelvin: 6500, intensity: 0.9, offset: [-0.8, 0.3, 0.5], distance: 6, tint: '#9fb8ff' },
    ] },
};

export class LightingRig {
  readonly group = new THREE.Group();
  readonly cameraGroup = new THREE.Group();
  current: LightingPreset = PRESETS.studio;
  private environment: THREE.Texture | null = null;
  private scene: THREE.Scene;

  constructor(scene: THREE.Scene, camera: THREE.Camera) {
    this.scene = scene;
    this.group.name = 'DigitalHumanLights';
    this.cameraGroup.name = 'DigitalHumanCameraLights';
    scene.add(this.group);
    camera.add(this.cameraGroup);
  }

  async buildEnvironment(renderer: THREE.WebGPURenderer): Promise<void> {
    const pmrem = new THREE.PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    const target = await pmrem.fromSceneAsync(room, 0.04);
    this.environment = target.texture;
    this.scene.environment = this.environment;
    pmrem.dispose();
  }

  /** Apply a preset around the head position `head` (world). */
  apply(name: LightingPresetName, head: THREE.Vector3, renderer: THREE.WebGPURenderer): LightingPreset {
    const preset = PRESETS[name];
    this.current = preset;
    for (const group of [this.group, this.cameraGroup]) {
      for (const child of [...group.children]) { group.remove(child); (child as THREE.Light).dispose?.(); }
    }
    this.scene.environment = this.environment;
    this.scene.environmentIntensity = preset.environmentIntensity;
    this.scene.background = new THREE.Color(preset.background);
    renderer.toneMappingExposure = preset.exposure;
    for (const spec of preset.lights) {
      const color = kelvinToLinear(spec.kelvin);
      if (spec.tint) color.multiply(new THREE.Color(spec.tint));
      let light: THREE.DirectionalLight | THREE.SpotLight | THREE.PointLight;
      if (spec.type === 'directional') light = new THREE.DirectionalLight(color, spec.intensity);
      else if (spec.type === 'spot') light = new THREE.SpotLight(color, spec.intensity, spec.distance ?? 0, THREE.MathUtils.degToRad(spec.angleDeg ?? 30), spec.penumbra ?? 0.5, 2);
      else light = new THREE.PointLight(color, spec.intensity, spec.distance ?? 0, 2);
      const [x, y, z] = spec.offset;
      if (spec.camera) {
        light.position.set(x, y, z);
        this.cameraGroup.add(light);
        if (light instanceof THREE.SpotLight) { light.target.position.set(0, 0, -1); this.cameraGroup.add(light.target); }
      } else {
        light.position.copy(head).add(new THREE.Vector3(x, y, z));
        this.group.add(light);
        if (light instanceof THREE.DirectionalLight || light instanceof THREE.SpotLight) {
          light.target.position.copy(head);
          this.group.add(light.target);
        }
      }
      if (spec.shadow) {
        light.castShadow = true;
        light.shadow.mapSize.set(2048, 2048);
        light.shadow.bias = -0.0002;
        light.shadow.normalBias = 0.01;
        if (light instanceof THREE.DirectionalLight) {
          const cam = light.shadow.camera;
          cam.left = -0.5; cam.right = 0.5; cam.top = 0.5; cam.bottom = -1.4; cam.near = 0.1; cam.far = 6;
        }
      }
    }
    return preset;
  }
}
