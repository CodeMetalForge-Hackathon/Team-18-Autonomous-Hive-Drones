import {useEffect,useRef,useState} from 'react';

const BLOCK_SECONDS=12;
const MIME='video/mp4; codecs="avc1.42C01E"';

export default function useRenderedReplay({enabled,session,speed,duration,positionRef,video,onError}){
 const factor=enabled?2**Math.floor(Math.log2(speed)):1;
 const [src,setSrc]=useState(),[preparing,setPreparing]=useState(false);
 const seekRef=useRef(null),desired=useRef(0);
 useEffect(()=>{
  if(!enabled||!session||!duration){setSrc(undefined);setPreparing(false);seekRef.current=null;return;}
  if(!window.MediaSource?.isTypeSupported(MIME)){onError('This browser cannot play the accelerated stream.');return;}
  const mediaSource=new MediaSource(),url=URL.createObjectURL(mediaSource),controller=new AbortController();
  let stopped=false,sourceBuffer,chain=Promise.resolve(),prunedBefore=0;
  const loaded=new Set(),requests=new Map(),count=Math.ceil(duration/(factor*BLOCK_SECONDS));
  desired.current=positionRef.current;setPreparing(true);setSrc(url);
  const pause=ms=>new Promise((resolve,reject)=>{const aborted=()=>{clearTimeout(timer);reject(new DOMException('Aborted','AbortError'));};const timer=setTimeout(()=>{controller.signal.removeEventListener('abort',aborted);resolve();},ms);controller.signal.addEventListener('abort',aborted,{once:true});});
  const updated=()=>new Promise((resolve,reject)=>{const cleanup=()=>{sourceBuffer.removeEventListener('updateend',done);sourceBuffer.removeEventListener('error',failed);};const done=()=>{cleanup();resolve();};const failed=error=>{cleanup();reject(error);};sourceBuffer.addEventListener('updateend',done);sourceBuffer.addEventListener('error',failed);});
  async function fetchBlock(block){
   while(!stopped){
    const response=await fetch('/api/camera/render?'+new URLSearchParams({session,factor,block}),{signal:controller.signal});
    if(!response.ok)throw Error('Could not prepare accelerated playback.');
    const result=await response.json();
    if(result.status==='error')throw Error('Accelerated playback could not be rendered.');
    if(result.status==='ready'){
     const file=await fetch(result.url,{signal:controller.signal});
     if(!file.ok)throw Error('Could not load accelerated playback.');
     return file.arrayBuffer();
    }
    await pause(250);
   }
  }
  async function ensure(block){
   if(block<0||block>=count||loaded.has(block)||stopped)return;
   if(!requests.has(block))requests.set(block,fetchBlock(block));
   const bytes=await requests.get(block);
   const append=chain.then(async()=>{
    if(stopped||loaded.has(block))return;
    sourceBuffer.timestampOffset=block*BLOCK_SECONDS;
    sourceBuffer.appendBuffer(bytes);await updated();loaded.add(block);
   });
   chain=append.catch(()=>{});await append;
  }
  function warm(block){for(let next=block+1;next<=block+2&&next<count;next++)ensure(next).catch(fail);}
  function fail(error){if(!stopped&&error?.name!=='AbortError'){setPreparing(false);onError(error.message||'Accelerated playback is unavailable.');}}
  async function seek(position){
   desired.current=position;setPreparing(true);
   const block=Math.min(count-1,Math.floor(position/(factor*BLOCK_SECONDS)));
   try{await ensure(block);if(stopped||desired.current!==position)return;video.current.currentTime=Math.min(duration/factor-.001,position/factor);setPreparing(false);warm(block);}catch(error){fail(error);}
  }
  function progress(){
   const block=Math.min(count-1,Math.floor(video.current.currentTime/BLOCK_SECONDS));warm(block);
   if(block>3&&sourceBuffer&&!sourceBuffer.updating&&(block-3)*BLOCK_SECONDS>prunedBefore){
    const cutoff=(block-3)*BLOCK_SECONDS;
    prunedBefore=cutoff;
    chain=chain.then(async()=>{if(stopped)return;sourceBuffer.remove(0,cutoff);await updated();for(const old of [...loaded])if(old<block-3){loaded.delete(old);requests.delete(old);}}).catch(fail);
   }
  }
  mediaSource.addEventListener('sourceopen',()=>{
   if(stopped)return;
   sourceBuffer=mediaSource.addSourceBuffer(MIME);mediaSource.duration=duration/factor;
   seekRef.current=seek;video.current.addEventListener('timeupdate',progress);seek(desired.current);
  },{once:true});
  return()=>{stopped=true;controller.abort();seekRef.current=null;video.current?.removeEventListener('timeupdate',progress);URL.revokeObjectURL(url);};
 },[enabled,session,factor,duration]);
 return {enabled,factor,src,preparing,seek(position){desired.current=position;seekRef.current?.(position);}};
}
