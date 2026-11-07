export const W=250,H=100,R=8.5,DT=.1;
export const defaults={range:80,noise:.4,speed:12,turn:90,battery:240,camera:true,fov:65,vision:120,ram:64,budget:32,seed:42};
export function addObject(map,type,x,y){
const id=`object-${(map.objects||[]).length}-${x}-${y}`;
const sizes={laptop:[32,23],bottle:[7,7],hidebox:[34,28]};
const [w,h]=sizes[type];x=Math.max(1,Math.min(W-w-1,x));y=Math.max(1,Math.min(H-h-1,y));
const object={id,type,x,y,w,h};(map.objects??=[]).push(object);
if(type==='hidebox')map.obstacles.push({x,y,w,h:1,owner:id},{x,y:y+h-1,w,h:1,owner:id},{x:x+w-1,y,w:1,h,owner:id});
else if(type==='bottle')map.obstacles.push({x,y,w,h,shape:'circle',owner:id});
else map.obstacles.push({x,y,w,h,owner:id});
return object;
}
export function arena(){const map={width:W,height:H,start:{x:18,y:50,a:0},obstacles:[],objects:[],targets:[{x:99,y:77},{x:222,y:77},{x:230,y:20}],observer:{x:132,y:7}};
addObject(map,'laptop',39,7);addObject(map,'laptop',112,32);addObject(map,'laptop',176,7);
addObject(map,'bottle',82,29);addObject(map,'bottle',159,66);addObject(map,'bottle',216,39);addObject(map,'bottle',53,82);
addObject(map,'hidebox',78,62);addObject(map,'hidebox',202,62);return map;}
export const roms={
'Explore + rescue':`; Three rangefinders + optional color-bearing camera\n; Target is confirmed automatically within 10 cm.\nsense r0 target\njz r0 roam\nsense r1 bearing\nturn r1\nmove 0.65\nyield\njmp 0\nroam:\nsense r0 front\nlt r0 20\njnz r0 avoid\nsense r0 left\nlt r0 13\njnz r0 right\nturn 0\nmove 1\nyield\njmp 0\navoid:\nturn 0.85\nmove 0\nyield\njmp 0\nright:\nturn 0.7\nmove 0.3\nyield\njmp 0`,
'Wall follower':`sense r0 target\njz r0 wall\nsense r1 bearing\nturn r1\nmove 0.6\nyield\njmp 0\nwall:\nsense r0 front\nlt r0 20\njnz r0 avoid\nsense r0 right\nlt r0 23\njnz r0 away\nturn 0.3\nmove 0.7\nyield\njmp 0\naway:\nturn -0.15\nmove 0.8\nyield\njmp 0\navoid:\nturn -0.9\nmove 0\nyield\njmp 0`,
'Reactive wander':`sense r0 front\nlt r0 23\njnz r0 avoid\nturn 0\nmove 1\nyield\njmp 0\navoid:\nturn -0.8\nmove 0\nyield\njmp 0`};
// Shared short contact recovery; finite body clearance can differ from a range ray.
for(const name of Object.keys(roms)) roms[name]=`sense r4 bumper
jz r4 recovery_check
set r3 10
recovery_check:
jnz r3 recovering
jmp normal_entry
recovering:
add r3 -1
move -0.35
turn -0.8
yield
jmp 0
normal_entry:
`+roms[name];
const specs={sense:2,set:2,add:2,sub:2,mul:2,div:2,gt:2,abs:1,sqrt:1,sin:1,cos:1,atan2:2,wrap:1,lt:2,jz:2,jnz:2,jmp:1,rand:1,move:1,strafe:1,turn:1,yield:0};
const sensors=['front','left','right','target','bearing','observer','battery','bumper','time','odom_x','odom_y','yaw','dock','rescued'];
export function compile(source,ram=64){const labels={},lines=[];for(const [i,raw] of source.split('\n').entries()){let line=raw.split(';')[0].trim();if(!line)continue;if(line.endsWith(':')){const label=line.slice(0,-1);if(label in labels)throw Error(`Line ${i+1}: duplicate label`);labels[label]=lines.length;continue;}lines.push({p:line.split(/\s+/),line:i+1});}if(!lines.length)throw Error('ROM is empty');if(lines.length>1024)throw Error('ROM exceeds 1024 instructions');const reg=s=>/^r\d+$/.test(s)&&+s.slice(1)<Math.floor(ram/4);const value=s=>reg(s)||Number.isFinite(Number(s));for(const l of lines){const [op,...args]=l.p;const bad=m=>{throw Error(`Line ${l.line}: ${m}`)};if(!(op in specs)||args.length!==specs[op])bad('unknown instruction or wrong argument count');if(['sense','set','add','sub','mul','div','lt','gt','abs','sqrt','sin','cos','atan2','wrap','rand'].includes(op)&&!reg(args[0]))bad('invalid register (each uses 4 bytes)');if(op==='sense'&&!sensors.includes(args[1]))bad('unknown sensor');if(['set','add','sub','mul','div','lt','gt','atan2'].includes(op)&&!value(args[1]))bad('invalid value');if(['move','strafe','turn'].includes(op)&&!value(args[0]))bad('invalid value');if(['jmp','jz','jnz'].includes(op)){if(op!=='jmp'&&!value(args[0]))bad('invalid condition');let j=args.length-1;const n=args[j] in labels?labels[args[j]]:Number(args[j]);if(!Number.isInteger(n)||n<0||n>=lines.length)bad('invalid jump');args[j]=String(n);l.p=[op,...args];}}return lines.map(l=>l.p);}
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
export class Sim{
constructor(map=arena(),config={},source=roms['Explore + rescue']){this.map=structuredClone(map);this.c={...defaults,...config};this.program=compile(source,this.c.ram);this.reg=new Float32Array(Math.floor(this.c.ram/4));this.pc=0;this.odom={x:0,y:0,a:0};this.odomRng=(this.c.seed+987654321)>>>0;this.rng=this.c.seed>>>0;this.robot={...map.start};this.t=0;this.energy=this.c.battery;this.found=new Set;this.collisions=0;this.distance=0;this.path=[];this.coverage=new Set;this.cmd={move:0,strafe:0,turn:0};this.bumper=0;this.status='Ready';this.readings=this.sense();}
odometryRandom(){this.odomRng=(Math.imul(1664525,this.odomRng)+1013904223)>>>0;return this.odomRng/4294967296;}
random(){this.rng=(Math.imul(1664525,this.rng)+1013904223)>>>0;return this.rng/4294967296;}
blocked(x,y,r=R){return x<r||y<r||x>W-r||y>H-r||this.map.obstacles.some(b=>b.shape==='circle'?Math.hypot(x-b.x-b.w/2,y-b.y-b.h/2)<r+b.w/2:Math.hypot(x-clamp(x,b.x,b.x+b.w),y-clamp(y,b.y,b.y+b.h))<r);}
ray(a,max){const {x,y}=this.robot;for(let d=0;d<=max;d+=.5)if(this.blocked(x+Math.cos(a)*d,y+Math.sin(a)*d,0.1))return d;return max;}
visible(p){const dx=p.x-this.robot.x,dy=p.y-this.robot.y,d=Math.hypot(dx,dy),a=Math.atan2(dy,dx),bearing=Math.atan2(Math.sin(a-this.robot.a),Math.cos(a-this.robot.a));return this.c.camera&&d<=this.c.vision&&Math.abs(bearing)<=this.c.fov*Math.PI/360&&this.ray(a,d)>=d-.5?bearing:null;}
sense(){const a=this.robot.a,range=offset=>clamp(this.ray(a+offset,this.c.range)+(this.random()*2-1)*this.c.noise,0,this.c.range);const seen=this.map.targets.map((p,i)=>({i,p,b:this.visible(p)})).filter(v=>!this.found.has(v.i)&&v.b!==null).sort((u,v)=>Math.hypot(u.p.x-this.robot.x,u.p.y-this.robot.y)-Math.hypot(v.p.x-this.robot.x,v.p.y-this.robot.y));return {front:range(0),left:range(-Math.PI/2),right:range(Math.PI/2),target:seen.length?1:0,bearing:seen.length?clamp(seen[0].b/(this.c.fov*Math.PI/360),-1,1):0,observer:this.map.observer&&this.visible(this.map.observer)!==null?1:0,battery:this.energy/this.c.battery,bumper:this.bumper,time:this.t,odom_x:this.odom.x,odom_y:this.odom.y,yaw:Math.atan2(Math.sin(this.odom.a),Math.cos(this.odom.a))*180/Math.PI,dock:Math.hypot(this.robot.x-this.map.start.x,this.robot.y-this.map.start.y)<=6?1:0,rescued:this.found.size};}
step(manual=null){if(this.status==='Complete'||this.status==='Battery depleted'||this.status.startsWith('Fault'))return;this.status='Running';const s=this.readings;const val=x=>/^r/.test(x)?this.reg[+x.slice(1)]:Number(x);if(manual)this.cmd={...manual};else for(let n=0;n<this.c.budget;n++){const [op,a,b]=this.program[this.pc];this.pc=(this.pc+1)%this.program.length;const r=+a?.slice(1);if(op==='sense')this.reg[r]=s[b];if(op==='set')this.reg[r]=val(b);if(op==='add')this.reg[r]+=val(b);if(op==='sub')this.reg[r]-=val(b);if(op==='mul')this.reg[r]*=val(b);if(op==='div')this.reg[r]=val(b)?this.reg[r]/val(b):0;if(op==='gt')this.reg[r]=this.reg[r]>val(b)?1:0;if(op==='abs')this.reg[r]=Math.abs(this.reg[r]);if(op==='sqrt')this.reg[r]=Math.sqrt(Math.max(0,this.reg[r]));if(op==='sin')this.reg[r]=Math.sin(this.reg[r]*Math.PI/180);if(op==='cos')this.reg[r]=Math.cos(this.reg[r]*Math.PI/180);if(op==='atan2')this.reg[r]=Math.atan2(this.reg[r],val(b))*180/Math.PI;if(op==='wrap')this.reg[r]=((this.reg[r]+180)%360+360)%360-180;if(op==='lt')this.reg[r]=this.reg[r]<val(b)?1:0;if(op==='rand')this.reg[r]=this.random()*2-1;if(op==='jmp'||op==='jz'&&val(a)===0||op==='jnz'&&val(a)!==0)this.pc=+(op==='jmp'?a:b);if(['move','turn','strafe'].includes(op))this.cmd[op]=Number.isFinite(val(a))?clamp(val(a),-1,1):0;if(Number.isInteger(r)&&r>=0&&r<this.reg.length&&!Number.isFinite(this.reg[r]))this.reg[r]=0;if(op==='yield')break;}
this.odom.a+=this.cmd.turn*this.c.turn*Math.PI/180*DT*(1+(this.odometryRandom()-.5)*.02);this.robot.a+=this.cmd.turn*this.c.turn*Math.PI/180*DT;let f=this.cmd.move,l=this.cmd.strafe;const norm=Math.max(1,Math.hypot(f,l));f/=norm;l/=norm;const drift=1+(this.odometryRandom()-.5)*.02;this.odom.x+=(Math.cos(this.odom.a)*f-Math.sin(this.odom.a)*l)*this.c.speed*DT*drift;this.odom.y+=(Math.sin(this.odom.a)*f+Math.cos(this.odom.a)*l)*this.c.speed*DT*drift;const a=this.robot.a,dx=(Math.cos(a)*f-Math.sin(a)*l)*this.c.speed*DT,dy=(Math.sin(a)*f+Math.cos(a)*l)*this.c.speed*DT;this.bumper=0;const segments=Math.max(1,Math.ceil(Math.hypot(dx,dy)/.5));for(let i=0;i<segments;i++){if(this.blocked(this.robot.x+dx/segments,this.robot.y+dy/segments)){this.bumper=1;this.collisions++;break;}this.robot.x+=dx/segments;this.robot.y+=dy/segments;this.distance+=Math.hypot(dx,dy)/segments;}this.t+=DT;this.energy=Math.max(0,this.energy-DT*(1+.4*Math.hypot(f,l)+.15*Math.abs(this.cmd.turn)));this.path.push({x:this.robot.x,y:this.robot.y});if(this.path.length>5000)this.path.shift();this.coverage.add(`${Math.floor(this.robot.x/40)},${Math.floor(this.robot.y/40)}`);this.map.targets.forEach((p,i)=>{if(Math.hypot(p.x-this.robot.x,p.y-this.robot.y)<10&&this.ray(Math.atan2(p.y-this.robot.y,p.x-this.robot.x),Math.hypot(p.x-this.robot.x,p.y-this.robot.y))>=Math.hypot(p.x-this.robot.x,p.y-this.robot.y)-.5)this.found.add(i)});if(!this.c.missionMode&&this.map.targets.length&&this.found.size===this.map.targets.length)this.status='Complete';else if(this.energy<=0)this.status='Battery depleted';this.readings=this.sense();}
}
