import './test-legacy.mjs';
import assert from 'node:assert/strict';
import {Sim,compile,defaults,roms,tabletopArena as arena,arena as photoArena,addObject,PROFILE,LEGACY_PROFILE} from './engine.mjs';
const empty={start:{x:100,y:50,a:0},obstacles:[],objects:[],targets:[],observer:null};
const config={noise:0,lightNoise:0,beam:1};
assert.equal(defaults.sensorModel,PROFILE);assert.equal(defaults.camera,false);assert.equal(defaults.bumpers,false);assert.equal(defaults.virtualRescue,false);
for(const source of Object.values(roms))assert.ok(compile(source).length);
for(const sensor of ['front','left','right','hidden'])assert.throws(()=>compile(`sense r0 ${sensor}`));
assert.ok(compile('pan -30\nsweep 30\nsense r0 range\nsense r1 light\nyield').length);
const wall={...empty,obstacles:[{x:150,y:20,w:1,h:60}]};const s=new Sim(wall,config,'yield');assert.equal(s.readings.range_valid,1);assert.ok(Math.abs(s.readings.range-43.25)<.01);assert.equal(s.readings.range_x,6.8);assert.equal(s.readings.range_y,0);assert.equal(s.readings.front,undefined);
const slew=new Sim(empty,config,'pan 45\nyield\njmp 0');slew.step();assert.equal(slew.readings.pan,9);assert.equal(slew.readings.pan_ready,0);assert.equal(slew.readings.range_angle,0);assert.ok(Math.abs(slew.readings.range_age-.1)<1e-7);for(let i=0;i<8;i++)slew.step();assert.equal(slew.readings.pan,45);assert.equal(slew.readings.pan_ready,1);
const scan=new Sim(empty,config,roms['Scan in place']);let min=0,max=0;for(let i=0;i<100;i++){scan.step();min=Math.min(min,scan.readings.pan);max=Math.max(max,scan.readings.pan);assert.ok(Math.abs(scan.readings.pan)<=45)}assert.ok(min<=-44&&max>=44);const held=scan.readings.pan;for(let i=0;i<10;i++)scan.step({move:0,strafe:0,turn:0,pan:held,sweep:0});assert.equal(scan.readings.pan,held);assert.equal(scan.readings.pan_ready,1);
const moving=new Sim(wall,config,'move 1\nyield\njmp 0');const ping=moving.readings.range_seq;moving.step();assert.equal(moving.readings.range_seq,ping);assert.equal(moving.readings.range_x,6.8);moving.step();assert.ok(moving.readings.range_seq>ping);assert.ok(moving.readings.range_x>9&&moving.readings.range_x<10);
const open=new Sim(empty,{...config,range:500},'yield');assert.equal(open.readings.range_valid,0);assert.equal(open.readings.range,-1);assert.equal(open.readings.bumper,0);assert.equal(open.readings.light,1);
const blind=new Sim({...empty,obstacles:[{x:108,y:10,w:1,h:80}]},config,'yield');assert.equal(blind.readings.range_valid,0);assert.equal(blind.readings.range,-1);
const desk={...structuredClone(empty),objects:[],obstacles:[]};addObject(desk,'laptop',130,39);const low=new Sim(desk,config,'yield');assert.equal(low.readings.range_valid,0);assert.equal(low.blocked(140,50),true);
const scene=arena();const box=scene.objects.find(o=>o.type==='hidebox');const under=new Sim({...scene,start:{x:box.x+17,y:box.y+14,a:0}},config,'yield');const entrance=new Sim({...scene,start:{x:box.x+1,y:box.y+14,a:0}},config,'yield');assert.ok(under.readings.light<.3);assert.ok(entrance.readings.light>under.readings.light);assert.equal(under.readings.hidden,undefined);const darkRoom=new Sim(empty,{...config,lightLevel:.05},'yield');assert.equal(darkRoom.readings.light,.05);
const shadeMap=structuredClone(empty);addObject(shadeMap,'shade',90,40);const shade=new Sim(shadeMap,config,'yield');assert.equal(shade.blocked(100,50),false);assert.ok(shade.readings.light<.3);assert.equal(shade.readings.range_valid,0);
const targetMap={...empty,targets:[{x:108,y:50}]};const noDetector=new Sim(targetMap,config,'yield');noDetector.step();assert.equal(noDetector.found.size,0);assert.equal(noDetector.readings.target,0);const virtual=new Sim(targetMap,{...config,virtualRescue:true,camera:true},'yield');virtual.step();assert.equal(virtual.status,'Complete');
const legacy=new Sim(wall,{sensorModel:LEGACY_PROFILE,noise:0},'sense r0 front\nyield');assert.equal(legacy.readings.front,50);assert.equal(legacy.readings.range,undefined);
console.log('Photo hardware checks passed: one cone, finite servo slew, repeated sweep reversal, hold, timestamped ping pose, unknown echoes/blind zone, invisible table edges, low laptop bases, light/shade ambiguity, disabled fictional sensors, and explicit legacy profile.');

const exposed=new Sim(empty,config,'yield');exposed.robot.x+=20;for(let i=0;i<300;i++)exposed.step();assert.equal(exposed.status,'Safety violation');assert.equal(exposed.safetyChecks[0].time,30);
const base=new Sim(empty,config,'yield');for(let i=0;i<610;i++)base.step();assert.equal(base.safetyChecks.length,2);assert.ok(base.safetyChecks.every(c=>c.safe&&c.dock));
const sheltered=new Sim(shadeMap,config,'yield');sheltered.robot.x+=7;for(let i=0;i<300;i++)sheltered.step();assert.equal(sheltered.safetyChecks[0].safe,true);sheltered.robot.x=150;sheltered.step();assert.equal(sheltered.readings.safe_dwell,0);
const pots=structuredClone(empty);addObject(pots,'plant',130,45);const pot=new Sim(pots,config,'yield');assert.equal(pot.readings.range_valid,1);assert.ok(pot.blocked(135,50));
console.log('Safety deadlines, base contact, low-light dwell/reset and plant echoes passed.');
// The refreshed challenge must not contain an objective isolated by the rover footprint.
const challenge=arena(),probe=new Sim(challenge,{},'yield'),queue=[[18,50]],visited=new Set(['18,50']);
for(let i=0;i<queue.length;i++){const [x,y]=queue[i];for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]){const a=x+dx,b=y+dy,key=a+','+b;if(a<0||a>250||b<0||b>100||visited.has(key)||probe.blocked(a,b))continue;visited.add(key);queue.push([a,b]);}}
assert.ok(challenge.targets.every(p=>visited.has(p.x+','+p.y)),'Every objective has a collision-free route from dock');
// BLE exposes noisy packets, never true range/bearing, and uses evidence-only confirmation.
const radio={...config,ble:true,bleNoise:0,bleDrop:0,bleMultipath:0,missionMode:true};
const beaconWorld={...structuredClone(empty),targets:[{x:140,y:50}]};
const rf=new Sim(beaconWorld,radio,'yield');
rf.robot.x=113.2;const farPower=rf.blePower(0);rf.robot.x=123.2;const nearPower=rf.blePower(0);assert.ok(Math.abs(nearPower-farPower-20*Math.log10(2))<1e-7);
const obstructed=structuredClone(beaconWorld);addObject(obstructed,'bottle',128,46.5);const rfBlocked=new Sim(obstructed,radio,'yield');rf.robot.x=100;assert.ok(rfBlocked.blePower(0)<rf.blePower(0)-3.9);
assert.equal(rf.readings.ble_id,1);assert.equal(rf.readings.ble_channel,37);assert.equal(rf.readings.ble_x,6.8);assert.equal(rf.readings.ble_valid,1);const serial=rf.readings.ble_seq;rf.sense();assert.equal(rf.readings.ble_seq,serial);assert.equal(rf.readings.ble_distance,undefined);assert.equal(rf.readings.ble_bearing,undefined);
const closeWorld={...structuredClone(empty),targets:[{x:108.8,y:50}]};const closeBLE=new Sim(closeWorld,radio,'yield');for(let i=0;i<9;i++)closeBLE.step();assert.equal(closeBLE.found.size,0);for(let i=0;i<3;i++)closeBLE.step();assert.equal(closeBLE.found.size,1);assert.equal(closeBLE.readings.ble_confirmed,1);
const missed=new Sim(closeWorld,{...radio,bleDrop:1},'yield');for(let i=0;i<20;i++)missed.step();assert.equal(missed.readings.ble_valid,0);assert.equal(missed.found.size,0);
closeBLE.c.bleDrop=1;for(let i=0;i<15;i++)closeBLE.step();assert.equal(closeBLE.readings.ble_valid,0);assert.ok(closeBLE.readings.ble_age>1);
const fading=new Sim(beaconWorld,{...radio,bleMultipath:4},'yield');assert.notEqual(fading.blePower(0,37),fading.blePower(0,38));
const multi=new Sim({...beaconWorld,targets:[{x:140,y:50},{x:170,y:50},{x:200,y:50}]},radio,'yield');const ids=new Set;for(let i=0;i<8;i++){multi.step();ids.add(multi.readings.ble_id)}assert.equal(ids.size,3);
const reverse=challenge.objects.find(o=>o.opening==='right');assert.ok(reverse);assert.ok(probe.blocked(reverse.x,reverse.y+reverse.h/2,0.1));assert.equal(probe.blocked(reverse.x+reverse.w,reverse.y+reverse.h/2,0.1),false);
assert.ok(compile('sense r0 ble_rssi\nsense r1 ble_seq\nsense r2 ble_id\nsense r3 ble_age\nyield').length);
console.log('BLE checks passed: 6 dB/doubling, obstacle attenuation, channel fading, packet caching/loss/age, identities, sustained RSSI confirmation and reversed shelter geometry.');

const slide=new Sim(empty,config,'yield');for(let i=0;i<10;i++)slide.step({move:0,strafe:1,turn:0});assert.equal(slide.robot.x,100);assert.ok(Math.abs(slide.robot.y-62)<1e-6);assert.equal(slide.robot.a,0);assert.ok(Math.abs(slide.odom.y-12)<.2);
const diagonal=new Sim(empty,config,'yield');for(let i=0;i<10;i++)diagonal.step({move:1,strafe:1,turn:0});assert.ok(Math.abs(Math.hypot(diagonal.robot.x-100,diagonal.robot.y-50)-12)<1e-6);
const {auditClearance}=await import('./arena-clearance.mjs');assert.equal(auditClearance(arena()).ok,true);assert.equal(auditClearance(arena()).required_lane_cm,25);
console.log('Roomy arena and mecanum checks passed: sideways without yaw, normalized diagonal drive, 5 cm side clearance to every objective and shelter.');

// The photographed arena: dock on the tape by the laptop, and every objective reachable by the true footprint.
const photo=photoArena(),photoSim=new Sim(photo,config,'yield'),tape=photo.objects.find(o=>o.type==='tape'),surface=photo.objects.find(o=>o.id==='surface-laptop'),shippingBox=photo.objects.find(o=>o.id==='shipping-box');
assert.equal(photoSim.blocked(photo.start.x,photo.start.y),false,'Dock must clear the laptop and partition');
assert.ok(photo.start.x>=tape.x&&photo.start.x<=tape.x+tape.w&&photo.start.y>=tape.y&&photo.start.y<=tape.y+tape.h,'Dock must be on the tape');
assert.ok(photo.start.y-(surface.y+surface.h)<15&&photo.start.x>surface.x&&photo.start.x<surface.x+surface.w,'Tape must be next to the laptop');
const photoAudit=auditClearance(photo,0);assert.equal(photoAudit.ok,true,JSON.stringify(photoAudit));
assert.equal(photoSim.blocked(shippingBox.x+.5,79),false,'Rover fits through the near doorway');assert.equal(photoSim.blocked(shippingBox.x+.5,70),true,'Doorway jamb is solid');
const lidEcho=new Sim({...photo,start:{x:124,y:30,a:-Math.PI/2}},config,'yield');assert.equal(lidEcho.readings.range_valid,1);assert.ok(lidEcho.readings.range>8&&lidEcho.readings.range<13,'Sonar sees the laptop lid on the room side');
const boxInterior=new Sim({...photo,start:{x:97,y:75,a:0}},config,'yield');assert.ok(boxInterior.readings.light<.3,'Box interior is a low-light refuge');
for(const object of photo.objects)assert.ok(object.x>=0&&object.y>=0&&object.x+object.w<=250&&object.y+object.h<=100,object.id);
console.log('Photo arena checks passed: dock on the tape, doorway, reachable objectives, laptop-lid echo and dark box interior.');
