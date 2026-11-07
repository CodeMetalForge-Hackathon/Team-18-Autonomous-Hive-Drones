import * as T from './vendor/three.module.mjs';
import {STLLoader} from './vendor/STLLoader.mjs';
// Approximate assembly inferred from the supplied photos. Units below are mm.
export async function buildPhysicalRover(){
 const group=new T.Group();group.name='photo-robot';group.scale.setScalar(.1);
 const material=(color,extra={})=>new T.MeshStandardMaterial({color,roughness:.65,...extra});
 const black=material('#141816'),grey=material('#424746'),orange=material('#ff7124',{transparent:true,opacity:.94}),yellow=material('#f8d628'),silver=material('#b8c1c3',{metalness:.8,roughness:.25}),blue=material('#184983');
 const mesh=(geometry,mat,parent=group,x=0,y=0,z=0)=>{const m=new T.Mesh(geometry,mat);m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m};
 const box=(parent,x,y,z,w,h,d,mat)=>mesh(new T.BoxGeometry(w,h,d),mat,parent,x,y,z);
 const loader=new STLLoader();
 async function cad(name,mat,transform,filter){let g=await loader.loadAsync('./assets/'+name);if(filter){const a=g.attributes.position.array,out=[];for(let i=0;i<a.length;i+=9)if(filter((a[i]+a[i+3]+a[i+6])/3))out.push(...a.slice(i,i+9));g.dispose();g=new T.BufferGeometry();g.setAttribute('position',new T.Float32BufferAttribute(out,3));g.computeVertexNormals();}g.computeBoundingBox();const c=g.boundingBox.getCenter(new T.Vector3());g.translate(-c.x,-c.y,-c.z);const m=mesh(g,mat);transform(m);}
 await Promise.all([
  cad('RoverC-Pro_Shell.stl',grey,m=>{m.position.set(0,29,0);m.rotation.y=Math.PI/2}),
  cad('StickC-Plus.stl',orange,m=>{m.geometry.rotateX(Math.PI/2);m.geometry.rotateY(Math.PI/2);m.position.set(-9,48,0)},x=>x> -30)
 ]);
 box(group,0,19,0,54,12,47,black);box(group,-9,47,0,47,11,24,orange);
 box(group,-5,54.1,0,30,.8,18,black);box(group,-5,54.6,0,25,.3,14,material('#53716c',{emissive:'#41675e',emissiveIntensity:.3}));
 box(group,12,54.8,0,4,1.1,7,grey);box(group,-34,48,0,3,5,10,silver);box(group,-35.6,48,0,.4,2.8,6,black);
 const wheels=[];
 for(const x of [-21,21])for(const z of [-35,35]){const w=new T.Group();w.name='yellow-mecanum-wheel';w.position.set(x,17,z);group.add(w);const hub=mesh(new T.CylinderGeometry(13.5,13.5,10,18),black,w);hub.rotation.x=Math.PI/2;for(let i=0;i<8;i++){const a=i*Math.PI/4,r=mesh(new T.CapsuleGeometry(3.5,6,3,6),yellow,w,13*Math.cos(a),13*Math.sin(a),0);r.quaternion.setFromAxisAngle(new T.Vector3(0,0,1),a).multiply(new T.Quaternion().setFromAxisAngle(new T.Vector3(1,0,0),(x*z>0?1:-1)*.75));}const cap=mesh(new T.CylinderGeometry(14.5,14.5,1.8,3),black,w,0,0,z>0?6:-6);cap.rotation.x=Math.PI/2;for(let i=0;i<3;i++){const a=i*2*Math.PI/3,spoke=box(w,6*Math.cos(a),6*Math.sin(a),z>0?7.1:-7.1,16,1.1,.6,grey);spoke.rotation.z=a;}wheels.push(w);}
 // SG90-like servo body and a yawing carrier for one paired ultrasonic module.
 box(group,32,29,0,20,22,13,blue);box(group,32,41,0,27,2,17,black);mesh(new T.CylinderGeometry(3,3,5,12),silver,group,43,39,0);
 const head=new T.Group();head.name='sonar-head';head.position.set(43,37,0);group.add(head);
 box(head,9,-7,0,22,4,12,black);box(head,10,-13,0,12,26,50,black);box(head,16.5,-13,0,1,20,45,blue);
 for(const z of [-12,12]){const can=mesh(new T.CylinderGeometry(8,8,10,24),silver,head,20,-13,z);can.rotation.z=-Math.PI/2;const face=mesh(new T.CylinderGeometry(6.8,6.8,.5,24),black,head,25.2,-13,z);face.rotation.z=-Math.PI/2;for(let i=-2;i<=2;i++)box(head,25.6,-13+i*2,z,.15,.25,11,grey);}
 // Upward-facing light module, connector, and indicator LED beside the flat controller.
 box(group,-9,43.5,-22,13,3,12,black);mesh(new T.CylinderGeometry(2.7,2.7,1,16),material('#b79b63'),group,-9,45.5,-22);box(group,-17,46,-22,4,5,7,material('#e7dfcc'));
 mesh(new T.SphereGeometry(1.4,10,8),material('#ff2d2d',{emissive:'#ff2525',emissiveIntensity:1.2}),group,-9,46,23);
 function wire(points,color,r=.7){mesh(new T.TubeGeometry(new T.CatmullRomCurve3(points.map(p=>new T.Vector3(...p))),30,r,6,false),material(color));}
 for(const[i,color]of ['#57291e','#dc3e28','#efc338'].entries()){const z=i*1.5;wire([[-20,51,z-12],[-14,77,z-7],[7,84,z+8],[29,67,z+10],[33,40,z+7]],color);wire([[-17,47,z-22],[-13,59,z-15],[0,56,z-9]],color,.5);}
 // Approximate USB sniffer board and lead: mounting is a simulator assumption.
 const ble=new T.Group();ble.name='ble-sniffer-assumed-mount';group.add(ble);
 box(ble,32,55,23,32,2,12,blue);box(ble,13,55,23,7,3,10,silver);box(ble,30,57,23,7,2,7,black);
 for(let i=0;i<4;i++)box(ble,43-i*2,56.3,23,1,.3,8-i,material('#d7b565'));
 wire([[12,55,23],[0,62,28],[-28,55,12]],'#151a18',1);
 return {group,head,wheels,ble,parts:2};
}
