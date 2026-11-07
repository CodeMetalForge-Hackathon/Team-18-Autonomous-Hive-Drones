#pragma once
const char CONTROL_PAGE[] PROGMEM = R"HTML(<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>RoverC Pro</title><style>
*{box-sizing:border-box}body{font:17px system-ui;background:#101820;color:#f4f7fa;margin:0;padding:22px;max-width:560px;margin:auto}
h1{margin-bottom:4px}p{color:#b9cbd7}button{font:inherit;border:0;border-radius:12px;padding:20px 8px;color:white;background:#244459;touch-action:none;user-select:none}
button:active{background:#407c9e}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin:20px 0}.wide{width:100%;margin:10px 0;background:#167b68}#stop{background:#b53c45}
input{width:100%}#status{min-height:50px;color:#9ce5ce}small{color:#b9cbd7}a{color:#9ce5ce}
</style><h1>RoverC Pro</h1><p>Hold to drive. Release to stop.</p>
<div id="status" role="status">Connecting…</div>
<button class="wide" id="arm">Arm driving</button>
<label>Speed: <output id="value">20</output><input id="speed" type="range" min="10" max="40" value="20"></label>
<div class="grid"><button data-d="Q">↶ Rotate</button><button data-d="F">↑ Forward</button><button data-d="E">Rotate ↷</button>
<button data-d="L">← Strafe</button><button data-d="B">↓ Reverse</button><button data-d="R">Strafe →</button></div>
<button class="wide" id="stop">STOP / DISARM</button>
<small>Arrow keys drive. Q / E rotate. Space stops.<br>Switching away from this page disarms the rover.<br>The M5Stick B button stops it too.</small>
<script>
'use strict';
const status=document.querySelector('#status'), speed=document.querySelector('#speed');
let token='',seq=0,direction=null,inflight=false,arming=false,revision=0;
const keys={ArrowUp:'F',ArrowDown:'B',ArrowLeft:'L',ArrowRight:'R',q:'Q',e:'E'};
async function request(path,data={},auth=token,keepalive=false){
 const response=await fetch(path,{method:'POST',headers:{'X-Rover-Control':'1','X-Rover-Token':auth},body:new URLSearchParams(data),signal:AbortSignal.timeout(1200),keepalive});
 const value=await response.json(); if(!response.ok)throw Error(value.error||'Request failed');return value;
}
function disarm(message='Stopped. Click Arm driving to resume.'){
 revision++;direction=null;const old=token;token='';status.textContent=message;
 request('/api/disarm',{},old,true).catch(()=>{});
}
async function stopMotion(){
 if(!direction)return;direction=null;
 if(!token)return;
 try{await request('/api/stop',{seq:++seq});}catch(e){disarm('Connection lost. Re-arm to resume.');}
}
document.querySelector('#arm').onclick=async()=>{
 if(arming)return;arming=true;const rev=revision;
 try{const v=await request('/api/arm');if(rev!==revision){request('/api/disarm',{},v.token,true).catch(()=>{});return;}
 token=v.token;seq=0;direction=null;status.textContent='Armed. Hold a direction to drive.';
 }catch(e){status.textContent=e.message;}finally{arming=false;}
};
document.querySelector('#stop').onclick=()=>disarm();
speed.oninput=()=>document.querySelector('#value').textContent=speed.value;
document.querySelectorAll('[data-d]').forEach(button=>{
 button.onpointerdown=e=>{e.preventDefault();if(token){button.setPointerCapture(e.pointerId);direction=button.dataset.d;}};
 button.onpointerup=stopMotion;button.onpointercancel=stopMotion;button.onlostpointercapture=stopMotion;
});
addEventListener('keydown',e=>{if(e.code==='Space'){e.preventDefault();disarm();}else if(keys[e.key]){e.preventDefault();if(token)direction=keys[e.key];}});
addEventListener('keyup',e=>{if(keys[e.key]===direction)stopMotion();});
addEventListener('blur',()=>disarm());addEventListener('pagehide',()=>disarm());
document.addEventListener('visibilitychange',()=>{if(document.hidden)disarm();});
setInterval(async()=>{
 if(!token||!direction||inflight)return;inflight=true;const old=token;
 try{await request('/api/drive',{d:direction,s:speed.value,seq:++seq},old);}catch(e){if(token===old)disarm('Drive stopped: '+e.message);}
 finally{inflight=false;}
},80);
setInterval(async()=>{
 const current=token;
 try{const response=await fetch('/api/status',{headers:{'X-Rover-Token':current},signal:AbortSignal.timeout(1200)});const v=await response.json();if(current!==token)return;
 if(token&&!v.owner){token='';direction=null;status.textContent='Disarmed. Click Arm driving to resume.';}
 else if(!token&&!arming)status.textContent=v.connected?'Rover ready. Click Arm driving.':'Rover not found. Check power.';
 }catch(e){if(token)disarm('Connection lost. Re-arm to resume.');else status.textContent='Connect to the rover Wi-Fi to continue.';}
},500);
</script></html>)HTML";
