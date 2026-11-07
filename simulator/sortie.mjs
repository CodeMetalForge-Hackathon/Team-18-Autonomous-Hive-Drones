// Trusted bridge. Its input and observer frames NEVER enter the agent workspace.
import {Sim} from './engine.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;
const job=JSON.parse(input),sim=new Sim(job.map,{...job.config,missionMode:true,seed:(job.config.seed??42)+job.sortie},job.rom);
sim.found=new Set(job.found||[]);sim.readings=sim.sense();
const replayFrames=[];
const frames=[],capacity=65536;let used=0,dropped=0,left=false,tick=0;
const emit=value=>process.stdout.write(JSON.stringify(value)+'\n');
function record(){const row={t:+sim.t.toFixed(2),readings:Object.fromEntries(Object.entries(sim.readings).map(([k,v])=>[k,+v.toFixed(4)])),commands:{...sim.cmd}};const size=Buffer.byteLength(JSON.stringify(row));frames.push(row);used+=size;while(used>capacity){used-=Buffer.byteLength(JSON.stringify(frames.shift()));dropped++}}
function snapshot(){return{robot:sim.robot,t:sim.t,energy:sim.energy,readings:sim.readings,cmd:sim.cmd,found:[...sim.found],distance:sim.distance,collisions:sim.collisions,path:sim.path.slice(-1200),c:sim.c,status:sim.status}}
function remember(){const {path,c,...frame}=snapshot();replayFrames.push(structuredClone(frame));}
record();remember();if(!job.replay)emit({type:'frame',state:snapshot()});
const speed=Math.max(1,Math.min(100,job.speed||8));const batch=Math.max(1,Math.round(speed));
let result='';while(!result){for(let i=0;i<batch&&!result;i++){sim.step();remember();tick++;if(Math.hypot(sim.robot.x-job.map.start.x,sim.robot.y-job.map.start.y)>10)left=true;if(tick%2===0)record();if(left&&sim.readings.dock){result='docked';record()}else if(sim.energy<=0)result='battery_depleted';else if(sim.t>=job.max_seconds)result=left?'stranded':'never_departed';}if(!job.replay)emit({type:'frame',state:snapshot()});if(!result&&!job.replay)await new Promise(r=>setTimeout(r,100))}
// The upload is withheld by the trusted server unless physical docking succeeded.
emit({type:'end',result,state:snapshot(),replay_frames:replayFrames,upload:result==='docked'?{sortie:job.sortie,elapsed_seconds:+sim.t.toFixed(2),logger:{capacity_bytes:capacity,used_bytes:used,dropped_samples:dropped,sample_hz:5},samples:frames}:null});
