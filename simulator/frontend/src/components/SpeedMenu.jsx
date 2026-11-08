import React,{useEffect,useRef,useState} from 'react';
import {Gauge,ChevronRight,ChevronLeft,Check} from 'lucide-react';
export default function SpeedMenu({value,onChange}){
 const [page,setPage]=useState(null),[draft,setDraft]=useState(String(value));
 const root=useRef(null),trigger=useRef(null);
 useEffect(()=>setDraft(String(value)),[value]);
 useEffect(()=>{if(!page)return;const close=e=>{if(!root.current?.contains(e.target))setPage(null);};document.addEventListener('pointerdown',close);return()=>document.removeEventListener('pointerdown',close);},[page]);
 function choose(speed){onChange(speed);setPage(null);trigger.current?.focus();}
 function apply(event){event.preventDefault();const speed=Number(draft);if(Number.isFinite(speed)&&speed>=.25&&speed<=1000)choose(speed);}
 return <div className="speed-menu" ref={root} onKeyDown={e=>{if(e.key==='Escape'){setPage(null);trigger.current?.focus();e.stopPropagation();}}}>
  <button ref={trigger} className="settings-trigger" aria-label="Playback speed" title={`Playback speed: ${value}×`} aria-expanded={Boolean(page)} onClick={()=>setPage(page?null:'speed')}><Gauge size={20}/></button>
  {page&&<div className="settings-popover">
   {page==='speed'&&<><div className="settings-heading">Playback speed</div><div className="speed-options">{[.25,.5,1,2,4,8,16,32,64,128,256,512,1000].map(speed=><button key={speed} className="speed-option" onClick={()=>choose(speed)}><span>{value===speed&&<Check size={15}/>}</span>{speed===1?'Normal':`${speed.toLocaleString()}×`}</button>)}</div><button className="settings-custom" onClick={()=>setPage('custom')}>Custom<ChevronRight size={15}/></button></>}
   {page==='custom'&&<><button className="settings-heading" onClick={()=>setPage('speed')}><ChevronLeft size={17}/>Custom speed</button><form className="custom-speed-form" onSubmit={apply}><div><input autoFocus aria-label="Custom playback speed" type="number" min="0.25" max="1000" step="any" value={draft} onChange={e=>setDraft(e.target.value)}/><span>×</span><button aria-label="Apply speed" type="submit"><Check size={18}/></button></div><input aria-label="Speed adjustment" type="range" min="-2" max={Math.log2(1000)} step="0.01" value={Math.log2(Math.min(1000,Math.max(.25,Number(draft)||1)))} onChange={e=>setDraft(String(Math.round(2**Number(e.target.value)*100)/100))}/></form></>}
  </div>}
 </div>;
}
