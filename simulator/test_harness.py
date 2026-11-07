"""No model calls: exercise real worker physics and trusted orchestration boundaries."""
import json, pathlib, subprocess, tempfile, time, threading, unittest
from unittest.mock import patch
import server
import dock_data

RETURN_ROM='''loop:
sense r0 time
lt r0 1.3
jnz r0 outbound
move -1
yield
jmp loop
outbound:
move 1
yield
jmp loop
'''
WORLD={'start':{'x':18,'y':50,'a':0},'obstacles':[],'objects':[],'targets':[],'observer':None}
CONFIG=server.hardware({})

def worker(rom=RETURN_ROM,**overrides):
    job={'map':WORLD,'config':CONFIG,'sortie':1,'speed':100,'max_seconds':5,'rom':rom,'found':[]}
    job.update(overrides)
    p=subprocess.run([server.NODE,server.node_path(server.ROOT/'sortie.mjs')],input=json.dumps(job),capture_output=True,text=True,timeout=20)
    assert p.returncode==0,p.stderr
    return [json.loads(line) for line in p.stdout.splitlines()]

class DockTests(unittest.TestCase):
    def test_physical_return_uploads_sensor_only_data(self):
        messages=worker();end=messages[-1]
        self.assertEqual(end['result'],'docked');upload=end['upload'];self.assertGreater(len(upload['samples']),5)
        serialized=json.dumps(upload)
        for secret in ('"robot"','"obstacles"','"objects"','"targets"','"path"','"start"','"seed"'):
            self.assertNotIn(secret,serialized)
        self.assertEqual(set(upload['samples'][0]),{'t','readings','commands'})
        self.assertEqual(upload['samples'][-1]['readings']['dock'],1)
    def test_safety_violation_withholds_log(self):
        end=worker('move 1\nyield\njmp 0',max_seconds=60)[-1]
        self.assertEqual(end['result'],'safety_violation')
        self.assertAlmostEqual(end['state']['t'],30)
        self.assertIsNone(end['upload'])
    def test_shared_deadline_stops_worker_and_withholds_log(self):
        end=worker('move 1\nyield\njmp 0',max_seconds=2.3,mission_remaining=2.3,mission_elapsed=297.7)[-1]
        self.assertEqual(end['result'],'mission_timeout');self.assertIsNone(end['upload']);self.assertAlmostEqual(end['state']['t'],2.3);self.assertEqual(end['state']['readings']['mission_left'],0)
    def test_mission_budget_spans_sorties_and_resume(self):
        calls=[]
        def planner(h,turn,review_only=False):
            if not review_only:calls.append(json.loads((h.agent/'inbox.json').read_text())['mission_seconds_remaining'])
            return {'action':'deploy','max_seconds':5,'summary':'Test deadline'},RETURN_ROM
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            with patch.object(server,'WORKSPACES',root/'agents'),patch.object(server,'RUNTIME',root/'runtime'),patch.object(server.Harness,'plan',planner):
                h=server.Harness();h.start({'map':WORLD,'config':CONFIG,'rounds':1,'speed':100,'mission_seconds':5});h.thread.join(20)
                used=h.state['mission_seconds_used'];self.assertGreater(used,0);self.assertLess(used,5)
                h.resume({'rounds':10,'speed':100});h.thread.join(20)
                self.assertEqual(h.state['phase'],'time_limit');self.assertEqual(h.state['mission_seconds_used'],5)
                self.assertEqual(calls[0],5);self.assertAlmostEqual(calls[1],5-used);self.assertEqual(json.loads((h.agent/'hardware.json').read_text())['mission_budget']['limit_seconds'],5);self.assertTrue(all(a>b for a,b in zip(calls,calls[1:])))
                self.assertEqual(len(list((h.agent/'observations').glob('*.json'))),2)
                last=json.loads(sorted(h.run.glob('deployment-*.json'))[-1].read_text());self.assertLess(last['max_seconds'],5)
                with self.assertRaises(ValueError):h.resume({'rounds':1})
    def test_until_complete_ignores_round_cap_and_discloses_count_only(self):
        calls=[]
        def planner(h,turn,review_only=False):
            calls.append((turn,review_only));contract=json.loads((h.agent/'hardware.json').read_text())
            self.assertEqual(contract['objective_count'],1);self.assertTrue(contract['run_until_complete']);self.assertNotIn('targets',contract);self.assertIsNone(contract['mission_budget']['limit_seconds'])
            return {'action':'deploy','max_seconds':5,'summary':'Continue'},RETURN_ROM
        def sortie(h,world,c,number,speed,mission,rom,found):
            result=[0] if number==4 else [];h.state['frame']={'found':result,'readings':{'dock':1}}
            return {'result':'docked','state':{'found':result},'upload':{'sortie':number,'samples':[],'logger':{'dropped_samples':0}}}
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            with patch.object(server,'WORKSPACES',root/'agents'),patch.object(server,'RUNTIME',root/'runtime'),patch.object(server.Harness,'plan',planner),patch.object(server.Harness,'sortie',sortie):
                h=server.Harness();h.start({'map':{**WORLD,'targets':[{'x':150,'y':50}]},'config':CONFIG,'rounds':1,'until_done':True,'speed':100});h.thread.join(12)
                self.assertEqual(h.state['phase'],'rescued');self.assertEqual(len(list((h.agent/'observations').glob('*.json'))),4);self.assertEqual(calls[-1],(5,True))
    def test_until_complete_worker_ignores_estimated_sortie_deadline(self):
        end=worker(RETURN_ROM,max_seconds=.5,until_done=True)[-1];self.assertEqual(end['result'],'docked');self.assertGreater(end['state']['t'],.5);self.assertIn('safety_checks',end['upload']);self.assertEqual(end['upload']['logger']['reserved_safety_bytes'],2048)
    def test_shelter_checkpoint_evidence_survives_bounded_log(self):
        world={**WORLD,'objects':[{'id':'roof','type':'shade','x':32,'y':38,'w':28,'h':25}],'obstacles':[]}
        rom='loop:\nsense r0 time\nlt r0 2\njnz r0 go\nsense r0 time\nlt r0 31\njnz r0 hold\nmove -1\nyield\njmp loop\ngo:\nmove 1\nyield\njmp loop\nhold:\nmove 0\nyield\njmp loop'
        end=worker(rom,map=world,until_done=True,max_seconds=5,config={**CONFIG,'lightNoise':0})[-1];self.assertEqual(end['result'],'docked');log=end['upload'];self.assertTrue(log['safety_checks'][0]['safe']);self.assertEqual(log['safety_checks'][0]['dock'],0);self.assertGreaterEqual(log['safety_checks'][0]['dwell'],2);self.assertLessEqual(log['logger']['used_bytes'],65536)
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'observations').mkdir();(root/'observations/sortie-001.json').write_text(json.dumps(log));check=log['safety_checks'][0]
            belief={'shelters':[{'x':check['odom_x'],'y':check['odom_y'],'shelter_status':'verified','evidence':['observations/sortie-001.json safety_checks t=30']}]};server.verify_shelter_evidence(belief,root)
            belief['shelters'][0]['x']=500
            with self.assertRaises(ValueError):server.verify_shelter_evidence(belief,root)
    def test_no_departure_no_upload(self):
        end=worker('yield\njmp 0')[-1];self.assertEqual(end['result'],'never_departed');self.assertIsNone(end['upload'])
    def test_stranded_no_upload(self):
        end=worker('move 1\nyield\njmp 0')[-1];self.assertEqual(end['result'],'stranded');self.assertIsNone(end['upload'])
    def test_flash_ring_is_bounded(self):
        rom='''loop:
sense r0 time
lt r0 120
jnz r0 hold
move -1
yield
jmp loop
hold:
sense r0 time
lt r0 1.3
jnz r0 go
move 0
yield
jmp loop
go:
move 1
yield
jmp loop
'''
        end=worker(rom,max_seconds=125,config={**CONFIG,"lightLevel":.1,"lightNoise":0})[-1];self.assertEqual(end['result'],'docked');log=end['upload'];self.assertLessEqual(log['logger']['used_bytes'],65536);self.assertGreater(log['logger']['dropped_samples'],0)
    def test_two_sortie_loop_delivers_before_next_planner(self):
        calls=[]
        def planner(h,turn,review_only=False):
            inbox=json.loads((h.agent/'inbox.json').read_text());calls.append({**inbox,'review_only':review_only})
            if turn==2:
                observation=json.loads((h.agent/inbox['latest_observation']).read_text());self.assertEqual(observation['samples'][-1]['readings']['dock'],1)
            h.state['turns'].append({'turn':turn,'action':'deploy','summary':'Test return'})
            return {'action':'deploy','max_seconds':5,'summary':'Test return'},RETURN_ROM
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            with patch.object(server,'WORKSPACES',root/'agents'),patch.object(server,'RUNTIME',root/'runtime'),patch.object(server.Harness,'plan',planner):
                h=server.Harness();h.start({'map':WORLD,'config':CONFIG,'rounds':2,'speed':100});h.thread.join(20)
                self.assertFalse(h.thread.is_alive());self.assertEqual(h.state['phase'],'limit');self.assertEqual(calls[0]['kind'],'initial');self.assertEqual(calls[0]['observation_files'],[]);self.assertEqual(calls[1]['kind'],'dock_return');self.assertEqual(len(list((h.agent/'observations').glob('*.json'))),2)
                h.resume({'rounds':1,'speed':100});h.thread.join(20);self.assertEqual(h.state['phase'],'limit');self.assertEqual(len(calls),5);self.assertTrue(calls[-1]['review_only']);self.assertEqual(len(list((h.agent/'observations').glob('*.json'))),3)
                h.state['phase']='stranded'
                with self.assertRaises(ValueError):h.resume({'rounds':1,'speed':100})
    def test_derived_analysis_tools_use_only_delivered_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'observations').mkdir();(root/'hardware.json').write_text(json.dumps(server.public_hardware(CONFIG)))
            (root/'observations/test.json').write_text(json.dumps({'samples':[{'t':0,'readings':{'odom_x':0,'odom_y':0,'yaw':0,'front':20,'left':80,'right':80,'target':0}}]}))
            projected=dock_data.project_ranges(root,cell_cm=5);self.assertIn({'x':20.0,'y':0.0,'hits':1},projected['occupied']);self.assertEqual(projected['sample_count'],1)
            with self.assertRaises(ValueError):dock_data.project_ranges(root,['../server.py'])
        self.assertEqual(dock_data.calculate('2+3*cos(0)'),5)
        self.assertEqual(dock_data.calculate('atan2(1,0)'),90)
        with self.assertRaises(ValueError):dock_data.calculate('__import__("os").listdir()')
        with self.assertRaises(ValueError):dock_data.calculate('10**100000000')

    def test_live_analysis_file_request_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            with patch.object(server,'WORKSPACES',root/'agents'),patch.object(server,'RUNTIME',root/'runtime'):
                h=server.Harness()
                class Process:
                    def poll(self):return None
                thread=threading.Thread(target=h.analysis_loop,args=(Process(),root,1));thread.start()
                try:
                    time.sleep(.1);(root/'analysis-request.json').write_text(json.dumps({'id':'test-calc','operation':'calculate','expression':'12*sin(90)'}))
                    deadline=time.time()+3
                    while not (root/'analysis-result.json').exists() and time.time()<deadline:time.sleep(.02)
                    result=json.loads((root/'analysis-result.json').read_text());self.assertEqual(result['id'],'test-calc');self.assertEqual(result['result']['value'],12)
                finally:h.cancel.set();thread.join(2)

    def test_debrief_schema_and_observation_link(self):
        valid={'observed_sortie':1,'learned':['A marker was confirmed'],'uncertainties':['Unknown remaining area'],'next_plan':'Explore east and return','rom_changes':[{'change':'Add a waypoint','why':'New free range rays'}],'evidence':['observations/sortie-001.json']}
        server.validate_debrief(valid,1)
        with self.assertRaises(ValueError):server.validate_debrief(valid,2)
        with self.assertRaises(ValueError):server.validate_debrief({**valid,'rom_changes':['missing reason']},1)
    def test_review_only_does_not_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            with patch.object(server,'WORKSPACES',root/'agents'),patch.object(server,'RUNTIME',root/'runtime'):
                h=server.Harness();h.agent=root/'agent';(h.agent/'observations').mkdir(parents=True);(h.agent/'observations/sortie-001.json').write_text('{}');h.run=root/'run';h.run.mkdir();(h.run/'return-001.json').write_text('{}');h.state['frame']={'readings':{'dock':1}}
                calls=[]
                def plan(turn,review_only=False):calls.append((turn,review_only));return {'action':'deploy','summary':'Prepare only'},RETURN_ROM
                with patch.object(h,'plan',plan),patch.object(h,'sortie',side_effect=AssertionError('Review must not deploy')):
                    h.review();h.thread.join(5)
                self.assertEqual(calls,[(2,True)]);self.assertFalse(h.state['active']);self.assertEqual(h.state['phase'],'limit');self.assertEqual(list(h.run.glob('deployment-*.json')),[])
    def test_single_panning_channel_uses_ping_pose_not_current_pose(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'observations').mkdir();(root/'hardware.json').write_text(json.dumps(server.public_hardware(CONFIG)))
            reading={'odom_x':100,'odom_y':100,'yaw':-90,'range':20,'range_valid':1,'range_seq':1,'range_x':5,'range_y':7,'range_yaw':0,'range_angle':90,'light':.12,'target':0}
            rows=[{'t':0,'readings':reading},{'t':.1,'readings':{**reading,'odom_x':200}},{'t':.2,'readings':{**reading,'range_seq':2,'range_valid':0,'range':-1}}]
            (root/'observations/test.json').write_text(json.dumps({'samples':rows}));result=dock_data.project_ranges(root,cell_cm=5)
            self.assertEqual(result['occupied'],[{'x':5.0,'y':25.0,'hits':1}]);self.assertTrue(result['light_samples']);self.assertEqual(result['light_samples'][0]['light'],.12)
    def test_ble_projection_uses_received_pose_and_unique_packets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'observations').mkdir();(root/'hardware.json').write_text(json.dumps(server.public_hardware(CONFIG)))
            r={'range':-1,'range_valid':0,'range_seq':1,'odom_x':999,'odom_y':888,'yaw':90,'ble_valid':1,'ble_seq':4,'ble_id':2,'ble_rssi':-62,'ble_channel':38,'ble_x':12,'ble_y':7,'ble_yaw':0,'ble_time':1.2,'ble_confirmed':0}
            rows=[{'t':1.2,'readings':r},{'t':1.4,'readings':{**r,'odom_x':200}},{'t':3,'readings':{**r,'ble_valid':0}}]
            (root/'observations/radio.json').write_text(json.dumps({'samples':rows}))
            packets=dock_data.project_ranges(root)['ble_samples'];self.assertEqual(len(packets),1);self.assertEqual(packets[0]['antenna_x'],12);self.assertEqual(packets[0]['rssi_dbm'],-62)
            for key in ('distance','target_x','target_y','bearing','world'):self.assertNotIn(key,packets[0])
    def test_ble_defaults_replace_legacy_detector(self):
        cfg=server.hardware({'virtualRescue':True});self.assertTrue(cfg['ble']);self.assertFalse(cfg['virtualRescue'])
        self.assertEqual(server.public_hardware(cfg)['ble']['contact_reference_dbm'],-35)
        for key,value in [('bleDrop',2),('bleNoise',-1),('bleContact',0)]:
            with self.assertRaises(ValueError):server.hardware({key:value})
    def test_photo_contract_has_no_fixed_range_or_camera_defaults(self):
        contract=server.public_hardware(CONFIG);self.assertEqual(contract['range_sensor_mount']['channels'],1);self.assertFalse(contract['camera']);self.assertFalse(contract['bumper_sensor']);self.assertFalse(contract['virtual_rescue_detector']);self.assertIn('provisional',contract['calibration_status'])
        with self.assertRaises(ValueError):server.node_validate('sense r0 front',64)
        self.assertTrue(server.node_validate('sense r0 front',64,profile=server.LEGACY_PROFILE)['ok'])
        with self.assertRaises(ValueError):server.hardware({'range':5,'rangeMin':5})
    def test_invalid_start_and_config(self):
        with self.assertRaises(ValueError):server.validate_map({**WORLD,'start':{'x':1000,'y':50,'a':0}})
        with self.assertRaises(ValueError):server.hardware({'speed':float('inf')})
    def test_new_math_and_odometry_contract(self):
        self.assertTrue(server.node_validate('set r0 90\nsin r0\nset r1 2\natan2 r0 r1\nwrap r0\nyield',64)['ok'])
        with self.assertRaises(ValueError):server.node_validate('sense r0 world_map',64)

if __name__=='__main__':unittest.main()
