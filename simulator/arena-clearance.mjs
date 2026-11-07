import {Sim,R} from './engine.mjs';
// Designer-only audit. Its routes, coordinates and geometry never enter Opus's workspace.
export function auditClearance(map,margin=5){
 const radius=R+margin,sim=new Sim(map,{ble:false},'yield'),start=[Math.round(map.start.x),Math.round(map.start.y)],queue=[start],seen=new Set([start.join(',')]);
 if(sim.blocked(...start,radius))return {ok:false,error:'Dock lacks the required clearance',radius};
 for(let i=0;i<queue.length;i++){const[x,y]=queue[i];for(const[dx,dy]of[[1,0],[-1,0],[0,1],[0,-1]]){const a=x+dx,b=y+dy,key=a+','+b;if(a<0||a>250||b<0||b>100||seen.has(key)||sim.blocked(a,b,radius))continue;seen.add(key);queue.push([a,b]);}}
 const reachable=p=>seen.has(Math.round(p.x)+','+Math.round(p.y));
 const targets=map.targets.map(reachable),shelters=(map.objects||[]).filter(o=>o.type==='hidebox').map(o=>({id:o.id,reachable:reachable({x:o.x+o.w/2,y:o.y+o.h/2})}));
 const approaches=map.targets.map(p=>{const roof=(map.objects||[]).find(o=>o.type==='hidebox'&&p.x>o.x&&p.x<o.x+o.w&&p.y>o.y&&p.y<o.y+o.h);return reachable({x:p.x+(roof?.opening==='right'?8.8:-8.8),y:p.y});});
 return {ok:targets.every(Boolean)&&approaches.every(Boolean)&&shelters.every(s=>s.reachable),radius_cm:radius,rover_diameter_cm:R*2,required_lane_cm:radius*2,side_margin_cm:margin,targets,approaches,shelters,connected_cells:seen.size};
}
