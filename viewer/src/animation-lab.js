import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

// Animation lab: QA overlays for Inez's clips in the real viewer.
// - external clip GLBs (armature + one action) listed in animation/runtime/clips.json,
//   each with its source label (procedural, CMU mocap, TERRA, synthetic test);
// - skeleton overlay, foot-contact markers with a live slip measurement on
//   the skinned boot soles (the definition used by the Blender audits),
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

// Sole vertices of each boot: the boots are one skinned mesh, so each vertex
// goes to the side whose bones (names ending in L / R once sanitised) carry
// most of its weight; the lowest 3 cm of each boot in the bind pose is kept.
function soleVertices(avatar) {
  let mesh;
  avatar.traverse(node => { if (!mesh && node.isSkinnedMesh && /boot/i.test(node.name)) mesh = node; });
  if (!mesh) return null;
  const position = mesh.geometry.attributes.position, index = mesh.geometry.attributes.skinIndex, weight = mesh.geometry.attributes.skinWeight;
  const bones = mesh.skeleton.bones, sides = { L: [], R: [] }, p = new THREE.Vector3();
  avatar.updateMatrixWorld(true);
  for (let i = 0; i < position.count; i++) {
    const total = { L: 0, R: 0 };
    for (let j = 0; j < 4; j++) {
      const side = bones[index.getComponent(i, j)]?.name.slice(-1);
      if (side === 'L' || side === 'R') total[side] += weight.getComponent(i, j);
    }
    if (!total.L && !total.R) continue;
    p.fromBufferAttribute(position, i).applyMatrix4(mesh.matrixWorld);
    sides[total.L >= total.R ? 'L' : 'R'].push([i, p.y]);
  }
  const result = {};
  for (const side of ['L', 'R']) {
    if (!sides[side].length) return null;
    const floor = Math.min(...sides[side].map(v => v[1]));
    result[side] = { mesh, indices: sides[side].filter(v => v[1] < floor + .03).map(v => v[0]) };
  }
  return result;
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
    this.soles = soleVertices(avatar);
    this.lastTime = 0;
    this.lastClip = null;
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
        // Blender writes the first baked frame at 1/fps; start the clip at 0
        // so a loop does not hold its first pose for an extra frame.
        const start = Math.min(...clip.tracks.map(track => track.times[0]));
        // Tracks share their time arrays (one glTF accessor), so copy before shifting.
        if (start > 0 && Number.isFinite(start)) {
          for (const track of clip.tracks) { track.times = track.times.slice(); track.shift(-start); }
          clip.resetDuration();
        }
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

  set(option, value) {
    if (option === 'contacts' && value && !this.options.contacts) this.resetContacts();
    this.options[option] = Boolean(value); this.apply(); return this.options[option];
  }

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
    // A new clip starts its own travel run and contact history.
    if (motion.current !== this.lastClip) { this.lastClip = motion.current; this.resetContacts(); this.travelOrigin = null; this.trailPoints = []; }
    // In-place clips with a matching speed travel at that speed (planted feet
    // then stay put in world space); the run restarts when the clip loops.
    if (this.options.travel && motion.mode === 'manual' && info.in_place && info.matching_speed_m_s > 0 && delta > 0) {
      if (!this.travelOrigin || motion.time < this.lastTime) {
        if (this.travelOrigin && follow) { const back = this.travelOrigin.clone().sub(this.characterRoot.position); follow(back); }
        if (this.travelOrigin) this.characterRoot.position.copy(this.travelOrigin);
        else this.travelOrigin = this.characterRoot.position.clone();
        this.resetContacts(false);
        this.trailPoints = [];
      }
      const step = new THREE.Vector3(0, 0, 1).applyQuaternion(this.characterRoot.quaternion)
        .multiplyScalar(info.matching_speed_m_s * delta * motion.mixer.timeScale);
      this.characterRoot.position.add(step); follow?.(step);
    } else if (this.travelOrigin && motion.mode !== 'manual') this.travelOrigin = null;
    this.lastTime = motion.time;
    this.characterRoot.updateMatrixWorld(true);
    // Sole sampling costs CPU per frame: only while the contact markers are on.
    if (this.options.contacts) this.updateContacts(delta);
    this.updateTrail();
    this.updateStick();
  }

  resetContacts(clearStats = true) {
    for (const foot of this.feet) { foot.contact = false; foot.last = null; foot.anchor = null; foot.drift = 0; foot.previous = null; }
    if (clearStats) this.stats = { contacts: ['-', '-'], lastPhaseSlipMm: [null, null], maxPhaseSlipMm: [0, 0], penetrationMm: [0, 0] };
  }

  // Planted = the lowest sole point within 2 mm of the floor under it (the
  // retargeter keeps swing feet at least 3 mm up). Slip per planted phase is
  // the summed horizontal travel, frame to frame, of the sole vertex that is
  // in contact: rolling over heel or toe moves the contact point, not the
  // material, so it is not counted. Without boot soles (another model) it
  // falls back to the toe ball.
  updateContacts(delta) {
    const p = new THREE.Vector3();
    for (const [k, foot] of this.feet.entries()) {
      const sole = this.soles?.[foot.side];
      let point, ground, step = 0;
      if (sole) {
        const { mesh, indices } = sole;
        const now = foot.previous && foot.previous.length === indices.length * 3 ? foot.previous : new Float32Array(indices.length * 3);
        const before = foot.previous ? now.slice() : null;
        let best = 0, lift = Infinity;
        mesh.skeleton.update();
        indices.forEach((index, n) => {
          mesh.getVertexPosition(index, p).applyMatrix4(mesh.matrixWorld);
          now.set([p.x, p.y, p.z], 3 * n);
          const height = p.y - this.heightAt(p.x, p.z);
          if (height < lift) { lift = height; best = n; }
        });
        foot.previous = now;
        point = new THREE.Vector3(now[3 * best], now[3 * best + 1], now[3 * best + 2]);
        ground = this.heightAt(point.x, point.z);
        if (before) step = Math.hypot(now[3 * best] - before[3 * best], now[3 * best + 2] - before[3 * best + 2]);
        const contact = lift < .002;
        if (contact && !foot.contact) foot.drift = 0;
        else if (contact) foot.drift += step;
        if (!contact && foot.contact) this.closePhase(k, foot);
        foot.contact = contact;
        this.stats.penetrationMm[k] = Math.round(Math.min(0, lift) * 10000) / 10;
      } else {
        point = foot.ball.getWorldPosition(new THREE.Vector3());
        ground = this.heightAt(point.x, point.z);
        const lift = point.y - foot.restBall - ground;
        const speed = foot.last && delta > 0 ? Math.hypot(point.x - foot.last.x, point.z - foot.last.z) / delta : 0;
        foot.last = point.clone();
        const contact = lift < .02 && speed < .3;
        if (contact && !foot.contact) { foot.anchor = point.clone(); foot.drift = 0; }
        if (contact && foot.anchor) foot.drift = Math.max(foot.drift, Math.hypot(point.x - foot.anchor.x, point.z - foot.anchor.z));
        if (!contact && foot.contact) this.closePhase(k, foot);
        foot.contact = contact;
        this.stats.penetrationMm[k] = Math.round(Math.min(0, lift) * 1000);
      }
      this.stats.contacts[k] = foot.contact ? 'planted' : 'swing';
      foot.marker.position.set(point.x, ground + .003, point.z);
      foot.marker.material.color.set(foot.contact ? '#1b9e4b' : '#d33');
    }
  }

  closePhase(k, foot) {
    const mm = Math.round(foot.drift * 10000) / 10;
    this.stats.lastPhaseSlipMm[k] = mm;
    this.stats.maxPhaseSlipMm[k] = Math.max(this.stats.maxPhaseSlipMm[k], mm);
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
