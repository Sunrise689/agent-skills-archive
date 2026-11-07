import json, subprocess, sys, unittest
from pathlib import Path
ROOT=Path(__file__).parents[1]
class TestProtocol(unittest.TestCase):
    def test_initialize_and_tools(self):
        lines='\n'.join([json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{}}),json.dumps({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})])+'\n'
        cp=subprocess.run([sys.executable,str(ROOT/'mcp_entry.py')],input=lines,text=True,capture_output=True,encoding='utf-8',cwd=ROOT,timeout=30)
        self.assertEqual(cp.returncode,0,cp.stderr); rows=[json.loads(x) for x in cp.stdout.splitlines() if x.strip()]; self.assertEqual(rows[0]['result']['serverInfo']['name'],'super-composer'); tools={x['name']:x for x in rows[1]['result']['tools']}; self.assertEqual(set(tools),{'create_project','save_draft','launch_role_cards','run_decision_audit','get_status','collect_results','finalize'}); self.assertIn('lanes',tools['launch_role_cards']['inputSchema']['properties'])
if __name__=='__main__': unittest.main()
