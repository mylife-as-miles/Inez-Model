// Inez Digital Human Lab: the real Inez GLB with the digital-human materials
// on WebGPURenderer (WebGPU, or its WebGL2 backend), plus controls and a QA
// API (window.inezDH) for fixed-camera comparisons.
//
// URL parameters (all optional):
//   backend=webgpu|webgl     renderer backend (default: WebGPU when available)
//   model=<file>             GLB under characters/inez/model/ (default inez_runtime.glb)
//   materials=dh|glb         start with digital-human or the GLB's own materials
//   normals=fixed|glb        recompute identity-layer normals at load (default fixed)
//   calibrated=1|0           calibrated skin albedo (default 1)
//   preset=studio|daylight|apartment|flashlight|backlight|practical
//   tonemap=neutral|agx|aces|none
//   view=face_front|face_34_left|face_34_right|face_profile_left|detail_cheek|body_front
//   skin=<JSON>              initial skin parameters, e.g. {"microNormal":0} (controlled comparisons)
import * as THREE from 'three/webgpu';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { AnimationController, EXPRESSION_NAMES, FacialControls, findBone as findBoneJS } from '../../character-controls.js';

const findBone = findBoneJS as unknown as (root: THREE.Object3D, name: string) => THREE.Object3D | null;
import { attachDigitalHuman, type DigitalHumanAttachment } from './attach.ts';
import { LightingRig, PRESETS, type LightingPresetName } from './lighting/presets.ts';
import type { SkinDebugView, SkinParams } from './skin/skin-material.ts';

const params = new URLSearchParams(location.search);
const assetRoot = (import.meta as unknown as { env?: { BASE_URL?: string } }).env?.BASE_URL ?? '/';
const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const TONE_MAPPINGS: Record<string, THREE.ToneMapping> = {
  neutral: THREE.NeutralToneMapping, agx: THREE.AgXToneMapping, aces: THREE.ACESFilmicToneMapping, none: THREE.NoToneMapping,
};
const VIEWS = ['face_front', 'face_34_left', 'face_34_right', 'face_profile_left', 'detail_cheek', 'body_front'] as const;
type ViewName = typeof VIEWS[number];

interface LabState {
  ready: boolean; error: string | null; backend: string; model: string; materials: 'digital' | 'glb'; normals: 'fixed' | 'glb';
  preset: LightingPresetName; toneMapping: string; exposure: number; view: ViewName; focalLengthMm: number;
  fps: number; cpuFrameMs: number; gpuFrameMs: number | null; drawCalls: number; triangles: number; warnings: string[];
}

const state: LabState = {
  ready: false, error: null, backend: '', model: params.get('model') ?? 'inez_runtime.glb',
  materials: params.get('materials') === 'glb' ? 'glb' : 'digital', normals: params.get('normals') === 'glb' ? 'glb' : 'fixed',
  preset: (params.get('preset') as LightingPresetName) in PRESETS ? params.get('preset') as LightingPresetName : 'studio',
  toneMapping: params.get('tonemap') ?? 'neutral', exposure: 1, view: (VIEWS as readonly string[]).includes(params.get('view') ?? '') ? params.get('view') as ViewName : 'face_front',
  focalLengthMm: 50, fps: 0, cpuFrameMs: 0, gpuFrameMs: null, drawCalls: 0, triangles: 0, warnings: [],
};

const canvas = $<HTMLCanvasElement>('render');
const wantWebGL = params.get('backend') === 'webgl';
const renderer = new THREE.WebGPURenderer({ canvas, antialias: true, forceWebGL: wantWebGL, trackTimestamp: true });
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(27, 1, 0.02, 60);
camera.filmGauge = 36; // full-frame width; setFocalLength uses it
scene.add(camera);
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
const lighting = new LightingRig(scene, camera);
const characterRoot = new THREE.Group();
scene.add(characterRoot);
const floor = new THREE.Mesh(new THREE.CircleGeometry(3, 64).rotateX(-Math.PI / 2), new THREE.MeshStandardMaterial({ color: '#5d6166', roughness: .9 }));
floor.receiveShadow = true;
scene.add(floor);

let avatar: THREE.Object3D | null = null;
let dh: DigitalHumanAttachment | null = null;
let motion: InstanceType<typeof AnimationController> | null = null;
let face: InstanceType<typeof FacialControls> | null = null;
let paused = false;
const head = new THREE.Vector3(0, 1.62, 0.05);
const faceCentre = new THREE.Vector3(0, 1.62, 0.08);

function resize() {
  const { clientWidth: w, clientHeight: h } = canvas.parentElement!;
  renderer.setSize(w, h, false);
  camera.aspect = w / Math.max(h, 1);
  camera.updateProjectionMatrix();
}

function setFocalLength(mm: number) {
  state.focalLengthMm = mm;
  camera.setFocalLength(mm); // 35 mm full-frame film gauge (camera.filmGauge = 35)
}

function setView(name: ViewName) {
  state.view = name;
  const vertical = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const isBody = name === 'body_front';
  // detail_cheek: 9 cm of the character's left cheek and nose wing, for pore-scale detail.
  const target = isBody ? new THREE.Vector3(faceCentre.x, 0.92, faceCentre.z)
    : name === 'detail_cheek' ? faceCentre.clone().add(new THREE.Vector3(0.028, -0.03, 0.04)) : faceCentre.clone();
  const span = isBody ? 1.95 : name === 'detail_cheek' ? 0.09 : 0.3;
  const distance = span / vertical;
  const yaw = { face_front: 0, face_34_left: 35, face_34_right: -35, face_profile_left: 90, detail_cheek: 20, body_front: 0 }[name];
  const direction = new THREE.Vector3(Math.sin(THREE.MathUtils.degToRad(yaw)), 0.02, Math.cos(THREE.MathUtils.degToRad(yaw))).normalize();
  camera.position.copy(target).addScaledVector(direction, distance);
  controls.target.copy(target);
  camera.lookAt(target);
  controls.update();
}

function setPreset(name: LightingPresetName) {
  state.preset = name;
  const preset = lighting.apply(name, head, renderer);
  state.exposure = preset.exposure;
  syncUI();
}

function setToneMapping(name: string) {
  state.toneMapping = name in TONE_MAPPINGS ? name : 'neutral';
  renderer.toneMapping = TONE_MAPPINGS[state.toneMapping];
}

function setExposure(value: number) { state.exposure = value; renderer.toneMappingExposure = value; }

async function load() {
  await renderer.init();
  state.backend = (renderer.backend as { isWebGPUBackend?: boolean }).isWebGPUBackend ? 'WebGPU' : 'WebGL2 (WebGPURenderer)';
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  setToneMapping(state.toneMapping);
  resize();
  await lighting.buildEnvironment(renderer);

  const ktx2 = new KTX2Loader().setTranscoderPath(`${assetRoot}basis/`);
  ktx2.detectSupport(renderer);
  const loader = new GLTFLoader().setKTX2Loader(ktx2).setMeshoptDecoder(MeshoptDecoder);
  const gltf = await loader.loadAsync(`${assetRoot}characters/inez/model/${state.model}`);
  avatar = gltf.scene;
  characterRoot.add(avatar);
  avatar.traverse(node => {
    const mesh = node as THREE.Mesh;
    if (mesh.isMesh) { mesh.castShadow = true; mesh.receiveShadow = true; mesh.frustumCulled = false; }
  });
  avatar.updateMatrixWorld(true);
  const eyeL = findBone(avatar, 'eye.L'), eyeR = findBone(avatar, 'eye.R'), headBone = findBone(avatar, 'head');
  if (eyeL && eyeR) {
    faceCentre.copy(eyeL.getWorldPosition(new THREE.Vector3())).add(eyeR.getWorldPosition(new THREE.Vector3())).multiplyScalar(.5);
    faceCentre.y -= 0.035;
  }
  if (headBone) headBone.getWorldPosition(head);

  let skin: Partial<SkinParams> = {};
  try { skin = JSON.parse(params.get('skin') ?? '{}'); } catch { state.warnings.push('Ignored unreadable skin= parameter.'); }
  dh = await attachDigitalHuman(avatar, { assetRoot, findBone, fixNormals: state.normals === 'fixed',
    calibrated: params.get('calibrated') !== '0', skin });
  dh.setMode(state.materials);

  const box = new THREE.Box3().setFromObject(avatar);
  face = new FacialControls(avatar);
  motion = new AnimationController(avatar, gltf.animations, box.max.y - box.min.y);
  setPreset(state.preset);
  setFocalLength(state.focalLengthMm);
  setView(state.view);
  buildUI(gltf.animations.map(a => a.name));
  state.ready = true;
  syncUI();
}

// --- UI -------------------------------------------------------------------
function slider(parent: HTMLElement, label: string, min: number, max: number, step: number, value: number, onInput: (v: number) => void, id?: string) {
  const row = document.createElement('label');
  row.className = 'row';
  const text = document.createElement('span');
  const out = document.createElement('output');
  const input = document.createElement('input');
  Object.assign(input, { type: 'range', min: String(min), max: String(max), step: String(step), value: String(value) });
  if (id) input.id = id;
  text.textContent = label;
  out.textContent = value.toFixed(3);
  input.oninput = () => { const v = Number(input.value); out.textContent = v.toFixed(3); onInput(v); };
  row.append(text, input, out);
  parent.append(row);
  return input;
}

function select(parent: HTMLElement, label: string, options: [string, string][], value: string, onChange: (v: string) => void, id?: string) {
  const row = document.createElement('label');
  row.className = 'row';
  const text = document.createElement('span');
  text.textContent = label;
  const input = document.createElement('select');
  if (id) input.id = id;
  for (const [v, l] of options) input.add(new Option(l, v, false, v === value));
  input.onchange = () => onChange(input.value);
  row.append(text, input);
  parent.append(row);
  return input;
}

function section(title: string) {
  const details = document.createElement('details');
  details.open = true;
  const summary = document.createElement('summary');
  summary.textContent = title;
  details.append(summary);
  $('panel').append(details);
  return details;
}

function buildUI(clips: string[]) {
  const m = section('Materials');
  select(m, 'Skin material', [['digital', 'Digital human (TSL)'], ['glb', 'GLB original (standard PBR)']], state.materials, v => { state.materials = v as 'digital' | 'glb'; dh?.setMode(state.materials); }, 'materials');
  select(m, 'Inspect', [['off', 'Shaded'], ['albedo', 'Albedo (calibrated)'], ['roughness', 'Roughness'], ['normal', 'Shading normal'], ['regions', 'Region masks'], ['micro', 'Micro height']],
    'off', v => dh?.setDebug(v as SkinDebugView), 'debug');
  const s = section('Skin');
  const p = dh!.params;
  const set = (update: Partial<SkinParams>) => dh?.setSkin(update);
  slider(s, 'Freckle detail', 0, 2, .01, p.freckleDetail, v => set({ freckleDetail: v }), 'freckle');
  slider(s, 'Roughness offset', -.3, .3, .005, p.roughnessOffset, v => set({ roughnessOffset: v }), 'roughness-offset');
  slider(s, 'T-zone roughness', -.3, .2, .005, p.tzoneRoughness, v => set({ tzoneRoughness: v }), 'tzone');
  slider(s, 'Lips roughness', -.3, .2, .005, p.lipsRoughness, v => set({ lipsRoughness: v }), 'lips');
  slider(s, 'Cheek roughness', -.2, .2, .005, p.cheeksRoughness, v => set({ cheeksRoughness: v }), 'cheeks');
  slider(s, 'Specular intensity', 0, 2, .01, p.specularIntensity, v => set({ specularIntensity: v }), 'specular');
  slider(s, 'IOR (F0)', 1.3, 1.6, .005, p.ior, v => set({ ior: v }), 'ior');
  slider(s, 'Primary normal', 0, 2, .01, p.primaryNormal, v => set({ primaryNormal: v }), 'primary-normal');
  slider(s, 'Micro-normal', 0, 1.5, .01, p.microNormal, v => set({ microNormal: v }), 'micro-normal');
  slider(s, 'Cavity', 0, .6, .01, p.cavity, v => set({ cavity: v }), 'cavity');
  const l = section('Lighting and colour');
  select(l, 'Environment', Object.values(PRESETS).map(pr => [pr.name, pr.label]), state.preset, v => setPreset(v as LightingPresetName), 'preset');
  select(l, 'Tone mapping', [['neutral', 'Khronos PBR Neutral'], ['agx', 'AgX'], ['aces', 'ACES Filmic'], ['none', 'None (clamp)']], state.toneMapping, setToneMapping, 'tonemap');
  slider(l, 'Exposure', .1, 4, .01, state.exposure, setExposure, 'exposure');
  slider(l, 'Environment light', 0, 2, .01, scene.environmentIntensity, v => { scene.environmentIntensity = v; }, 'env');
  const c = section('Camera');
  select(c, 'View', VIEWS.map(v => [v, v.replaceAll('_', ' ')]), state.view, v => setView(v as ViewName), 'view');
  slider(c, 'Focal length (mm)', 24, 135, 1, state.focalLengthMm, v => { setFocalLength(v); setView(state.view); }, 'focal');
  const a = section('Animation');
  select(a, 'Clip', [['rest', 'Rest pose'], ...clips.filter(n => !n.startsWith('Expr_')).map(n => [n, n] as [string, string])], 'rest', v => motion?.set(v, { transition: .3 }), 'clip');
  select(a, 'Expression', EXPRESSION_NAMES.map((n: string) => [n, n] as [string, string]), 'Neutral', v => face?.setExpression(v), 'expression');
  const pause = document.createElement('button');
  pause.textContent = 'Pause';
  pause.onclick = () => { paused = !paused; pause.textContent = paused ? 'Play' : 'Pause'; };
  a.append(pause);
}

function syncUI() {
  const preset = $<HTMLSelectElement>('preset');
  if (preset) preset.value = state.preset;
  const exposure = $<HTMLInputElement>('exposure');
  if (exposure) { exposure.value = String(state.exposure); (exposure.nextElementSibling as HTMLOutputElement).textContent = state.exposure.toFixed(3); }
  const env = $<HTMLInputElement>('env');
  if (env) { env.value = String(scene.environmentIntensity); (env.nextElementSibling as HTMLOutputElement).textContent = scene.environmentIntensity.toFixed(3); }
}

// --- Frame loop -------------------------------------------------------------
const timer = new THREE.Timer();
let frames = 0, statsStart = performance.now(), gpuPending = false;
function frame() {
  timer.update();
  const dt = paused ? 0 : Math.min(timer.getDelta(), 0.05);
  const t0 = performance.now();
  step(dt);
  controls.update();
  renderer.render(scene, camera);
  state.cpuFrameMs += ((performance.now() - t0) - state.cpuFrameMs) * .05;
  state.drawCalls = renderer.info.render.drawCalls;
  state.triangles = renderer.info.render.triangles;
  frames++;
  const now = performance.now();
  if (now - statsStart > 1000) {
    state.fps = frames * 1000 / (now - statsStart); frames = 0; statsStart = now;
    if (!gpuPending && renderer.hasFeature?.('timestamp-query')) {
      gpuPending = true;
      renderer.resolveTimestampsAsync(THREE.TimestampQuery.RENDER).then((ms: number | undefined) => { state.gpuFrameMs = ms ?? null; gpuPending = false; })
        .catch(() => { gpuPending = false; });
    }
    $('stats').textContent = `${state.backend} · ${state.fps.toFixed(1)} FPS · CPU ${state.cpuFrameMs.toFixed(2)} ms · GPU ${state.gpuFrameMs === null ? 'n/a' : state.gpuFrameMs.toFixed(2) + ' ms'} · ${state.drawCalls} draws · ${state.triangles.toLocaleString()} tris`;
  }
}

function step(dt: number) {
  if (!avatar) return;
  face?.restore();
  motion?.update(dt);
  face?.apply(dt, characterRoot.getWorldQuaternion(new THREE.Quaternion()));
  characterRoot.updateMatrixWorld(true);
}

window.addEventListener('resize', resize);

// --- QA API -----------------------------------------------------------------
declare global { interface Window { inezDH: Record<string, unknown> } }
(window as unknown as { __dhScene: THREE.Scene }).__dhScene = scene;
window.inezDH = {
  state,
  get attachment() { return dh?.describe() ?? null; },
  setPreset, setToneMapping, setExposure, setView, setFocalLength,
  setMode: (mode: 'digital' | 'glb') => { state.materials = mode; dh?.setMode(mode); },
  setDebug: (view: SkinDebugView) => dh?.setDebug(view),
  setSkin: (update: Partial<SkinParams>) => dh?.setSkin(update),
  setAnimation: (name: string) => motion?.set(name, { transition: 0 }),
  setExpression: (name: string) => face?.setExpression(name),
  pause: (value = true) => { paused = value; },
  advance: (seconds: number) => { let r = seconds; while (r > 1e-6) { const d = Math.min(r, 1 / 60); step(d); r -= d; } },
  /** Render one frame now and return it as a PNG data URL. */
  capture: async () => { controls.update(); await renderer.renderAsync(scene, camera); return canvas.toDataURL('image/png'); },
};

load().catch(error => { state.error = String(error?.stack ?? error); $('stats').textContent = `Error: ${error}`; console.error(error); })
  .finally(() => renderer.setAnimationLoop(frame));
