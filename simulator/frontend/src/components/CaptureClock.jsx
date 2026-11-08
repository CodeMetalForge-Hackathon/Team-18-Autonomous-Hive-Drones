import React,{useEffect,useState} from 'react';
export default function CaptureClock({timestamp}){
 const [now,setNow]=useState(Date.now());
 useEffect(()=>{if(timestamp!=null)return;const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[timestamp]);
 const date=new Date(timestamp??now);
 if(Number.isNaN(date.getTime()))return null;
 return <time className="capture-clock" dateTime={date.toISOString()} title={date.toLocaleString()} aria-label={timestamp==null?'Current time':'Recording time'}>{date.toLocaleTimeString(undefined,{hour12:false})}</time>;
}
