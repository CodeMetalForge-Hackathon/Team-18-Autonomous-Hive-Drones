import assert from 'node:assert/strict';
import {createLiveCamera} from './live-camera.mjs';

function element(){
  const classes=new Set();
  return {hidden:true,disabled:true,textContent:'',classList:{
    add:name=>classes.add(name),remove:name=>classes.delete(name),contains:name=>classes.has(name)}};
}
const button=element(),panel=element(),image=element(),status=element();
const handlers={},timers=new Map(),requests=[];
let timerId=0,frameAvailable=true,shown=0;
globalThis.document={hidden:false,body:element(),addEventListener:(name,fn)=>handlers[name]=fn};
globalThis.setTimeout=(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId};
globalThis.clearTimeout=id=>timers.delete(id);
globalThis.fetch=async(path,options)=>{
  requests.push({path,options});
  if(path.endsWith('/status'))return {ok:true,json:async()=>({configured:true})};
  return {ok:frameAvailable,headers:new Map([['X-Captured-Ms',String(Date.now())],['X-Frame-Width','640'],['X-Frame-Height','400']]),blob:async()=>new Blob(['frame'])};
};
const settle=()=>new Promise(resolve=>setImmediate(resolve));
const viewer=createLiveCamera({button,panel,image,status,onShow:()=>shown++});
await settle();
assert.equal(button.disabled,false);
assert.equal(requests.length,1,'configuration check must not fetch camera frames');
viewer.show();await settle();
assert.equal(shown,1);assert.equal(panel.hidden,false);assert.equal(image.hidden,false);
assert.equal(status.textContent,'Connected');
const firstImage=image.src;
viewer.hide();
assert.equal(panel.hidden,true);assert.equal(timers.size,0,'hidden view must stop polling');
frameAvailable=false;viewer.show();await settle();
assert.equal(status.textContent,'Reconnecting');
assert.equal(image.src,firstImage);
assert.equal(panel.classList.contains('unavailable'),true);
frameAvailable=true;
const retry=[...timers.entries()].find(([,t])=>t.ms===1000);assert.ok(retry);timers.delete(retry[0]);retry[1].fn();await settle();
assert.equal(panel.classList.contains('unavailable'),false);
document.hidden=true;handlers.visibilitychange();
assert.equal(timers.size,0);
document.hidden=false;handlers.visibilitychange();await settle();
assert.equal(status.textContent,'Connected');
viewer.hide();URL.revokeObjectURL(image.src);
console.log('Live camera view: lazy loading, fresh frames, failure/recovery, and hidden-view cancellation passed.');
