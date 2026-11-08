import React, {useCallback, useEffect, useMemo, useRef, useState} from 'react';
import LiveFeed from './LiveFeed.jsx';
import SpeedMenu from './SpeedMenu.jsx';
import CaptureClock from './CaptureClock.jsx';
import {formatTime, locateTime} from '../timeline.js';
import useClipSource from '../useClipSource.js';
import useRenderedReplay from '../useRenderedReplay.js';
import {Radio, History, Play, Pause, RotateCcw, RotateCw, Maximize, RefreshCw, Film, Aperture, LoaderCircle} from 'lucide-react';

const sessionName=id=>{const match=/^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(id);return match?`${match[1]}-${match[2]}-${match[3]} · ${match[4]}:${match[5]}`:id;};
function IconButton({icon:Icon,label,...props}){return <button type="button" title={label} aria-label={label} {...props}><Icon size={19} strokeWidth={1.8}/></button>;}

export default function CameraPlayer(){
 const panel=useRef(null);
 const [active,setActive]=useState(false),[all,setAll]=useState([]),[session,setSession]=useState(''),[position,setPosition]=useState(0),[index,setIndex]=useState(0),[speed,setSpeed]=useState(1),[playing,setPlaying]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState('');
 const video=useRef(null),surface=useRef(null),target=useRef(0),seekPending=useRef(false),generation=useRef(0),currentPosition=useRef(0);
 const [controlsVisible,setControlsVisible]=useState(true),[buffering,setBuffering]=useState(false),[hoverTime,setHoverTime]=useState(null);
 const hideControls=useRef(null);
 const [showBuffering,setShowBuffering]=useState(false);
 useEffect(()=>{if(!buffering){setShowBuffering(false);return;}const timer=setTimeout(()=>setShowBuffering(true),700);return()=>clearTimeout(timer);},[buffering]);
 useEffect(()=>{
  if(!active)return;
  const media=video.current,canvas=surface.current,context=canvas.getContext('2d',{alpha:false});
  let stopped=false,callback,lastDrawn=-1;
  function paint(){
   if(stopped)return;
   if(media.readyState>=2&&media.videoWidth&&!media.seeking&&media.currentTime!==lastDrawn){
    if(canvas.width!==media.videoWidth||canvas.height!==media.videoHeight){canvas.width=media.videoWidth;canvas.height=media.videoHeight;}
    context.drawImage(media,0,0,canvas.width,canvas.height);
    lastDrawn=media.currentTime;
    canvas.dataset.ready='true';
    canvas.dataset.frames=String(Number(canvas.dataset.frames||0)+1);
   }
  }
  function draw(){
   if(stopped)return;
   paint();
   callback=media.requestVideoFrameCallback?media.requestVideoFrameCallback(draw):requestAnimationFrame(draw);
  }
  media.addEventListener('seeked',paint);
  draw();
  return()=>{stopped=true;media.removeEventListener('seeked',paint);if(media.cancelVideoFrameCallback)media.cancelVideoFrameCallback(callback);else cancelAnimationFrame(callback);};
 },[active]);
 const clips=useMemo(()=>all.filter(c=>c.session===session).sort((a,b)=>a.file.slice(-19).localeCompare(b.file.slice(-19))),[all,session]);
 const duration=useMemo(()=>clips.reduce((sum,c)=>sum+c.duration,0),[clips]);
 const rendered=useRenderedReplay({enabled:active&&speed>16,session,speed,duration,positionRef:currentPosition,video,onError:setError});
 const sessions=useMemo(()=>[...new Set(all.map(c=>c.session))],[all]);
 const updatePosition=value=>{currentPosition.current=value;setPosition(value);};
 const leave=useCallback(()=>{generation.current++;setActive(false);setPlaying(false);video.current?.pause();},[]);

 const seek=useCallback(value=>{
  const next=Math.max(0,Math.min(duration,value)),point=locateTime(clips,next);
  target.current=point.offset;updatePosition(next);setIndex(point.index);
  if(rendered.enabled){rendered.seek(next);return;}
  seekPending.current=true;
  if(point.index===index&&video.current?.readyState>=1){video.current.currentTime=point.offset;seekPending.current=false;}
 },[clips,duration,index,rendered.enabled]);
 const applyPlayback=useCallback(()=>{
  const el=video.current;if(!el)return;
  el.playbackRate=rendered.enabled?speed/rendered.factor:speed;
  if(playing&&!rendered.preparing)el.play().catch(e=>{if(e.name!=='AbortError'){setError('Playback could not start. Press play to retry.');setPlaying(false);}});else el.pause();
 },[playing,speed,rendered.enabled,rendered.factor,rendered.preparing]);
 useEffect(applyPlayback,[applyPlayback]);
 async function refresh(){const request=++generation.current;setLoading(true);setError('');try{const response=await fetch('/api/camera/recordings',{cache:'no-store'});if(!response.ok)throw Error('The recording archive is unavailable.');const data=await response.json();if(request!==generation.current)return;const valid=data.clips.filter(c=>c.duration>0);setAll(valid);if(!valid.some(c=>c.session===session)){setSession(valid[0]?.session||'');setIndex(0);target.current=0;updatePosition(0);}}catch(e){if(request===generation.current)setError(e.message);}finally{if(request===generation.current)setLoading(false);}}
 function open(){setActive(true);refresh();}
 function chooseSession(value){setPlaying(false);setSession(value);setIndex(0);target.current=0;updatePosition(0);setError('');}
 function toggle(){if(position>=duration)seek(0);setPlaying(value=>!value);}
 function fullscreen(){if(document.fullscreenElement)document.exitFullscreen();else panel.current.requestFullscreen().catch(()=>{});}
 function revealControls(){setControlsVisible(true);clearTimeout(hideControls.current);hideControls.current=setTimeout(()=>setControlsVisible(false),2200);}
 useEffect(()=>()=>clearTimeout(hideControls.current),[]);
 useEffect(()=>{
  if(!active)return;
  function keydown(event){
   if(event.altKey||event.ctrlKey||event.metaKey||event.target.closest('input,select,textarea,[contenteditable="true"]'))return;
   const key=event.key.toLowerCase();
   if([' ','k','j','l','arrowleft','arrowright','f','home','end'].includes(key)||/^\d$/.test(key)){
    event.preventDefault();revealControls();
    if(key===' '||key==='k'){if(clips.length)toggle();}
    else if(key==='j'||key==='arrowleft')seek(position-(key==='j'?10:5));
    else if(key==='l'||key==='arrowright')seek(position+(key==='l'?10:5));
    else if(key==='home')seek(0);
    else if(key==='end')seek(duration);
    else if(key==='f')fullscreen();
    else seek(duration*Number(key)/10);
   }
  }
  document.addEventListener('keydown',keydown);
  return()=>document.removeEventListener('keydown',keydown);
 });
 const clip=clips[index],originalSrc=useClipSource(speed>16?[]:clips,index,speed),src=rendered.enabled?rendered.src:originalSrc;
 const capturedAt=clip?.started_at?Date.parse(clip.started_at)+Math.max(0,position-clips.slice(0,index).reduce((sum,item)=>sum+item.duration,0))*1000:null;
 return <div className="camera-app" ref={panel}>
  <header className="app-header"><div className="brand"><Aperture size={20}/><strong>Rover Lab</strong><span className="brand-separator"/>Camera</div>
   <nav aria-label="Camera view"><button className={!active?'selected':''} onClick={leave}><Radio size={15}/>Live</button><button className={active?'selected':''} onClick={open}><History size={15}/>Replay</button></nav>
   {active?<div className="archive-picker"><CaptureClock timestamp={capturedAt}/><select aria-label="Recording session" value={session} onChange={e=>chooseSession(e.target.value)} disabled={loading||!sessions.length}>{!sessions.length&&<option>No recordings</option>}{sessions.map(s=><option value={s} key={s}>{sessionName(s)}</option>)}</select><IconButton icon={RefreshCw} label="Refresh recordings" onClick={refresh} disabled={loading}/></div>:<span className="live-label"><CaptureClock/><i/>LIVE</span>}
  </header>
  {!active?<LiveFeed/>:<main className={'player'+(playing?' is-playing':'')+(controlsVisible?' controls-visible':'')} aria-label="Replay player" tabIndex={0} onPointerMove={revealControls} onPointerDown={revealControls} onFocus={revealControls}>
   <video className="decode-source" ref={video} src={src} playsInline preload="auto" onClick={toggle} onWaiting={()=>setBuffering(true)} onCanPlay={()=>setBuffering(false)} onPlaying={()=>setBuffering(false)} onLoadedMetadata={()=>{if(!rendered.enabled){video.current.currentTime=target.current;seekPending.current=false;}applyPlayback();}} onTimeUpdate={()=>{
    if(rendered.enabled){if(!rendered.preparing){const at=Math.min(duration,video.current.currentTime*rendered.factor);updatePosition(at);const point=locateTime(clips,at);target.current=point.offset;if(point.index!==index)setIndex(point.index);}}
    else if(!seekPending.current&&video.current.readyState>=2&&!video.current.seeking){const start=clips.slice(0,index).reduce((sum,c)=>sum+c.duration,0);target.current=video.current.currentTime;updatePosition(start+video.current.currentTime);}
   }} onEnded={()=>{if(!rendered.enabled&&index<clips.length-1)seek(clips.slice(0,index+1).reduce((sum,c)=>sum+c.duration,0));else{updatePosition(duration);setPlaying(false);}}} onError={()=>{if(!rendered.preparing){setError('This recording could not be played.');setPlaying(false);}}}/>

   <canvas className="video-surface" ref={surface} onClick={toggle} aria-label="Recorded camera video"/>
   {playing&&showBuffering&&!rendered.preparing&&<div className="buffering" role="status" aria-label="Loading video"><LoaderCircle size={30}/></div>}
   {!playing&&clip&&<button className="center-play" aria-label="Play replay" onClick={toggle}><Play size={30} fill="currentColor"/></button>}
   {!clip&&<div className="empty-state"><Film size={32}/><h2>{loading?'Loading…':'No recordings yet'}</h2></div>}
   <div className="player-chrome">
    <div className="timeline-track" onPointerLeave={()=>setHoverTime(null)} onPointerMove={event=>{const box=event.currentTarget.getBoundingClientRect();setHoverTime({left:Math.min(96,Math.max(4,(event.clientX-box.left)/box.width*100)),time:Math.max(0,Math.min(duration,(event.clientX-box.left)/box.width*duration))});}}>
    {hoverTime&&<span className="timeline-preview" style={{left:`${hoverTime.left}%`}}>{formatTime(hoverTime.time)}</span>}
    <input className="timeline" style={{'--progress':`${duration?100*position/duration:0}%`}} aria-label="Full recording timeline" aria-valuetext={formatTime(position)} type="range" min="0" max={duration||1} step="0.1" value={position} disabled={!clips.length} onChange={e=>seek(Number(e.target.value))}/></div>
    <div className="control-row"><IconButton icon={playing?Pause:Play} label={playing?'Pause replay':'Play replay'} onClick={toggle} disabled={!clips.length}/><IconButton icon={RotateCcw} label="Back 10 seconds" onClick={()=>seek(position-10)} disabled={!clips.length}/><IconButton icon={RotateCw} label="Forward 10 seconds" onClick={()=>seek(position+10)} disabled={!clips.length}/><span className="time-display">{formatTime(position)} <span>/ {formatTime(duration)}</span></span>
    <div className="control-spacer"/><SpeedMenu value={speed} onChange={setSpeed}/><IconButton icon={Maximize} label="Fullscreen" onClick={fullscreen}/></div>
   </div>
   {rendered.preparing&&<div className="live-message" role="status">Preparing playback?</div>}
   {error&&<div className="player-error" role="status">{error}</div>}
  </main>}
 </div>;
}
