import {rfCanvas} from './rf-overlay.mjs';
import {buildPhysicalRover} from './robot-physical.mjs';
import * as T from './vendor/three.module.mjs';
import {STLLoader} from './vendor/STLLoader.mjs';
import {OrbitControls} from './vendor/OrbitControls.mjs';
export async function createView(host){
const scene=new T.Scene();scene.background=new T.Color('#172019');scene.fog=new T.Fog('#172019',1000,2300);
const renderer=new T.WebGLRenderer({antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio,2));renderer.shadowMap.enabled=true;renderer.shadowMap.type=T.PCFSoftShadowMap;renderer.outputColorSpace=T.SRGBColorSpace;host.append(renderer.domElement);
const camera=new T.PerspectiveCamera(42,1,.5,3000);const controls=new OrbitControls(camera,renderer.domElement);controls.enableDamping=true;controls.maxPolarAngle=Math.PI/2-.03;controls.minDistance=18;controls.maxDistance=1500;camera.position.set(215,195,235);controls.target.set(125,0,50);
const fillLight=new T.HemisphereLight(0xe7f3e1,0x28382a,2.5);scene.add(fillLight);const sun=new T.DirectionalLight(0xfff5df,3.2);sun.position.set(200,650,200);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);Object.assign(sun.shadow.camera,{left:-700,right:700,top:700,bottom:-700,far:1600});sun.shadow.bias=-.001;scene.add(sun);scene.add(sun.target);sun.target.position.set(125,0,50);
function mat(color,extra={}){return new T.MeshStandardMaterial({color,roughness:.65,...extra})}const orange=mat('#ff7929'),black=mat('#19201e'),metal=mat('#aeb5b1',{metalness:.65,roughness:.3}),white=mat('#e3e5dd');
function mesh(g,m,parent,x=0,y=0,z=0){const o=new T.Mesh(g,m);o.position.set(x,y,z);o.castShadow=true;o.receiveShadow=true;parent.add(o);return o}
function box(parent,x,y,z,w,h,d,m){return mesh(new T.BoxGeometry(w,h,d),m,parent,x,y,z)}
const floor=mesh(new T.PlaneGeometry(1500,1500),mat('#17231d'),scene,125,-77,50);floor.rotation.x=-Math.PI/2;
box(scene,125,-2.1,50,250,4,100,mat('#b69a72'));
for(const x of [7,243])for(const z of [7,93])box(scene,x,-39,z,5,74,5,mat('#323a36',{metalness:.6}));
const grid=new T.GridHelper(250,50,0x8f7c5e,0xa38c69);grid.position.set(125,.02,50);grid.scale.z=100/250;scene.add(grid);
function label(text,x,y,z){const c=document.createElement('canvas');c.width=512;c.height=64;const g=c.getContext('2d');g.font='32px monospace';g.fillStyle='#f5e7c9';g.textAlign='center';g.fillText(text,256,43);const sprite=new T.Sprite(new T.SpriteMaterial({map:new T.CanvasTexture(c),depthTest:false,transparent:true}));sprite.position.set(x,y,z);sprite.scale.set(55,7,1);scene.add(sprite)}
label('250 cm',125,-5,105);label('100 cm',258,-5,50);

let rfKey='',rfTexture=null;const rfPlane=new T.Mesh(new T.PlaneGeometry(250,100),new T.MeshBasicMaterial({transparent:true,opacity:.85,depthWrite:false}));rfPlane.rotation.x=-Math.PI/2;rfPlane.position.set(125,.08,50);scene.add(rfPlane);
const environment=new T.Group();scene.add(environment);const rover=new T.Group();scene.add(rover);const model=new T.Group();model.scale.setScalar(.1);rover.add(model);
// Official CAD uses millimetres; convert to centimetres at 1:1 visual scale.
box(model,0,13,0,56,10,50,black);const wheels=[];
for(const x of [-21,21])for(const z of [-35,35]){const wheel=new T.Group();wheel.position.set(x,17,z);model.add(wheel);const hub=mesh(new T.CylinderGeometry(16,16,11,16),black,wheel);hub.rotation.x=Math.PI/2;const cap=mesh(new T.CylinderGeometry(7,7,12,16),metal,wheel);cap.rotation.x=Math.PI/2;for(let i=0;i<8;i++){const a=i*Math.PI/4;const roll=mesh(new T.CapsuleGeometry(3.5,8,3,6),mat('#777e79'),wheel,13*Math.cos(a),13*Math.sin(a),0);roll.rotation.z=a+Math.PI/2;roll.rotation.y=(x*z>0?1:-1)*.55;}wheels.push(wheel)}
const loader=new STLLoader();let parts=0;
async function stl(name,material,transform,filter){let geo=await loader.loadAsync('./assets/'+name);if(filter){const arr=geo.attributes.position.array,out=[];for(let i=0;i<arr.length;i+=9)if(filter((arr[i]+arr[i+3]+arr[i+6])/3))out.push(...arr.slice(i,i+9));geo.dispose();geo=new T.BufferGeometry();geo.setAttribute('position',new T.Float32BufferAttribute(out,3));geo.computeVertexNormals();}geo.computeBoundingBox();const center=geo.boundingBox.getCenter(new T.Vector3());geo.translate(-center.x,-center.y,-center.z);const o=mesh(geo,material,model);transform(o);parts++;return o;}
await Promise.all([
stl('RoverC-Pro_Shell.stl',orange,o=>{o.position.set(0,29,0);o.rotation.y=Math.PI/2}),
stl('StickC-Plus.stl',orange,o=>{o.position.set(-10,61,0);o.rotation.y=Math.PI/2},x=>x>-30),
stl('RoverC-Pro_Servo_Clamp_Support_Bracket.stl',black,o=>{o.rotation.set(-Math.PI/2,0,-Math.PI/2);o.position.set(39,22,0)}),
stl('RoverC-Pro_Servo_Claw_B_Version_Left_Arm.stl',orange,o=>{o.rotation.set(-Math.PI/2,0,-Math.PI/2);o.position.set(64,15,-15)}),
stl('RoverC-Pro_Servo_Claw_B_Version_Right_Arm.stl',orange,o=>{o.rotation.set(-Math.PI/2,0,-Math.PI/2);o.position.set(64,15,15)})
]);
// Display/buttons and missing hardware are simple meshes, not additional manufacturer CAD.
box(model,-2.8,64,0,1,25,15,black);box(model,-2.1,66,0,.5,18,11,mat('#183347',{emissive:'#407f70',emissiveIntensity:.5}));box(model,-2,48,0,1.5,4,6,white);box(model,38,18,0,19,22,24,black);
const physical=await buildPhysicalRover();rover.add(physical.group);
const sensorLines=new T.Group();scene.add(sensorLines);let lastMap='',following=false,prev=null,previousDistance=0;const followOffset=new T.Vector3(-35,40,45);
new ResizeObserver(()=>{const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix()}).observe(host);
function disposeGroup(group){while(group.children.length){const o=group.children[0];group.remove(o);o.traverse(v=>{v.geometry?.dispose();if(v.material&&!Array.isArray(v.material))v.material.dispose()})}}
return {parts:physical.parts,follow(close=false){following=true;prev=null;followOffset.set(close?17:-35,close?13:40,close?18:45)},overview(){following=false;camera.position.set(215,195,235);controls.target.set(125,0,50)},update(sim,map,truth){if(host.hidden)return;const legacy=sim.c.sensorModel!=='pan-sonar-light-v2';
rfPlane.visible=truth&&!legacy&&!!sim.c.ble&&!!document.getElementById('rf-show')?.checked&&map.targets.length>0;
if(rfPlane.visible){const index=Math.min(map.targets.length-1,Number(document.getElementById('rf-beacon')?.value)||0),key=JSON.stringify([map,index,sim.c.bleContact,sim.c.bleMultipath]);if(key!==rfKey){rfKey=key;rfTexture?.dispose();rfTexture=new T.CanvasTexture(rfCanvas(map,sim.c,index));rfTexture.colorSpace=T.SRGBColorSpace;rfPlane.material.map=rfTexture;rfPlane.material.needsUpdate=true;}}
host.dataset.rfVisible=String(rfPlane.visible);fillLight.intensity=legacy?2.5:.15+1.8*sim.c.lightLevel;sun.intensity=legacy?3.2:3.2*Math.max(.03,sim.c.lightLevel);model.visible=legacy;physical.group.visible=!legacy;physical.ble.visible=!legacy&&!!sim.c.ble;physical.head.rotation.y=-(sim.readings.pan||0)*Math.PI/180;host.dataset.hardware=legacy?'legacy-three-ray-v1':'pan-sonar-light-v2';host.dataset.headAngle=String(sim.readings.pan||0);const signature=JSON.stringify([map,truth,[...sim.found],legacy,sim.c.virtualRescue]);if(signature!==lastMap){lastMap=signature;disposeGroup(environment);if(truth){const dock=map.start;mesh(new T.CylinderGeometry(10,10,.3,48),mat('#245759',{emissive:'#285d5b',emissiveIntensity:.4}),environment,dock.x,.2,dock.y);const ring=mesh(new T.TorusGeometry(9.5,.3,6,48),mat('#7ce5df'),environment,dock.x,.45,dock.y);ring.rotation.x=Math.PI/2;box(environment,dock.x-7,1,dock.y,2,2,12,mat('#b8d7cf'));for(const b of map.obstacles.filter(b=>!b.owner))box(environment,b.x+b.w/2,7,b.y+b.h/2,b.w,14,b.h,mat('#71816e'));
for(const obj of map.objects||[]){const {x,y,w,h,type}=obj;
if(type==='laptop'){
const silver=mat('#9ca4a4',{metalness:.65,roughness:.35});box(environment,x+w/2,.65,y+h/2,w,1.3,h,silver);box(environment,x+w/2,1.34,y+h*.43,w-3,.12,h*.46,mat('#293332'));box(environment,x+w/2,1.4,y+h*.8,9,.1,5,silver);
const lid=new T.Group();lid.position.set(x+w/2,1.3,y+1);lid.rotation.x=-.17;environment.add(lid);box(lid,0,10,0,w,20,.7,silver);box(lid,0,10,.4,w-2,18,.15,mat('#254355',{emissive:'#31647c',emissiveIntensity:.25}));
// Keyboard rows and screen content keep the laptop recognizable from above.
for(let row=0;row<4;row++)for(let col=0;col<10;col++)box(environment,x+3+col*2.8,1.46,y+4+row*2,2,.1,1.1,black);
for(let row=0;row<4;row++)box(lid,-3,14-row*2,.51,18-row*2,.3,.08,mat('#78b5c5'));
}else if(type==='bottle'){
const cx=x+w/2,cz=y+h/2;mesh(new T.CylinderGeometry(2.8,3.4,16,24),mat('#9acbde',{transparent:true,opacity:.65,roughness:.2}),environment,cx,9,cz);mesh(new T.CylinderGeometry(3.25,3.25,6,24),mat('#3f91a9',{transparent:true,opacity:.8}),environment,cx,8,cz);mesh(new T.CylinderGeometry(1.4,2.8,3,24),mat('#aed9df',{transparent:true,opacity:.7}),environment,cx,18.5,cz);mesh(new T.CylinderGeometry(1.5,1.5,2,20),mat('#2d77b8'),environment,cx,21,cz);
}else if(type==='plant'){
const cx=x+w/2,cz=y+h/2,wood=Math.round(x)%2===1;
if(wood)box(environment,cx,4,cz,w,8,h,mat('#93623d'));else mesh(new T.CylinderGeometry(w/2,w*.38,8,24),mat('#252c29'),environment,cx,4,cz);
mesh(new T.CylinderGeometry(w*.43,w*.43,.5,24),mat('#34291d'),environment,cx,8.2,cz);
for(let layer=0;layer<3;layer++)for(let i=0;i<9;i++){const a=i*Math.PI*2/9+layer*.4,r=3-layer*.7;const leaf=mesh(new T.SphereGeometry(1,10,7),mat(layer===2?'#9ab384':'#477f50'),environment,cx+Math.cos(a)*r,9+layer*1.5,cz+Math.sin(a)*r);leaf.scale.set(2.2,.65,.9);leaf.rotation.y=-a;leaf.rotation.z=.3+layer*.15;}
}else if(type==='shade'){box(environment,x+w/2,12.5,y+h/2,w,1,h,mat('#526c72'));
}else if(type==='hidebox'){
const cardboard=mat('#b58c59'),edge=mat('#d0ab76');box(environment,x+w/2,7.5,y+.5,w,15,1,cardboard);box(environment,x+w/2,7.5,y+h-.5,w,15,1,cardboard);box(environment,obj.opening==='right'?x+.5:x+w-.5,7.5,y+h/2,1,15,h,cardboard);box(environment,x+w/2,15.5,y+h/2,w,1,h,cardboard);box(environment,x+w/2,16.1,y+h/2,w,0.1,3,edge);
// Open left face is a real navigable entrance; the roof is overhead only.
}
}
if(legacy||sim.c.virtualRescue||sim.c.ble)map.targets.forEach((p,i)=>{const color=sim.found.has(i)?'#4d663e':'#c7f86c';const target=mesh(new T.CylinderGeometry(2,2,.6,24),mat(color),environment,p.x,.4,p.y);box(environment,p.x,.75,p.y,2.5,.1,.6,black);box(environment,p.x,.75,p.y,.6,.1,2.5,black)});if(map.observer){const p=map.observer;box(environment,p.x,10,p.y,.7,20,.7,metal);box(environment,p.x,18,p.y,7,5,.7,mat('#eeb269'));}}}
const r=sim.robot;rover.position.set(r.x,0,r.y);rover.rotation.y=-r.a;let traveled=sim.distance-previousDistance;if(traveled<0)traveled=0;previousDistance=sim.distance;(legacy?wheels:physical.wheels).forEach(w=>w.rotation.z-=traveled/(legacy?4.8:1.6));
if(following){const position=new T.Vector3(r.x,4,r.y);if(!prev){camera.position.copy(position).add(followOffset);controls.target.copy(position)}else{camera.position.add(position.clone().sub(prev));controls.target.copy(position)}prev=position;}
disposeGroup(sensorLines);
function line(x,y,a,d,color,height=2.4){const geo=new T.BufferGeometry().setFromPoints([new T.Vector3(x,height,y),new T.Vector3(x+Math.cos(a)*d,height,y+Math.sin(a)*d)]);sensorLines.add(new T.Line(geo,new T.LineBasicMaterial({color,transparent:true,opacity:.6})));}
if(legacy){for(const[offset,key]of [[0,'front'],[-Math.PI/2,'left'],[Math.PI/2,'right']])line(r.x,r.y,r.a+offset,sim.readings[key],'#79dfc0',4);}
else{const head=r.a+(sim.readings.pan||0)*Math.PI/180,x=r.x+4.3*Math.cos(r.a)+2.5*Math.cos(head),y=r.y+4.3*Math.sin(r.a)+2.5*Math.sin(head),d=sim.readings.range_valid?sim.readings.range:sim.c.range;const color=sim.readings.range_valid?'#79dfc0':'#d9aa6b';line(x,y,head,d,color);line(x,y,head-sim.c.beam*Math.PI/360,d,color);line(x,y,head+sim.c.beam*Math.PI/360,d,color);}
controls.update();renderer.render(scene,camera);},renderer,rover};
}
