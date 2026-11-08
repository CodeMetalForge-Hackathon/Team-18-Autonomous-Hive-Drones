import {createLiveCamera} from './live-camera.mjs';
const $=id=>document.getElementById(id);
const camera=createLiveCamera({panel:$('live-camera'),image:$('camera-image'),status:$('camera-status')});
let simulator=null;
export async function setMode(mode,loadSimulator=()=>import('./simulator.mjs')){
  const live=mode==='live';
  document.body.dataset.mode=live?'live':'simulator';
  $('live-mode').hidden=!live;$('simulator-mode').hidden=live;
  for(const name of ['live','simulator']){
    $('mode-'+name)?.classList.toggle('primary',name===mode);
    $('mode-'+name)?.setAttribute('aria-selected',String(name===mode));
  }

  if(live)camera.show();else{
    camera.hide();
    try{simulator ||= loadSimulator();await simulator;}
    catch(error){simulator=null;console.error('Simulator unavailable',error);}
  }
  window.dispatchEvent(new Event('rover-mode'));
}
setMode(new URLSearchParams(location.search).get('mode')==='simulator'?'simulator':'live');
