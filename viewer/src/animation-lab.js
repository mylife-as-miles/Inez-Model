import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

// Animation lab: QA overlays for Inez's clips in the real viewer.
// - external clip GLBs (armature + one action) listed in animation/runtime/clips.json,
//   each with its source label (procedural, CMU mocap, TERRA, synthetic test);
// - skeleton overlay, foot-contact markers with a live slide measurement,
//   root trail, the source motion as a stick figure beside Inez;
// - terrain test floors (the clips are not terrain-adaptive: there is no
//   runtime foot IK, so contact markers show the resulting float/penetration).

const STICK = [['pelvis', 'spine'], ['spine', 'chest'], ['chest', 'neck'], ['neck', 'head'], ['head', 'head_top'],
  ['chest', 'shoulder_l'], ['shoulder_l', 'elbow_l'], ['elbow_l', 'wrist_l'], ['wrist_l', 'hand_l'],
  ['chest', 'shoulder_r'], ['shoulder_r', 'elbow_r'], ['elbow_r', 'wrist_r'], ['wrist_r', 'hand_r'],
  ['pelvis', 'hip_l'], ['hip_l', 'knee_l'], ['knee_l', 'ankle_l'], ['ankle_l', 'toe_l'],
  ['pelvis', 'hip_r'], ['hip_r', 'knee_r'], ['knee_r', 'ankle_r'], ['ankle_r', 'toe_r']];
export const TERRAINS = {
  studio: 'Flat studio floor',
  stairs: 'Short staircase · 6 × 17 cm',
  uneven: 'Uneven floor · ±2.5 cm',
  slope: 'Sloped platform · 8°',
  apartment_2026: 'Apartment 2026 · clean floor, 2 cm threshold',
  apartment_2009: 'Apartment 2009 · older floor, rug edge',
  apartment_2060: 'Apartment 2060 · damaged floor, debris'
};
const PROCEDURAL = { label: 'Procedural (Blender, tools/inez/animation_build.py)', terra: false };

function noise(x, z) {
  return Math.sin(x * 7.1 + 1.3) * Math.cos(z * 5.3 - .7) * .6 + Math.sin(x * 13.7 - z * 11.1) * .4;
}

export class AnimationLab {
  constructor({ scene, characterRoot, avatar, motion, assetRoot, warnings, findBone }) {
    Object.assign(this, { scene, characterRoot, avatar, motion, assetRoot, warnings, findBone });
    this.sources = {};
    this.trajectories = {};
    this.options = { skeleton: false, contacts: false, trail: false, comparison: false, travel: true };
    this.terrain = 'studio';
    this.terrainGroup = new THREE.Group(); this.terrainGroup.name = 'LabTerrain'; scene.add(this.terrainGroup);
    this.overlay = new THREE.Group(); this.overlay.name = 'LabOverlay'; scene.add(this.overlay);
    this.skeleton = new THREE.SkeletonHelper(avatar); this.skeleton.visible = false; scene.add(this.skeleton);
    const markerGeometry = new THREE.RingGeometry(.035, .05, 24).rotateX(-Math.PI / 2);
    this.feet = ['L', 'R'].map(side => {
      const marker = new THREE.Mesh(markerGeometry, new THREE.MeshBasicMaterial({ color: '#d33', depthTest: false, transparent: true, opacity: .9 }));
      marker.renderOrder = 10; marker.visible = false; this.overlay.add(marker);
      return { side, ankle: findBone(avatar, 'foot.' + side), ball: findBone(avatar, 'toe1-1.' + side) ?? findBone(avatar, 'foot.' + side),
        marker, last: null, contact: false, anchor: null, drift: 0, phases: [], restAnkle: 0, restBall: 0 };
    });
    avatar.updateMatrixWorld(true);
    for (const foot of this.feet) {
      foot.restAnkle = foot.ankle.getWorldPosition(new THREE.Vector3()).y;
      foot.restBall = foot.ball.getWorldPosition(new THREE.Vector3()).y;
    }
    this.trail = new THREE.Line(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: '#2a6' }));
    this.trailPoints = []; this.trail.visible = false; this.overlay.add(this.trail);
    this.stick = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: '#d47a00' }));
    this.stick.geometry.setAttribute('position', new THREE.Float32BufferAttribute(new Float32Array(STICK.length * 6), 3));
    this.stick.visible = false; this.stick.frustumCulled = false; characterRoot.add(this.stick);
    this.root = findBone(avatar, 'root');
    this.lastTime = 0;
    this.travelOrigin = null;
    this.stats = { contacts: ['-', '-'], lastPhaseSlipMm: [null, null], maxPhaseSlipMm: [0, 0], penetrationMm: [0, 0] };
  }

  async loadClips(manifestPath = 'animation/runtime/clips.json') {
    const response = await fetch(this.assetRoot + manifestPath, { cache: 'no-store' });
    if (!response.ok) { this.warnings.push('No external animation clips (' + manifestPath + ').'); return []; }
    const manifest = await response.json();
    const loader = new GLTFLoader();
    const loaded = [];
    for (const entry of manifest.clips ?? []) {
      try {
        const gltf = await loader.loadAsync(this.assetRoot + entry.file);
        const clip = gltf.animations[0];
        if (!clip) throw new Error('no animation in ' + entry.file);
        clip.name = entry.name;
        const missing = clip.tracks.filter(track => !this.avatar.getObjectByName(track.name.split('.')[0])).length;
        if (missing) this.warnings.push(`${entry.name}: ${missing} tracks target bones that are not in the loaded model.`);
        this.motion.addClip(clip, { ...entry, external: true });
        this.sources[entry.name] = entry;
        if (entry.trajectory) {
          const t = await fetch(this.assetRoot + entry.trajectory, { cache: 'no-store' });
          if (t.ok) this.trajectories[entry.name] = await t.json();
        }
        loaded.push(entry.name);
      } catch (error) { this.warnings.push(`Clip ${entry.name} failed to load: ${error.message}`); }
    }
    return loaded;
  }

  source(name) { return this.sources[name] ?? (name && name !== 'rest' && name !== 'automatic' ? PROCEDURAL : null); }

  set(option, value) { this.options[option] = Boolean(value); this.apply(); return this.options[option]; }

  apply() {
    this.skeleton.visible = this.options.skeleton;
    for (const foot of this.feet) foot.marker.visible = this.options.contacts;
    this.trail.visible = this.options.trail;
    this.stick.visible = this.options.comparison && Boolean(this.trajectories[this.motion.current]);
  }

  setTerrain(name = 'studio') {
    if (!TERRAINS[name]) return false;
    this.terrain = name;
    for (const child of [...this.terrainGroup.children]) { this.terrainGroup.remove(child); child.geometry?.dispose(); }
    const material = color => new THREE.MeshStandardMaterial({ color, roughness: .9 });
    const add = (geometry, color, x, y, z) => { const m = new THREE.Mesh(geometry, material(color)); m.position.set(x, y, z); m.receiveShadow = m.castShadow = true; this.terrainGroup.add(m); };
    if (name === 'stairs') for (let i = 0; i < 6; i++) add(new THREE.BoxGeometry(1.2, .17 * (i + 1), .28), '#9aa1a6', 0, .085 * (i + 1), .7 + .28 * i + .14);
    if (name === 'slope') {
      const ramp = new THREE.Mesh(new THREE.BoxGeometry(1.4, .02, 3), material('#9aa1a6'));
      ramp.rotation.x = -THREE.MathUtils.degToRad(8); ramp.position.set(0, Math.tan(THREE.MathUtils.degToRad(8)) * 1.5, .5 + 1.5);
      ramp.receiveShadow = true; this.terrainGroup.add(ramp);
    }
    if (name === 'uneven' || name === 'apartment_2060') {
      const geometry = new THREE.PlaneGeometry(4, 4, 80, 80).rotateX(-Math.PI / 2);
      const p = geometry.attributes.position;
      for (let i = 0; i < p.count; i++) p.setY(i, this.heightAt(p.getX(i), p.getZ(i)));
      geometry.computeVertexNormals();
      add(geometry, name === 'uneven' ? '#a7adb2' : '#6d655b', 0, 0, 0);
      if (name === 'apartment_2060') for (const [x, z, s] of [[.5, 1.2, .12], [-.4, 2.1, .08], [.2, 2.8, .15]]) add(new THREE.BoxGeometry(s, s * .6, s * 1.4), '#5a514a', x, s * .3, z);
    }
    if (name.startsWith('apartment')) {
      const floor = { apartment_2026: '#b79a76', apartment_2009: '#7d6852', apartment_2060: null }[name];
      if (floor) add(new THREE.BoxGeometry(4, .01, 6).translate(0, -.004, 0), floor, 0, 0, 1.5);
      for (const [w, d, x, z] of [[.1, 6, -1.6, 1.5], [.1, 6, 1.6, 1.5], [3.3, .1, 0, 4.5]]) add(new THREE.BoxGeometry(w, 2.6, d), name === 'apartment_2060' ? '#57524c' : '#d8d3cb', x, 1.3, z);
      if (name === 'apartment_2026') add(new THREE.BoxGeometry(1.0, .02, .08), '#8a8580', 0, .01, 1.5);
      if (name === 'apartment_2009') add(new THREE.BoxGeometry(1.4, .01, 1.0), '#7a3b33', 0, .005, 1.6);
    }
    return true;
  }

  heightAt(x, z) {
    switch (this.terrain) {
      case 'stairs': { const i = Math.floor((z - .7) / .28); return i >= 0 && i < 6 && Math.abs(x) < .6 ? .17 * (i + 1) : 0; }
      case 'slope': return z > .5 && z < 3.5 && Math.abs(x) < .7 ? (z - .5) * Math.tan(THREE.MathUtils.degToRad(8)) : 0;
      case 'uneven': case 'apartment_2060': return Math.abs(x) < 2 && Math.abs(z) < 2 ? noise(x, z) * (this.terrain === 'uneven' ? .025 : .03) : 0;
      case 'apartment_2026': return Math.abs(x) < .5 && Math.abs(z - 1.5) < .04 ? .02 : 0;
      case 'apartment_2009': return Math.abs(x) < .7 && Math.abs(z - 1.6) < .5 ? .01 : 0;
      default: return 0;
    }
  }

  // Called once per rendered frame after the mixer update.
  update(delta, follow) {
    const motion = this.motion;
    const info = motion.clipInfo[motion.current] ?? {};
    // In-place clips with a matching speed travel at that speed (planted feet
    // then stay put in world space); the run restarts when the clip loops.
    if (this.options.travel && motion.mode === 'manual' && info.in_place && info.matching_speed_m_s > 0 && delta > 0) {
      if (!this.travelOrigin || motion.time < this.lastTime) {
        if (this.travelOrigin && follow) { const back = this.travelOrigin.clone().sub(this.characterRoot.position); follow(back); }
        if (this.travelOrigin) this.characterRoot.position.copy(this.travelOrigin);
        else this.travelOrigin = this.characterRoot.position.clone();
        for (const foot of this.feet) { foot.contact = false; foot.last = null; }
        this.trailPoints = [];
      }
      const step = new THREE.Vector3(0, 0, 1).applyQuaternion(this.characterRoot.quaternion)
        .multiplyScalar(info.matching_speed_m_s * delta * motion.mixer.timeScale);
      this.characterRoot.position.add(step); follow?.(step);
    } else if (this.travelOrigin && motion.mode !== 'manual') this.travelOrigin = null;
    this.lastTime = motion.time;
    this.characterRoot.updateMatrixWorld(true);
    this.updateContacts(delta);
    this.updateTrail();
    this.updateStick();
  }

  updateContacts(delta) {
    for (const [k, foot] of this.feet.entries()) {
      const ankle = foot.ankle.getWorldPosition(new THREE.Vector3());
      const ball = foot.ball.getWorldPosition(new THREE.Vector3());
      const groundBall = this.heightAt(ball.x, ball.z);
      const groundAnkle = this.heightAt(ankle.x, ankle.z);
      const lift = Math.min(ankle.y - foot.restAnkle - groundAnkle, ball.y - foot.restBall - groundBall);
      const speed = foot.last && delta > 0 ? Math.hypot(ball.x - foot.last.x, ball.z - foot.last.z) / delta : 0;
      foot.last = ball.clone();
      const contact = lift < .02 && speed < .3;
      if (contact && !foot.contact) { foot.anchor = ball.clone(); foot.drift = 0; }
      if (contact && foot.anchor) foot.drift = Math.max(foot.drift, Math.hypot(ball.x - foot.anchor.x, ball.z - foot.anchor.z));
      if (!contact && foot.contact && foot.anchor) {
        this.stats.lastPhaseSlipMm[k] = Math.round(foot.drift * 1000);
        this.stats.maxPhaseSlipMm[k] = Math.max(this.stats.maxPhaseSlipMm[k], Math.round(foot.drift * 1000));
      }
      foot.contact = contact;
      this.stats.contacts[k] = contact ? 'planted' : 'swing';
      this.stats.penetrationMm[k] = Math.round(Math.min(0, lift) * 1000);
      foot.marker.position.set(ball.x, groundBall + .003, ball.z);
      foot.marker.material.color.set(contact ? '#1b9e4b' : '#d33');
    }
  }

  updateTrail() {
    if (!this.options.trail || !this.root) return;
    const p = this.root.getWorldPosition(new THREE.Vector3());
    p.y = this.heightAt(p.x, p.z) + .004;
    this.trailPoints.push(p);
    if (this.trailPoints.length > 240) this.trailPoints.shift();
    this.trail.geometry.setFromPoints(this.trailPoints);
  }

  updateStick() {
    const traj = this.trajectories[this.motion.current];
    this.stick.visible = this.options.comparison && Boolean(traj);
    if (!this.stick.visible) return;
    const f = this.motion.time * traj.fps / traj.every;
    const i = Math.min(Math.floor(f), traj.source_joints.length - 1), j = Math.min(i + 1, traj.source_joints.length - 1), a = f - i;
    const v = traj.average_velocity_m_s ?? [0, 0, 0];
    const t = this.motion.time;
    const index = Object.fromEntries(traj.joints.map((name, n) => [name, n]));
    const array = this.stick.geometry.attributes.position.array;
    STICK.forEach(([from, to], s) => {
      for (const [slot, name] of [[0, from], [1, to]]) {
        const p0 = traj.source_joints[i][index[name]], p1 = traj.source_joints[j][index[name]];
        // Blender Z-up (x, y, z) -> glTF (x, z, -y); in-place clips drop the
        // straight-line average velocity, exactly as the retargeter does.
        const x = p0[0] + (p1[0] - p0[0]) * a - (traj.in_place ? v[0] * t : 0);
        const y = p0[1] + (p1[1] - p0[1]) * a - (traj.in_place ? v[1] * t : 0);
        const z = p0[2] + (p1[2] - p0[2]) * a;
        array.set([x + .9, z, -y], s * 6 + slot * 3);
      }
    });
    this.stick.geometry.attributes.position.needsUpdate = true;
  }

  boneInfo(name) {
    const bone = this.findBone(this.avatar, name);
    if (!bone) return null;
    const euler = new THREE.Euler().setFromQuaternion(bone.quaternion);
    const world = bone.getWorldPosition(new THREE.Vector3());
    const round = v => Math.round(v * 1000) / 1000;
    return { bone: bone.name, local_position_m: bone.position.toArray().map(round),
      local_rotation_deg: [euler.x, euler.y, euler.z].map(r => round(THREE.MathUtils.radToDeg(r))),
      local_quaternion: bone.quaternion.toArray().map(round), world_position_m: world.toArray().map(round) };
  }
}
