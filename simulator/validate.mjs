import {compile,Sim} from './engine.mjs';
let data='';for await(const chunk of process.stdin)data+=chunk;
try{const {source,ram,world}=JSON.parse(data);if(world){const s=new Sim(world,{},'yield');if(s.blocked(world.start.x,world.start.y))throw Error('Download dock overlaps an obstacle or table edge');}const program=compile(source,ram);process.stdout.write(JSON.stringify({ok:true,instructions:program.length}));}catch(e){process.stdout.write(JSON.stringify({ok:false,error:e.message}));process.exitCode=1;}
