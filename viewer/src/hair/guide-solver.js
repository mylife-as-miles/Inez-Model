// Portable world-space XPBD foundation. No rendering, skeleton or Jolt types.
// Guide topology must come from the inspected asset; no hairstyle is invented.
const add=(a,b)=>a.map((v,i)=>v+b[i]),sub=(a,b)=>a.map((v,i)=>v-b[i]);
const mul=(a,s)=>a.map(v=>v*s),dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const norm=a=>Math.hypot(...a),unit=a=>mul(a,1/Math.max(norm(a),1e-12));
const mix=(a,b,t)=>a.map((v,i)=>v+(b[i]-v)*t);
function rotate(p,q) {
  const [x,y,z,w]=q,[a,b,c]=p;
  const u=[2*(y*c-z*b),2*(z*a-x*c),2*(x*b-y*a)];
  return [a+w*u[0]+y*u[2]-z*u[1],b+w*u[1]+z*u[0]-x*u[2],c+w*u[2]+x*u[1]-y*u[0]];
}
function quatMix(a,b,t) {
  let d=dot(a,b);if(d<0){b=mul(b,-1);d=-d;}
  if(d>.9995)return unit(mix(a,b,t));
  const angle=Math.acos(Math.min(d,1)),s=Math.sin(angle);
  return add(mul(a,Math.sin((1-t)*angle)/s),mul(b,Math.sin(t*angle)/s));
}
const poseMix=(a,b,t)=>({position:mix(a.position,b.position,t),rotation:quatMix(a.rotation,b.rotation,t)});
const point=(p,pose)=>add(pose.position,rotate(p,pose.rotation));
const validPose=p=>p?.position?.length===3 && p?.rotation?.length===4 && [...p.position,...p.rotation].every(Number.isFinite) && norm(p.rotation)>.99 && norm(p.rotation)<1.01;
const clonePose=p=>({position:[...p.position],rotation:[...p.rotation]});

export class HairGuideSolver {
  constructor(guides,settings={}) {
    this.settings={hz:60,iterations:24,mass:.001,lengthCompliance:0,bendCompliance:.05,
      shapeCompliance:20,drag:3,friction:.2,gravity:[0,-9.81,0],wind:[0,0,0],
      maxAcceleration:60,maxSpeed:15,maxDelta:.25,maxSubsteps:8,teleportDistance:.5,...settings};
    if(!guides.length || guides.some(g=>g.points.length<3 || g.points.some(p=>p.length!==3 || !p.every(Number.isFinite))))throw new Error('Measured guides with >=3 finite points required');
    const s=this.settings;
    if(!Number.isFinite(s.hz)||s.hz<=0||!Number.isInteger(s.iterations)||s.iterations<1||!Number.isInteger(s.maxSubsteps)||s.maxSubsteps<1 ||
       ![s.mass,s.maxSpeed,s.maxDelta,s.maxAcceleration,s.teleportDistance].every(v=>Number.isFinite(v)&&v>0) ||
       ![s.lengthCompliance,s.bendCompliance,s.shapeCompliance,s.drag,s.friction].every(v=>Number.isFinite(v)&&v>=0)||s.friction>1)throw new Error('Invalid fixed-step settings');
    this.guides=guides.map(g=>{
      const rest=g.points.map(p=>[...p]),lengths=rest.slice(1).map((p,i)=>norm(sub(p,rest[i])));
      if(lengths.some(l=>l<1e-6))throw new Error('Zero-length guide segment');
      return {name:g.name,rest,lengths,bends:rest.slice(2).map((p,i)=>norm(sub(p,rest[i]))),
        positions:rest.map(p=>[...p]),previous:rest.map(p=>[...p]),velocity:rest.map(()=>[0,0,0]),radius:g.radius??.002};
    });
    this.accumulator=0;this.ticks=0;this.resets=0;this.recoveries=0;this.paused=false;this.lastPose=null;
  }
  reset(pose) {
    if(!validPose(pose))throw new Error('Invalid attachment pose');
    this.lastPose=clonePose(pose);this.accumulator=0;this.resets++;
    for(const g of this.guides){g.positions=g.rest.map(p=>point(p,pose));g.previous=g.positions.map(p=>[...p]);g.velocity=g.rest.map(()=>[0,0,0]);}
  }
  pause(value=true){this.paused=Boolean(value);}
  update(delta,pose,colliders=[]) {
    if(!validPose(pose)||!Number.isFinite(delta)||delta<0)throw new Error('Nonfinite time/attachment pose');
    if(!this.lastPose){this.reset(pose);return 0;}
    if(delta>this.settings.maxDelta || norm(sub(pose.position,this.lastPose.position))>this.settings.teleportDistance){this.reset(pose);return 0;}
    if(this.paused){
      // Hold the deformed shape in attachment space while paused, so head
      // movement cannot stretch a frozen world-space strand across the scene.
      const old=this.lastPose,inverse=[-old.rotation[0],-old.rotation[1],-old.rotation[2],old.rotation[3]];
      for(const g of this.guides){g.positions=g.positions.map(p=>point(rotate(sub(p,old.position),inverse),pose));
        g.previous=g.positions.map(p=>[...p]);g.velocity=g.positions.map(()=>[0,0,0]);}
      this.lastPose=clonePose(pose);return 0;
    }
    const h=1/this.settings.hz,old=this.accumulator,start=this.lastPose;this.accumulator+=delta;
    let count=0;
    while(this.accumulator+1e-12>=h && count<this.settings.maxSubsteps) {
      const t=delta>0?Math.max(0,Math.min(1,(h-old+count*h)/delta)):1;
      this.step(poseMix(start,pose,t),typeof colliders==='function'?colliders(t):colliders);
      this.accumulator=Math.max(0,this.accumulator-h);count++;
    }
    if(this.accumulator>=h){this.reset(pose);this.recoveries++;}
    this.lastPose=clonePose(pose);return count;
  }
  singleStep(pose,colliders=[]) {
    if(!validPose(pose))throw new Error('Invalid attachment pose');
    if(!this.lastPose)this.reset(pose);
    this.step(pose,colliders);this.lastPose=clonePose(pose);this.accumulator=0;
  }
  step(pose,colliders) {
    const s=this.settings,h=1/s.hz,w=1/s.mass;
    let acceleration=add(s.gravity,s.wind);
    if(!acceleration.every(Number.isFinite)){this.reset(pose);this.recoveries++;return;}
    if(norm(acceleration)>s.maxAcceleration)acceleration=mul(unit(acceleration),s.maxAcceleration);
    for(const g of this.guides) {
      g.previous=g.positions.map(p=>[...p]);const before=g.positions.map(p=>[...p]);
      const root=point(g.rest[0],pose);g.positions[0]=root;
      for(let i=1;i<g.positions.length;i++) {
        let v=mul(g.velocity[i],Math.exp(-s.drag*h));if(norm(v)>s.maxSpeed)v=mul(unit(v),s.maxSpeed);
        g.positions[i]=add(add(g.positions[i],mul(v,h)),mul(acceleration,h*h));
      }
      const lengths=new Float64Array(g.lengths.length),bends=new Float64Array(g.bends.length);
      const shape=g.positions.map(()=>[0,0,0]);const contacts=new Map();
      const distance=(i,j,rest,compliance,lambda,k)=>{
        const d=sub(g.positions[j],g.positions[i]),n=norm(d);if(n<1e-12)return;
        const wi=i===0?0:w,wj=j===0?0:w,alpha=compliance/(h*h);
        const change=(-(n-rest)-alpha*lambda[k])/(wi+wj+alpha);lambda[k]+=change;
        g.positions[i]=sub(g.positions[i],mul(d,wi*change/n));g.positions[j]=add(g.positions[j],mul(d,wj*change/n));
      };
      for(let iteration=0;iteration<s.iterations;iteration++) {
        for(let i=1;i<g.positions.length;i++) {
          const target=point(g.rest[i],pose),alpha=s.shapeCompliance/(h*h);
          for(let axis=0;axis<3;axis++) {
            const change=(-(g.positions[i][axis]-target[axis])-alpha*shape[i][axis])/(w+alpha);
            shape[i][axis]+=change;g.positions[i][axis]+=w*change;
          }
        }
        for(let i=0;i<g.bends.length;i++)distance(i,i+2,g.bends[i],s.bendCompliance,bends,i);
        for(let i=0;i<g.lengths.length;i++)distance(i,i+1,g.lengths[i],s.lengthCompliance,lengths,i);
        for(let i=1;i<g.positions.length;i++)for(const c of colliders) {
          if(c.a?.length!==3||!c.a.every(Number.isFinite)|| (c.b && (c.b.length!==3||!c.b.every(Number.isFinite))) ||!Number.isFinite(c.radius)||c.radius<=0)throw new Error('Invalid collision proxy');
          let center=c.a;
          if(c.b){const axis=sub(c.b,c.a),t=Math.max(0,Math.min(1,dot(sub(g.positions[i],c.a),axis)/Math.max(dot(axis,axis),1e-12)));center=add(c.a,mul(axis,t));}
          const d=sub(g.positions[i],center),size=norm(d),radius=c.radius+g.radius;
          if(size<radius){const normal=size>1e-9?mul(d,1/size):[1,0,0];g.positions[i]=add(center,mul(normal,radius));contacts.set(i,{normal,velocity:c.velocity??[0,0,0]});}
        }
      }
      for(let i=1;i<g.positions.length;i++) {
        let v=mul(sub(g.positions[i],before[i]),1/h);const contact=contacts.get(i);
        if(contact){const relative=sub(v,contact.velocity),n=dot(relative,contact.normal);
          const tangent=sub(relative,mul(contact.normal,n));v=add(contact.velocity,add(mul(contact.normal,Math.max(n,0)),mul(tangent,1-s.friction)));}
        g.velocity[i]=norm(v)>s.maxSpeed?mul(unit(v),s.maxSpeed):v;
      }
      g.velocity[0]=[0,0,0];
    }
    this.ticks++;
    if(this.guides.some(g=>[...g.positions.flat(),...g.velocity.flat()].some(v=>!Number.isFinite(v)||Math.abs(v)>1e8))){this.reset(pose);this.recoveries++;}
  }
  interpolated(pose=this.lastPose) {
    const alpha=this.accumulator*this.settings.hz;
    return this.guides.map(g=>({name:g.name,points:g.positions.map((p,i)=>i===0?point(g.rest[0],pose):mix(g.previous[i],p,alpha))}));
  }
  get diagnostics(){return {guides:this.guides.length,particles:this.guides.reduce((n,g)=>n+g.positions.length,0),ticks:this.ticks,
    resets:this.resets,recoveries:this.recoveries,paused:this.paused,simulationHz:this.settings.hz,
    maxRelativeLengthError:Math.max(...this.guides.flatMap(g=>g.lengths.map((l,i)=>Math.abs(norm(sub(g.positions[i+1],g.positions[i]))/l-1))))};}
}
