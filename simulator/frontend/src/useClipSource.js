import {useEffect,useRef} from 'react';

export function clipUrl(clip){return clip?'/api/camera/recording?'+new URLSearchParams({session:clip.session,file:clip.file}):undefined;}

// Keep a small rolling window in memory so changing files does not wait on disk.
export default function useClipSource(clips,index,speed=1){
 const cache=useRef(new Map()),selected=useRef({key:null,src:undefined});
 const key=clipUrl(clips[index]);
 const lookahead=Math.min(6,Math.max(2,Math.ceil(speed/200)));
 if(selected.current.key!==key)selected.current={key,src:cache.current.get(key)?.url||key};
 useEffect(()=>{
  const wanted=new Set(clips.slice(index,index+lookahead+1).map(clipUrl));
  for(const [url,item] of cache.current){if(!wanted.has(url)){item.controller?.abort();if(item.url)URL.revokeObjectURL(item.url);cache.current.delete(url);}}
  for(const clip of clips.slice(index+1,index+lookahead+1)){
   const url=clipUrl(clip);
   if(cache.current.has(url))continue;
   const item={controller:new AbortController(),url:null};cache.current.set(url,item);
   fetch(url,{signal:item.controller.signal}).then(response=>{if(!response.ok)throw Error('Unavailable');return response.blob();}).then(blob=>{
    if(cache.current.get(url)===item)item.url=URL.createObjectURL(blob);
   }).catch(()=>{if(cache.current.get(url)===item)cache.current.delete(url);});
  }
 },[clips,index,lookahead]);
 useEffect(()=>()=>{for(const item of cache.current.values()){item.controller?.abort();if(item.url)URL.revokeObjectURL(item.url);}cache.current.clear();},[]);
 return selected.current.src;
}
