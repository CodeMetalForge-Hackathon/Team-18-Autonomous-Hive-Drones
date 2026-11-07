import assert from 'node:assert/strict';
import{Sim,compile,roms,arena,addObject,W,H,R}from './legacy/engine-v1.mjs';
for(const source of Object.values(roms))assert.ok(compile(source).length);
assert.throws(()=>compile('sense r16 front',64));assert.throws(()=>compile('jmp missing'));assert.throws(()=>compile('sense r0 position'));assert.throws(()=>compile('yield 1'));
const a=new Sim(),b=new Sim();for(let i=0;i<1000;i++){a.step();b.step()}assert.deepEqual(a.robot,b.robot);assert.deepEqual(a.readings,b.readings);assert.ok(!a.blocked(a.robot.x,a.robot.y));
const m={start:{x:100,y:50,a:0},obstacles:[{x:150,y:20,w:20,h:60}],targets:[{x:200,y:50}],observer:null};const s=new Sim(m,{noise:0},'move 1\nyield\njmp 0');assert.equal(s.readings.front,50);assert.equal(s.readings.target,0);for(let i=0;i<50;i++)s.step();assert.ok(s.robot.x<150-R);assert.ok(s.collisions>0);assert.equal(s.found.size,0);
const t=new Sim({...m,obstacles:[],targets:[{x:108,y:50}]},{noise:0},'yield');t.step();assert.equal(t.status,'Complete');
const bounded=new Sim(arena(),{budget:5},'add r0 1\njmp 0');bounded.step();assert.equal(bounded.reg[0],3);
const noCamera=new Sim({...m,obstacles:[]},{camera:false},'yield');assert.equal(noCamera.readings.target,0);
const empty=new Sim({...m,obstacles:[],targets:[]},{battery:.1},'yield');empty.step();assert.equal(empty.status,'Battery depleted');
console.log('Passed: ROM validation, determinism, occlusion, collision, rescue, instruction budget, camera toggle, battery termination.');

const desk=arena();assert.equal(W,250);assert.equal(H,100);assert.equal(desk.objects.filter(o=>o.type==='laptop').length,3);
const shelter=desk.objects.find(o=>o.type==='hidebox');const shelterSim=new Sim(desk,{noise:0},'yield');assert.equal(shelterSim.blocked(shelter.x+17,shelter.y+14),false);assert.equal(shelterSim.blocked(shelter.x,shelter.y+14),false);assert.equal(shelterSim.blocked(shelter.x+33,shelter.y+14),true);
const edge=new Sim({start:{x:W-R-.1,y:50,a:0},obstacles:[],targets:[],observer:null},{speed:150},'move 1\nyield\njmp 0');edge.step();assert.ok(edge.robot.x<=W-R);assert.equal(edge.bumper,1);
const thin=new Sim({start:{x:30,y:50,a:0},obstacles:[{x:40,y:10,w:1,h:80}],targets:[],observer:null},{speed:150},'move 1\nyield\njmp 0');thin.step();assert.ok(thin.robot.x<=40-R);assert.equal(thin.bumper,1);
const bottle=desk.objects.find(o=>o.type==='bottle');assert.equal(shelterSim.blocked(bottle.x+bottle.w/2,bottle.y+bottle.h/2),true);
console.log('Tabletop checks passed: desk dimensions, three laptops, enterable shelters, solid backs, round bottles, edge stop and thin-wall swept movement.');

const mathSim=new Sim({...m,obstacles:[],targets:[]},{budget:32},'set r0 90\nsin r0\nset r1 1\nset r2 0\natan2 r1 r2\nset r3 190\nwrap r3\nset r4 -3\nabs r4\nmul r4 r4\nsqrt r4\nyield');mathSim.step();assert.equal(mathSim.reg[0],1);assert.equal(mathSim.reg[1],90);assert.equal(mathSim.reg[3],-170);assert.equal(mathSim.reg[4],3);
const deadReckoning=new Sim({start:{x:30,y:50,a:0},obstacles:[{x:40,y:10,w:1,h:80}],targets:[],observer:null},{speed:12},'move 1\nyield\njmp 0');for(let i=0;i<10;i++)deadReckoning.step();assert.ok(deadReckoning.readings.odom_x>deadReckoning.robot.x-30+5);assert.equal(deadReckoning.readings.dock,1);assert.equal(deadReckoning.readings.rescued,0);
console.log('Opus sensors/math passed: degree trig, angle wrapping, local dock detection, and command-based odometry distinct from true blocked motion.');
