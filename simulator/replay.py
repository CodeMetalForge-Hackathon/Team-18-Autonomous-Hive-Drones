"""Read-only observer history. Never exposed to the agent's file tools."""
from runtime import node_script_path
import copy, difflib, functools, json, pathlib, re, subprocess

@functools.lru_cache(maxsize=256)
def _load(path,mtime,size):return json.loads(pathlib.Path(path).read_text(encoding='utf-8'))
def load(path):
    stat=path.stat();return _load(str(path),stat.st_mtime_ns,stat.st_size)
def optional(path,default=None):
    try:return load(path)
    except (OSError,ValueError):return default

def text(path):
    try:return path.read_text(encoding='utf-8')[:100000]
    except OSError:return ''

def run_folder(root,run_id):
    if not isinstance(run_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,96}',run_id):raise ValueError('Invalid experiment ID')
    path=root/run_id
    if not path.is_dir() or path.is_symlink():raise ValueError('Experiment not found')
    return path

def report(folder,number):
    job=load(folder/f'deployment-{number:03d}.json');end=load(folder/f'return-{number:03d}.json')
    before=folder/f'turn-{number:03d}';after=folder/f'turn-{number+1:03d}'
    mission=optional(before/'mission.json',{'summary':''});next_mission=optional(after/'mission.json')
    prior=optional(before/'map.json',{});revised=optional(after/'map.json') if end.get('upload') else None
    if not isinstance(prior,dict):prior={}
    if not isinstance(revised,dict):revised=None
    samples=(end.get('upload') or {}).get('samples',[])
    old_rom=text(folder/f'turn-{number-1:03d}'/'controller.rom') if number>1 else ''
    if number>1 and not old_rom:old_rom=optional(folder/f'deployment-{number-1:03d}.json',{}).get('rom','')
    new_rom=job['rom'];diff=list(difflib.unified_diff(old_rom.splitlines(),new_rom.splitlines(),fromfile=f'sortie-{number-1:03d}.rom' if number>1 else 'empty.rom',tofile=f'sortie-{number:03d}.rom',lineterm=''))
    added=sum(s.startswith('+') and not s.startswith('+++') for s in diff);removed=sum(s.startswith('-') and not s.startswith('---') for s in diff)
    counts=lambda m:{key:len(m.get(key,[])) if isinstance(m.get(key),list) else 0 for key in ('occupied','free','landmarks')}
    if not end.get('upload'):knowledge='No log was delivered. Opus did not receive this outing’s observations.'
    elif revised is None:knowledge='Log delivered; the post-sortie analysis is not archived yet. See the live workspace or continue from dock.'
    else:knowledge=str(revised.get('notes',''))
    next_rom=text(after/'controller.rom');next_diff=list(difflib.unified_diff(new_rom.splitlines(),next_rom.splitlines(),fromfile=f'sortie-{number:03d}.rom',tofile=f'next-{number+1:03d}.rom',lineterm='')) if next_rom else []
    debrief=optional(after/'debrief.json')
    return {'notes_before':text(before/'notes.md'),'debrief':debrief,'next_rom':next_rom,'next_rom_diff':'\n'.join(next_diff),'sortie':number,'outcome':end['result'],'duration':end['state']['t'],'distance_cm':end['state']['distance'],'contacts':end['state']['collisions'],'rescued_new':len(end['state']['found'])-len(job.get('found',[])),'uploaded':bool(end.get('upload')),'samples':len(samples),'target_sightings':sum(bool(row['readings'].get('target')) for row in samples),'dropped_samples':(end.get('upload') or {}).get('logger',{}).get('dropped_samples',0),'departure_plan':mission.get('summary',''),'knowledge':knowledge,'analysis_ready':revised is not None,'before_map':prior,'after_map':revised,'before_counts':counts(prior),'after_counts':counts(revised) if revised is not None else None,'notes_after':text(after/'notes.md') if revised is not None else '', 'next_plan':next_mission.get('summary','') if next_mission else None,'next_action':next_mission.get('action') if next_mission else None,'rom':new_rom,'previous_rom':old_rom,'rom_diff':'\n'.join(diff),'added_lines':added,'removed_lines':removed,'first_rom':number==1}

def history(root,current=None):
    runs=[]
    if not root.exists():return {'runs':[],'current_run':current}
    for folder in sorted(root.iterdir(),reverse=True):
        if not folder.is_dir() or folder.is_symlink():continue
        sorties=[]
        for path in sorted(folder.glob('return-*.json')):
            try:
                n=int(path.stem.split('-')[1]);r=report(folder,n)
                sorties.append({k:r[k] for k in ('sortie','outcome','duration','uploaded','rescued_new','analysis_ready','added_lines','removed_lines')})
            except (OSError,ValueError,KeyError):continue
        if sorties:runs.append({'id':folder.name,'sorties':sorties})
    return {'runs':runs,'current_run':current}

@functools.lru_cache(maxsize=64)
def reconstruct(job_path,job_mtime,return_path,return_mtime,engine_mtime,worker_mtime,node,worker_path,legacy_worker_path):
    job=load(pathlib.Path(job_path));
    if 'sensorModel' not in job['config'] or job['config']['sensorModel']=='legacy-three-ray-v1':worker_path=legacy_worker_path
    job={**job,'replay':True,'speed':100}
    proc=subprocess.run([node,worker_path],input=json.dumps(job),text=True,encoding='utf-8',errors='replace',capture_output=True,timeout=30)
    if proc.returncode:raise ValueError('Replay reconstruction failed: '+proc.stderr[:500])
    end=json.loads(proc.stdout.splitlines()[-1]);saved=load(pathlib.Path(return_path));a,b=end['state'],saved['state']
    exact=abs(a['t']-b['t'])<1e-7 and all(abs(a['robot'][k]-b['robot'][k])<1e-7 for k in ('x','y','a')) and a['found']==b['found'] and a['collisions']==b['collisions']
    exact=exact and a.get('path')==b.get('path') and end.get('upload')==saved.get('upload')
    if not exact:raise ValueError('The current simulator does not match this saved sortie. No historical trace was recorded for it, so an inaccurate replay is withheld.')
    return end['replay_frames']

def get_replay(root,run_id,number,node,worker,worker_path):
    folder=run_folder(root,run_id)
    if not isinstance(number,int) or not 1<=number<=10000:raise ValueError('Invalid sortie number')
    job_path=folder/f'deployment-{number:03d}.json';end_path=folder/f'return-{number:03d}.json'
    job=load(job_path);end=load(end_path);recorded=end.get('replay_frames')
    if recorded:frames=recorded;source='recorded'
    else:
        frames=reconstruct(str(job_path),job_path.stat().st_mtime_ns,str(end_path),end_path.stat().st_mtime_ns,(worker.parent/'engine.mjs').stat().st_mtime_ns,worker.stat().st_mtime_ns,node,worker_path,node_script_path(worker.parent/'legacy/sortie-v1.mjs',node));source='verified reconstruction'
    return {'run_id':run_id,'world':job['map'],'config':{**job['config'],'sensorModel':job['config'].get('sensorModel','legacy-three-ray-v1'),'missionMode':True},'frames':frames,'source':source,'report':report(folder,number),'dock_timeline':dock_timeline(folder,number)}

def dock_timeline(folder,number):
    """Published events and actual file snapshots from planning turn N+1, never thinking blocks."""
    turn=number+1;events=[];updates=[]
    try:
        for line in (folder/'events.jsonl').read_text(encoding='utf-8').splitlines():
            try:
                e=json.loads(line)
                if e.get('turn')==turn:events.append(e)
            except ValueError:continue
    except OSError:pass
    try:
        updates=[json.loads(line) for line in (folder/f'updates-{turn:03d}.jsonl').read_text(encoding='utf-8').splitlines()]
    except (OSError,ValueError):pass
    steps=[];has_updates=bool(updates);last_map=None
    for e in events:
        kind=e.get('kind');body=e.get('text','');at=e.get('at',0)
        if kind in ('assistant','assistant_stream'):
            if steps and steps[-1]['kind']=='explanation':steps[-1]['text']+=body
            else:steps.append({'kind':'explanation','title':'Opus explains its decision','text':body,'at':at})
        elif kind=='tool':
            name,_,raw=body.partition(' ')
            try:args=json.loads(raw)
            except ValueError:args={}
            filename=pathlib.Path(args.get('file_path',args.get('path',''))).name
            steps.append({'kind':'tool','title':f'{name} · {filename}' if filename else f'Opus uses {name}','text':str(args.get('pattern',''))[:500],'at':at})
            if not has_updates and name=='Write' and filename=='controller.rom' and isinstance(args.get('content'),str):steps.append({'kind':'workspace','title':'Opus rewrites the controller','text':'Published ROM update','rom':args['content'],'at':at+.001})
            if not has_updates and name=='Write' and filename=='map.json':
                try:
                    map_value=json.loads(args['content'])
                    if isinstance(map_value,dict):steps.append({'kind':'map','title':'Opus publishes an estimated map','text':str(map_value.get('notes','')),'map':map_value,'at':at+.001});last_map=map_value
                except (ValueError,KeyError):pass
        elif kind in ('analysis','decision','validation','error'):
            steps.append({'kind':kind,'title':{'analysis':'Analyze delivered observations','decision':'Next-round decision','validation':'ROM validation feedback','error':'Planning error'}[kind],'text':body,'at':at})
    for update in updates:
        file=update.get('file');content=update.get('content');step={'kind':'workspace','title':f'Workspace update · {file}','text':'Published file snapshot','at':update['at']}
        if file=='map.json' and isinstance(content,dict):step.update(kind='map',map=content,text=str(content.get('notes','')))
        elif file=='controller.rom' and isinstance(content,str):step.update(rom=content)
        elif file=='notes.md' and isinstance(content,str):step.update(notes=content)
        elif file=='debrief.json' and isinstance(content,dict):step.update(debrief=content)
        else:continue
        steps.append(step)
    steps.sort(key=lambda e:e['at'])
    final=optional(folder/f'turn-{turn:03d}'/'map.json')
    if isinstance(final,dict) and (not steps or not any(step.get('map')==final for step in steps)):
        steps.append({'kind':'map','title':'Archived map after analysis','text':str(final.get('notes','')),'map':final,'at':steps[-1]['at']+.1 if steps else 0})
    base=optional(folder/f'deployment-{number:03d}.json',{}).get('rom','')
    for step in steps:
        if isinstance(step.get('rom'),str):step['rom_diff']='\n'.join(difflib.unified_diff(base.splitlines(),step['rom'].splitlines(),fromfile=f'sortie-{number:03d}.rom',tofile='published-update.rom',lineterm=''))
    return {'steps':steps,'capture':'published events and file snapshots' if has_updates else 'legacy published events; only recoverable map writes and final archived map are available','private_reasoning':False}
