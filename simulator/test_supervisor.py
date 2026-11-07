import copy,json,pathlib,tempfile,unittest
from unittest.mock import patch
import server,supervisor
from test_harness import WORLD,CONFIG,RETURN_ROM

BRIEF={'observed_sortie':1,'reports':[{'kind':'learned','text':'The old passage is blocked.','confidence':'revised'},{'kind':'plan','text':'Check the alternate opening and return.','confidence':'uncertain'},{'kind':'rom','text':'Add clearance checks before each forward move.','confidence':'observed'}]}
class SupervisorTests(unittest.TestCase):
    def test_caption_limits_and_three_distinct_categories(self):
        supervisor.validate_brief(BRIEF,1)
        for bad in [{**BRIEF,'reports':[BRIEF['reports'][0]]*3},{**BRIEF,'reports':[{**BRIEF['reports'][0],'text':'x'*73},*BRIEF['reports'][1:]]},{**BRIEF,'reports':[{**BRIEF['reports'][0],'text':'a '*13},*BRIEF['reports'][1:]]}]:
            with self.assertRaises(ValueError):supervisor.validate_brief(bad,1)
    def test_map_confidence_age_and_revision_validation(self):
        m={'frame':'dock-relative-cm','revision':2,'occupied':[{'x':10,'y':5,'confidence':.5,'last_seen_sortie':1,'status':'uncertain'}],'free':[],'landmarks':[]}
        supervisor.validate_belief(m,1,{'revision':1})
        with self.assertRaises(ValueError):supervisor.validate_belief({**m,'revision':1},1,{'revision':1})
        bad=copy.deepcopy(m);bad['occupied'][0]['last_seen_sortie']=2
        with self.assertRaises(ValueError):supervisor.validate_belief(bad,1)
        bad=copy.deepcopy(m);del bad['occupied'][0]['confidence']
        with self.assertRaises(ValueError):supervisor.validate_belief(bad,1)
    def test_projection_contains_beliefs_not_true_world_or_pose(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);(root/'observations').mkdir();(root/'map.json').write_text(json.dumps({'occupied':[{'x':12,'y':4,'confidence':.5,'last_seen_sortie':1}],'free':[],'landmarks':[],'revision':2}));(root/'supervisor.json').write_text(json.dumps(BRIEF));(root/'inbox.json').write_text(json.dumps({'latest_observation':'observations/sortie-001.json'}));(root/'observations/sortie-001.json').write_text(json.dumps({'samples':[{'readings':{'odom_x':5,'odom_y':1,'yaw':2}}]}))
            class H:
                agent=root
                def snapshot(self):return {'run_id':'test','phase':'planning','active':True,'sortie':2,'world':{'SECRET_TRUE_MAP':99999},'frame':{'robot':{'x':98765,'y':87654}},'config':{'sensorModel':server.PROFILE}}
            data=supervisor.projection(H());self.assertNotIn('world',data);self.assertNotIn('frame',data);self.assertNotIn('SECRET_TRUE_MAP',json.dumps(data));self.assertNotIn('98765',json.dumps(data));self.assertEqual(data['last_returned_estimate']['x'],5);self.assertEqual(data['reports'],BRIEF['reports']);self.assertEqual(data['report_source'],'opus')
    def test_revision_tracks_agent_map_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);p=root/'map.json';p.write_text(json.dumps({'occupied':[{'x':10,'y':0}]}))
            class H:
                agent=root
                def snapshot(self):return {'phase':'idle','active':False}
            first=supervisor.projection(H())['map_revision'];p.write_text(json.dumps({'occupied':[],'changes':[{'type':'removed','x':10,'y':0}]}));second=supervisor.projection(H())['map_revision'];self.assertNotEqual(first,second)
    def test_environment_changes_do_not_notify_agent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            with patch.object(server,'WORKSPACES',root/'agents'),patch.object(server,'RUNTIME',root/'runtime'):
                h=server.Harness();h.agent=root/'agent';h.agent.mkdir();(h.agent/'inbox.json').write_text('{"kind":"dock_return"}');(h.agent/'map.json').write_text('{"occupied":[]}');h.run=root/'run';h.run.mkdir();h.state.update(run_id='test',phase='planning',active=True,config=CONFIG,world=copy.deepcopy(WORLD),frame={'readings':{'dock':1}})
                before={p.name:p.read_bytes() for p in h.agent.iterdir()};new=copy.deepcopy(WORLD);new['obstacles']=[{'x':80,'y':40,'w':10,'h':10}];h.update_environment({'map':new});self.assertEqual(h.state['world']['obstacles'],new['obstacles']);self.assertEqual(before,{p.name:p.read_bytes() for p in h.agent.iterdir()});h.state['phase']='deployed'
                with self.assertRaises(ValueError):h.update_environment({'map':WORLD})
    def test_next_deployment_uses_changed_world(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);worlds=[]
            def planner(h,turn,review_only=False):
                if turn==2:
                    new=copy.deepcopy(WORLD);new['obstacles']=[{'x':80,'y':40,'w':10,'h':10}];h.update_environment({'map':new})
                return {'action':'deploy','max_seconds':5,'summary':'Test'},RETURN_ROM
            def sortie(h,world,c,number,speed,mission,rom,found):
                worlds.append(copy.deepcopy(world));h.state['frame']={'readings':{'dock':1}}
                return {'result':'docked','state':{'found':[]},'upload':{'sortie':number,'samples':[],'logger':{'dropped_samples':0}}}
            with patch.object(server,'WORKSPACES',root/'agents'),patch.object(server,'RUNTIME',root/'runtime'),patch.object(server.Harness,'plan',planner),patch.object(server.Harness,'sortie',sortie):
                h=server.Harness();h.start({'map':WORLD,'config':CONFIG,'rounds':2,'speed':100});h.thread.join(10);self.assertEqual(h.state['phase'],'limit');self.assertEqual(worlds[0]['obstacles'],[]);self.assertEqual(len(worlds[1]['obstacles']),1)
if __name__=='__main__':unittest.main()
