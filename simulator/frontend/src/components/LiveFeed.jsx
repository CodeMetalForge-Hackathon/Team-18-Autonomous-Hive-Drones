import React, {useEffect, useState} from 'react';

export default function LiveFeed(){
  const [image,setImage]=useState(''),[error,setError]=useState(false);
  useEffect(()=>{
    let stopped=false,timer,url,controller;
    async function next(){
      if(stopped)return;
      controller=new AbortController();
      const timeout=setTimeout(()=>controller.abort(),4000);
      try{
        const response=await fetch('/api/camera.jpg',{cache:'no-store',signal:controller.signal});
        if(!response.ok)throw Error('Unavailable');
        const captured=Number(response.headers.get('X-Captured-Ms'));
        if(!captured||Date.now()-captured>2000)throw Error('Stale');
        const blob=await response.blob();
        if(stopped)return;
        const previous=url;url=URL.createObjectURL(blob);setImage(url);setError(false);
        if(previous)URL.revokeObjectURL(previous);
      }catch{if(!stopped)setError(true);}
      finally{clearTimeout(timeout);if(!stopped)timer=setTimeout(next,200);}
    }
    next();
    return()=>{stopped=true;clearTimeout(timer);controller?.abort();if(url)URL.revokeObjectURL(url);};
  },[]);
  return <main className="player live-player">{image&&<img src={image} alt="Live rover camera"/>}{(!image||error)&&<div className="live-message" role="status">{error?'Reconnecting…':'Connecting…'}</div>}</main>;
}
