import {chromium} from '@playwright/test';
import assert from 'node:assert/strict';
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage({viewport:{width:1280,height:800}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://localhost:8765');
 await page.getByRole('button',{name:'Replay',exact:true}).click();
 await page.waitForSelector('.video-surface[data-ready=true]');
 for(const speed of [37,1000]){
  const factor=2**Math.floor(Math.log2(speed));
  await page.getByRole('button',{name:'Playback speed',exact:true}).click();
  await page.getByRole('button',{name:'Custom',exact:true}).click();
  await page.getByRole('spinbutton',{name:'Custom playback speed'}).fill(String(speed));
  await page.getByRole('button',{name:'Apply speed',exact:true}).click();
  await page.waitForFunction(({speed,factor})=>{const v=document.querySelector('video'),t=document.querySelector('.timeline');return v?.readyState>=3&&Math.abs(v.duration-Number(t.max)/factor)<.1&&Math.abs(v.playbackRate-speed/factor)<.01&&!document.body.innerText.includes('Preparing playback');},{speed,factor},{timeout:120000});
  if(speed===1000){
   await page.locator('.timeline').evaluate(el=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'6100');el.dispatchEvent(new Event('input',{bubbles:true}));});
   await page.waitForFunction(()=>!document.querySelector('video').seeking&&document.querySelector('video').readyState>=3&&Math.abs(document.querySelector('video').currentTime-6100/512)<.1);
  }
  await page.getByRole('button',{name:'Play replay',exact:true}).first().click();
  await page.waitForFunction(()=>!document.querySelector('video').paused);
  const before=await page.evaluate(()=>{window.testSeeks=0;document.querySelector('video').addEventListener('seeking',()=>window.testSeeks++);return {src:document.querySelector('video').src,frames:Number(document.querySelector('canvas').dataset.frames),position:Number(document.querySelector('.timeline').value),at:performance.now()};});
  await page.waitForTimeout(3000);
  await page.keyboard.press('k');
  const after=await page.evaluate(()=>({src:document.querySelector('video').src,seeks:window.testSeeks,frames:Number(document.querySelector('canvas').dataset.frames),position:Number(document.querySelector('.timeline').value),at:performance.now()}));
  const fps=(after.frames-before.frames)/((after.at-before.at)/1000);
  assert.equal(after.src,before.src,'one continuous media source');
  assert.equal(after.seeks,0,'no seek loop during playback');
  assert.ok(fps>30,`expected smooth playback, got ${fps.toFixed(1)} fps`);
  if(speed===1000)assert.ok(after.position>6144,'continued across rendered boundary');
  console.log(JSON.stringify({speed,framesPerSecond:+fps.toFixed(1),advancedSeconds:+(after.position-before.position).toFixed(1),seeks:after.seeks}));
 }
 assert.deepEqual(errors,[]);
}finally{await browser.close();}
