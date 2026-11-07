#!/usr/bin/env python3
"""Analysis helpers over ALREADY DELIVERED logs. No simulator import or world access."""
import ast, json, math, operator, pathlib, sys

def calculate(expression):
    if not isinstance(expression,str) or len(expression)>512:raise ValueError('Expression too long')
    tree=ast.parse(expression,mode='eval')
    if len(list(ast.walk(tree)))>100:raise ValueError('Expression too complex')
    funcs={'sin':lambda x:math.sin(math.radians(x)),'cos':lambda x:math.cos(math.radians(x)),'atan2':lambda y,x:math.degrees(math.atan2(y,x)),'sqrt':math.sqrt,'abs':abs,'min':min,'max':max}
    ops={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Mod:operator.mod}
    def visit(n):
        if isinstance(n,ast.Expression):v=visit(n.body)
        elif isinstance(n,ast.Constant) and type(n.value) in (int,float):v=n.value
        elif isinstance(n,ast.Name) and n.id=='pi':v=math.pi
        elif isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):v=visit(n.operand)*(1 if isinstance(n.op,ast.UAdd) else -1)
        elif isinstance(n,ast.BinOp) and type(n.op) in ops:v=ops[type(n.op)](visit(n.left),visit(n.right))
        elif isinstance(n,ast.BinOp) and isinstance(n.op,ast.Pow):
            left,right=visit(n.left),visit(n.right)
            if abs(right)>8:raise ValueError('Exponent is limited to ±8')
            v=left**right
        elif isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in funcs and not n.keywords and 1<=len(n.args)<=3:v=funcs[n.func.id](*[visit(a) for a in n.args])
        else:raise ValueError('Numeric arithmetic only')
        if not isinstance(v,(int,float)) or not math.isfinite(v) or abs(v)>1e12:raise ValueError('Numeric result outside allowed range')
        return v
    return visit(tree)

def project_ranges(root,files=None,cell_cm=5):
    root=pathlib.Path(root).resolve();cell=float(cell_cm)
    if not 2<=cell<=20:raise ValueError('Cell size must be 2..20 cm')
    hardware=json.loads((root/'hardware.json').read_text());reach=hardware['range_max_cm'];noise=hardware['range_uniform_noise_cm'];occupied={};free={};bearings=[];sample_count=0;used=[];light_samples=[];seen_pings=set()
    files=files if files is not None else [str(p.relative_to(root)) for p in sorted((root/'observations').glob('*.json'))]
    if len(files)>50:raise ValueError('At most 50 delivered logs per call')
    def key(x,y):return(round(x/cell)*cell,round(y/cell)*cell)
    for name in files:
        p=(root/name).resolve()
        if not p.is_relative_to(root/'observations') or p.suffix!='.json' or not p.is_file() or p.stat().st_size>262144:raise ValueError('Only delivered observation JSON files are available')
        log=json.loads(p.read_text());used.append(name)
        for row in log['samples']:
            s=row['readings'];x,y,yaw=s['odom_x'],s['odom_y'],s['yaw'];sample_count+=1
            if 'light' in s and (not light_samples or light_samples[-1]['file']!=name or row['t']-light_samples[-1]['t']>=1 or abs(s['light']-light_samples[-1]['light'])>.08):light_samples.append({'file':name,'t':row['t'],'x':round(x,2),'y':round(y,2),'light':s['light']})
            if 'range' in s:
                ping=(name,s.get('range_seq',row['t']))
                rays=[] if not s.get('range_valid') or ping in seen_pings else [(s['range'],s.get('range_x',x),s.get('range_y',y),s.get('range_yaw',yaw)+s.get('range_angle',s.get('pan',0)))]
                seen_pings.add(ping)
            else:rays=[(s[label],x,y,yaw+offset) for label,offset in [('front',0),('left',-90),('right',90)]]
            for distance,origin_x,origin_y,angle in rays:
                d=max(0,min(reach,distance));a=math.radians(angle);dx,dy=math.cos(a),math.sin(a)
                if d<reach-max(1,noise*2):
                    endpoint=key(origin_x+d*dx,origin_y+d*dy);occupied[endpoint]=occupied.get(endpoint,0)+1
                step=cell
                while step<d-cell:
                    point=key(origin_x+step*dx,origin_y+step*dy);free[point]=free.get(point,0)+1;step+=cell
            if s.get('target') and (not bearings or row['t']-bearings[-1]['t']>1 or bearings[-1]['file']!=name):
                bearings.append({'file':name,'t':row['t'],'x':round(x,1),'y':round(y,1),'heading_deg':round(yaw,1),'bearing_deg':round(s['bearing']*hardware['camera_fov_deg']/2,1)})
    occ=[{'x':x,'y':y,'hits':hits} for (x,y),hits in sorted(occupied.items(),key=lambda p:-p[1])[:2000]]
    fr=[{'x':x,'y':y,'passes':passes} for (x,y),passes in sorted(free.items(),key=lambda p:-p[1]) if (x,y) not in occupied][:2000]
    return {'frame':'dock-relative-cm','method':'range rays transformed only by logged command-integrated odometry; drift, collisions and sensor noise remain','cell_cm':cell,'files':used,'sample_count':sample_count,'occupied':occ,'free':fr,'target_bearings':bearings[:100],'light_samples':light_samples[-200:],'warning':'Candidate point cloud only. Not true geometry. Maximum-range rays do not establish an occupied endpoint; height and occlusion ambiguity remain. Swept sonar uses each ping’s stored pose and angle; cone width makes endpoints uncertain. Invalid/no-echo samples do not establish free space. Low light is evidence only, not proof of concealment.'}
