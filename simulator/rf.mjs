// Empirical RF approximation, NOT a calibrated electromagnetic solver. cm and dBm.
export const RF_LOSS_DB={laptop:8,bottle:4,plant:3,hidebox:2,wall:2};
function intersects(ax,ay,bx,by,b){
 if(b.shape==='circle'){const dx=bx-ax,dy=by-ay,t=Math.max(0,Math.min(1,((b.x+b.w/2-ax)*dx+(b.y+b.h/2-ay)*dy)/(dx*dx+dy*dy||1)));return Math.hypot(ax+t*dx-b.x-b.w/2,ay+t*dy-b.y-b.h/2)<=b.w/2;}
 let near=0,far=1;for(const [origin,delta,lo,hi]of [[ax,bx-ax,b.x,b.x+b.w],[ay,by-ay,b.y,b.y+b.h]]){if(Math.abs(delta)<1e-10){if(origin<lo||origin>hi)return false;}else{let a=(lo-origin)/delta,c=(hi-origin)/delta;if(a>c)[a,c]=[c,a];near=Math.max(near,a);far=Math.min(far,c);if(near>far)return false;}}return true;
}
export function expectedRSSI(map,c,rx,ry,index,channel=37){
 const p=map.targets[index];if(!p)return -127;const d=Math.hypot(p.x-rx,p.y-ry);let attenuation=0;
 for(const b of map.obstacles||[]){if(!intersects(rx,ry,p.x,p.y,b))continue;const o=(map.objects||[]).find(o=>o.id===b.owner);attenuation+=RF_LOSS_DB[o?.type]??5;}
 // Wavelength-scale spatial fading; channel-dependent phase, tapered near contact.
 const fade=(c.bleMultipath??3)*Math.min(1,Math.max(0,(d-2)/20))*Math.sin(rx*.43+index*1.7+channel)*Math.cos(ry*.37-channel);
 return Math.min(c.bleContact??-35,(c.bleContact??-35)-20*Math.log10(Math.max(2,d)/2)-attenuation+fade);
}
