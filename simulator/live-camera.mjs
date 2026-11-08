export function createLiveCamera({button,panel,image,status,onShow=()=>{}}) {
  let active=false,generation=0,timer=null,controller=null,url=null;
  function cancel(){generation++;clearTimeout(timer);controller?.abort();controller=null;}
  async function poll(){
    if(!active||document.hidden)return;
    const current=generation;
    const requestController=new AbortController();controller=requestController;
    const timeout=setTimeout(()=>requestController.abort(),4000);
    try{
      const response=await fetch('/api/camera.jpg',{cache:'no-store',signal:controller.signal});
      if(!response.ok)throw Error('unavailable');
      const captured=Number(response.headers.get('X-Captured-Ms'));
      const blob=await response.blob();
      if(!active||current!==generation)return;
      if(!Number.isFinite(captured)||Date.now()-captured>1500)throw Error('stale');
      const previous=url;url=URL.createObjectURL(blob);image.src=url;image.hidden=false;panel.classList.add('has-frame');
      if(previous)URL.revokeObjectURL(previous);
      status.textContent='Connected';
      panel.classList.remove('unavailable');
    }catch(error){
      if(active&&current===generation){status.textContent='Reconnecting';panel.classList.add('unavailable');}
    }finally{
      clearTimeout(timeout);
      if(active&&current===generation)timer=setTimeout(poll,panel.classList.contains('unavailable')?1000:150);
    }
  }
  function hide(){active=false;cancel();panel.hidden=true;button?.classList.remove('primary');document.body.classList.remove('camera-view');}
  function show(){hide();active=true;panel.hidden=false;button?.classList.add('primary');document.body.classList.add('camera-view');status.textContent='Connecting…';onShow();poll();}
  if(button)button.onclick=show;
  document.addEventListener('visibilitychange',()=>{cancel();if(active&&!document.hidden)poll();});
  fetch('/api/camera/status',{cache:'no-store'}).then(r=>r.ok?r.json():null).then(state=>{
    if(button){button.disabled=!state?.configured;button.title=state?.configured?'Show the physical camera':'Start the server with a camera configuration';}
    if(!state?.configured)status.textContent='Camera not configured';
  }).catch(()=>{if(button)button.title='Camera backend unavailable';});
  return {show,hide};
}
