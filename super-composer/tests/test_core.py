import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parents[1]))
from decision import sentences, pair_candidates, jobs_for
import core
from core import SuperComposer

def _offline(sc):
    def dispatch(root, item, scope):
        card_dir=root/'cards'/item['card_id']; card_dir.mkdir(parents=True,exist_ok=True)
        args={'card_id':item['card_id'],'profile_id':item['profile_id'],'model':item['model'],'taskbook_path':item['taskbook'],'write_scope':scope}
        if item['effort']: args['effort']=item['effort']
        (card_dir/'launch.json').write_text(json.dumps(args,ensure_ascii=False),encoding='utf-8')
        (card_dir/'launch.log').write_text('exit=1\nmissing profile',encoding='utf-8')
        item['status']='launch_failed'; item['error']='missing profile'
    sc._dispatch=dispatch
    return sc

class TestDecision(unittest.TestCase):
    def setUp(self):
        self.text='# 标题\n\n第一句话足够长，可以被拆出来。第二句话也足够长，可以参与窗口。第三句话继续推进内容。\n\n第四段有数字2026和一个明确的因果关系，因此需要事实候选。'
    def test_sentence_split(self):
        self.assertEqual(len(sentences(self.text)),4)
    def test_three_window(self):
        jobs,shape=jobs_for(Path(self._write()),False)
        self.assertEqual(shape['sentences'],4)
        self.assertEqual(sum(1 for j in jobs if j['meta']['kind']=='window3'),2)
    def test_pair_budget(self):
        ss=[f'第{i}句有独特内容。' for i in range(60)]
        pairs=pair_candidates(ss,False)
        self.assertLess(len(pairs),500)
        self.assertEqual(len(pair_candidates(ss,True)),1770)
    def _write(self):
        p=Path(tempfile.mktemp(suffix='.md')); p.write_text(self.text,encoding='utf-8'); self.addCleanup(lambda: p.unlink(missing_ok=True)); return p

class TestProject(unittest.TestCase):
    def test_project_and_revision(self):
        with tempfile.TemporaryDirectory() as d:
            sc=SuperComposer(); sc.create_project(d,{'genre':'test'}); out=sc.save_draft(d,'一句测试稿。','draft'); self.assertEqual(out['revision'],1); self.assertEqual(sc.get_status(d)['stage'],'drafted')

    def test_launch_failure_is_visible(self):
        with tempfile.TemporaryDirectory() as d:
            sc=_offline(SuperComposer()); sc.create_project(d,{'genre':'test'}); sc.save_draft(d,'一句足够长的测试稿，用来发卡。','draft')
            out=sc.launch_role_cards(d,'A',responsibility='只看事实',policy={'profile_id':'__missing_profile__','model':'none'})
            self.assertEqual(out['cards'][0]['status'],'launch_failed')
            self.assertTrue(out['cards'][0]['error'])
            card=Path(d)/'cards'/out['cards'][0]['card_id']
            self.assertTrue((card/'launch.json').exists())
            self.assertIn('exit=', (card/'launch.log').read_text(encoding='utf-8'))
            self.assertEqual(sc.get_status(d)['cards'][0]['status'],'launch_failed')

    def test_lanes_keep_their_own_profile(self):
        with tempfile.TemporaryDirectory() as d:
            sc=_offline(SuperComposer()); sc.create_project(d,{'genre':'test'}); sc.save_draft(d,'一句足够长的测试稿，用来发卡。','draft')
            lanes=[{'name':'minimax','profile_id':'CC-U','model':'__missing_minimax_model__','count':8},{'name':'openrouter','profile_id':'CC-U','model':'openrouter/__missing_model__','count':2}]
            out=sc.launch_role_cards(d,'A',responsibility='只看事实',policy={'lanes':{'minimax':{'profile_id':'CC-U','model':'MiniMax-M3.1-Flash','min':1,'max':10},'openrouter':{'profile_id':'CC-U','model':'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free','min':1,'max':20}}},lanes=lanes)
            self.assertEqual([x['launched']+x['failed'] for x in out['lanes']],[8,2])
            for card in out['cards']:
                self.assertEqual(card['status'],'launch_failed')
                args=json.loads((Path(d)/'cards'/card['card_id']/'launch.json').read_text(encoding='utf-8'))
                self.assertEqual(args['profile_id'],card['profile_id'])
                self.assertEqual(args['model'],card['model'])

    def test_rejected_lanes_write_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            sc=SuperComposer(); sc.create_project(d,{'genre':'test'}); sc.save_draft(d,'一句足够长的测试稿，用来发卡。','draft')
            base={'lanes':{'minimax':{'profile_id':'CC-U','model':'MiniMax-M3.1-Flash','min':8,'max':10},'openrouter':{'profile_id':'CC-U','model':'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free','min':1,'max':20}}}
            for lanes in ([{'name':'minimax','profile_id':'CX-U-OFFICIAL','count':8}],[{'name':'minimax','count':11}],[{'name':'openrouter','count':21}]):
                with self.assertRaises(ValueError): sc.launch_role_cards(d,'A',policy=base,lanes=lanes)
            self.assertEqual(list((Path(d)/'taskbooks').iterdir()),[])
            import gc; gc.collect()

    def test_without_lanes_policy_still_launches(self):
        with tempfile.TemporaryDirectory() as d:
            sc=_offline(SuperComposer()); sc.create_project(d,{'genre':'test'}); sc.save_draft(d,'一句足够长的测试稿，用来发卡。','draft')
            out=sc.launch_role_cards(d,'A',responsibility='只看事实',policy={'profile_id':'__missing_profile__','model':'gpt-6-luna','effort':'high'})
            self.assertEqual(out['cards'][0]['status'],'launch_failed')
            self.assertEqual(out['lanes'][0]['name'],'default')
            self.assertTrue(out['cards'][0]['error'])

    def test_hits_block_unconfirmed_finalize(self):
        with tempfile.TemporaryDirectory() as d:
            sc=SuperComposer(); sc.create_project(d,{'genre':'test'}); saved=sc.save_draft(d,'二〇一九年，这件事被正式确认。','draft')
            audit=Path(d)/'audit'/'manual'; audit.mkdir(parents=True)
            hit={'kind':'fact_risk','i':0,'sentence':'二〇一九年，这件事被正式确认。'}
            (audit/'decision-results.json').write_text(json.dumps({'hits':[hit,hit]}),encoding='utf-8')
            root,db=sc._db(d); added=sc._record_hits(db,saved['revision'],audit/'decision-results.json'); db.commit(); db.close()
            self.assertEqual(added,1)
            self.assertEqual(sc.get_status(d)['open_issues'],1)
            with self.assertRaises(ValueError): sc.finalize(d,saved['revision'],confirm=False)
            done=sc.finalize(d,saved['revision'],confirm=True)
            self.assertEqual(done['open_issues'],1)
            self.assertEqual(Path(done['final']).read_text(encoding='utf-8'),'二〇一九年，这件事被正式确认。')

if __name__=='__main__': unittest.main()
