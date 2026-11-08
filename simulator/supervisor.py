"""Public operator projection: published agent beliefs and brief reports, no true world."""
import hashlib,json,pathlib,time,math

KINDS=('learned','plan','rom')
def validate_brief(value,expected):
    if not isinstance(value,dict) or value.get('observed_sortie')!=expected or 'observed_sortie' not in value:raise ValueError('supervisor.json must identify the latest observed_sortie')
    reports=value.get('reports')
    if not isinstance(reports,list) or len(reports)!=3 or sorted(r.get('kind','') for r in reports if isinstance(r,dict))!=sorted(KINDS):raise ValueError('supervisor.json requires exactly one learned, plan and rom report')
    for r in reports:
        text=r.get('text')
        if not isinstance(text,str) or not 1<=len(text)<=72 or len(text.split())>12 or '\n' in text:raise ValueError('Each supervisor report must be one short sentence: at most 72 characters and 12 words')
        if r.get('confidence','uncertain') not in ('observed','uncertain','revised'):raise ValueError('Unknown report confidence')

def validate_belief(value,observed_sortie,previous=None):
    if not isinstance(value,dict) or value.get('frame')!='dock-relative-cm':raise ValueError('map.json needs frame dock-relative-cm')
    revision=value.get('revision')
    if type(revision) is not int or revision<1:raise ValueError('map.json needs a positive integer revision')
    previous=previous if isinstance(previous,dict) else {}
    prior_revision=previous.get('revision',0)
    if type(prior_revision) is not int:prior_revision=0
    changed=any(value.get(k,[])!=previous.get(k,[]) for k in ('occupied','free','landmarks','shelters'))
    if revision<prior_revision or changed and revision<=prior_revision:raise ValueError('Increase map revision when point beliefs change; never decrease it')
    for kind in ('occupied','free','landmarks','shelters'):
        points=value.get(kind,[] if kind=='shelters' else None)
        if not isinstance(points,list) or len(points)>2000:raise ValueError('Map point lists must contain at most 2000 entries each')
        for point in points:
            if not isinstance(point,dict) or not all(type(point.get(k)) in (int,float) and math.isfinite(point[k]) and abs(point[k])<10000 for k in ('x','y')):raise ValueError('Map points need finite dock-relative coordinates')
            if type(point.get('confidence')) not in (int,float) or not 0<=point['confidence']<=1:raise ValueError('Every map point needs confidence 0..1')
            if type(point.get('last_seen_sortie')) is not int or not 0<=point['last_seen_sortie']<=observed_sortie:raise ValueError('Every map point needs a valid last_seen_sortie; future evidence does not exist')
            if point.get('status') not in ('observed','uncertain','revised'):raise ValueError('Map point status must be observed, uncertain or revised')
    for shelter in value.get('shelters',[]):
        if shelter.get('shelter_status') not in ('candidate','verified','stale','blocked'):raise ValueError('Shelter needs candidate, verified, stale or blocked status')
        if shelter.get('shelter_status')=='verified':
            if type(shelter.get('light_max')) not in (int,float) or not 0<=shelter['light_max']<=.3 or type(shelter.get('dwell_seconds')) not in (int,float) or shelter['dwell_seconds']<2 or not isinstance(shelter.get('evidence'),list) or not shelter['evidence']:raise ValueError('Verified shelters need measured low-light dwell and evidence')
    changes=value.get('changes',[])
    if not isinstance(changes,list) or len(changes)>100:raise ValueError('Map changes must be a compact list')
    for change in changes:
        if not isinstance(change,dict) or change.get('type') not in ('added','revised','removed','conflict') or not isinstance(change.get('reason'),str) or not change['reason']:raise ValueError('Map changes need type and an evidence-based reason')

def compact(text):
    text=' '.join(str(text).split());words=text.split()[:12];value=' '.join(words)
    if len(value)>69:value=value[:69].rsplit(' ',1)[0]
    return value+'…' if value!=text else value

def safe_map(value):
    if not isinstance(value,dict):return {'frame':'dock-relative-cm','occupied':[],'free':[],'landmarks':[],'notes':'No published map yet.'}
    result={k:value[k] for k in ('frame','revision','notes','changes') if k in value}
    for key in ('occupied','free','landmarks','shelters'):
        items=value.get(key,[]);result[key]=items[:2000] if isinstance(items,list) else []
    if not isinstance(result.get('changes',[]),list):result['changes']=[]
    if 'changes' in result:result['changes']=result['changes'][:100]
    return result

def projection(harness):
    state=harness.snapshot();agent=harness.agent;map_value=None;brief=None;debrief=None;stamp=0
    def read(name):
        nonlocal stamp
        if not agent:return None
        p=agent/name
        if p.is_symlink() or not p.is_file() or p.stat().st_size>262144:return None
        try:result=json.loads(p.read_text(encoding='utf-8'));stamp=max(stamp,p.stat().st_mtime);return result
        except (OSError,ValueError):return None
    map_value=read('map.json');map_stamp=(agent/'map.json').stat().st_mtime if agent and (agent/'map.json').is_file() and not (agent/'map.json').is_symlink() else 0;brief=read('supervisor.json');debrief=read('debrief.json')
    reports=[];source='awaiting'
    if isinstance(brief,dict):
        try:
            validate_brief(brief,brief.get('observed_sortie'));reports=brief['reports'];source='opus'
        except ValueError:pass
    if not reports and isinstance(debrief,dict):
        learned=debrief.get('learned',[]);changes=debrief.get('rom_changes',[])
        reports=[{'kind':'learned','text':compact(learned[0] if learned else 'No findings published.'),'confidence':'uncertain'},{'kind':'plan','text':compact(debrief.get('next_plan','No next plan published.')),'confidence':'uncertain'},{'kind':'rom','text':compact(changes[0].get('change','No change published.') if changes and isinstance(changes[0],dict) else 'No change published.'),'confidence':'uncertain'}];source='archive_excerpt'
    # Read only the last returned estimate, never the observer's true live pose.
    returned=None;inbox=read('inbox.json')
    if isinstance(inbox,dict) and isinstance(inbox.get('latest_observation'),str) and agent:
        name=inbox['latest_observation'];p=(agent/name).resolve()
        if p.is_relative_to((agent/'observations').resolve()):
            try:
                if p.stat().st_size<=262144:
                    samples=json.loads(p.read_text(encoding='utf-8')).get('samples',[])
                    if samples:
                        s=samples[-1]['readings'];returned={'x':s['odom_x'],'y':s['odom_y'],'yaw':s['yaw'],'sortie':brief.get('observed_sortie') if isinstance(brief,dict) else debrief.get('observed_sortie') if isinstance(debrief,dict) else None}
            except (OSError,ValueError,KeyError):pass
    live=read('live.json');live_stamp=0
    if agent:
        p=agent/'live.json'
        if p.is_file() and not p.is_symlink():live_stamp=p.stat().st_mtime
    if not isinstance(live,dict) or live.get('kind') not in KINDS or not isinstance(live.get('text'),str) or not 1<=len(live['text'])<=72 or len(live['text'].split())>12 or '\n' in live['text'] or live.get('confidence','uncertain') not in ('observed','uncertain','revised'):live=None
    else:live={k:live[k] for k in ('kind','text','confidence') if k in live}
    report_stamp=0
    if agent:
        p=agent/('supervisor.json' if source=='opus' else 'debrief.json')
        if p.is_file() and not p.is_symlink():report_stamp=p.stat().st_mtime
    activity='Waiting for the next mission step';activity_at=state.get('phase_started_at',0)
    for e in reversed(getattr(harness,'events',[])):
        if e.get('kind') not in ('tool','assistant','activity'):continue
        if e.get('at',0)<state.get('phase_started_at',0):break
        activity_at=e.get('at',activity_at)
        text=e.get('text','')
        if e.get('kind')=='tool':
            if 'controller.rom' in text:activity='Working on the rover ROM'
            elif 'map.json' in text:activity='Reading or updating the map'
            elif 'analysis-' in text or 'observations/' in text:activity='Studying returned sensor data'
            elif 'live.json' in text or 'supervisor.json' in text:activity='Publishing a short update'
            else:activity='Working in the mission workspace'
        else:activity='Opus is working on this turn'
        break
    mapped=safe_map(map_value);revision=hashlib.sha256(json.dumps(mapped,sort_keys=True).encode()).hexdigest()[:12]
    report_sortie=brief.get('observed_sortie') if isinstance(brief,dict) else debrief.get('observed_sortie') if isinstance(debrief,dict) else None
    packet=hashlib.sha256(json.dumps([report_sortie,reports],sort_keys=True).encode()).hexdigest()[:12]
    frame=state.get('frame')or{};readings=frame.get('readings')or{}
    sonar={k:readings[k] for k in ('pan','range','range_valid','range_angle','range_age','range_seq','light','safety_due','safe_dwell','dock') if type(readings.get(k)) in (int,float) and math.isfinite(readings[k])}
    sonar.update(phase=state['phase'],pan_span=(state.get('config')or{}).get('panSpan',90),beam=(state.get('config')or{}).get('beam',15),source='human observer only; not sent to Opus')
    return {'sonar':sonar,'objective_count':state.get('objective_count'),'confirmed_count':len(frame.get('found',[])) if state.get('phase')!='deployed' else (inbox or {}).get('confirmed_count',0),'until_done':state.get('until_done',False),'report_updated_at':report_stamp,'live_report':live,'live_updated_at':live_stamp,'phase_started_at':state.get('phase_started_at',0),'activity':activity,'activity_at':activity_at,'mission_seconds_limit':state.get('mission_seconds_limit'),'mission_seconds_used':state.get('mission_seconds_used',0),'run_id':state.get('run_id'),'phase':state['phase'],'active':state['active'],'sortie':state.get('sortie',0),'hardware_profile':state.get('config',{}).get('sensorModel'),'map':mapped,'map_revision':revision,'updated_at':stamp,'map_updated_at':map_stamp,'reports':reports,'report_packet':packet,'report_source':source,'report_sortie':report_sortie,'last_returned_estimate':returned}
