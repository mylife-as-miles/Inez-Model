import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { KTX2Loader } from 'three/addons/loaders/KTX2Loader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';
import { FacialControls, AnimationController, findBone } from './character-controls.js';
import { MaterialInspector, describeMaterial } from './materials.js';
import { AnimationLab, TERRAINS } from './animation-lab.js';
import { DigitalHumanRegistry } from './digital-human/material-registry.js';
import { DIGITAL_HUMAN_LIGHTS } from './digital-human/lighting/digital-human-presets.js';
import './style.css';

const $ = id => document.getElementById(id);
const assetRoot = '/characters/inez/';
const errors = [];
const warnings = [];
const state = { ready: false, loading: true, backend: 'WebGL2', requestedBackend: 'WebGL2', error: null,
  animationNames: [], morphNames: [], resourceBytes: 0, assetInfo: null, paused: false, currentAnimation: 'rest',
  animationMode: 'rest', actionWeights: {}, clipTime: 0, clipDuration: 0, playbackRate: 1, transition: .35,
  locomotionSpeed: 0, previewSpeed: 0, characterPosition: [0, 0, 0], characterYaw: 0, velocity: [0, 0, 0],
  view: 'body_front', lighting: 'studio', inspection: 'pbr', material: 'all', wireframe: false, capture: false,
  lightControls: { exposure: 1, key: 1, fill: 1, ambient: 1 }, facialControls: {}, fps: 0 };
const recordError = error => { const message = error?.message ?? String(error); errors.push(message); return message; };
window.addEventListener('error', event => recordError(event.error ?? event.message));
window.addEventListener('unhandledrejection', event => recordError(event.reason));

const scene = new THREE.Scene();
scene.background = new THREE.Color('#c8ccd0');
const characterRoot = new THREE.Group(); characterRoot.name = 'Inez_PlayerPosition'; scene.add(characterRoot);
const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, .005, 100);
camera.position.set(0, .9, 4);
let renderer;
const gpuRequested = new URLSearchParams(location.search).get('renderer') === 'webgpu';
state.requestedBackend = gpuRequested ? 'WebGPU' : 'WebGL2';
if (gpuRequested && navigator.gpu) {
  try {
    const { WebGPURenderer } = await import('three/webgpu');
    renderer = new WebGPURenderer({ canvas: $('render'), antialias: true });
    await renderer.init();
    state.backend = renderer.backend.isWebGPUBackend ? 'WebGPU' : 'WebGL2 (WebGPU fallback)';
  } catch (error) {
    warnings.push(`Requested WebGPU initialization failed: ${error.message}`);
    renderer?.dispose(); renderer = null;
  }
} else if (gpuRequested) warnings.push('WebGPU is unavailable in this browser; using WebGL2.');
renderer ??= new THREE.WebGLRenderer({ canvas: $('render'), antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1;
if (renderer.shadowMap) { renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap; }
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true; controls.target.set(0, .9, 0); controls.minZoom = .3; controls.maxZoom = 8;
const hemisphere = new THREE.HemisphereLight('#ffffff', '#777e83', 1.05);
const key = new THREE.DirectionalLight('#ffffff', 2.1);
const fill = new THREE.DirectionalLight('#e5ecf2', .8);
const rim = new THREE.DirectionalLight('#ffffff', .65);
key.position.set(-2.5, 3.5, 4); fill.position.set(3, 2, 2); rim.position.set(1, 3, -3);
key.castShadow = true; key.shadow.mapSize.set(1024, 1024);
key.shadow.camera.left = key.shadow.camera.bottom = -3;
key.shadow.camera.right = key.shadow.camera.top = 3;
key.shadow.camera.near = .1; key.shadow.camera.far = 15; key.shadow.bias = -.0001;
scene.add(hemisphere, key, key.target, fill, fill.target, rim, rim.target);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(24, 24), new THREE.MeshStandardMaterial({ color: '#b6bcc1', roughness: .95 }));
ground.rotation.x = -Math.PI / 2; ground.position.y = -.002; ground.receiveShadow = true; scene.add(ground);
let avatar, motion, face, inspector, lab, digitalHuman;
const timing = { animation_ms: 0, render_ms: 0, lab_ms: 0 };
let height = 1.7, span = 1.95;
const allInitialMorphs = new Map();
const keys = new Set();
const velocity = new THREE.Vector3();
const scriptedDirection = new THREE.Vector3(0, 0, 1);
let scriptedMovement = false;
let captureRestore;

function resize() {
  const { width, height: viewportHeight } = $('viewport').getBoundingClientRect();
  const aspect = width / Math.max(viewportHeight, 1);
  camera.left = -span * aspect / 2; camera.right = span * aspect / 2;
  camera.top = span / 2; camera.bottom = -span / 2;
  camera.updateProjectionMatrix(); renderer.setSize(Math.max(width, 1), Math.max(viewportHeight, 1), false);
}
new ResizeObserver(resize).observe($('viewport'));
function setView(name = 'body_front') {
  if (![...$('view').options].some(option => option.value === name)) return false;
  state.view = name; $('view').value = name;
  const portrait = name.startsWith('face_');
  const targetY = characterRoot.position.y + height * (portrait ? .897 : .51);
  span = height * (portrait ? .30 : 1.15);
  let angle = characterRoot.rotation.y;
  if (name.endsWith('_left')) angle += Math.PI / 2;
  if (name.endsWith('_right')) angle -= Math.PI / 2;
  if (name.endsWith('_back')) angle += Math.PI;
  if (name.endsWith('three_quarter')) angle += Math.PI / 4;
  controls.target.set(characterRoot.position.x, targetY, characterRoot.position.z);
  const distance = Math.max(4, height * 3);
  camera.position.set(controls.target.x + Math.sin(angle) * distance, targetY, controls.target.z + Math.cos(angle) * distance);
  camera.zoom = 1; const damping = controls.enableDamping; controls.enableDamping = false;
  controls.update(); controls.enableDamping = damping; resize(); renderFrame();
  return true;
}

const lightingPresets = DIGITAL_HUMAN_LIGHTS;
function applyLighting() {
  const preset = lightingPresets[state.lighting]; const multipliers = state.lightControls;
  scene.background.set(preset.background); ground.material.color.set(preset.ground);
  hemisphere.intensity = preset.ambient * multipliers.ambient;
  hemisphere.groundColor.set(preset.groundColor ?? '#777e83');
  key.intensity = preset.key * multipliers.key; key.color.set(preset.keyColor);
  fill.intensity = preset.fill * multipliers.fill; fill.color.set(preset.fillColor); rim.intensity = preset.rim;
  renderer.toneMappingExposure = multipliers.exposure;
  syncCharacterLights();
  for (const [name, value] of Object.entries(multipliers)) {
    const id = { exposure: 'exposure', key: 'key-light', fill: 'fill-light', ambient: 'ambient-light' }[name];
    $(id).value = value; $(`${id}-value`).textContent = value.toFixed(2) + (name === 'exposure' ? '' : '×');
  }
}
function setLighting(preset = state.lighting, values) {
  if (!lightingPresets[preset]) return false;
  state.lighting = preset; $('lighting').value = preset;
  state.lightControls = { exposure: 1, key: 1, fill: 1, ambient: 1, ...values };
  setLightControls(state.lightControls); return true;
}
function setLightControls(values = {}) {
  for (const name of ['exposure', 'key', 'fill', 'ambient']) if (name in values) state.lightControls[name] = THREE.MathUtils.clamp(Number(values[name]) || 0, name === 'exposure' ? .25 : 0, name === 'exposure' ? 2.5 : 3);
  applyLighting(); renderFrame(); return { ...state.lightControls };
}

function syncFaceUI() {
  if (!face) return;
  const v = face.values; state.facialControls = { ...v };
  $('expression').value = v.expression || 'Neutral'; $('viseme').value = v.viseme || 'none'; $('auto-blink').checked = v.autoBlink;
  const ids = { expressionStrength: 'expression-strength', visemeStrength: 'viseme-strength', blinkLeft: 'blink-left', blinkRight: 'blink-right',
    jaw: 'jaw', eyeYaw: 'eye-yaw', eyePitch: 'eye-pitch', headYaw: 'head-yaw', headPitch: 'head-pitch', headRoll: 'head-roll' };
  for (const [name, id] of Object.entries(ids)) {
    $(id).value = v[name]; $(`${id}-value`).textContent = /Yaw|Pitch|Roll/.test(name) ? `${v[name].toFixed(0)}°` : v[name].toFixed(2);
  }
}
function setExpression(name = 'Neutral', strength = 1) {
  if (!face || !face.setExpression(name, strength)) return false;
  syncFaceUI(); refreshPose(); return true;
}
function setViseme(name = '', strength = 1) {
  if (!face || !face.setViseme(name, strength)) return false;
  syncFaceUI(); refreshPose(); return true;
}
function setFaceControls(values = {}) {
  if (!face) return false;
  face.set(values); syncFaceUI(); refreshPose(); return { ...face.values };
}
function resetFace() { if (!face) return false; face.reset(); syncFaceUI(); refreshPose(); return true; }
function setAnimation(name = 'rest', options = {}) {
  if (!motion) return false;
  face?.restore();
  if (!motion.set(name, options)) { refreshPose(); return false; }
  state.currentAnimation = motion.current; state.animationMode = motion.mode;
  $('animation').value = motion.current;
  if (motion.mode !== 'automatic') { state.previewSpeed = 0; velocity.set(0, 0, 0); scriptedMovement = false; $('movement-speed').value = 0; }
  refreshPose(); syncAnimationUI(); return true;
}
// One-shot body clips: a turn ends with the root rotated, so its yaw moves to
// the character and the idle pose resumes seamlessly; crouch transitions
// chain into the crouch loop or back to locomotion.
function clipFinished(action) {
  const name = motion?.clipName(action);
  if (!name || motion.overlays.has(name)) { syncAnimationUI(); return; }
  const info = motion.clipInfo[name] ?? {};
  if (info.root_rotation_deg) {
    characterRoot.rotation.y += THREE.MathUtils.degToRad(info.root_rotation_deg);
    setAnimation(Object.keys(motion.roles).length ? 'automatic' : 'Idle', { transition: 0 });
  } else if (name === 'CrouchDown') setAnimation('Crouch', { transition: 0 });
  else if (name === 'CrouchUp') setAnimation(Object.keys(motion.roles).length ? 'automatic' : 'Idle', { transition: 0 });
}
function turn(direction = 'Left') {
  const name = 'Turn' + (String(direction).toLowerCase().startsWith('r') ? 'Right' : 'Left');
  return setAnimation(name, { transition: .15 });
}
function crouch(on = true) {
  state.crouching = Boolean(on); $('crouch').textContent = state.crouching ? 'Stand up' : 'Crouch';
  return setAnimation(state.crouching ? 'CrouchDown' : 'CrouchUp', { transition: .2 });
}
function playPerformance(name = $('performance').value, weight = 1) {
  if (!motion) return false;
  const played = motion.playOverlay(name, weight);
  state.performance = played || null; return Boolean(played);
}
function stopPerformance() { if (!motion) return false; motion.stopOverlay(); state.performance = null; return true; }
function setPlaybackSpeed(rate = 1) {
  if (!motion) return false;
  motion.setRate(rate); state.playbackRate = motion.playbackRate;
  $('playback-speed').value = state.playbackRate; $('playback-speed-value').textContent = `${state.playbackRate.toFixed(2)}×`;
  return true;
}
function setLocomotionSpeed(speed = 0, options = {}) {
  if (!motion || !Object.keys(motion.roles).length) return false;
  if (motion.mode !== 'automatic') setAnimation('automatic', { transition: 0 });
  state.previewSpeed = THREE.MathUtils.clamp(Number(speed) || 0, 0, motion.runSpeed);
  $('movement-speed').value = state.previewSpeed;
  scriptedMovement = Boolean(options.move);
  if (options.direction) scriptedDirection.fromArray(options.direction).setY(0).normalize();
  if (options.immediate !== false) refreshPose();
  return true;
}
function pause(on = true) {
  state.paused = Boolean(on); $('pause').textContent = state.paused ? 'Resume' : 'Pause';
  refreshPose(); return state.paused;
}
function seek(seconds = 0) {
  if (!motion) return false;
  face?.restore(); motion.seek(seconds);
  face?.apply(0, characterRoot.getWorldQuaternion(new THREE.Quaternion()));
  updateState(); syncAnimationUI(); renderFrame(); return state.clipTime;
}
function resetPosition() {
  if (!avatar) return false;
  const oldPosition = characterRoot.position.clone();
  characterRoot.position.set(0, 0, 0); characterRoot.rotation.set(0, 0, 0);
  velocity.set(0, 0, 0); keys.clear(); scriptedMovement = false; state.previewSpeed = 0; $('movement-speed').value = 0;
  controls.target.sub(oldPosition); camera.position.sub(oldPosition);
  refreshPose(); return true;
}
function syncCharacterLights() {
  key.position.copy(characterRoot.position).add(new THREE.Vector3(...(lightingPresets[state.lighting].keyOffset ?? [-2.5, 3.5, 4])));
  fill.position.copy(characterRoot.position).add(new THREE.Vector3(3, 2, 2));
  rim.position.copy(characterRoot.position).add(new THREE.Vector3(1, 3, -3));
  for (const light of [key, fill, rim]) light.target.position.copy(characterRoot.position).add(new THREE.Vector3(0, height * .5, 0));
}
function updateMovement(delta) {
  const before = characterRoot.position.clone();
  const targetVelocity = new THREE.Vector3();
  if (state.ready && motion?.mode === 'automatic') {
    const x = (keys.has('KeyD') || keys.has('ArrowRight') ? 1 : 0) - (keys.has('KeyA') || keys.has('ArrowLeft') ? 1 : 0);
    const z = (keys.has('KeyW') || keys.has('ArrowUp') ? 1 : 0) - (keys.has('KeyS') || keys.has('ArrowDown') ? 1 : 0);
    if (x || z) {
      const forward = controls.target.clone().sub(camera.position).setY(0).normalize();
      const right = forward.clone().cross(new THREE.Vector3(0, 1, 0));
      const direction = forward.multiplyScalar(z).addScaledVector(right, x).normalize();
      targetVelocity.copy(direction).multiplyScalar(keys.has('ShiftLeft') || keys.has('ShiftRight') ? motion.runSpeed : motion.walkSpeed);
    } else if (scriptedMovement) targetVelocity.copy(scriptedDirection).multiplyScalar(state.previewSpeed);
  }
  velocity.lerp(targetVelocity, 1 - Math.exp(-delta * 10));
  if (velocity.lengthSq() < .000001) velocity.set(0, 0, 0);
  characterRoot.position.addScaledVector(velocity, delta);
  if (velocity.lengthSq() > .0001) {
    const desiredYaw = Math.atan2(velocity.x, velocity.z);
    const difference = Math.atan2(Math.sin(desiredYaw - characterRoot.rotation.y), Math.cos(desiredYaw - characterRoot.rotation.y));
    characterRoot.rotation.y += difference * (1 - Math.exp(-delta * 12));
  }
  const displacement = characterRoot.position.clone().sub(before);
  if ($('follow').checked) { controls.target.add(displacement); camera.position.add(displacement); }
  syncCharacterLights();
  state.locomotionSpeed = motion?.mode === 'automatic' ? Math.max(velocity.length(), state.previewSpeed) : 0;
}
function updateState() {
  state.characterPosition = characterRoot.position.toArray(); state.characterYaw = characterRoot.rotation.y; state.velocity = velocity.toArray();
  if (motion) {
    state.currentAnimation = motion.current; state.animationMode = motion.mode; state.actionWeights = motion.weights;
    state.clipTime = motion.time; state.clipDuration = motion.duration; state.playbackRate = motion.playbackRate;
    state.performance = motion.overlayName;
  }
  if (face) state.facialControls = { ...face.values };
  state.renderStats = { triangles: renderer.info.render.triangles, drawCalls: renderer.info.render.calls,
    geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures };
}
function syncAnimationUI() {
  if (!motion) return;
  $('timeline').max = Math.max(motion.duration, .001); $('timeline').value = motion.time;
  $('timeline').disabled = !motion.duration;
  $('timeline-value').textContent = `${motion.time.toFixed(2)} / ${motion.duration.toFixed(2)} s`;
  $('movement-speed-value').textContent = `${state.locomotionSpeed.toFixed(2)} m/s`;
  const weights = Object.entries(state.actionWeights).filter(([, weight]) => weight > .001).map(([name, weight]) => `${name} ${(weight * 100).toFixed(0)}%`).join(' · ');
  const missing = ['Idle', 'Walk', 'Run'].filter(name => !motion.roles[name]);
  $('blend-info').textContent = motion.mode === 'rest' ? 'Exported rest pose. No clip is playing.' : `${weights || 'No clip contributes.'}${missing.length ? ` · Missing: ${missing.join(', ')}` : ''}`;
}
function refreshPose() {
  face?.restore(); updateMovement(0); motion?.update(0, state.locomotionSpeed, true);
  face?.apply(0, characterRoot.getWorldQuaternion(new THREE.Quaternion()));
  characterRoot.updateMatrixWorld(true); renderFrame(); updateState(); syncAnimationUI();
}
// Explicit fixed steps also work while paused, for repeatable QA of real
// mixer fades, skeleton deformation and translation. No pose is synthesized.
// The lab (travel, contact tracking) steps with the mixer; { render: false }
// skips the draw for sampling loops on slow software renderers.
function advance(seconds = 0, { render = true } = {}) {
  if (!avatar) return false;
  let remaining = THREE.MathUtils.clamp(Number(seconds) || 0, 0, 10);
  while (remaining > .000001) {
    const delta = Math.min(remaining, 1 / 60);
    face?.restore(); updateMovement(delta); motion?.update(delta, state.locomotionSpeed);
    face?.apply(delta, characterRoot.getWorldQuaternion(new THREE.Quaternion()));
    lab?.update(delta, followCamera); remaining -= delta;
  }
  characterRoot.updateMatrixWorld(true); if (render) renderFrame(); updateState(); syncAnimationUI(); syncLabUI(); return state.clipTime;
}
function renderFrame() {
  digitalHuman?.updateLight(camera, key);
  if (!digitalHuman?.render(scene, camera, state.inspection)) renderer.render(scene, camera);
}
function syncSkinUI() {
  if (!digitalHuman) return;
  const s = digitalHuman.settings;
  $('skin-mode').value = s.mode; $('skin-sss').checked = s.sss; $('skin-thin').checked = s.thinTransmission;
  $('skin-debug').value = s.debug; $('skin-quality').value = s.quality;
  for (const [key, id] of Object.entries({ strength: 'skin-strength', radius: 'skin-radius', roughnessVariation: 'skin-roughness', microNormal: 'skin-micro' })) {
    $(id).value = s[key]; $(`${id}-value`).textContent = s[key].toFixed(2) + (key === 'radius' ? '× mm profile' : '');
  }
  $('skin-info').textContent = JSON.stringify(digitalHuman.diagnostics, null, 1);
  state.digitalHuman = digitalHuman.diagnostics;
}
function setSkin(values = {}) {
  if (!digitalHuman) return false;
  digitalHuman.configure(values); digitalHuman.apply(state.inspection); syncSkinUI(); renderFrame();
  state.digitalHuman = digitalHuman.diagnostics; return { ...digitalHuman.settings };
}
function screenshot() {
  refreshPose(); const a = document.createElement('a');
  a.download = `inez-${state.view}-${state.lighting}-${digitalHuman?.settings.mode ?? 'pbr'}.png`;
  a.href = renderer.domElement.toDataURL('image/png'); a.click(); return a.href;
}
function followCamera(step) {
  if (!$('follow').checked) return;
  controls.target.add(step); camera.position.add(step);
}
function syncLabUI() {
  if (!lab || !motion) return;
  const name = motion.mode === 'manual' ? motion.current : motion.mode;
  const source = lab.source(name);
  const info = motion.clipInfo[name] ?? {};
  $('clip-source').textContent = !source ? 'Clip source: none (rest pose or automatic blend of procedural clips).'
    : `Clip source: ${source.label}${source.terra ? '' : ' · not TERRA'}${info.matching_speed_m_s ? ` · in place, matching speed ${info.matching_speed_m_s.toFixed(2)} m/s` : ''}${source.licence ? ' · ' + source.licence : ''}`;
  state.lab = { terrain: lab.terrain, options: { ...lab.options }, contacts: [...lab.stats.contacts],
    lastPhaseSlipMm: [...lab.stats.lastPhaseSlipMm], maxPhaseSlipMm: [...lab.stats.maxPhaseSlipMm],
    penetrationMm: [...lab.stats.penetrationMm], timing: { ...timing }, source: source ?? null };
  const bone = $('lab-bone').value ? lab.boneInfo($('lab-bone').value) : null;
  $('lab-info').textContent = JSON.stringify({ feet: { L: lab.stats.contacts[0], R: lab.stats.contacts[1] },
    contact_slip_last_phase_mm: lab.stats.lastPhaseSlipMm, contact_slip_max_mm: lab.stats.maxPhaseSlipMm,
    below_floor_mm: lab.stats.penetrationMm, cpu_ms: Object.fromEntries(Object.entries(timing).map(([k, v]) => [k, Math.round(v * 100) / 100])),
    bone }, null, 1);
}
function setLab(option, on = true) { if (!lab) return false; const value = lab.set(option, on); const box = $('lab-' + option); if (box) box.checked = value; return value; }
function setTerrain(name = 'studio') { if (!lab || !lab.setTerrain(name)) return false; $('lab-terrain').value = name; renderFrame(); return true; }
function inspectMaterials(mode = state.inspection, selected = state.material) {
  if (!inspector) return false;
  try {
    if (!inspector.set(mode, selected, state.wireframe)) return false;
    state.inspection = mode; state.material = selected; $('inspection').value = mode; $('material').value = selected;
    digitalHuman?.apply(mode);
    $('material-info').textContent = JSON.stringify(inspector.information, null, 2);
    renderFrame(); return true;
  } catch (error) { recordError(error); $('material-info').textContent = `Inspection failed: ${error.message}`; return false; }
}
function setWireframe(on = true) { state.wireframe = Boolean(on); $('wireframe').checked = state.wireframe; return inspectMaterials(); }
function setReference(value = 'none') {
  const panel = $('comparison'); panel.hidden = value === 'none'; $('reference').value = value;
  if (value !== 'none') {
    $('reference-image').src = assetRoot + 'references/' + value;
    $('reference-caption').textContent = value.startsWith('original/') ? 'Original reference. Compare proportions and silhouette under equivalent camera views; lighting differs.'
      : value.startsWith('approved/') ? 'Reviewed detail reference. The originals remain final authority; a reviewed image does not approve the model.'
      : 'Unapproved modeling proposal. Hidden geometry is inferred; compare against the originals.';
  }
  resize(); renderFrame(); return true;
}
function captureMode(on = true, { freeze = true } = {}) {
  const enabled = Boolean(on);
  if (enabled && !state.capture) {
    captureRestore = { paused: state.paused, autoRotate: controls.autoRotate, autoBlink: face?.values.autoBlink, damping: controls.enableDamping };
    if (freeze) { pause(true); controls.autoRotate = false; face?.set({ autoBlink: false }); }
    controls.enableDamping = false; controls.update();
  } else if (!enabled && state.capture && captureRestore) {
    state.paused = captureRestore.paused; controls.autoRotate = captureRestore.autoRotate; controls.enableDamping = captureRestore.damping;
    face?.set({ autoBlink: captureRestore.autoBlink }); $('pause').textContent = state.paused ? 'Resume' : 'Pause';
  }
  state.capture = enabled; document.body.classList.toggle('capture', enabled); resize(); refreshPose(); return enabled;
}
function getMorphInfluences() {
  const result = [];
  avatar?.traverse(mesh => {
    if (!mesh.morphTargetDictionary) return;
    const initial = allInitialMorphs.get(mesh);
    result.push({ mesh: mesh.name, targets: Object.entries(mesh.morphTargetDictionary).map(([name, index]) => ({ name, index,
      value: mesh.morphTargetInfluences[index], initial: initial[index], controlled: [...(face?.morphs.values() ?? [])].some(records => records.some(record => record.mesh === mesh && record.index === index)) })) });
  });
  return result;
}
function boneWorldPositions(names) {
  const result = {};
  characterRoot.updateMatrixWorld(true);
  if (!names) { names = []; avatar?.traverse(node => { if (node.isBone) names.push(node.name); }); }
  for (const name of names) {
    const bone = findBone(avatar, name);
    result[name] = bone ? { name: bone.name, position: bone.getWorldPosition(new THREE.Vector3()).toArray(),
      quaternion: bone.getWorldQuaternion(new THREE.Quaternion()).toArray() } : null;
  }
  return result;
}
function sampleDeformedVertices(meshName, indices) {
  let mesh;
  avatar?.traverse(node => { if (!mesh && node.isMesh && (!meshName || node.name === meshName)) mesh = node; });
  if (!mesh) return null;
  characterRoot.updateMatrixWorld(true); mesh.skeleton?.update();
  const count = mesh.geometry.attributes.position.count;
  const selected = indices ?? [0, Math.floor(count / 4), Math.floor(count / 2), Math.floor(count * .75), count - 1];
  return { mesh: mesh.name, skinned: Boolean(mesh.isSkinnedMesh), vertexCount: count, samples: selected.filter(index => Number.isInteger(index) && index >= 0 && index < count).map(index => {
    const local = mesh.getVertexPosition(index, new THREE.Vector3());
    return { index, local: local.toArray(), world: local.clone().applyMatrix4(mesh.matrixWorld).toArray() };
  }) };
}

const motionKeys = new Set(['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ShiftLeft', 'ShiftRight']);
window.addEventListener('keydown', event => {
  if (!motionKeys.has(event.code) || /INPUT|SELECT|TEXTAREA|BUTTON/.test(event.target.tagName) || event.ctrlKey || event.metaKey || event.altKey) return;
  if (!state.ready || motion?.mode !== 'automatic') return;
  event.preventDefault(); keys.add(event.code);
});
window.addEventListener('keyup', event => keys.delete(event.code));
window.addEventListener('blur', () => keys.clear());
document.addEventListener('visibilitychange', () => { if (document.hidden) keys.clear(); });
$('render').addEventListener('pointerdown', () => $('render').focus({ preventScroll: true }));
$('view').onchange = event => setView(event.target.value);
$('lighting').onchange = event => setLighting(event.target.value);
$('animation').onchange = event => setAnimation(event.target.value);
$('lab-terrain').replaceChildren(...Object.entries(TERRAINS).map(([value, label]) => new Option(label, value)));
$('lab-terrain').onchange = event => setTerrain(event.target.value);
for (const option of ['skeleton', 'contacts', 'trail', 'comparison', 'travel']) $('lab-' + option).onchange = event => setLab(option, event.target.checked);
$('transition').oninput = event => { state.transition = Number(event.target.value); if (motion) motion.transition = state.transition; $('transition-value').textContent = `${state.transition.toFixed(2)} s`; };
$('playback-speed').oninput = event => setPlaybackSpeed(Number(event.target.value));
$('movement-speed').oninput = event => setLocomotionSpeed(Number(event.target.value));
$('pause').onclick = () => pause(!state.paused);
$('reset-position').onclick = resetPosition;
$('timeline').oninput = event => { pause(true); seek(Number(event.target.value)); };
$('expression').onchange = event => setExpression(event.target.value, Number($('expression-strength').value));
$('expression-strength').oninput = event => setExpression($('expression').value, Number(event.target.value));
$('viseme').onchange = event => setViseme(event.target.value, Number($('viseme-strength').value));
$('viseme-strength').oninput = event => setViseme($('viseme').value, Number(event.target.value));
const faceSliderNames = { 'blink-left': 'blinkLeft', 'blink-right': 'blinkRight', jaw: 'jaw', 'eye-yaw': 'eyeYaw', 'eye-pitch': 'eyePitch', 'head-yaw': 'headYaw', 'head-pitch': 'headPitch', 'head-roll': 'headRoll' };
for (const [id, name] of Object.entries(faceSliderNames)) $(id).oninput = event => setFaceControls({ [name]: Number(event.target.value) });
$('auto-blink').onchange = event => setFaceControls({ autoBlink: event.target.checked });
$('reset-face').onclick = resetFace;
for (const [id, name] of Object.entries({ exposure: 'exposure', 'key-light': 'key', 'fill-light': 'fill', 'ambient-light': 'ambient' })) $(id).oninput = event => setLightControls({ [name]: Number(event.target.value) });
$('inspection').onchange = event => inspectMaterials(event.target.value);
$('material').onchange = event => inspectMaterials(state.inspection, event.target.value);
$('wireframe').onchange = event => setWireframe(event.target.checked);
$('rotate').onchange = event => { controls.autoRotate = event.target.checked; controls.autoRotateSpeed = 1; };
$('reference').onchange = event => setReference(event.target.value);
$('play-performance').onclick = () => playPerformance($('performance').value);
$('turn-left').onclick = () => turn('Left');
$('turn-right').onclick = () => turn('Right');
$('crouch').onclick = () => crouch(!state.crouching);
$('skin-mode').onchange = e => setSkin({ mode: e.target.value });
$('skin-sss').onchange = e => setSkin({ sss: e.target.checked });
$('skin-thin').onchange = e => setSkin({ thinTransmission: e.target.checked });
$('skin-debug').onchange = e => setSkin({ debug: e.target.value });
$('skin-quality').onchange = e => setSkin({ quality: e.target.value });
for (const [id, key] of Object.entries({ 'skin-strength': 'strength', 'skin-radius': 'radius', 'skin-roughness': 'roughnessVariation', 'skin-micro': 'microNormal' })) $(id).oninput = e => setSkin({ [key]: Number(e.target.value) });
$('screenshot').onclick = screenshot;
$('model-version').onchange = e => {
  const url = new URL(location.href); url.searchParams.set('model', e.target.value); location.href = url.href;
};

window.inezViewer = { state, errors, warnings, setView, setLighting, setLightControls, setExpression, setViseme, setFaceControls, resetFace,
  setAnimation, setPlaybackSpeed, setLocomotionSpeed, pause, seek, advance, resetPosition, captureMode, inspectMaterials, setWireframe, setReference,
  turn, crouch, playPerformance, stopPerformance, setLab, setTerrain, setSkin, screenshot,
  get digitalHuman() { return digitalHuman; }, get renderer() { return renderer; },
  get lab() { return lab; }, boneInfo: name => lab?.boneInfo(name) ?? null,
  sampleDeformedVertices, boneWorldPositions, getBoneWorldPositions: boneWorldPositions, getMorphInfluences, renderFrame: refreshPose,
  getBone: name => findBone(avatar, name), getAvatar: () => avatar, get avatar() { return avatar; }, get assetInfo() { return state.assetInfo; },
  get meshInventory() { return state.assetInfo?.meshInventory ?? []; },
  get mixer() { return motion?.mixer; }, get camera() { return camera; }, get controls() { return controls; },
  get effectiveWeights() { return state.actionWeights; }, get actorPosition() { return state.characterPosition; } };
setView('body_front'); applyLighting();

function enableAssetControls(gltf) {
  $('animation').replaceChildren(new Option('A-pose · exported rest', 'rest'));
  if (Object.keys(motion.roles).length) $('animation').add(new Option('Automatic · idle / walk / run', 'automatic'));
  for (const name of motion.actions.keys()) {
    const source = lab?.source(name);
    const tag = source?.terra ? 'TERRA' : source?.kind === 'cmu_mocap' ? 'CMU mocap' : source?.kind === 'synthetic' ? 'synthetic test' : 'procedural';
    $('animation').add(new Option(`${name} · ${tag}`, name));
  }
  $('animation').disabled = false;
  for (const id of ['pause', 'reset-position', 'reset-face']) $(id).disabled = false;
  $('performance').replaceChildren(...[...motion.overlays.keys()].map(name => new Option(name.replace(/^Expr_/, ''), name)));
  $('performance').disabled = $('play-performance').disabled = !motion.overlays.size;
  $('turn-left').disabled = !motion.actions.has('TurnLeft'); $('turn-right').disabled = !motion.actions.has('TurnRight');
  $('crouch').disabled = !(motion.actions.has('CrouchDown') && motion.actions.has('Crouch') && motion.actions.has('CrouchUp'));
  $('playback-speed').disabled = !gltf.animations.length;
  $('movement-speed').disabled = !Object.keys(motion.roles).length; $('movement-speed').max = motion.runSpeed;
  $('expression').replaceChildren(new Option('Neutral', 'Neutral'));
  for (const name of face.expressions.filter(name => name !== 'Neutral')) $('expression').add(new Option(name, name));
  $('expression').disabled = !face.expressions.length; $('expression-strength').disabled = !face.expressions.length;
  $('viseme').replaceChildren(new Option('Resting mouth', 'none'));
  for (const name of face.visemes) $('viseme').add(new Option(name.replace('Viseme_', ''), name));
  $('viseme').disabled = !face.visemes.length; $('viseme-strength').disabled = !face.visemes.length;
  $('blink-left').disabled = !face.morphs.has('Blink_L'); $('blink-right').disabled = !face.morphs.has('Blink_R');
  $('auto-blink').disabled = !face.morphs.has('Blink_L') && !face.morphs.has('Blink_R');
  $('jaw').disabled = !face.bones.jaw;
  for (const id of ['eye-yaw', 'eye-pitch']) $(id).disabled = !face.bones.leftEye && !face.bones.rightEye;
  for (const id of ['head-yaw', 'head-pitch', 'head-roll']) $(id).disabled = !face.bones.head;
  $('face-info').textContent = `${face.expressions.length} actual expressions · ${face.visemes.length} mouth targets. ${face.preservedMorphs.length} source/fit channels preserved at export defaults.`;
  $('material').replaceChildren(new Option('All materials', 'all'));
  for (const [uuid, material] of inspector.materials) $('material').add(new Option(material.name || '(unnamed)', uuid));
  $('material').disabled = false; syncFaceUI();
  const boneNames = []; avatar.traverse(node => { if (node.isBone) boneNames.push(node.name); });
  $('lab-bone').replaceChildren(new Option('Select a bone…', ''), ...boneNames.map(name => new Option(name, name)));
  $('lab-bone').disabled = false;
}
function collectAssetInfo(gltf) {
  let meshCount = 0, skinnedCount = 0, vertexCount = 0, triangles = 0;
  const bones = new Set(), geometries = new Set(), textures = new Map(), buffers = new Set(), morphs = new Set(), meshInformation = [];
  avatar.traverse(mesh => {
    if (!mesh.isMesh) return;
    meshCount++; if (mesh.isSkinnedMesh) { skinnedCount++; mesh.skeleton.bones.forEach(bone => bones.add(bone)); }
    const geometry = mesh.geometry; geometries.add(geometry);
    vertexCount += geometry.attributes.position.count; triangles += (geometry.index?.count ?? geometry.attributes.position.count) / 3;
    for (const attribute of [...Object.values(geometry.attributes), ...Object.values(geometry.morphAttributes).flat(), geometry.index].filter(Boolean)) buffers.add((attribute.array ?? attribute.data?.array).buffer);
    for (const material of Array.isArray(mesh.material) ? mesh.material : [mesh.material]) {
      for (const value of Object.values(material)) if (value?.isTexture) textures.set(value.uuid, value);
    }
    Object.keys(mesh.morphTargetDictionary ?? {}).forEach(name => morphs.add(name));
    meshInformation.push({ name: mesh.name, skinned: Boolean(mesh.isSkinnedMesh), vertices: geometry.attributes.position.count,
      triangles: (geometry.index?.count ?? geometry.attributes.position.count) / 3,
      materials: (Array.isArray(mesh.material) ? mesh.material : [mesh.material]).map(material => material.name),
      morphs: Object.keys(mesh.morphTargetDictionary ?? {}) });
  });
  state.animationNames = gltf.animations.map(clip => clip.name); state.morphNames = [...morphs];
  state.walkSpeed = motion.walkSpeed; state.runSpeed = motion.runSpeed;
  const textureInformation = [...textures.values()].map(texture => ({ name: texture.name, uuid: texture.uuid,
    width: texture.image?.width ?? 0, height: texture.image?.height ?? 0, colorSpace: texture.colorSpace }));
  return { meshCount, skinnedCount, vertexCount, triangles, boneCount: bones.size, bones: [...bones].map(bone => bone.name),
    heightMeters: height, worldScaleProvisional: true, embeddedGLBMegabytes: state.resourceBytes / 1048576,
    geometryCount: geometries.size, geometryBufferBytes: [...buffers].reduce((total, buffer) => total + buffer.byteLength, 0),
    textureCount: textures.size, textures: textureInformation, materials: [...inspector.materials.values()].map(describeMaterial),
    animations: state.animationNames, animationClips: gltf.animations.map(clip => ({ name: clip.name, duration: clip.duration, tracks: clip.tracks.length, trackNames: clip.tracks.map(track => track.name) })),
    morphs: state.morphNames, drivenExpressions: face.expressions, drivenVisemes: face.visemes, preservedMorphs: face.preservedMorphs,
    facialBones: Object.fromEntries(Object.entries(face.bones).map(([role, bone]) => [role, bone?.name ?? null])),
    locomotionReferenceSpeeds: { walk: motion.walkSpeed, run: motion.runSpeed }, meshes: meshInformation,
    meshInventory: meshInformation.map(mesh => ({ name: mesh.name, vertexCount: mesh.vertices, skinned: mesh.skinned, morphNames: mesh.morphs })) };
}

async function loadAnimationManifest() {
  if (!motion?.roles.Walk && !motion?.roles.Run) return false;
  try {
    const response = await fetch(assetRoot + 'rig/animation_manifest.json', { cache: 'no-store' });
    if (!response.ok) { warnings.push('Animation speed manifest unavailable; viewer rates remain provisional.'); return false; }
    const manifest = await response.json(); state.animationManifest = manifest;
    motion.setClipInfo(manifest.clip_info ?? {});
    const walk = Number(manifest.clip_info?.Walk?.matching_viewer_speed_m_s);
    const run = Number(manifest.clip_info?.Run?.matching_viewer_speed_m_s);
    if (Number.isFinite(walk) && walk > 0) motion.walkSpeed = walk;
    if (Number.isFinite(run) && run > motion.walkSpeed) motion.runSpeed = run;
    return true;
  } catch (error) { warnings.push(`Animation speed manifest unreadable: ${error.message}`); return false; }
}

let last = performance.now(), frames = 0, statsStart = last, uiLast = last;
renderer.setAnimationLoop(() => {
  const now = performance.now(); const delta = state.paused ? 0 : Math.min(Math.max((now - last) / 1000, 0), .05); last = now;
  face?.restore(); updateMovement(delta);
  const t0 = performance.now(); motion?.update(delta, state.locomotionSpeed); const t1 = performance.now();
  face?.apply(delta, characterRoot.getWorldQuaternion(new THREE.Quaternion()));
  lab?.update(delta, followCamera); const t2 = performance.now();
  controls.update(); renderFrame(); const t3 = performance.now(); updateState(); frames++;
  // Rolling averages of CPU time per frame (render time is the submission
  // cost on the CPU; GPU time is not measurable here without timer queries).
  timing.animation_ms += ((t1 - t0) - timing.animation_ms) * .05;
  timing.lab_ms += ((t2 - t1) - timing.lab_ms) * .05;
  timing.render_ms += ((t3 - t2) - timing.render_ms) * .05;
  if (now - uiLast > 120) { syncAnimationUI(); syncLabUI(); uiLast = now; }
  if (now - statsStart > 1000) {
    state.fps = frames * 1000 / (now - statsStart); frames = 0; statsStart = now;
    const info = state.renderStats;
    $('stats').textContent = `${state.backend} · ${state.fps.toFixed(0)} FPS · anim ${timing.animation_ms.toFixed(2)} ms · render ${timing.render_ms.toFixed(2)} ms · ${info.triangles.toLocaleString()} triangles · ${info.drawCalls} draws · ${info.geometries} geometries / ${info.textures} textures · ${(state.resourceBytes / 1048576).toFixed(1)} MB GLB`;
  }
});

try {
  const response = await fetch(assetRoot + 'qa/production_status.json', { cache: 'no-store' });
  if (!response.ok) throw new Error('Production status unavailable: HTTP ' + response.status);
  const status = await response.json(); state.productionStatus = status;
  setLighting(status.default_lighting ?? 'studio');
  $('asset-status').textContent = status.label || (status.model_available ? 'Prototype · approval pending' : 'Character model unavailable');
  if (!status.model_available) {
    $('notice').textContent = status.blocker || 'The authored character is unavailable. No character model is loaded.';
    $('play-hint').textContent = 'Character controls will activate when the authored GLB is available. Drag to orbit; scroll to zoom.';
    $('asset-info').textContent = JSON.stringify({ modelLoaded: false, backend: state.backend, productionStatus: status }, null, 2);
  } else {
    $('notice').textContent = 'Loading authored character GLB…';
    // ?model= selects another export below model/ (for example a staged work/
    // revision under review). Anything outside that folder is refused.
    const requestedModel = new URLSearchParams(location.search).get('model') || status.default_model || 'inez_runtime.glb';
    if (!/^[\w-]+(\/[\w.-]+)*\.glb$/.test(requestedModel) || requestedModel.includes('..')) throw new Error(`Refused model path: ${requestedModel}`);
    state.modelPath = 'model/' + requestedModel;
    $('model-version').value = requestedModel;
    const modelResponse = await fetch(assetRoot + state.modelPath, { cache: 'no-store' });
    if (!modelResponse.ok) throw new Error('GLB missing: HTTP ' + modelResponse.status);
    const buffer = await modelResponse.arrayBuffer(); state.resourceBytes = buffer.byteLength;
    // Runtime exports use KTX2 (Basis) textures and meshopt geometry; the
    // master export uses JPEG/PNG. Both loaders are harmless when unused.
    const ktx2 = new KTX2Loader().setTranscoderPath('/basis/').detectSupport(renderer);
    const loader = new GLTFLoader().setKTX2Loader(ktx2).setMeshoptDecoder(MeshoptDecoder);
    const gltf = await loader.parseAsync(buffer, assetRoot + 'model/');
    avatar = gltf.scene; characterRoot.add(avatar); avatar.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(avatar); const center = bounds.getCenter(new THREE.Vector3());
    height = bounds.max.y - bounds.min.y;
    if (!Number.isFinite(height) || height <= 0) throw new Error('GLB has no usable character bounds');
    avatar.position.x -= center.x; avatar.position.z -= center.z; avatar.position.y -= bounds.min.y; avatar.updateMatrixWorld(true);
    avatar.traverse(mesh => {
      if (!mesh.isMesh) return;
      mesh.castShadow = true; mesh.receiveShadow = true;
      if (mesh.morphTargetInfluences) allInitialMorphs.set(mesh, [...mesh.morphTargetInfluences]);
    });
    face = new FacialControls(avatar); motion = new AnimationController(avatar, gltf.animations, height); motion.transition = state.transition;
    motion.onFinished = clipFinished;
    await loadAnimationManifest();
    lab = new AnimationLab({ scene, characterRoot, avatar, motion, assetRoot, warnings, findBone });
    state.externalClips = await lab.loadClips();
    inspector = new MaterialInspector(avatar); state.assetInfo = collectAssetInfo(gltf);
    digitalHuman = new DigitalHumanRegistry(avatar, renderer, state.backend); syncSkinUI();
    if (!digitalHuman.supported) {
      for (const element of document.querySelectorAll('#skin-lab input, #skin-lab select')) element.disabled = true;
      $('skin-support').textContent = digitalHuman.diagnostics.fallback;
    }
    $('asset-info').textContent = JSON.stringify(state.assetInfo, null, 2);
    state.ready = true; enableAssetControls(gltf); inspectMaterials(state.inspection, state.material);
    $('notice').textContent = status.production_approved ? '' : status.blocker || 'Authored prototype. Geometry, likeness and deformation approval are pending.';
    if (Object.keys(motion.roles).length) setAnimation('automatic', { transition: 0 });
    else setAnimation('rest', { transition: 0 });
    setView('body_front');
  }
} catch (error) {
  state.ready = false; state.error = recordError(error); $('notice').textContent = 'Asset load blocked: ' + state.error;
  $('asset-status').textContent = 'Load blocked';
} finally { state.loading = false; }
