import {expectedRSSI} from './rf.mjs';
let cacheKey='',cached;
export function rfCanvas(map,config,index){
 const key=JSON.stringify([map,config.bleContact,config.bleMultipath,index]);if(cacheKey===key)return cached;
 cacheKey=key;cached=document.createElement('canvas');cached.width=125;cached.height=50;const ctx=cached.getContext('2d'),pixels=ctx.createImageData(125,50);
 const stops=[[30,55,145],[30,165,175],[70,195,100],[245,185,55],[240,65,45]];
 for(let y=0;y<50;y++)for(let x=0;x<125;x++){const rssi=[37,38,39].reduce((sum,ch)=>sum+expectedRSSI(map,config,x*2+1,y*2+1,index,ch),0)/3,v=Math.max(0,Math.min(3.999,(rssi+95)/60*4)),i=Math.floor(v),f=v-i,k=(y*125+x)*4;for(let c=0;c<3;c++)pixels.data[k+c]=Math.round(stops[i][c]*(1-f)+stops[i+1][c]*f);pixels.data[k+3]=205;}
 ctx.putImageData(pixels,0,0);return cached;
}
