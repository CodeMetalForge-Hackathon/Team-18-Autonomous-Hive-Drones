import json,pathlib,tempfile,unittest
import replay,server
from test_harness import worker,RETURN_ROM,WORLD,CONFIG
class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.temp.name);self.folder=self.root/'test-run';self.folder.mkdir()
        for n,rom in [(1,RETURN_ROM),(2,'; changed second sortie\n'+RETURN_ROM)]:
            job={'map':WORLD,'config':CONFIG,'sortie':n,'speed':100,'max_seconds':5,'rom':rom,'found':[]};end=worker(rom,sortie=n)[-1]
            (self.folder/f'deployment-{n:03d}.json').write_text(json.dumps(job));(self.folder/f'return-{n:03d}.json').write_text(json.dumps(end));turn=self.folder/f'turn-{n:03d}';turn.mkdir();(turn/'controller.rom').write_text(rom);(turn/'mission.json').write_text(json.dumps({'action':'deploy','summary':'Probe first' if n==1 else 'Investigate opening next'}));(turn/'map.json').write_text(json.dumps({'occupied':[] if n==1 else [{'x':20,'y':0}],'free':[],'landmarks':[],'notes':'Unknown' if n==1 else 'A measured obstruction ahead'}));(turn/'notes.md').write_text('Archived agent findings')
    def tearDown(self):self.temp.cleanup()
    def get(self,n):return replay.get_replay(self.root,'test-run',n,server.NODE,server.ROOT/'sortie.mjs',server.node_path(server.ROOT/'sortie.mjs'))
    def test_recorded_playback_and_post_return_summary(self):
        result=self.get(1);self.assertEqual(result['source'],'recorded');self.assertGreater(len(result['frames']),10);r=result['report'];self.assertTrue(r['analysis_ready']);self.assertEqual(r['next_plan'],'Investigate opening next');self.assertEqual(r['before_counts']['occupied'],0);self.assertEqual(r['after_counts']['occupied'],1);self.assertEqual(r['notes_after'],'Archived agent findings');self.assertEqual(r['knowledge'],'A measured obstruction ahead')
    def test_rom_diff_and_pending_analysis(self):
        r=self.get(2)['report'];self.assertIn('+; changed second sortie',r['rom_diff']);self.assertEqual(r['added_lines'],1);self.assertFalse(r['analysis_ready']);self.assertIsNone(r['next_plan']);self.assertTrue(self.get(1)['report']['first_rom'])
    def test_legacy_verified_reconstruction(self):
        p=self.folder/'return-001.json';saved=json.loads(p.read_text());saved.pop('replay_frames');p.write_text(json.dumps(saved));result=self.get(1);self.assertEqual(result['source'],'verified reconstruction');self.assertAlmostEqual(result['frames'][-1]['robot']['x'],saved['state']['robot']['x']);self.assertEqual(len(result['frames']),round(saved['state']['t']/.1)+1)
    def test_mismatched_reconstruction_is_withheld(self):
        p=self.folder/'return-001.json';saved=json.loads(p.read_text());saved.pop('replay_frames');saved['state']['robot']['x']+=1;p.write_text(json.dumps(saved))
        with self.assertRaises(ValueError):self.get(1)
    def test_dock_timeline_has_public_map_and_rom_updates_only(self):
        events=[{'turn':2,'at':1,'kind':'assistant_stream','text':'Found '},{'turn':2,'at':2,'kind':'assistant_stream','text':'an opening.'},{'turn':2,'at':3,'kind':'thinking','text':'PRIVATE_NOT_FOR_REPLAY'},{'turn':2,'at':4,'kind':'tool','text':'Write '+json.dumps({'file_path':'/agent/map.json','content':json.dumps({'occupied':[{'x':15,'y':0}],'notes':'New range evidence'})})},{'turn':2,'at':5,'kind':'tool','text':'Write '+json.dumps({'file_path':'/agent/controller.rom','content':'; updated return\n'+RETURN_ROM})}]
        (self.folder/'events.jsonl').write_text('\n'.join(json.dumps(e) for e in events));result=replay.dock_timeline(self.folder,1);self.assertEqual(result['steps'][0]['text'],'Found an opening.');self.assertNotIn('PRIVATE_NOT_FOR_REPLAY',json.dumps(result));self.assertTrue(any(step.get('map',{}).get('notes')=='New range evidence' for step in result['steps']));self.assertTrue(any('+; updated return' in step.get('rom_diff','') for step in result['steps']))
    def test_workspace_snapshots_replay_in_publication_order(self):
        snapshots=[{'at':2,'file':'map.json','content':{'notes':'First estimate','occupied':[]}},{'at':3,'file':'map.json','content':{'notes':'Refined estimate','occupied':[{'x':20,'y':0}]}},{'at':4,'file':'debrief.json','content':{'learned':['Measured wall'],'next_plan':'Explore opening'}}]
        (self.folder/'updates-002.jsonl').write_text('\n'.join(json.dumps(e) for e in snapshots));steps=replay.dock_timeline(self.folder,1)['steps'];self.assertEqual([s['map']['notes'] for s in steps if s.get('map')][:2],['First estimate','Refined estimate']);self.assertTrue(any('debrief' in s for s in steps))
    def test_history_readonly_and_invalid_paths(self):
        files=sorted(str(p) for p in self.folder.rglob('*'));h=replay.history(self.root,'test-run');self.assertEqual(len(h['runs'][0]['sorties']),2);self.get(1);self.assertEqual(files,sorted(str(p) for p in self.folder.rglob('*')))
        with self.assertRaises(ValueError):replay.run_folder(self.root,'../outside')
if __name__=='__main__':unittest.main()
