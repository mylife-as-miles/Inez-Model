// Controller regression tests using in-memory Three.js clips and transforms.
// This is not GLB, likeness, skinning, or browser validation; it serves no asset.
import assert from 'node:assert/strict';
import test from 'node:test';
import * as THREE from 'three';
import { AnimationController, FacialControls } from '../src/character-controls.js';

const close = (actual, expected, message) => assert.ok(Math.abs(actual - expected) < 1e-7,
  `${message}: expected ${expected}, got ${actual}`);
const weightsEqual = (actual, expected) => {
  assert.deepEqual(Object.keys(actual), Object.keys(expected));
  for (const name of Object.keys(expected)) close(actual[name], expected[name], `${name} weight`);
};

function animationFixture() {
  const root = new THREE.Group();
  const bone = new THREE.Bone(); bone.name = 'testBone'; root.add(bone);
  const clips = ['Idle', 'Walk', 'Run'].map((name, value) => new THREE.AnimationClip(name, 4,
    [new THREE.NumberKeyframeTrack('testBone.position[x]', [0, 4], [value, value])]));
  return { root, bone, motion: new AnimationController(root, clips, 1.68) };
}

function faceFixture() {
  const root = new THREE.Group();
  const bones = ['head', 'jaw', 'eye.L', 'eye.R'].map(name => {
    const bone = new THREE.Bone(); bone.name = name; return bone;
  });
  root.add(bones[0]); bones[0].add(...bones.slice(1));
  bones.forEach((bone, index) => bone.rotation.set(.02 * index, -.03 * index, .1 + .01 * index));
  const mesh = new THREE.Mesh(new THREE.BufferGeometry(), new THREE.MeshBasicMaterial());
  mesh.name = 'SyntheticMorphFixture';
  mesh.morphTargetDictionary = { Inez_HeadFit_test: 0, Neutral: 1, Anger: 2,
    Viseme_AA: 3, Blink_L: 4, Blink_R: 5, SourceShape: 6 };
  mesh.morphTargetInfluences = [1, 0, .1, 0, 0, 0, .6]; root.add(mesh);
  return { root, bones, mesh, face: new FacialControls(root) };
}

test('an interrupted fade keeps current weights and pose, then stops only completed actions', () => {
  const { bone, motion } = animationFixture();
  motion.set('Idle', { transition: 0 });
  motion.set('Walk', { transition: 1 }); motion.update(.5);
  weightsEqual(motion.weights, { Idle: .5, Walk: .5, Run: 0 });
  close(bone.position.x, .5, 'half Idle/Walk pose');
  const before = motion.weights;
  motion.set('Run', { transition: 1 });
  weightsEqual(motion.weights, before);
  close(bone.position.x, .5, 'pose immediately after interruption');
  motion.update(.5); // The old Idle stop deadline must not affect this fade.
  weightsEqual(motion.weights, { Idle: .25, Walk: .25, Run: .5 });
  close(bone.position.x, 1.25, 'pose at old stop deadline');
  motion.update(.5);
  weightsEqual(motion.weights, { Idle: 0, Walk: 0, Run: 1 });
  close(bone.position.x, 2, 'pose on completion');
  assert.deepEqual([...motion.actions].filter(([, action]) => action.isScheduled()).map(([name]) => name), ['Run']);
  motion.update(.2);
  weightsEqual(motion.weights, { Idle: 0, Walk: 0, Run: 1 });
});

test('reusing a fading action preserves weights and restart:false preserves its clip time', () => {
  const { bone, motion } = animationFixture();
  motion.set('Idle', { transition: 0 });
  motion.set('Walk', { transition: 1 }); motion.update(.4);
  const idleTime = motion.actions.get('Idle').time;
  const before = motion.weights;
  motion.set('Idle', { transition: 1, restart: false });
  weightsEqual(motion.weights, before);
  close(bone.position.x, .4, 'pose when reusing Idle');
  close(motion.active.time, idleTime, 'reused clip time');
  motion.update(.2);
  weightsEqual(motion.weights, { Idle: .68, Walk: .32, Run: 0 });
  const repeatedTime = motion.active.time;
  const repeatedWeights = motion.weights;
  motion.set('Idle', { transition: 0, restart: false });
  weightsEqual(motion.weights, repeatedWeights);
  close(motion.active.time, repeatedTime, 'repeated selection clip time');
  motion.update(.8);
  weightsEqual(motion.weights, { Idle: 1, Walk: 0, Run: 0 });
  close(bone.position.x, 0, 'completed reused Idle pose');
  motion.set('Idle', { transition: 0, restart: true });
  close(motion.active.time, 0, 'explicit restart clip time');
});

test('zero-delta refresh and seek freeze a fade while playback rate scales its clock once', () => {
  const { motion } = animationFixture();
  motion.set('Idle', { transition: 0 }); motion.setRate(2);
  motion.set('Walk', { transition: 1 }); motion.update(.25);
  weightsEqual(motion.weights, { Idle: .5, Walk: .5, Run: 0 });
  close(motion.active.time, .5, 'scaled clip time');
  for (let i = 0; i < 5; i++) motion.update(0);
  motion.seek(1.25);
  weightsEqual(motion.weights, { Idle: .5, Walk: .5, Run: 0 });
  close(motion.active.time, 1.25, 'seeked clip time');
  motion.setRate(.5); motion.update(.5);
  weightsEqual(motion.weights, { Idle: .25, Walk: .75, Run: 0 });
  close(motion.active.time, 1.5, 'clip time after rate change');
  motion.update(.5);
  weightsEqual(motion.weights, { Idle: 0, Walk: 1, Run: 0 });
});

test('a manual fade includes paused automatic gaits and immediate modes cancel it', () => {
  const { bone, motion } = animationFixture();
  motion.set('automatic'); motion.update(0, motion.walkSpeed / 2, true);
  assert.equal(motion.actions.get('Walk').paused, true);
  const before = motion.weights;
  motion.set('Run', { transition: 1 });
  weightsEqual(motion.weights, before);
  close(bone.position.x, .5, 'automatic-to-manual pose');
  motion.update(.5);
  weightsEqual(motion.weights, { Idle: .25, Walk: .25, Run: .5 });
  motion.set('Walk', { transition: 0 }); motion.update(.1);
  weightsEqual(motion.weights, { Idle: 0, Walk: 1, Run: 0 });
  close(bone.position.x, 1, 'immediate manual pose');
  motion.set('Run', { transition: 1 }); motion.update(.2);
  motion.set('automatic'); motion.update(0, 0, true);
  weightsEqual(motion.weights, { Idle: 1, Walk: 0, Run: 0 });
  motion.set('rest'); motion.update(1);
  weightsEqual(motion.weights, { Idle: 0, Walk: 0, Run: 0 });
  close(bone.position.x, 0, 'rest transform');
});

test('face overlays preserve fitted/source morphs and restore bone baselines without accumulation', () => {
  const { root, bones, mesh, face } = faceFixture();
  const baselineMorphs = [...mesh.morphTargetInfluences];
  const baselineQuaternions = bones.map(bone => bone.quaternion.clone());
  face.set({ expression: 'Anger', expressionStrength: .65, viseme: 'AA', visemeStrength: .55,
    blinkLeft: .4, jaw: .6, eyeYaw: 12, eyePitch: -5, headYaw: 23, headPitch: 7, headRoll: 6 });
  face.apply(0, root.getWorldQuaternion(new THREE.Quaternion()));
  const controlledQuaternions = bones.map(bone => bone.quaternion.clone());
  assert.ok(controlledQuaternions.every((quaternion, index) => quaternion.angleTo(baselineQuaternions[index]) > .01));
  for (let i = 0; i < 100; i++) {
    face.restore();
    bones.forEach((bone, index) => close(bone.quaternion.angleTo(baselineQuaternions[index]), 0, 'restored bone angle'));
    face.apply(1 / 60, root.getWorldQuaternion(new THREE.Quaternion()));
    [1, 0, .75, .55, .4, 0, .6].forEach((expected, index) => close(mesh.morphTargetInfluences[index], expected, `morph ${index}`));
    bones.forEach((bone, index) => close(bone.quaternion.angleTo(controlledQuaternions[index]), 0, 'stable controlled bone angle'));
  }
  face.restore();
  assert.deepEqual(mesh.morphTargetInfluences, baselineMorphs);
  assert.equal(face.preservedMorphs.find(item => item.name === 'Inez_HeadFit_test').initial, 1);
});

test('neutral, rest, and none clear visemes case-insensitively while invalid names preserve the selection', () => {
  const { face } = faceFixture();
  for (const alias of ['Neutral', 'NEUTRAL', ' neutral ', 'rest', 'REST', 'None', 'NONE', '']) {
    assert.equal(face.setViseme('aA', .8), true);
    assert.equal(face.values.viseme, 'Viseme_AA');
    assert.equal(face.setViseme(alias, .35), true, alias);
    assert.equal(face.values.viseme, '');
    close(face.values.visemeStrength, .35, 'clear alias strength');
  }
  face.setViseme('Viseme_AA', .6);
  assert.equal(face.setViseme('unknown', .2), false);
  assert.equal(face.values.viseme, 'Viseme_AA');
  close(face.values.visemeStrength, .6, 'invalid selection strength');
});
