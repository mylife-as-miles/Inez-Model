import test from 'node:test';
import assert from 'node:assert/strict';
import { HairGuideSolver } from '../src/hair/guide-solver.js';

// Executed solver fixtures, not claims about fitting or animating Fab hair.
const guide={name:'measured-input-fixture',points:[[0,0,0],[0,-.04,0],[.008,-.079,0],[.012,-.119,0],[.008,-.159,0]]};
const pose=(t=0)=>({position:[t*.15,1,0],rotation:[0,Math.sin(t*.15),0,Math.cos(t*.15)]});
const make=()=>new HairGuideSolver([guide]);
const run=(hz)=>{const s=make();s.reset(pose());for(let i=1;i<=hz*3;i++)s.update(1/hz,pose(i/hz));return s;};
test('idle settles, guides remain rooted and bounded with small length error',()=>{
  const s=make();s.reset(pose());for(let i=0;i<1200;i++)s.update(1/60,pose());
  assert.deepEqual(s.guides[0].positions[0],[0,1,0]);assert.equal(s.recoveries,0);
  assert.ok(s.diagnostics.maxRelativeLengthError<.005);
  assert.ok(Math.max(...s.guides[0].velocity.flat().map(Math.abs))<.003);
});
test('30/60/120 presentation and irregular timing preserve fixed-step trajectory',()=>{
  const reference=run(60);
  for(const hz of [30,120]){const s=run(hz);assert.equal(s.ticks,180);
    assert.ok(Math.max(...s.guides[0].positions.flat().map((v,i)=>Math.abs(v-reference.guides[0].positions.flat()[i])))<.00001);}
  const s=make();s.reset(pose());let t=0,i=0;const pattern=[.009,.021,.014,.026,.017];
  while(t<3-1e-9){const d=Math.min(pattern[i++%pattern.length],3-t);t+=d;s.update(d,pose(t));}
  assert.equal(s.ticks,180);assert.ok(Math.max(...s.guides[0].positions.flat().map((v,i)=>Math.abs(v-reference.guides[0].positions.flat()[i])))<.00001);
});
test('identical fixed-step replay is deterministic and gravity/inertia are real forces',()=>{
  const a=run(60),b=run(60);assert.deepEqual(a.guides[0].positions,b.guides[0].positions);
  const stationary=make();stationary.reset(pose(3));for(let i=0;i<180;i++)stationary.update(1/60,pose(3));
  assert.ok(Math.abs(a.guides[0].positions.at(-1)[0]-stationary.guides[0].positions.at(-1)[0])>.0001);
});
test('sphere/capsule constraints prevent point penetration',()=>{
  const s=make(),sphere={a:[.02,.91,0],radius:.025},capsule={a:[.023,.87,-.02],b:[.023,.82,.02],radius:.013};
  s.reset(pose());for(let i=0;i<120;i++)s.update(1/60,pose(),[sphere,capsule]);
  for(const p of s.guides[0].positions.slice(1)) {
    assert.ok(Math.hypot(...p.map((v,i)=>v-sphere.a[i]))>=sphere.radius+.002-1e-8);
    const ab=capsule.b.map((v,i)=>v-capsule.a[i]),ap=p.map((v,i)=>v-capsule.a[i]);
    const t=Math.max(0,Math.min(1,ap.reduce((s,v,i)=>s+v*ab[i],0)/ab.reduce((s,v)=>s+v*v,0)));
    assert.ok(Math.hypot(...p.map((v,i)=>v-capsule.a[i]-t*ab[i]))>=capsule.radius+.002-1e-8);
  }
  assert.ok(s.diagnostics.maxRelativeLengthError<.03);assert.equal(s.recoveries,0);
});
test('pause, single step, resume, teleport and large-delta recovery',()=>{
  const s=make();s.reset(pose());s.pause();const before=structuredClone(s.guides[0].positions);
  s.update(.1,pose());assert.deepEqual(s.guides[0].positions,before);s.singleStep(pose());assert.equal(s.ticks,1);
  s.update(.1,pose(.1));assert.deepEqual(s.guides[0].positions[0],pose(.1).position);
  s.pause(false);s.update(1/60,pose());assert.equal(s.ticks,2);
  const moved={position:[9,1,0],rotation:[0,0,0,1]};s.update(1/60,moved);assert.deepEqual(s.guides[0].positions[0],[9,1,0]);
  assert.ok(s.guides[0].velocity.flat().every(v=>v===0));s.update(1,moved);assert.equal(s.accumulator,0);
});
test('NaN state recovers and invalid input is rejected',()=>{
  const s=make();s.reset(pose());s.guides[0].positions[2][0]=NaN;s.update(1/60,pose());assert.equal(s.recoveries,1);
  assert.ok(s.guides[0].positions.flat().every(Number.isFinite));assert.throws(()=>s.update(NaN,pose()));
});
