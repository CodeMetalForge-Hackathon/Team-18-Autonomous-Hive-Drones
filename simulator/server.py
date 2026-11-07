#!/usr/bin/env python3
"""Trusted human observer + dock/Claude orchestrator. Never put this in agent cwd."""
import argparse, copy, hashlib, json, math, os, pathlib, re, shutil, signal, subprocess, threading, time, uuid
import replay
import supervisor
from runtime import find_node, node_script_path
from dock_data import calculate, project_ranges
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, unquote

ROOT = pathlib.Path(__file__).resolve().parent
WORKSPACES = pathlib.Path.home() / 'rover-opus-workspaces'
RUNTIME = ROOT / '.runs'
CONTRACT = (ROOT / 'opus-contract.txt').read_text()
PROFILE='pan-sonar-light-v2'
LEGACY_PROFILE='legacy-three-ray-v1'
CLAUDE = shutil.which('claude')
NODE = find_node()

def node_path(path):
    return node_script_path(path, NODE)

def node_validate(source, ram, world=None, profile=PROFILE):
    result = subprocess.run([NODE, node_path(ROOT / 'validate.mjs')], input=json.dumps({'source':source,'ram':ram,'world':world,'profile':profile}), text=True, capture_output=True, timeout=15)
    try:
        out = json.loads(result.stdout)
    except ValueError:
        raise ValueError('ROM validator failed: ' + result.stderr[:500])
    if not out.get('ok'):
        raise ValueError(out.get('error', 'Invalid ROM'))
    return out

def validate_map(m):
    def position(p):
        return isinstance(p, dict) and all(isinstance(p.get(k), (int,float)) and math.isfinite(p[k]) for k in ('x','y')) and 0 <= p['x'] <= 250 and 0 <= p['y'] <= 100
    if not isinstance(m,dict) or not position(m.get('start')) or not isinstance(m['start'].get('a'),(int,float)) or not math.isfinite(m['start']['a']):
        raise ValueError('Invalid dock/start')
    obstacles, targets = m.get('obstacles'), m.get('targets')
    if not isinstance(obstacles,list) or len(obstacles)>500 or not isinstance(targets,list) or len(targets)>100 or not all(position(p) for p in targets):
        raise ValueError('Invalid arena')
    for b in obstacles:
        if not position(b) or not all(isinstance(b.get(k),(int,float)) and math.isfinite(b[k]) and b[k]>0 for k in ('w','h')) or b['x']+b['w']>250 or b['y']+b['h']>100:
            raise ValueError('Invalid obstacle')
    objects=m.get('objects',[])
    if not isinstance(objects,list) or len(objects)>100:raise ValueError('Invalid desk objects')
    identities=set()
    for obj in objects:
        if not position(obj) or obj.get('type') not in ('laptop','bottle','hidebox','shade','plant') or not isinstance(obj.get('id'),str) or not obj['id'] or obj['id'] in identities or not all(isinstance(obj.get(k),(int,float)) and not isinstance(obj[k],bool) and math.isfinite(obj[k]) and obj[k]>0 for k in ('w','h')) or obj['x']+obj['w']>250 or obj['y']+obj['h']>100:raise ValueError('Invalid desk object geometry or identity')
        if obj.get('opening','left') not in ('left','right'):raise ValueError('Invalid shelter opening')
        identities.add(obj['id'])
    return copy.deepcopy(m)

def hardware(config):
    limits={'range':(5,500),'rangeMin':(.5,10),'noise':(0,30),'panSpan':(20,180),'panSpeed':(10,180),'beam':(1,45),'pingHz':(1,10),'lightLevel':(0,1),'lightNoise':(0,.2),'coverLeak':(0,1),'speed':(1,150),'turn':(10,360),'battery':(10,1000),'fov':(10,150),'vision':(20,600),'ram':(4,520000),'budget':(1,512),'seed':(0,999999),'bleContact':(-70,-10),'bleNoise':(0,12),'bleDrop':(0,1),'bleMultipath':(0,12)}
    defaults={'range':80,'rangeMin':2,'noise':.4,'panSpan':90,'panSpeed':90,'beam':15,'pingHz':5,'lightLevel':1,'lightNoise':.02,'coverLeak':.08,'speed':12,'turn':90,'battery':240,'fov':65,'vision':120,'ram':64,'budget':32,'seed':42,'bleContact':-35,'bleNoise':2,'bleDrop':.08,'bleMultipath':3}
    c={k:config.get(k,default) for k,default in defaults.items()}
    for k,(low,high) in limits.items():
        if isinstance(c[k],bool) or not isinstance(c[k],(int,float)) or not math.isfinite(c[k]) or not low<=c[k]<=high:raise ValueError('Invalid hardware setting: '+k)
    for k in ('ram','budget','seed'):
        if int(c[k])!=c[k]:raise ValueError(k+' must be an integer')
    if c['rangeMin']>=c['range']:raise ValueError('Minimum range must be below maximum range')
    c['sensorModel']=config.get('sensorModel',PROFILE)
    if c['sensorModel'] not in (PROFILE,LEGACY_PROFILE):raise ValueError('Unknown hardware profile')
    c['ble']=bool(config.get('ble',True));c['camera']=bool(config.get('camera',False));c['bumpers']=bool(config.get('bumpers',False));c['virtualRescue']=bool(config.get('virtualRescue',False))
    if c['ble']:c['virtualRescue']=False
    return c

def legacy_hardware(c):
    return {'range_max_cm':c['range'],'range_uniform_noise_cm':c['noise'],'translation_max_cm_s':c['speed'],'turn_max_deg_s':c['turn'],'energy_units':c['battery'],'camera':c['camera'],'camera_fov_deg':c['fov'],'camera_range_cm':c['vision'],'register_ram_bytes':c['ram'],'instructions_per_tick':c['budget'],'tick_seconds':.1,'rom_instruction_capacity':1024,'collision_radius_cm':8.5,'logger_flash_capacity_bytes':65536,'logger_hz':5,'dock_contact_radius_cm':6,'must_depart_dock_by_cm':10,'odometry':'command-integrated, independent +/-1% scale jitter per tick; collisions may accumulate error','coordinate_frame':'dock is origin; departure forward +x, right +y; yaw clockwise degrees','mission':'explore, map, locate rescue markers, return with observations; hidden marker count is unknown'}

def public_hardware(c):
    if c.get('sensorModel')==LEGACY_PROFILE:return {**legacy_hardware(c),'sensor_model':LEGACY_PROFILE,'schema_version':1}
    return {**legacy_hardware(c),'safety_rule':{'interval_seconds':30,'light_max':.30,'continuous_dwell_seconds':2,'alternative':'dock contact','failure':'stop; no upload away from dock'},'ble':{'enabled':c.get('ble',False),'receiver':'Bluefruit LE Sniffer P2269, simulated packet/RSSI interface; onboard USB-host integration unverified','contact_reference_dbm':c.get('bleContact',-35),'reference_antenna_distance_cm':2,'path_loss_exponent':2,'noise_uniform_db':c.get('bleNoise',2),'multipath_amplitude_db':c.get('bleMultipath',3),'packet_drop_probability':c.get('bleDrop',.08),'receiver_floor_dbm':-95,'scheduled_packets_hz':5,'antenna_forward_cm':6.8,'antenna':'fixed chassis front; mounting assumed','confirmation':'3 fresh packets for one ID spanning >=1 second, gap <=1.5 seconds, RSSI >= contact reference minus 2 dB; operational proximity only','discovery':'only received target advertisements; no target count, bearing or exact distance','calibration':'all RF parameters provisional; known contact reference stands in for user calibration'},'schema_version':3,'collision_radius_cm':7.5,'sensor_model':PROFILE,'camera':c['camera'],'bumper_sensor':c['bumpers'],'virtual_rescue_detector':c['virtualRescue'],'range_min_cm':c['rangeMin'],'range_beam_deg':c['beam'],'range_sample_hz':c['pingHz'],'range_sensor_mount':{'pivot_forward_cm':4.3,'transducer_forward_cm':2.5,'height_cm':2.4,'channels':1,'pan_span_deg':c['panSpan'],'pan_speed_deg_s':c['panSpeed'],'control':'pan DEG holds an angle; sweep DEG_PER_SEC oscillates, sweep 0 holds current angle'},'light_sensor':{'position':'upward-facing on top of chassis','reading':'normalized 0..1, not lux or an oracle hidden flag','ambient_level':c['lightLevel'],'noise':c['lightNoise'],'box_light_leak':c['coverLeak']},'calibration_status':'RF attenuation, RSSI/contact calibration, antenna mounting, range, blind zone, beam width, servo speed, sensor dimensions, motion and light response are provisional simulator assumptions, NOT verified hardware specifications.','mission':'Find BLE-emitting objectives using noisy per-packet RSSI when enabled; map with one steerable ultrasonic channel; find possible shelter using light changes and local geometry, verify with multiple samples and dwell, then return with evidence. Darkness alone does not prove concealment. RGB, bumpers and virtual rescue detection are absent unless explicitly enabled.','edge_sensing':'Horizontal sonar cannot sense tabletop drop-offs. Simulator edge guard blocks falls without emitting a range echo; do not assume a measured boundary wall.'}

def mission_hardware(c,count,budget=None,until_done=False):
    return {**public_hardware(c),'objective_count':count,'run_until_complete':until_done,'mission_budget':{'limit_seconds':budget,'clock':'cumulative deployed simulated rover time; planning at base excluded','goal':'Confirm all '+str(count)+' objectives and return to the dock. Positions are unknown.','sortie_deadline':False if until_done else 'mission.json max_seconds'}}

def verify_shelter_evidence(belief,agent):
    for shelter in belief.get('shelters',[]):
        if shelter.get('shelter_status')!='verified':continue
        matched=False
        for reference in shelter.get('evidence',[]):
            name=re.search(r'observations/sortie-\d+\.json',str(reference))
            if not name:continue
            path=agent/name.group(0)
            try:log=json.loads(read_agent(path))
            except (OSError,ValueError):continue
            evidence=[row.get('readings',{}) for row in log.get('samples',[])]+[{'odom_x':c.get('odom_x'),'odom_y':c.get('odom_y'),'light':c.get('light'),'safe_dwell':c.get('dwell'),'dock':c.get('dock')} for c in log.get('safety_checks',[])]
            for r in evidence:
                if all(type(r.get(k)) in (int,float) for k in ('odom_x','odom_y','light','safe_dwell')) and not r.get('dock') and r['light']<=.3 and r['safe_dwell']>=2-1e-6 and math.hypot(r['odom_x']-shelter['x'],r['odom_y']-shelter['y'])<=15:matched=True;break
            if matched:break
        if not matched:raise ValueError('Verified shelter lacks delivered low-light dwell evidence near its estimated position. Keep it candidate or stale until measured.')

def read_agent(path, limit=262144):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Missing, oversized or symlinked workspace file: '+path.name)
    return path.read_text()

def validate_debrief(value,expected):
    if not isinstance(value,dict) or 'observed_sortie' not in value or value.get('observed_sortie')!=expected:raise ValueError('debrief.json must identify the latest delivered observed_sortie (null initially)')
    for key in ('learned','uncertainties','evidence'):
        items=value.get(key)
        if not isinstance(items,list) or not (1 if key!='evidence' else 0)<=len(items)<=12 or not all(isinstance(s,str) and 0<len(s)<=2000 for s in items):raise ValueError('debrief.json '+key+' must be a bounded list of concise strings')
    if not isinstance(value.get('next_plan'),str) or not 1<=len(value['next_plan'])<=4000:raise ValueError('debrief.json needs a concise next_plan')
    changes=value.get('rom_changes')
    if not isinstance(changes,list) or len(changes)>12 or not all(isinstance(c,dict) and all(isinstance(c.get(k),str) and 1<=len(c[k])<=2000 for k in ('change','why')) for c in changes):raise ValueError('debrief.json rom_changes requires change/why objects')

class Harness:
    def __init__(self):
        self.lock=threading.RLock();self.cancel=threading.Event();self.process=None;self.thread=None;self.events=[];self.state={'active':False,'phase':'idle','run_id':None,'sortie':0,'message':'Ready for a new experiment.','frame':None,'world':None,'turns':[]};self.agent=None;self.run=None;self.event_id=0
        # Restart restores observer state and agent files, never invents an upload or resumes an in-flight turn.
        states=sorted(RUNTIME.glob('*/observer-state.json'),key=lambda p:p.stat().st_mtime) if RUNTIME.exists() else []
        if states:
            try:
                previous=json.loads(states[-1].read_text());agent=pathlib.Path(previous.get('workspace_path',''))
                if agent.is_relative_to(WORKSPACES) and agent.is_dir():
                    previous.setdefault('config',{}).setdefault('sensorModel',LEGACY_PROFILE)
                    if previous.get('frame'):previous['frame'].setdefault('c',{}).setdefault('sensorModel',LEGACY_PROFILE)
                    self.state=previous;self.agent=agent;self.run=states[-1].parent
                    if self.state.get('active'):
                        self.state.update(active=False,phase='interrupted',message='Server restarted during an experiment. Saved workspace is available; no undocked observations were recovered.')
                    eventfile=self.run/'events.jsonl'
                    if eventfile.exists():self.events=[json.loads(line) for line in eventfile.read_text().splitlines()[-2000:]]
                    self.event_id=max((e['id'] for e in self.events),default=0)
            except (OSError,ValueError,KeyError):pass
    def event(self,kind,text,**extra):
        with self.lock:
            self.event_id+=1
            event={'id':self.event_id,'at':time.time(),'kind':kind,'text':str(text)[:20000],**extra}
            self.events.append(event);self.events=self.events[-2000:]
            if self.run:
                with (self.run/'events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
    def phase(self,phase,message):
        with self.lock:self.state.update(phase=phase,message=message,phase_started_at=time.time())
        self.event('harness',message,phase=phase);self.persist()
    def persist(self):
        with self.lock:
            if self.run:(self.run/'observer-state.json').write_text(json.dumps(self.state))
    def start(self,body):
        with self.lock:
            if self.state['active']:raise ValueError('An experiment is already active')
            if not CLAUDE:raise ValueError('Claude Code is not installed')
            world=validate_map(body.get('map'));c=hardware(body.get('config',{}));node_validate('yield',int(c['ram']),world,c['sensorModel'])
            rounds=int(body.get('rounds',8));speed=float(body.get('speed',8))
            if not 1<=rounds<=50 or not 1<=speed<=100:raise ValueError('Use 1–50 sorties and 1–100× speed')
            until_done=bool(body.get('until_done',False))
            budget=body.get('mission_seconds')
            if until_done and budget is not None:raise ValueError('Until-complete missions cannot have a time budget')
            if until_done and not world['targets']:raise ValueError('Add at least one objective')
            if budget is not None and (type(budget) not in (int,float) or not math.isfinite(budget) or not 5<=budget<=3600):raise ValueError('Mission budget must be 5–3600 simulated seconds')
            run_id=time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]
            self.run=RUNTIME/run_id;self.run.mkdir(parents=True)
            self.agent=WORKSPACES/run_id/'agent';self.agent.mkdir(parents=True)
            (self.agent/'observations').mkdir()
            (self.agent/'hardware.json').write_text(json.dumps(mission_hardware(c,len(world['targets']),budget,until_done),indent=2))
            (self.agent/'inbox.json').write_text(json.dumps({'kind':'initial','observation_files':[],'objective_count':len(world['targets']),'confirmed_count':0,'until_done':until_done,'mission_seconds_remaining':budget,'mission_seconds_used':0,'message':'No environmental observations have been delivered. Design your first short returnable sortie. Mission clock, if configured, spans ALL sorties; planning at base is excluded.'},indent=2))
            (self.agent/'controller.rom').write_text('; Write your first controller. Commands persist.\nmove 0\nyield\njmp 0\n')
            (self.agent/'mission.json').write_text(json.dumps({'action':'deploy','max_seconds':30,'summary':'Awaiting Opus first design.'},indent=2))
            (self.agent/'map.json').write_text(json.dumps({'frame':'dock-relative-cm','occupied':[],'free':[],'landmarks':[],'shelters':[],'notes':'Unknown. No observations yet.'},indent=2))
            (self.agent/'notes.md').write_text('No observations yet. The environment is unknown.\n')
            self.cancel.clear();self.events=[];self.event_id=0
            self.state={'active':True,'phase':'planning','run_id':run_id,'sortie':0,'message':'Starting Opus from an empty map.','frame':None,'world':world,'config':c,'turns':[],'workspace_path':str(self.agent),'until_done':until_done,'objective_count':len(world['targets']),'max_rounds':None if until_done else rounds,'speed':speed,'model':'opus','mission_seconds_limit':budget,'mission_seconds_used':0}
            self.thread=threading.Thread(target=self.loop,args=(world,c,rounds,speed),daemon=True);self.persist();self.thread.start()
            return self.snapshot()
    def resume(self,body):
        with self.lock:
            if self.state['active']:raise ValueError('An experiment is already active')
            if self.state.get('config',{}).get('sensorModel',LEGACY_PROFILE)==LEGACY_PROFILE:raise ValueError('This archive uses legacy fixed sensors. Replay it, but start a new experiment for the photo-based hardware.')
            if not self.state.get('config',{}).get('ble'):raise ValueError('Pre-BLE experiments are replay-only. Start a fresh BLE experiment.')
            if not self.agent or not self.run or not self.state.get('world'):raise ValueError('No saved experiment')
            if self.mission_remaining() is not None and self.mission_remaining()<=0:raise ValueError('Mission time budget exhausted; start a new experiment')
            frame=self.state.get('frame')
            if self.state['phase']=='stranded' or frame and not frame.get('readings',{}).get('dock'):
                raise ValueError('The rover is not at the dock. Its undelivered data cannot be recovered.')
            if self.state['phase'] not in ('limit','finished','stopped','interrupted','error'):raise ValueError('No docked experiment to continue')
            rounds=int(body.get('rounds',8));speed=float(body.get('speed',8))
            if not 1<=rounds<=50 or not 1<=speed<=100:raise ValueError('Use 1–50 sorties and 1–100× speed')
            # Restage immutable inputs from trusted successful return records, never from failed/undocked sorties.
            c=self.state['config'];delivered=[]
            for path in sorted(self.run.glob('return-*.json')):
                record=json.loads(path.read_text())
                if record.get('result')=='docked' and record.get('upload'):
                    number=record['upload']['sortie'];name=f'observations/sortie-{number:03d}.json'
                    (self.agent/name).write_text(json.dumps(record['upload'],indent=2));delivered.append(name)
            (self.agent/'hardware.json').write_text(json.dumps(mission_hardware(c,len(self.state['world']['targets']),self.state.get('mission_seconds_limit'),self.state.get('until_done',False)),indent=2))
            inbox={'kind':'dock_return','latest_observation':delivered[-1],'observation_files':delivered,'message':'Continuing from a physically docked state with the existing workspace. No additional environmental observations were supplied.'} if delivered else {'kind':'initial','observation_files':[],'message':'Continuing initial planning. No environmental observations have been supplied.'}
            inbox.update(mission_seconds_remaining=self.mission_remaining(),mission_seconds_used=self.state.get('mission_seconds_used',0),objective_count=len(self.state['world']['targets']),confirmed_count=len((self.state.get('frame') or {}).get('found',[])),until_done=self.state.get('until_done',False))
            (self.agent/'inbox.json').write_text(json.dumps(inbox,indent=2))
            start_turn=max((int(p.stem.split('-')[-1]) for p in self.run.glob('deployment-*.json')),default=0)+1
            self.cancel.clear();self.state.update(active=True,phase='planning',message='Continuing the existing docked workspace.',max_rounds=None if self.state.get('until_done') else start_turn+rounds-1,speed=speed)
            self.thread=threading.Thread(target=self.loop,args=(self.state['world'],c,rounds,speed,start_turn),daemon=True)
            self.persist();self.thread.start();return self.snapshot()
    def update_environment(self,body):
        with self.lock:
            if not self.state.get('run_id'):raise ValueError('Start an experiment before changing its environment')
            if self.state.get('config',{}).get('sensorModel')!=PROFILE:raise ValueError('Legacy experiments are replay-only for environment changes')
            frame=self.state.get('frame')
            if self.state['phase']=='deployed' or frame and not frame.get('readings',{}).get('dock'):raise ValueError('Changes can be applied only while the rover is at the dock')
            updated=validate_map(body.get('map'));current=self.state['world']
            if updated['start']!=current['start']:raise ValueError('Keep the dock fixed during an experiment')
            if self.state['config'].get('virtualRescue') and updated['targets']!=current['targets']:raise ValueError('Keep virtual targets fixed during an experiment')
            node_validate('yield',int(self.state['config']['ram']),updated,PROFILE)
            self.state['world']=updated;self.state['world_revision']=self.state.get('world_revision',0)+1
            self.event('environment','Human changed the table at the dock. Opus is not notified; it must discover changes from new sensor data.')
            self.persist();return {'ok':True,'world_revision':self.state['world_revision']}
    def snapshot(self):
        with self.lock:return copy.deepcopy(self.state)
    def stop(self):
        self.cancel.set()
        with self.lock:p=self.process
        if p and p.poll() is None:
            try:os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        self.event('harness','Stop requested. No undocked data will be delivered.')
    def protected(self):
        return {str(p.relative_to(self.agent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [self.agent/'hardware.json',self.agent/'inbox.json',*(self.agent/'observations').glob('*.json')]}
    def launch(self,args,**kw):
        if self.cancel.is_set():raise InterruptedError('Experiment stopped')
        p=subprocess.Popen(args,start_new_session=True,**kw)
        with self.lock:self.process=p
        return p
    def watch_workspace(self,process,agent,turn):
        seen={}
        while process.poll() is None and not self.cancel.is_set():
            for name in ('map.json','notes.md','controller.rom','debrief.json','supervisor.json','live.json'):
                try:
                    content=read_agent(agent/name);digest=hashlib.sha256(content.encode()).hexdigest()
                    if seen.get(name)==digest:continue
                    value=json.loads(content) if name.endswith('.json') else content
                    if name.endswith('.json') and not isinstance(value,dict):continue
                    seen[name]=digest
                    snapshot={'at':time.time(),'turn':turn,'file':name,'content':value}
                    with self.lock:
                        with (self.run/f'updates-{turn:03d}.jsonl').open('a') as f:f.write(json.dumps(snapshot)+'\n')
                except (OSError,ValueError):pass
            self.cancel.wait(.15)
    def review(self,body=None):
        with self.lock:
            if self.state['active']:raise ValueError('An experiment is already active')
            if not self.agent or not self.state.get('frame',{}).get('readings',{}).get('dock'):raise ValueError('Review requires the rover at its physical dock')
            last=max((int(p.stem.split('-')[-1]) for p in self.run.glob('return-*.json')),default=0)
            if not last or not (self.agent/f'observations/sortie-{last:03d}.json').is_file():raise ValueError('No returned observations to review')
            self.cancel.clear();self.state.update(active=True,phase='reviewing',message='Reviewing returned data; no rover will be deployed.')
            def work():
                try:
                    self.plan(last+1,review_only=True);self.phase('limit','Dock debrief and next ROM/plan archived. No rover deployed.')
                except Exception as e:self.phase('error',str(e))
                finally:
                    with self.lock:self.state['active']=False;self.process=None
                    self.persist()
            self.thread=threading.Thread(target=work,daemon=True);self.thread.start();return self.snapshot()
    def analysis_loop(self,process,agent,turn):
        last=None;request=agent/'analysis-request.json'
        if request.is_file() and not request.is_symlink():last=hashlib.sha256(request.read_bytes()).hexdigest()
        while process.poll() is None and not self.cancel.is_set():
            try:
                text=read_agent(request,4096);digest=hashlib.sha256(text.encode()).hexdigest()
                if digest!=last:
                    data=json.loads(text);identity=data.get('id');operation=data.get('operation')
                    if not isinstance(identity,str) or not 1<=len(identity)<=80:raise ValueError('Request needs a unique string id of 1..80 characters')
                    last=digest
                    try:
                        if operation=='project_ranges':result=project_ranges(agent,data.get('files'),data.get('cell_cm',5))
                        elif operation=='calculate':result={'value':calculate(data.get('expression'))}
                        else:raise ValueError('Unknown analysis operation')
                        response={'id':identity,'operation':operation,'ok':True,'result':result}
                        self.event('analysis',f'{operation}: derived from already delivered data only.',turn=turn)
                    except Exception as e:response={'id':identity,'operation':operation,'ok':False,'error':str(e)}
                    temp=agent/'.analysis-result.tmp';temp.write_text(json.dumps(response));temp.replace(agent/'analysis-result.json')
            except (OSError,ValueError):pass
            self.cancel.wait(.05)
    def plan(self,turn,review_only=False):
        before=self.protected()
        try:prior_map=json.loads(read_agent(self.agent/'map.json'))
        except (ValueError,OSError):prior_map={}
        self.phase('reviewing' if review_only else 'planning',f'Opus turn {turn}: '+('reviewing the last return without deploying.' if review_only else 'reading only its workspace and dock-delivered evidence.'))
        args=[CLAUDE,'-p','--model','opus','--effort','medium','--restricted','--safe-mode','--no-chrome','--disable-slash-commands','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--tools','Read,Write,Edit,Glob,Grep','--allowedTools','Read,Write,Edit,Glob,Grep','--permission-mode','dontAsk','--no-session-persistence','--output-format','stream-json','--include-partial-messages','--verbose','--system-prompt',(ROOT/'legacy/opus-contract-v1.txt').read_text() if self.state['config'].get('sensorModel')==LEGACY_PROFILE else CONTRACT]
        prompt=f'Automatic dock turn {turn}. Read inbox.json and hardware.json, and validation.txt if present; inspect your existing workspace and delivered observations, then update controller.rom, mission.json, map.json, notes.md, debrief.json and supervisor.json. Publish live.json immediately with one short public progress sentence, then refresh it after discoveries or plan changes while working. This is an evidence/action summary, not private reasoning. Publish a concise evidence/decision summary. Finish this turn after writing the files; the harness will validate and deploy them.'
        if review_only:prompt+=' This is REVIEW ONLY at the dock. Analyze the last delivered log and prepare an evidence-backed debrief and next ROM/plan. Nothing will be deployed during this call.'
        stderr_path=self.run/f'claude-{turn:03d}.stderr.log'
        streamed=False;result=None
        with stderr_path.open('a') as err:
            p=self.launch(args,cwd=self.agent,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True,bufsize=1,env={**os.environ,'CLAUDE_CODE_DISABLE_AUTO_MEMORY':'1'})
            threading.Thread(target=self.analysis_loop,args=(p,self.agent,turn),daemon=True).start()
            threading.Thread(target=self.watch_workspace,args=(p,self.agent,turn),daemon=True).start()
            p.stdin.write(prompt);p.stdin.close()
            for line in p.stdout:
                if self.cancel.is_set():break
                try:e=json.loads(line)
                except ValueError:continue
                kind=e.get('type')
                if kind=='stream_event':
                    stream=e.get('event',{});delta=stream.get('delta',{})
                    if stream.get('type')=='content_block_start' and stream.get('content_block',{}).get('type')=='thinking':
                        self.event('activity','Opus is processing this turn. Private internal reasoning is not included in the transcript.',turn=turn)
                    elif delta.get('type')=='text_delta':
                        text=delta.get('text','')
                        self.event('assistant_stream',text,turn=turn);streamed=True
                elif kind=='assistant':
                    model=e.get('message',{}).get('model')
                    if model:
                        with self.lock:self.state['resolved_model']=model
                    for block in e.get('message',{}).get('content',[]):
                        if block.get('type')=='text' and not streamed:self.event('assistant',block.get('text',''),turn=turn)
                        elif block.get('type')=='tool_use':self.event('tool',block.get('name','')+' '+json.dumps(block.get('input',{})),turn=turn)
                        # Thinking/redacted_thinking blocks are deliberately excluded.
                elif kind=='user':
                    for block in e.get('message',{}).get('content',[]) if isinstance(e.get('message',{}).get('content'),list) else []:
                        if block.get('type')=='tool_result':
                            content=block.get('content','');text=content if isinstance(content,str) else json.dumps(content)
                            self.event('tool_result',text[:12000],turn=turn)
                elif kind=='result':result=e
            code=p.wait();p.stdout.close()
        if self.cancel.is_set():raise InterruptedError('Experiment stopped')
        if code or not result or result.get('is_error'):
            detail=(result or {}).get('result') or stderr_path.read_text()[-1500:] or f'Claude exited {code} without a successful result'
            raise RuntimeError(str(detail))
        if self.protected()!=before:raise RuntimeError('Agent modified an immutable hardware/inbox/observation file; deployment blocked.')
        mission=json.loads(read_agent(self.agent/'mission.json'));rom=read_agent(self.agent/'controller.rom',65536)
        if mission.get('action') not in ('deploy','finish'):raise ValueError('mission.json action must be deploy or finish')
        if mission['action']=='finish' and self.state.get('until_done') and len((self.state.get('frame')or{}).get('found',[]))<self.state['objective_count']:raise ValueError('Mission incomplete: continue deploying until all known objectives are confirmed and returned to base.')
        if mission['action']=='deploy':
            seconds=mission.get('max_seconds',60)
            if isinstance(seconds,bool) or not isinstance(seconds,(int,float)) or not math.isfinite(seconds) or not 5<=seconds<=180:raise ValueError('max_seconds must be 5–180')
            node_validate(rom,int(self.state['config']['ram']),profile=self.state['config'].get('sensorModel',PROFILE))
        debrief=json.loads(read_agent(self.agent/'debrief.json'))
        inbox=json.loads(read_agent(self.agent/'inbox.json'));latest=inbox.get('latest_observation');expected=int(pathlib.Path(latest).stem.split('-')[-1]) if latest else None
        validate_debrief(debrief,expected)
        if self.state['config'].get('sensorModel')!=LEGACY_PROFILE:
            supervisor.validate_brief(json.loads(read_agent(self.agent/'supervisor.json')),expected)
            belief=json.loads(read_agent(self.agent/'map.json'));supervisor.validate_belief(belief,expected or 0,prior_map);verify_shelter_evidence(belief,self.agent)
        archive=self.run/f'turn-{turn:03d}';archive.mkdir(exist_ok=True)
        for name in ('mission.json','controller.rom','map.json','notes.md','debrief.json','supervisor.json'):
            path=self.agent/name
            if path.exists():(archive/name).write_text(read_agent(path))
        summary=str(mission.get('summary',''))[:3000]
        with self.lock:
            self.state['turns']=[t for t in self.state['turns'] if t['turn']!=turn]
            self.state['turns'].append({'turn':turn,'summary':summary,'action':mission['action'],'at':time.time(),'review_only':review_only})
        self.event('decision',summary,turn=turn)
        return mission,rom
    def mission_remaining(self):
        limit=self.state.get('mission_seconds_limit')
        return None if limit is None else max(0,round(limit-self.state.get('mission_seconds_used',0),2))
    def final_review(self,turn):
        for attempt in range(3):
            try:self.plan(turn,review_only=True);return
            except ValueError as e:
                if attempt==2:raise
                (self.agent/'validation.txt').write_text('Review output validation failed; no new environment data exists. '+str(e))
    def sortie(self,world,c,number,speed,mission,rom,found):
        with self.lock:self.state['deployed_rom']=rom
        self.phase('deployed',f'Sortie {number}: rover disconnected. Opus is idle until physical docking.')
        self.persist()
        job={'map':world,'config':c,'sortie':number,'speed':speed,'max_seconds':mission['max_seconds'],'rom':rom,'found':found,'until_done':self.state.get('until_done',False)}
        elapsed=self.state.get('mission_seconds_used',0);remaining=self.mission_remaining()
        if remaining is not None:
            job.update(mission_remaining=remaining,mission_elapsed=elapsed);job['max_seconds']=min(job['max_seconds'],remaining)
        (self.run/f'deployment-{number:03d}.json').write_text(json.dumps(job))
        with (self.run/f'rover-{number:03d}.stderr.log').open('w') as err:
            p=self.launch([NODE,node_path(ROOT/'sortie.mjs')],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err,text=True,bufsize=1)
            p.stdin.write(json.dumps(job));p.stdin.close();end=None
            for line in p.stdout:
                if self.cancel.is_set():break
                event=json.loads(line)
                if event['type']=='frame':
                    with self.lock:
                        self.state['frame']=event['state']
                        self.state['mission_seconds_used']=round(elapsed+event['state']['t'],2)
                elif event['type']=='end':end=event
            p.wait(timeout=10);p.stdout.close()
        if self.cancel.is_set():raise InterruptedError('Experiment stopped')
        if not end:raise RuntimeError('Rover worker ended without a result')
        with self.lock:
            self.state['frame']=end['state']
            self.state['mission_seconds_used']=round(elapsed+end['state']['t'],2)
        (self.run/f'return-{number:03d}.json').write_text(json.dumps(end))
        return end
    def loop(self,world,c,rounds,speed,start_turn=1):
        found=list((self.state.get('frame') or {}).get('found',[])) if start_turn>1 else [];delivered=[str(p.relative_to(self.agent)) for p in sorted((self.agent/'observations').glob('*.json'))]
        try:
            turn=start_turn
            while self.state.get('until_done') or turn<start_turn+rounds:
                if self.cancel.is_set():raise InterruptedError('Experiment stopped')
                if self.mission_remaining() is not None and self.mission_remaining()<=0:
                    self.phase('time_limit','Shared mission time budget exhausted; no further deployment.');break
                with self.lock:self.state['sortie']=turn
                for attempt in range(3):
                    try:
                        mission,rom=self.plan(turn)
                        (self.agent/'validation.txt').unlink(missing_ok=True)
                        break
                    except ValueError as e:
                        if attempt==2:raise
                        self.event('validation',str(e),turn=turn)
                        (self.agent/'validation.txt').write_text('Your output was not deployed. Fix the following local output/ROM validation error. No new environment data exists.\n'+str(e))
                if mission['action']=='finish':self.phase('finished','Opus ended the experiment: '+str(mission.get('summary','')));break
                with self.lock:current_world=copy.deepcopy(self.state.get('world',world))
                result=self.sortie(current_world,c,turn,speed,mission,rom,found)
                if result['result']!='docked':
                    self.phase('time_limit' if result['result']=='mission_timeout' else 'stranded',f'Sortie {turn}: {result["result"]}. No observations uploaded; Opus has not seen this outing.');break
                self.phase('downloading',f'Physical dock connection: downloading sortie {turn} observations and recharging.')
                name=f'observations/sortie-{turn:03d}.json';(self.agent/name).write_text(json.dumps(result['upload'],indent=2));delivered.append(name);found=result['state']['found']
                (self.agent/'inbox.json').write_text(json.dumps({'kind':'dock_return','latest_observation':name,'observation_files':delivered,'objective_count':len(current_world['targets']),'confirmed_count':len(found),'until_done':self.state.get('until_done',False),'mission_seconds_remaining':self.mission_remaining(),'mission_seconds_used':self.state.get('mission_seconds_used',0),'message':'Rover has physically docked, log uploaded, battery recharged, departure orientation restored. Review the new data and decide the next move.'},indent=2))
                self.event('download',f'{name}: {len(result["upload"]["samples"])} samples, {result["upload"]["logger"]["dropped_samples"]} overwritten.')
                self.persist()
                complete=bool(current_world.get('targets')) and len(set(found))==len(current_world['targets'])
                expired=self.mission_remaining() is not None and self.mission_remaining()<=0
                if complete or expired:
                    self.final_review(turn+1)
                    self.phase('rescued' if complete else 'time_limit','All objectives confirmed and rover returned within the mission budget.' if complete else 'Mission budget exhausted at the dock. Final review archived; no more sorties.')
                    break
                self.cancel.wait(.7)
                turn+=1
            else:
                self.final_review(turn)
                self.phase('limit','Sortie limit reached at the dock. Final debrief and next plan archived; no further deployments scheduled.')
        except InterruptedError:self.phase('stopped','Experiment stopped. No undocked data delivered.')
        except Exception as e:self.phase('error',str(e));self.event('error',str(e))
        finally:
            with self.lock:self.state['active']=False;self.process=None
            self.persist()
    def workspace(self):
        if not self.agent:return {'files':[],'map':None}
        files=[]
        for p in self.agent.rglob('*'):
            if p.is_file() and not p.is_symlink() and not any(part.startswith('.') for part in p.relative_to(self.agent).parts):
                files.append({'path':str(p.relative_to(self.agent)),'bytes':p.stat().st_size,'mtime':p.stat().st_mtime})
                if len(files)>=300:break
        estimate=None
        try:estimate=json.loads(read_agent(self.agent/'map.json'))
        except (OSError,ValueError):pass
        return {'files':sorted(files,key=lambda f:f['path']),'map':estimate}

harness=Harness()
def static_path_allowed(path):
    decoded=unquote(path)
    parts=pathlib.PurePosixPath(decoded).parts
    suffix=pathlib.PurePosixPath(decoded).suffix.lower()
    notices=('/vendor/THREE-LICENSE.txt','/assets/M5STACK-LICENSE.txt')
    return not (any(p.startswith('.') for p in parts) or suffix not in ('','.html','.css','.mjs','.js','.stl','.json','.ico','.png','.txt') or suffix=='.txt' and decoded not in notices or decoded in ('/sortie.mjs','/validate.mjs'))

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def log_message(self,*args):pass
    def local_host(self):
        host=self.headers.get('Host','').lower()
        port=self.server.server_port
        allowed={f'localhost:{port}',f'127.0.0.1:{port}'}
        if port==80:allowed.update(('localhost','127.0.0.1'))
        return host in allowed
    def do_HEAD(self):
        if not self.local_host():return self.send_error(403,'Local hostnames only')
        path=urlparse(self.path).path
        if path.startswith('/api/'):return self.send_error(405,'Use GET for read-only API requests')
        if not static_path_allowed(path):return self.send_error(404)
        return super().do_HEAD()
    def send_json(self,data,status=200):
        encoded=json.dumps(data,allow_nan=False).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(encoded)));self.end_headers();self.wfile.write(encoded)
    def do_GET(self):
        if not self.local_host():return self.send_json({'error':'Local hostnames only'},403)
        route=urlparse(self.path);query=parse_qs(route.query)
        try:
            if route.path=='/api/status':return self.send_json({'backend':True,'claude_available':bool(CLAUDE),'state':harness.snapshot(),'workspace':harness.workspace(),'events':[e for e in harness.events if e['id']>int(query.get('after',['0'])[0])]})
            if route.path=='/api/supervisor':return self.send_json(supervisor.projection(harness))
            if route.path=='/api/history':return self.send_json(replay.history(RUNTIME,harness.state.get('run_id')))
            if route.path=='/api/sortie-report':return self.send_json(replay.report(replay.run_folder(RUNTIME,query.get('run',[''])[0]),int(query.get('sortie',['0'])[0])))
            if route.path=='/api/replay':return self.send_json(replay.get_replay(RUNTIME,query.get('run',[''])[0],int(query.get('sortie',['0'])[0]),NODE,ROOT/'sortie.mjs',node_path(ROOT/'sortie.mjs')))
            if route.path=='/api/file':
                if not harness.agent:raise ValueError('No workspace yet')
                name=query.get('path',['notes.md'])[0];path=(harness.agent/name).resolve()
                if not path.is_relative_to(harness.agent.resolve()):raise ValueError('Workspace path only')
                return self.send_json({'path':name,'content':read_agent(path)})
            # Never serve trusted runtime state, agent assets, dotfiles, or backend source.
            if not static_path_allowed(route.path):return self.send_error(404)
            return super().do_GET()
        except (ValueError,OSError) as e:return self.send_json({'error':str(e)},400)
    def do_POST(self):
        if not self.local_host():return self.send_json({'error':'Local hostnames only'},403)
        origin=self.headers.get('Origin')
        if origin and (urlparse(origin).scheme!='http' or urlparse(origin).netloc.lower()!=self.headers.get('Host','').lower()):return self.send_json({'error':'Same-origin requests only'},403)
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1000000:raise ValueError('Invalid request size')
            body=json.loads(self.rfile.read(length))
            if self.path=='/api/start':return self.send_json(harness.start(body))
            if self.path=='/api/environment':return self.send_json(harness.update_environment(body))
            if self.path=='/api/review':return self.send_json(harness.review(body))
            if self.path=='/api/resume':return self.send_json(harness.resume(body))
            if self.path=='/api/stop':harness.stop();return self.send_json({'ok':True})
            return self.send_error(404)
        except (ValueError,OSError) as e:return self.send_json({'error':str(e)},400)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    print(f'Rover Lab + Opus dock harness: http://localhost:{args.port}',flush=True)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    try:server.serve_forever()
    except KeyboardInterrupt:harness.stop()
