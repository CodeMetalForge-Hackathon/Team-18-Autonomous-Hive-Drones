const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname, '../firmware/roverc-test/ControlPage.h'), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
const controls = Object.fromEntries(['#status','#speed','#value','#arm','#stop'].map(k => [k, {value:'20'}]));
const buttons = ['Q','F','E','L','B','R'].map(d=>({dataset:{d},setPointerCapture(){}}));
const events = {}, intervals = [], requests = [];
let armResponse;
const context = {
 document: {querySelector:k=>controls[k],querySelectorAll:()=>buttons,addEventListener:(k,f)=>events[k]=f,hidden:false},
 addEventListener:(k,f)=>events[k]=f,
 setInterval:(f,ms)=>intervals.push({f,ms}),
 AbortSignal, URLSearchParams,
 fetch:async(path,options={})=>{
  requests.push({path,options});
  if(path==='/api/arm' && armResponse) return await armResponse;
  return {ok:true,json:async()=>path==='/api/arm'?{token:'session-one'}:{ok:true,connected:true,owner:true}};
 }
};
vm.runInNewContext(source,context);
const tick = intervals.find(i=>i.ms===80).f;
(async()=>{
 await controls['#arm'].onclick();
 buttons[1].onpointerdown({preventDefault(){},pointerId:1});
 await tick();
 const drive=requests.find(r=>r.path==='/api/drive');
 assert.equal(drive.options.body.get('d'),'F');
 assert.equal(drive.options.body.get('seq'),'1');
 await buttons[1].onpointerup();
 const stop=requests.find(r=>r.path==='/api/stop');
 assert.equal(stop.options.body.get('seq'),'2');
 const before=requests.filter(r=>r.path==='/api/drive').length;
 await tick();
 assert.equal(requests.filter(r=>r.path==='/api/drive').length,before);
 events.blur();
 assert.equal(requests.at(-1).path,'/api/disarm');
 buttons[1].onpointerdown({preventDefault(){},pointerId:1});
 await tick();
 assert.equal(requests.filter(r=>r.path==='/api/drive').length,before);
 let resolve;
 armResponse=new Promise(r=>resolve=r);
 const pending=controls['#arm'].onclick();
 events.blur();
 resolve({ok:true,json:async()=>({token:'late-session'})});
 await pending;
 assert.equal(requests.at(-1).path,'/api/disarm');
 assert.equal(requests.at(-1).options.headers['X-Rover-Token'],'late-session');
 await tick();
 assert.equal(requests.filter(r=>r.path==='/api/drive').length,before);
 console.log('PASS: hold/release ordering, no drive after release, focus-loss disarm, late-arm cancellation.');
})().catch(error=>{console.error(error);process.exitCode=1;});
