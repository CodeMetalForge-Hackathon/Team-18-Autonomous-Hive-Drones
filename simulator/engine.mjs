import {expectedRSSI} from './rf.mjs';
import {Sim as LegacySim, compile as legacyCompile, roms as legacyRoms} from './legacy/engine-v1.mjs';
export const PROFILE='pan-sonar-light-v2',LEGACY_PROFILE='legacy-three-ray-v1';
export const HEAD_PIVOT_CM=4.3,HEAD_OFFSET_CM=2.5;
export const W=250,H=100,R=7.5,DT=.1;
export const defaults={range:80,noise:.4,speed:12,turn:90,battery:240,camera:false,fov:65,vision:120,ram:64,budget:32,seed:42,sensorModel:PROFILE,panSpan:90,panSpeed:90,beam:15,rangeMin:2,pingHz:5,lightLevel:1,lightNoise:.02,coverLeak:.08,bumpers:false,virtualRescue:false,ble:false,bleContact:-35,bleNoise:2,bleDrop:.08,bleMultipath:3};
export function addObject(map,type,x,y,opening='left'){
const base=`object-${(map.objects||[]).length}-${x}-${y}`;let id=base,suffix=1;while((map.objects||[]).some(o=>o.id===id))id=base+'-'+suffix++;
const sizes={laptop:[32,23],bottle:[7,7],hidebox:[34,34],shade:[28,24],plant:[10,10]};
const [w,h]=sizes[type];x=Math.max(1,Math.min(W-w-1,x));y=Math.max(1,Math.min(H-h-1,y));
const object={id,type,x,y,w,h,...(type==='hidebox'?{opening}: {})};(map.objects??=[]).push(object);
if(type==='hidebox')map.obstacles.push({x,y,w,h:1,owner:id},{x,y:y+h-1,w,h:1,owner:id},{x:opening==='right'?x:x+w-1,y,w:1,h,owner:id});
else if(type==='shade'){}
else if(type==='bottle'||type==='plant')map.obstacles.push({x,y,w,h,shape:'circle',owner:id});
else map.obstacles.push({x,y,w,h,owner:id});
return object;
}
export function arena(){const map={width:W,height:H,start:{x:18,y:50,a:0},obstacles:[],objects:[],targets:[{x:74,y:81},{x:146,y:81},{x:208,y:81}],observer:{x:132,y:7}};
// Furniture clusters leave a 37 cm main lane, >=28 cm between shelters,
// 32 cm shelter interiors, and a 26 cm route around the reversed entrance.
for(const [type,x,y]of [['laptop',40,4],['laptop',114,4],['laptop',188,4],['bottle',72,20],['bottle',146,20],['bottle',220,20],['bottle',230,10],['hidebox',56,64],['hidebox',128,64],['hidebox',190,64],['plant',30,8],['plant',72,8],['plant',146,8],['plant',220,8],['plant',1,82],['plant',90,86],['plant',1,4],['plant',11,4]])addObject(map,type,x,y,type==='hidebox'&&x===190?'right':'left');return map;}
export const roms={
'Scan in place':`; One movable ultrasonic channel. Two transducers are one range module.
sweep 30
move 0
strafe 0
turn 0
yield
jmp 0`,
'Guarded forward probe':`pan 0
loop:
sense r0 pan_ready
jz r0 stop
sense r0 range_valid
jz r0 stop
sense r0 range
lt r0 20
jnz r0 avoid
move 0.4
turn 0
yield
jmp loop
avoid:
move 0
turn 0.4
yield
jmp loop
stop:
move 0
turn 0
yield
jmp loop`,
'Seek low light':`sweep 30
loop:
sense r0 light
lt r0 0.3
jnz r0 dark
sense r0 range_valid
jz r0 pause
sense r0 range_angle
abs r0
lt r0 12
jz r0 pause
sense r0 range
lt r0 20
jnz r0 avoid
move 0.35
turn 0
yield
jmp loop
avoid:
move 0
turn 0.4
yield
jmp loop
pause:
move 0
turn 0
yield
jmp loop
dark:
move 0
turn 0
sweep 0
yield
jmp dark`};
const specs={sense:2,set:2,add:2,sub:2,mul:2,div:2,gt:2,abs:1,sqrt:1,sin:1,cos:1,atan2:2,wrap:1,lt:2,jz:2,jnz:2,jmp:1,rand:1,move:1,strafe:1,turn:1,pan:1,sweep:1,yield:0};
const sensors=['range','range_valid','range_angle','range_age','range_seq','range_x','range_y','range_yaw','range_time','pan','pan_ready','light','target','bearing','observer','battery','bumper','time','odom_x','odom_y','yaw','dock','rescued','safety_due','safe_dwell','ble_id','ble_rssi','ble_valid','ble_age','ble_seq','ble_channel','ble_confirmed','ble_x','ble_y','ble_yaw','ble_time','mission_left'];
export function compile(source,ram=64,profile=PROFILE){if(profile===LEGACY_PROFILE)return legacyCompile(source,ram);const labels={},lines=[];for(const [i,raw] of source.split('\n').entries()){let line=raw.split(';')[0].trim();if(!line)continue;if(line.endsWith(':')){const label=line.slice(0,-1);if(label in labels)throw Error(`Line ${i+1}: duplicate label`);labels[label]=lines.length;continue;}lines.push({p:line.split(/\s+/),line:i+1});}if(!lines.length)throw Error('ROM is empty');if(lines.length>1024)throw Error('ROM exceeds 1024 instructions');const reg=s=>/^r\d+$/.test(s)&&+s.slice(1)<Math.floor(ram/4);const value=s=>reg(s)||Number.isFinite(Number(s));for(const l of lines){const [op,...args]=l.p;const bad=m=>{throw Error(`Line ${l.line}: ${m}`)};if(!(op in specs)||args.length!==specs[op])bad('unknown instruction or wrong argument count');if(['sense','set','add','sub','mul','div','lt','gt','abs','sqrt','sin','cos','atan2','wrap','rand'].includes(op)&&!reg(args[0]))bad('invalid register (each uses 4 bytes)');if(op==='sense'&&!sensors.includes(args[1]))bad('unknown sensor');if(['set','add','sub','mul','div','lt','gt','atan2'].includes(op)&&!value(args[1]))bad('invalid value');if(['move','strafe','turn','pan','sweep'].includes(op)&&!value(args[0]))bad('invalid value');if(['jmp','jz','jnz'].includes(op)){if(op!=='jmp'&&!value(args[0]))bad('invalid condition');let j=args.length-1;const n=args[j] in labels?labels[args[j]]:Number(args[j]);if(!Number.isInteger(n)||n<0||n>=lines.length)bad('invalid jump');args[j]=String(n);l.p=[op,...args];}}return lines.map(l=>l.p);}
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export class Sim{
constructor(map=arena(),config={},source=null){if(config.sensorModel&&![PROFILE,LEGACY_PROFILE].includes(config.sensorModel))throw Error('Unknown sensor profile');if(config.sensorModel===LEGACY_PROFILE)return new LegacySim(map,config,source??legacyRoms['Explore + rescue']);source=source??roms['Scan in place'];this.map=structuredClone(map);this.c={...defaults,...config};this.program=compile(source,this.c.ram,this.c.sensorModel);this.reg=new Float32Array(Math.floor(this.c.ram/4));this.pc=0;this.odom={x:0,y:0,a:0};this.odomRng=(this.c.seed+987654321)>>>0;this.rng=this.c.seed>>>0;this.robot={...map.start};this.t=0;this.energy=this.c.battery;this.found=new Set;this.collisions=0;this.distance=0;this.path=[];this.coverage=new Set;this.cmd={move:0,strafe:0,turn:0,pan:0,sweep:0};this.head={angle:0,target:0,rate:0,direction:1};this.sensorRng=(this.c.seed+43129)>>>0;this.ping=null;this.lightTime=-1;this.lightValue=0;this.bleRng=(this.c.seed+70391)>>>0;this.blePacket=null;this.bleTick=-1;this.bleStreaks=new Map;this.bumper=0;this.safeDwell=0;this.safetyDeadline=30;this.safetyChecks=[];this.status='Ready';this.readings=this.sense();}
odometryRandom(){this.odomRng=(Math.imul(1664525,this.odomRng)+1013904223)>>>0;return this.odomRng/4294967296;}
random(){this.rng=(Math.imul(1664525,this.rng)+1013904223)>>>0;return this.rng/4294967296;}
blocked(x,y,r=R){return x<r||y<r||x>W-r||y>H-r||this.map.obstacles.some(b=>b.shape==='circle'?Math.hypot(x-b.x-b.w/2,y-b.y-b.h/2)<r+b.w/2:Math.hypot(x-clamp(x,b.x,b.x+b.w),y-clamp(y,b.y,b.y+b.h))<r);}
ray(a,max){const {x,y}=this.robot;for(let d=0;d<=max;d+=.5)if(this.blocked(x+Math.cos(a)*d,y+Math.sin(a)*d,0.1))return d;return max;}
visible(p){const dx=p.x-this.robot.x,dy=p.y-this.robot.y,d=Math.hypot(dx,dy),a=Math.atan2(dy,dx),bearing=Math.atan2(Math.sin(a-this.robot.a),Math.cos(a-this.robot.a));return this.c.camera&&d<=this.c.vision&&Math.abs(bearing)<=this.c.fov*Math.PI/360&&this.ray(a,d)>=d-.5?bearing:null;}
sensorRandom(){this.sensorRng=(Math.imul(1664525,this.sensorRng)+1013904223)>>>0;return this.sensorRng/4294967296;}
headCommand(op,value){value=Number.isFinite(value)?value:0;if(op==='pan'){this.head.rate=0;this.head.target=clamp(value,-this.c.panSpan/2,this.c.panSpan/2);this.cmd.pan=this.head.target;this.cmd.sweep=0;}else{const rate=clamp(value,-this.c.panSpeed,this.c.panSpeed);if(rate!==this.head.rate)this.head.direction=rate<0?-1:1;this.head.rate=rate;this.cmd.sweep=rate;if(!rate){this.head.target=this.head.angle;this.cmd.pan=this.head.angle;}}}
advanceHead(){const h=this.head,limit=this.c.panSpan/2;if(h.rate){h.angle+=Math.abs(h.rate)*h.direction*DT;while(h.angle>limit||h.angle< -limit){if(h.angle>limit){h.angle=2*limit-h.angle;h.direction=-1;}else{h.angle=-2*limit-h.angle;h.direction=1;}}}else h.angle+=clamp(h.target-h.angle,-this.c.panSpeed*DT,this.c.panSpeed*DT);}
sonarOrigin(estimated=false){const p=estimated?this.odom:this.robot;const angle=p.a+this.head.angle*Math.PI/180;return {x:p.x+HEAD_PIVOT_CM*Math.cos(p.a)+HEAD_OFFSET_CM*Math.cos(angle),y:p.y+HEAD_PIVOT_CM*Math.sin(p.a)+HEAD_OFFSET_CM*Math.sin(angle),a:angle};}
sonarBlocked(x,y){const objects=this.map.objects||[];const ordinary=this.map.obstacles.filter(b=>!objects.some(o=>o.id===b.owner&&(o.type==='laptop'||o.type==='shade')));if(ordinary.some(b=>b.shape==='circle'?Math.hypot(x-b.x-b.w/2,y-b.y-b.h/2)<=b.w/2:x>=b.x&&x<=b.x+b.w&&y>=b.y&&y<=b.y+b.h))return true;return objects.some(o=>o.type==='laptop'&&x>=o.x&&x<=o.x+o.w&&y>=o.y+.4&&y<=o.y+1.2);}
sonarRay(origin,a,max){for(let d=0;d<=max;d+=.25)if(this.sonarBlocked(origin.x+Math.cos(a)*d,origin.y+Math.sin(a)*d))return d;return null;}
lightTransmission(){let transmission=1;for(const o of this.map.objects||[]){if(!['hidebox','shade'].includes(o.type))continue;const {x,y}=this.robot;if(x>o.x&&x<o.x+o.w&&y>o.y&&y<o.y+o.h){const depth=o.type==='hidebox'?(o.opening==='right'?o.x+o.w-x:x-o.x):Math.min(x-o.x,o.x+o.w-x,y-o.y,o.y+o.h-y);const leak=this.c.coverLeak+(1-this.c.coverLeak)*.45*Math.exp(-depth/8);transmission=Math.min(transmission,leak);}}return transmission;}
bleRandom(){this.bleRng=(Math.imul(1664525,this.bleRng)+1013904223)>>>0;return this.bleRng/4294967296;}
blePower(index,channel=37){return expectedRSSI(this.map,this.c,this.robot.x+6.8*Math.cos(this.robot.a),this.robot.y+6.8*Math.sin(this.robot.a),index,channel);}
bleSense(){
if(!this.c.ble)return {ble_id:0,ble_rssi:-127,ble_valid:0,ble_age:-1,ble_seq:0,ble_channel:0,ble_confirmed:0,ble_x:0,ble_y:0,ble_yaw:0,ble_time:-1};
const tick=Math.floor((this.t+1e-7)*5),count=this.map.targets.length;
if(tick!==this.bleTick){this.bleTick=tick;if(count){const index=tick%count,channel=37+Math.floor(tick/count)%3,power=this.blePower(index,channel),noise=(this.bleRandom()*2-1)*this.c.bleNoise,lost=this.bleRandom()<this.c.bleDrop;
if(!lost&&power+noise>=-95){const rssi=Math.round(clamp(power+noise,-95,this.c.bleContact)),old=this.blePacket;this.blePacket={id:index+1,index,rssi,time:this.t,seq:(old?.seq||0)+1,channel,x:this.odom.x+6.8*Math.cos(this.odom.a),y:this.odom.y+6.8*Math.sin(this.odom.a),yaw:this.odom.a*180/Math.PI};
let streak=this.bleStreaks.get(index);if(rssi>=this.c.bleContact-2){if(!streak||this.t-streak.last>1.5)streak={first:this.t,last:this.t,count:0};streak.last=this.t;streak.count++;this.bleStreaks.set(index,streak);if(streak.count>=3&&this.t-streak.first>=1-1e-7)this.found.add(index);}else this.bleStreaks.delete(index);
}}}
const p=this.blePacket,age=p?this.t-p.time:-1;return {ble_id:p?.id||0,ble_rssi:p?.rssi??-127,ble_valid:p&&age<=1?1:0,ble_age:age,ble_seq:p?.seq||0,ble_channel:p?.channel||0,ble_confirmed:p&&this.found.has(p.index)?1:0,ble_x:p?.x||0,ble_y:p?.y||0,ble_yaw:p?.yaw||0,ble_time:p?.time??-1};
}
sense(){if(!this.ping||this.t-this.ping.time>=1/this.c.pingHz-1e-7){const origin=this.sonarOrigin(),estimate=this.sonarOrigin(true);let distance=null;for(let i=0;i<5;i++){const a=origin.a+(i/4-.5)*this.c.beam*Math.PI/180,d=this.sonarRay(origin,a,this.c.range);if(d!==null&&(distance===null||d<distance))distance=d;}const valid=distance!==null&&distance>=this.c.rangeMin;this.ping={world_x:origin.x,world_y:origin.y,world_a:origin.a,time:this.t,seq:(this.ping?.seq||0)+1,angle:this.head.angle,x:estimate.x,y:estimate.y,yaw:this.odom.a*180/Math.PI,valid:valid?1:0,range:valid?clamp(distance+(this.sensorRandom()*2-1)*this.c.noise,this.c.rangeMin,this.c.range):-1};}if(this.lightTime!==this.t){this.lightTime=this.t;this.lightValue=clamp(this.c.lightLevel*this.lightTransmission()+(this.sensorRandom()*2-1)*this.c.lightNoise,0,1);}const p=this.ping;const seen=this.map.targets.map((p,i)=>({i,p,b:this.visible(p)})).filter(v=>!this.found.has(v.i)&&v.b!==null).sort((u,v)=>Math.hypot(u.p.x-this.robot.x,u.p.y-this.robot.y)-Math.hypot(v.p.x-this.robot.x,v.p.y-this.robot.y));return {range:p.range,range_valid:p.valid,range_angle:p.angle,range_age:this.t-p.time,range_seq:p.seq,range_x:p.x,range_y:p.y,range_yaw:p.yaw,range_time:p.time,pan:this.head.angle,pan_ready:!this.head.rate&&Math.abs(this.head.angle-this.head.target)<.1?1:0,light:this.lightValue,target:seen.length?1:0,bearing:seen.length?clamp(seen[0].b/(this.c.fov*Math.PI/360),-1,1):0,observer:this.map.observer&&this.visible(this.map.observer)!==null?1:0,battery:this.energy/this.c.battery,bumper:this.c.bumpers?this.bumper:0,time:this.t,odom_x:this.odom.x,odom_y:this.odom.y,yaw:Math.atan2(Math.sin(this.odom.a),Math.cos(this.odom.a))*180/Math.PI,dock:Math.hypot(this.robot.x-this.map.start.x,this.robot.y-this.map.start.y)<=6?1:0,...this.bleSense(),rescued:this.found.size,safety_due:Math.max(0,this.safetyDeadline-this.t),safe_dwell:this.safeDwell,mission_left:this.c.missionRemaining===undefined?-1:Math.max(0,this.c.missionRemaining-this.t)};}
step(manual=null){if(this.status==='Complete'||this.status==='Battery depleted'||this.status.startsWith('Fault')||this.status==='Safety violation')return;this.status='Running';const s=this.readings;const val=x=>/^r/.test(x)?this.reg[+x.slice(1)]:Number(x);if(manual){this.cmd={...this.cmd,...manual};if(manual.pan!==undefined&&manual.sweep===0)this.headCommand('pan',manual.pan);if(manual.sweep!==undefined&&manual.sweep!==0)this.headCommand('sweep',manual.sweep);}else for(let n=0;n<this.c.budget;n++){const [op,a,b]=this.program[this.pc];this.pc=(this.pc+1)%this.program.length;const r=+a?.slice(1);if(op==='sense')this.reg[r]=s[b];if(op==='set')this.reg[r]=val(b);if(op==='add')this.reg[r]+=val(b);if(op==='sub')this.reg[r]-=val(b);if(op==='mul')this.reg[r]*=val(b);if(op==='div')this.reg[r]=val(b)?this.reg[r]/val(b):0;if(op==='gt')this.reg[r]=this.reg[r]>val(b)?1:0;if(op==='abs')this.reg[r]=Math.abs(this.reg[r]);if(op==='sqrt')this.reg[r]=Math.sqrt(Math.max(0,this.reg[r]));if(op==='sin')this.reg[r]=Math.sin(this.reg[r]*Math.PI/180);if(op==='cos')this.reg[r]=Math.cos(this.reg[r]*Math.PI/180);if(op==='atan2')this.reg[r]=Math.atan2(this.reg[r],val(b))*180/Math.PI;if(op==='wrap')this.reg[r]=((this.reg[r]+180)%360+360)%360-180;if(op==='lt')this.reg[r]=this.reg[r]<val(b)?1:0;if(op==='rand')this.reg[r]=this.random()*2-1;if(op==='jmp'||op==='jz'&&val(a)===0||op==='jnz'&&val(a)!==0)this.pc=+(op==='jmp'?a:b);if(['move','turn','strafe'].includes(op))this.cmd[op]=Number.isFinite(val(a))?clamp(val(a),-1,1):0;if(Number.isInteger(r)&&r>=0&&r<this.reg.length&&!Number.isFinite(this.reg[r]))this.reg[r]=0;if(op==='pan'||op==='sweep')this.headCommand(op,val(a));if(op==='yield')break;}
this.advanceHead();this.odom.a+=this.cmd.turn*this.c.turn*Math.PI/180*DT*(1+(this.odometryRandom()-.5)*.02);this.robot.a+=this.cmd.turn*this.c.turn*Math.PI/180*DT;let f=this.cmd.move,l=this.cmd.strafe;const norm=Math.max(1,Math.hypot(f,l));f/=norm;l/=norm;const drift=1+(this.odometryRandom()-.5)*.02;this.odom.x+=(Math.cos(this.odom.a)*f-Math.sin(this.odom.a)*l)*this.c.speed*DT*drift;this.odom.y+=(Math.sin(this.odom.a)*f+Math.cos(this.odom.a)*l)*this.c.speed*DT*drift;const a=this.robot.a,dx=(Math.cos(a)*f-Math.sin(a)*l)*this.c.speed*DT,dy=(Math.sin(a)*f+Math.cos(a)*l)*this.c.speed*DT;this.bumper=0;const segments=Math.max(1,Math.ceil(Math.hypot(dx,dy)/.5));for(let i=0;i<segments;i++){if(this.blocked(this.robot.x+dx/segments,this.robot.y+dy/segments)){this.bumper=1;this.collisions++;break;}this.robot.x+=dx/segments;this.robot.y+=dy/segments;this.distance+=Math.hypot(dx,dy)/segments;}this.t+=DT;this.energy=Math.max(0,this.energy-DT*(1+.4*Math.hypot(f,l)+.15*Math.abs(this.cmd.turn)));this.path.push({x:this.robot.x,y:this.robot.y});if(this.path.length>5000)this.path.shift();this.coverage.add(`${Math.floor(this.robot.x/40)},${Math.floor(this.robot.y/40)}`);if(this.c.virtualRescue&&!this.c.ble)this.map.targets.forEach((p,i)=>{if(Math.hypot(p.x-this.robot.x,p.y-this.robot.y)<10&&this.ray(Math.atan2(p.y-this.robot.y,p.x-this.robot.x),Math.hypot(p.x-this.robot.x,p.y-this.robot.y))>=Math.hypot(p.x-this.robot.x,p.y-this.robot.y)-.5)this.found.add(i)});if((this.c.virtualRescue||this.c.ble)&&!this.c.missionMode&&this.map.targets.length&&this.found.size===this.map.targets.length)this.status='Complete';else if(this.energy<=0)this.status='Battery depleted';this.readings=this.sense();this.safeDwell=this.readings.light<=.3?this.safeDwell+DT:0;
if(this.t+1e-7>=this.safetyDeadline){const safe=!!this.readings.dock||this.safeDwell+1e-7>=2;this.safetyChecks.push({time:this.safetyDeadline,safe,dock:this.readings.dock,light:this.readings.light,dwell:this.safeDwell,odom_x:this.readings.odom_x,odom_y:this.readings.odom_y,yaw:this.readings.yaw});this.safetyDeadline+=30;if(!safe)this.status='Safety violation';}
this.readings.safety_due=Math.max(0,this.safetyDeadline-this.t);this.readings.safe_dwell=this.safeDwell;}
}
