import * as THREE from 'three';

export const EXPRESSION_NAMES = ['Neutral', 'Confused', 'Suspicious', 'SubtleFear', 'IntenseFear', 'Anger', 'Exhaustion'];
export const VISEME_NAMES = ['Viseme_AA', 'Viseme_EE', 'Viseme_OH', 'Viseme_MM', 'Viseme_FV'];
const BLINK_NAMES = ['Blink_L', 'Blink_R'];
const normalize = name => String(name).toLowerCase().replace(/[^a-z0-9]/g, '');
const clamp = (n, lo, hi) => THREE.MathUtils.clamp(Number(n) || 0, lo, hi);

export function findBone(root, name) {
  const wanted = normalize(name);
  let result;
  root?.traverse(node => { if (!result && node.isBone && normalize(node.name) === wanted) result = node; });
  return result;
}

// Only these authored functional targets are writable. Fitted/source shape keys
// remain outside this map, including Inez_HeadFit_* at its exported default.
export class FacialControls {
  constructor(root) {
    this.root = root;
    this.morphs = new Map();
    this.preservedMorphs = [];
    this.controlledBones = new Set();
    this.beforeBoneControls = new Map();
    this.applied = false;
    this.elapsed = 0;
    this.bones = { head: findBone(root, 'head'), jaw: findBone(root, 'jaw'), leftEye: findBone(root, 'eye.L'), rightEye: findBone(root, 'eye.R') };
    root.updateMatrixWorld(true);
    this.headRestWorldQuaternion = this.bones.head?.getWorldQuaternion(new THREE.Quaternion()) ?? new THREE.Quaternion();
    Object.values(this.bones).filter(Boolean).forEach(bone => this.controlledBones.add(bone));
    const canonicalNames = new Map([...EXPRESSION_NAMES, ...VISEME_NAMES, ...BLINK_NAMES].map(name => [normalize(name), name]));
    root.traverse(mesh => {
      if (!mesh.morphTargetDictionary || !mesh.morphTargetInfluences) return;
      for (const [name, index] of Object.entries(mesh.morphTargetDictionary)) {
        const canonicalName = canonicalNames.get(normalize(name));
        if (canonicalName) {
          const record = { mesh, name, index, initial: mesh.morphTargetInfluences[index], before: mesh.morphTargetInfluences[index] };
          if (!this.morphs.has(canonicalName)) this.morphs.set(canonicalName, []);
          this.morphs.get(canonicalName).push(record);
        } else this.preservedMorphs.push({ mesh: mesh.name, name, index, initial: mesh.morphTargetInfluences[index] });
      }
    });
    this.expressions = EXPRESSION_NAMES.filter(name => this.morphs.has(name));
    this.visemes = VISEME_NAMES.filter(name => this.morphs.has(name));
    this.values = { expression: this.morphs.has('Neutral') ? 'Neutral' : '', expressionStrength: 1, viseme: '', visemeStrength: 1,
      blinkLeft: 0, blinkRight: 0, autoBlink: false, jaw: 0, eyeYaw: 0, eyePitch: 0, headYaw: 0, headPitch: 0, headRoll: 0 };
  }

  restore() {
    if (!this.applied) return;
    for (const [bone, quaternion] of this.beforeBoneControls) bone.quaternion.copy(quaternion);
    for (const records of this.morphs.values()) for (const record of records) record.mesh.morphTargetInfluences[record.index] = record.before;
    this.applied = false;
    this.root.updateMatrixWorld(true);
  }

  setExpression(name = 'Neutral', strength = this.values.expressionStrength) {
    const resolved = this.expressions.find(n => normalize(n) === normalize(name));
    if (!resolved && name && normalize(name) !== 'neutral') return false;
    this.values.expression = resolved || '';
    this.values.expressionStrength = clamp(strength, 0, 1);
    return true;
  }

  setViseme(name = '', strength = this.values.visemeStrength) {
    const wanted = normalize(name);
    const clear = ['', 'neutral', 'rest', 'none'].includes(wanted);
    const resolved = clear ? '' : this.visemes.find(n => normalize(n) === wanted || normalize(n.replace('Viseme_', '')) === wanted);
    if (!resolved && !clear) return false;
    this.values.viseme = resolved || '';
    this.values.visemeStrength = clamp(strength, 0, 1);
    return true;
  }

  set(values = {}) {
    if ('expression' in values || 'expressionStrength' in values) this.setExpression(values.expression ?? this.values.expression, values.expressionStrength ?? this.values.expressionStrength);
    if ('viseme' in values || 'visemeStrength' in values) this.setViseme(values.viseme ?? this.values.viseme, values.visemeStrength ?? this.values.visemeStrength);
    for (const key of ['blinkLeft', 'blinkRight', 'jaw']) if (key in values) this.values[key] = clamp(values[key], 0, 1);
    const limits = { eyeYaw: 25, eyePitch: 20, headYaw: 45, headPitch: 30, headRoll: 25 };
    for (const [key, limit] of Object.entries(limits)) if (key in values) this.values[key] = clamp(values[key], -limit, limit);
    if ('autoBlink' in values) this.values.autoBlink = Boolean(values.autoBlink);
  }

  reset() {
    this.restore();
    for (const records of this.morphs.values()) for (const record of records) record.mesh.morphTargetInfluences[record.index] = record.initial;
    this.set({ expression: 'Neutral', expressionStrength: 1, viseme: '', visemeStrength: 1, blinkLeft: 0, blinkRight: 0,
      autoBlink: false, jaw: 0, eyeYaw: 0, eyePitch: 0, headYaw: 0, headPitch: 0, headRoll: 0 });
    this.elapsed = 0;
  }

  addMorph(name, amount) {
    if (!amount) return;
    for (const record of this.morphs.get(name) ?? []) {
      record.mesh.morphTargetInfluences[record.index] = clamp(record.before + amount, 0, 1);
    }
  }

  rotateInFrame(bone, referenceQuaternion, pitch, yaw, roll = 0) {
    if (!bone || (!pitch && !yaw && !roll)) return;
    // Source bones have anatomical roll. Convert a head/character-relative
    // delta to world space, then back through this bone's current parent.
    const delta = new THREE.Quaternion().setFromEuler(new THREE.Euler(pitch, yaw, roll, 'YXZ'));
    const worldDelta = referenceQuaternion.clone().multiply(delta).multiply(referenceQuaternion.clone().invert());
    const worldQuaternion = bone.getWorldQuaternion(new THREE.Quaternion());
    const parentQuaternion = bone.parent?.getWorldQuaternion(new THREE.Quaternion()) ?? new THREE.Quaternion();
    bone.quaternion.copy(parentQuaternion.invert().multiply(worldDelta.multiply(worldQuaternion)));
    bone.updateWorldMatrix(false, true);
  }

  apply(delta, characterQuaternion) {
    this.elapsed += delta;
    this.beforeBoneControls.clear();
    for (const bone of this.controlledBones) this.beforeBoneControls.set(bone, bone.quaternion.clone());
    for (const records of this.morphs.values()) for (const record of records) record.before = record.mesh.morphTargetInfluences[record.index];
    const v = this.values;
    this.addMorph(v.expression, v.expressionStrength);
    this.addMorph(v.viseme, v.visemeStrength);
    const blinkPhase = this.elapsed % 4.6;
    const blink = v.autoBlink ? Math.max(0, 1 - Math.abs(blinkPhase - 3.8) / .115) : 0;
    this.addMorph('Blink_L', Math.max(v.blinkLeft, blink));
    this.addMorph('Blink_R', Math.max(v.blinkRight, blink));
    const rad = THREE.MathUtils.degToRad;
    this.root.updateMatrixWorld(true);
    this.rotateInFrame(this.bones.head, characterQuaternion, rad(-v.headPitch), rad(v.headYaw), rad(v.headRoll));
    // Remove the exported head's rest roll so gaze axes begin at Three.js
    // world +Y/+X and then follow the head's animated/control rotation.
    const headQuaternion = this.bones.head ? this.bones.head.getWorldQuaternion(new THREE.Quaternion()).multiply(this.headRestWorldQuaternion.clone().invert()) : characterQuaternion;
    this.rotateInFrame(this.bones.jaw, headQuaternion, rad(v.jaw * 35), 0);
    this.rotateInFrame(this.bones.leftEye, headQuaternion, rad(-v.eyePitch), rad(v.eyeYaw));
    this.rotateInFrame(this.bones.rightEye, headQuaternion, rad(-v.eyePitch), rad(v.eyeYaw));
    this.applied = true;
    this.root.updateMatrixWorld(true);
  }
}

export class AnimationController {
  constructor(root, clips, height) {
    this.root = root;
    this.clips = clips;
    this.mixer = new THREE.AnimationMixer(root);
    this.actions = new Map(clips.map(clip => [clip.name, this.mixer.clipAction(clip)]));
    this.restTransforms = new Map();
    root.traverse(node => this.restTransforms.set(node, { position: node.position.clone(), quaternion: node.quaternion.clone(), scale: node.scale.clone() }));
    this.roles = {};
    for (const role of ['Idle', 'Walk', 'Run']) {
      const clip = clips.find(item => normalize(item.name) === normalize(role));
      if (clip) this.roles[role] = this.actions.get(clip.name);
    }
    this.walkSpeed = .95 * height / 1.68;
    this.runSpeed = 2.65 * height / 1.68;
    this.mode = 'rest';
    this.current = 'rest';
    this.active = null;
    this.transition = .35;
    this.playbackRate = 1;
    this.phase = 0;
    this.autoWeights = { Idle: 1, Walk: 0, Run: 0 };
    this.manualTransition = null;
  }

  setRate(rate) {
    this.playbackRate = clamp(rate, .1, 2);
    this.mixer.timeScale = this.playbackRate;
  }

  set(name, options = {}) {
    if (typeof options === 'number') options = { transition: options };
    const duration = clamp(options.transition ?? this.transition, 0, 2);
    if (name === 'rest' || name === '' || name === 'A-pose') {
      this.mixer.stopAllAction();
      this.manualTransition = null;
      this.mode = 'rest'; this.current = 'rest'; this.active = null;
      for (const [node, transform] of this.restTransforms) {
        node.position.copy(transform.position); node.quaternion.copy(transform.quaternion); node.scale.copy(transform.scale);
      }
      this.root.updateMatrixWorld(true);
      return true;
    }
    if (name === 'automatic' || name === 'locomotion' || name === 'auto') {
      if (!Object.keys(this.roles).length) return false;
      this.mixer.stopAllAction(); this.manualTransition = null;
      this.mode = 'automatic'; this.current = 'automatic'; this.active = null; this.phase = 0;
      this.autoWeights = { Idle: this.roles.Idle ? 1 : 0, Walk: 0, Run: 0 };
      for (const [role, action] of Object.entries(this.roles)) {
        action.reset().setEffectiveWeight(this.autoWeights[role]).setEffectiveTimeScale(1).play();
        action.paused = role !== 'Idle';
      }
      return true;
    }
    const actualName = [...this.actions.keys()].find(n => normalize(n) === normalize(name));
    if (!actualName) return false;
    const next = this.actions.get(actualName);
    if (this.mode === 'manual' && next === this.active && options.restart === false) return true;
    // Capture every contributing action, including paused automatic gaits.
    // A replacement transition starts at the currently rendered blend rather
    // than restarting Three.js fade multipliers or retaining old stop timers.
    const from = new Map([...this.actions.values()].filter(action => action.isScheduled())
      .map(action => [action, action.getEffectiveWeight()]));
    if (options.restart !== false || !next.isScheduled()) next.reset();
    next.enabled = true; next.paused = false;
    next.setEffectiveTimeScale(1).play();
    if (!from.has(next)) from.set(next, 0);
    for (const [action, weight] of from) action.setEffectiveWeight(weight);
    this.manualTransition = duration && [...from.values()].some(weight => weight > 0)
      ? { from, next, elapsed: 0, duration } : null;
    if (!this.manualTransition) {
      for (const action of this.actions.values()) {
        if (action === next) action.setEffectiveWeight(1);
        else action.stop();
      }
    }
    this.mode = 'manual'; this.current = actualName; this.active = next;
    this.mixer.update(0);
    this.root.updateMatrixWorld(true);
    return true;
  }

  desiredWeights(speed) {
    const walk = clamp(speed / this.walkSpeed, 0, 1);
    const run = clamp((speed - this.walkSpeed) / Math.max(.01, this.runSpeed - this.walkSpeed), 0, 1);
    const weights = { Idle: 1 - walk, Walk: walk * (1 - run), Run: run };
    let total = 0;
    for (const role of Object.keys(weights)) { if (!this.roles[role]) weights[role] = 0; total += weights[role]; }
    if (total < .0001) weights[Object.keys(this.roles)[0]] = 1;
    else for (const role of Object.keys(weights)) weights[role] /= total;
    return weights;
  }

  update(delta, speed = 0, immediate = false) {
    if (this.mode === 'manual' && this.manualTransition) {
      const transition = this.manualTransition;
      // Fades use the same scaled clock as AnimationMixer. A zero-delta pose
      // refresh or seek does not advance them, including while the UI is paused.
      transition.elapsed = Math.min(transition.duration, transition.elapsed + Math.max(0, delta * this.mixer.timeScale));
      const progress = transition.elapsed / transition.duration;
      for (const [action, weight] of transition.from) {
        action.setEffectiveWeight(THREE.MathUtils.lerp(weight, action === transition.next ? 1 : 0, progress));
      }
      if (progress === 1) {
        // Stop zero-weight actions before evaluating the new pose so reported
        // weights and the skeleton belong to the same completed transition.
        for (const action of transition.from.keys()) if (action !== transition.next) action.stop();
        this.manualTransition = null;
      }
    }
    if (this.mode === 'automatic') {
      const desired = this.desiredWeights(speed);
      const factor = immediate ? 1 : 1 - Math.exp(-delta * 10);
      for (const role of ['Idle', 'Walk', 'Run']) this.autoWeights[role] = THREE.MathUtils.lerp(this.autoWeights[role], desired[role], factor);
      const walkDuration = this.roles.Walk?.getClip().duration ?? 1;
      const runDuration = this.roles.Run?.getClip().duration ?? 1;
      const gaitWeight = this.autoWeights.Walk + this.autoWeights.Run;
      const frequency = gaitWeight > .0001 ? (this.autoWeights.Walk * speed / this.walkSpeed / walkDuration + this.autoWeights.Run * speed / this.runSpeed / runDuration) / gaitWeight : 0;
      this.phase = (this.phase + delta * this.playbackRate * frequency) % 1;
      for (const [role, action] of Object.entries(this.roles)) {
        action.setEffectiveWeight(this.autoWeights[role]);
        if (role !== 'Idle') action.time = this.phase * action.getClip().duration;
      }
    }
    this.mixer.update(delta);
    this.root.updateMatrixWorld(true);
  }

  seek(seconds) {
    const t = Math.max(0, Number(seconds) || 0);
    if (this.mode === 'manual' && this.active) this.active.time = clamp(t, 0, this.active.getClip().duration);
    if (this.mode === 'automatic') {
      const duration = this.duration;
      this.phase = duration > 0 ? (t / duration) % 1 : 0;
      for (const [role, action] of Object.entries(this.roles)) action.time = role === 'Idle' ? t % action.getClip().duration : this.phase * action.getClip().duration;
    }
    this.mixer.update(0);
    this.root.updateMatrixWorld(true);
    return this.time;
  }

  get duration() {
    if (this.mode === 'manual') return this.active?.getClip().duration ?? 0;
    if (this.mode === 'automatic') return Math.max(0, ...Object.values(this.roles).map(action => action.getClip().duration));
    return 0;
  }
  get time() { return this.mode === 'automatic' ? this.phase * this.duration : this.active?.time ?? 0; }
  get weights() { return Object.fromEntries([...this.actions].map(([name, action]) => [name, action.isScheduled() ? action.getEffectiveWeight() : 0])); }
}
