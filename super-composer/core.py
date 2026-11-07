from __future__ import annotations
import hashlib, json, os, re, sqlite3, subprocess, sys, time, uuid
from pathlib import Path
from decision import run_decision_job

CARD_LAUNCHER = Path(os.environ.get("AGENT_LAUNCHER_ROOT", str(Path.home() / ".agent-launcher")))
MCP_CALL = CARD_LAUNCHER/'tools'/'mcp_call.py'
POLICY_PATH = Path(__file__).resolve().parent/'policy.json'
PROMPTS = Path(__file__).resolve().parent/'prompts'
ROLE_PROMPT = {'C':'composer.md','A':'auditor.md','P':'polish.md'}
PINNED_FREE_MODEL = 'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free'
ALLOWED_PROFILES = {'CC-U','CC-U-OR-free','CC-U-OR-free-nemotron'}
PINNED_PROFILES = {'CC-U-OR-free','CC-U-OR-free-nemotron'}
FALLBACK_LANES = {
    'minimax': {'profile_id':'CC-U','model':'MiniMax-M3.1-Flash','min':8,'max':10},
    'openrouter': {'profile_id':'CC-U','model':PINNED_FREE_MODEL,'min':1,'max':20},
}

class SuperComposer:
    def _paths(self, project_dir):
        root=Path(project_dir).resolve(); root.mkdir(parents=True,exist_ok=True)
        (root/'versions').mkdir(exist_ok=True); (root/'taskbooks').mkdir(exist_ok=True); (root/'cards').mkdir(exist_ok=True); (root/'audit').mkdir(exist_ok=True)
        return root, root/'composer.sqlite'
    def _db(self, project_dir):
        root, dbp=self._paths(project_dir); db=sqlite3.connect(dbp,timeout=30); db.row_factory=sqlite3.Row
        db.executescript('''CREATE TABLE IF NOT EXISTS project (id INTEGER PRIMARY KEY CHECK(id=1), style_json TEXT NOT NULL, materials_json TEXT NOT NULL, policy_json TEXT NOT NULL, stage TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS versions (revision INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, path TEXT NOT NULL, label TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS cards (card_id TEXT PRIMARY KEY, role TEXT NOT NULL, taskbook TEXT NOT NULL, status TEXT NOT NULL, result_path TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, kind TEXT NOT NULL, revision INTEGER, status TEXT NOT NULL, result_path TEXT, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS issues (id INTEGER PRIMARY KEY AUTOINCREMENT, revision INTEGER, kind TEXT, location TEXT, text TEXT, status TEXT NOT NULL DEFAULT "open");'''); return root,db
    def _policy(self, override=None):
        base={'lanes':{name:dict(spec) for name,spec in FALLBACK_LANES.items()}}
        if POLICY_PATH.exists():
            file_policy=json.loads(POLICY_PATH.read_text(encoding='utf-8'))
            if 'profile_id' in file_policy:
                base['profile_id']=file_policy['profile_id']; base['model']=file_policy.get('model'); base['effort']=file_policy.get('effort')
            else:
                base.update(file_policy)
        if override: base.update(override)
        return base
    def _lane_specs(self, lanes, policy):
        if not lanes:
            raise ValueError('lanes is empty')
        table=policy.get('lanes') or {}
        specs=[]
        for lane in lanes:
            name=str(lane.get('name') or '')
            spec=table.get(name)
            if not spec: raise ValueError(f'unknown lane {name}')
            profile=lane.get('profile_id') or spec['profile_id']
            model=lane.get('model') or spec['model']
            if profile not in ALLOWED_PROFILES:
                raise ValueError(f'{profile} is not an allowed lane profile')
            if name=='minimax' and model!='MiniMax-M3.1-Flash' and lane.get('model') is None:
                raise ValueError('minimax lane only accepts MiniMax-M3.1-Flash')
            if name=='openrouter' and not str(model).startswith('openrouter/'):
                raise ValueError('openrouter lane only accepts an openrouter/ model')
            if profile in PINNED_PROFILES and model!=PINNED_FREE_MODEL:
                raise ValueError(f'{profile} only accepts its pinned free model')
            count=int(lane.get('count') or 1)
            lo=int(spec.get('min') or 1); hi=int(spec.get('max') or count)
            if lane.get('count') is None and (count<lo or count>hi):
                raise ValueError(f'{name} count {count} is outside {lo}-{hi}')
            if count<1 or count>hi:
                raise ValueError(f'{name} count {count} is outside 1-{hi}')
            specs.append({'name':name,'profile_id':profile,'model':model,'effort':lane.get('effort'),'count':count})
        return specs
    def _project(self, db):
        row=db.execute('SELECT * FROM project WHERE id=1').fetchone()
        if not row: raise ValueError('project is not initialized')
        return row
    def create_project(self, project_dir, style_brief, materials=None, policy=None):
        root,db=self._db(project_dir); now=time.time(); materials=materials or []; policy=policy or {}
        db.execute('INSERT OR REPLACE INTO project VALUES(1,?,?,?,?,?,?)',(json.dumps(style_brief,ensure_ascii=False),json.dumps(materials,ensure_ascii=False),json.dumps(policy,ensure_ascii=False),'initialized',now,now)); db.commit(); db.close()
        return {'project_dir':str(root),'stage':'initialized','trigger':'super composer / 超级创作'}
    def save_draft(self, project_dir, text, label='draft'):
        root,db=self._db(project_dir); self._project(db); rev=(db.execute('SELECT COALESCE(MAX(revision),0)+1 FROM versions').fetchone()[0]); sha=hashlib.sha256(text.encode('utf-8')).hexdigest(); path=root/'versions'/f'{rev:03d}-{label}.md'; path.write_text(text,encoding='utf-8'); db.execute('INSERT INTO versions VALUES(?,?,?,?,?)',(rev,sha,str(path),label,time.time())); db.execute('UPDATE project SET stage="drafted",updated_at=? WHERE id=1',(time.time(),)); db.commit(); db.close(); return {'revision':rev,'sha256':sha,'path':str(path)}
    def launch_role_cards(self, project_dir, role, responsibility='', spans=None, count=None, policy=None, lanes=None):
        root,db=self._db(project_dir); self._project(db); latest=db.execute('SELECT * FROM versions ORDER BY revision DESC LIMIT 1').fetchone();
        if not latest: raise ValueError('save a draft before launching cards')
        if role not in ROLE_PROMPT: raise ValueError('role must be C, A or P')
        pol=self._policy(policy); spans=spans or ['whole draft']; cards=[]; lane_specs=[]
        if lanes:
            lane_specs=self._lane_specs(lanes, pol)
        else:
            lane_specs=[{'name':'default','profile_id':pol['profile_id'],'model':pol['model'],'effort':pol.get('effort'),'count':count or max(1,len(spans))}]
        prompt=(root/'versions'/Path(latest['path']).name).read_text(encoding='utf-8')
        role_file=PROMPTS/ROLE_PROMPT[role]
        role_prompt=role_file.read_text(encoding='utf-8').strip() if role_file.exists() else ''
        scope='workspace-write' if role=='P' else 'read-only'
        for spec in lane_specs:
            for i in range(spec['count']):
                cid=f'SC-{role}-{int(time.time())}-{len(cards)+1}'; tb=root/'taskbooks'/f'{cid}.md'
                duty=responsibility or spans[i%len(spans)]
                tb.write_text(f'# Super Composer {role} card\n\n## Responsibility\n{duty}\n\n只处理上面这一项职责，不改稿，不扩到别的职责。\n\n## Rules\n{role_prompt}\n\n## Input draft\n{prompt}\n\n## Deliverable\n把 Markdown 报告写到工作目录，文件名用 report.md。每条发现写 location、quoted text、issue、evidence、suggested direction。\n',encoding='utf-8')
                db.execute('INSERT OR REPLACE INTO cards VALUES(?,?,?,?,?,?)',(cid,role,str(tb),'created',None,time.time())); cards.append({'card_id':cid,'taskbook':str(tb),'lane':spec['name'],'profile_id':spec['profile_id'],'model':spec['model'],'effort':spec['effort']})
        db.execute('UPDATE project SET stage=?,updated_at=? WHERE id=1',({'A':'fact_structure_audit','P':'language_audit','C':'materials_ready'}[role],time.time())); db.commit()
        for item in cards:
            self._dispatch(root, item, scope)
            db.execute('UPDATE cards SET status=? WHERE card_id=?',(item['status'],item['card_id']))
        db.commit(); db.close()
        return self._summary(role, cards, lane_specs, scope)
    def _dispatch(self, root, item, scope):
        card_dir=root/'cards'/item['card_id']; card_dir.mkdir(parents=True,exist_ok=True)
        (card_dir/'work').mkdir(parents=True,exist_ok=True)
        args={'card_id':item['card_id'],'profile_id':item['profile_id'],'model':item['model'],'taskbook_path':item['taskbook'],'workdir':str(card_dir/'work'),'write_scope':scope}
        if item['effort']: args['effort']=item['effort']
        argfile=card_dir/'launch.json'; argfile.write_text(json.dumps(args,ensure_ascii=False,indent=2),encoding='utf-8')
        log=card_dir/'launch.log'
        try:
            cp=subprocess.run([sys.executable,str(MCP_CALL),'launch_card',str(argfile)],cwd=str(CARD_LAUNCHER),capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
            log.write_text(f'exit={cp.returncode}\n{cp.stdout}\n{cp.stderr}',encoding='utf-8')
            accepted='"ok": true' in cp.stdout or '"ok":true' in cp.stdout or '\\"ok\\":true' in cp.stdout or '\\"ok\\": true' in cp.stdout
            status='launched' if cp.returncode==0 and accepted else 'launch_failed'
            reason=(cp.stderr or cp.stdout or f'exit {cp.returncode}')[-500:]
        except Exception as exc:
            log.write_text(f'exit=error\n{type(exc).__name__}: {exc}',encoding='utf-8')
            status,reason='launch_failed',f'{type(exc).__name__}: {exc}'
        item['status']=status
        if status!='launched': item['error']=reason.strip()
    def _summary(self, role, cards, lane_specs, scope):
        summary=[]
        for spec in lane_specs:
            mine=[c for c in cards if c['lane']==spec['name']]
            summary.append({'name':spec['name'],'profile_id':spec['profile_id'],'model':spec['model'],'effort':spec['effort'],'launched':sum(1 for c in mine if c['status']=='launched'),'failed':sum(1 for c in mine if c['status']!='launched')})
        return {'role':role,'cards':cards,'lanes':summary,'profile_id':lane_specs[0]['profile_id'],'model':lane_specs[0]['model'],'effort':lane_specs[0]['effort'],'write_scope':scope}
    def run_decision_audit(self, project_dir, revision=None, parallel=6, force_all_pairs=False):
        root,db=self._db(project_dir); self._project(db); row=db.execute('SELECT * FROM versions WHERE revision=?',(revision,)).fetchone() if revision else db.execute('SELECT * FROM versions ORDER BY revision DESC LIMIT 1').fetchone();
        if not row: raise ValueError('no draft revision')
        job_id='D-'+uuid.uuid4().hex[:12]; out=root/'audit'/job_id; out.mkdir(parents=True,exist_ok=True); db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?)',(job_id,'decision',row['revision'],'running',str(out),time.time())); db.execute('UPDATE project SET stage="decision_audit",updated_at=? WHERE id=1',(time.time(),)); db.commit(); db.close()
        result=run_decision_job(Path(row['path']),out,parallel,force_all_pairs)
        db=sqlite3.connect(root/'composer.sqlite'); db.row_factory=sqlite3.Row
        added=self._record_hits(db,row['revision'],out/'decision-results.json')
        db.execute('UPDATE jobs SET status="finished" WHERE job_id=?',(job_id,)); db.commit(); db.close()
        result['issues_added']=added
        return {'job_id':job_id,'revision':row['revision'],'result':result}
    def _record_hits(self, db, revision, result_path):
        if not result_path.exists(): return 0
        data=json.loads(result_path.read_text(encoding='utf-8')); added=0
        for hit in data.get('hits') or []:
            if not isinstance(hit, dict): continue
            kind=str(hit.get('kind') or '')
            loc='-'.join(str(hit[k]) for k in ('i','start','end','j') if k in hit)
            text=str(hit.get('sentence') or hit.get('a') or '')[:500]
            exists=db.execute('SELECT 1 FROM issues WHERE revision=? AND kind=? AND location=? AND text=?',(revision,kind,loc,text)).fetchone()
            if exists: continue
            db.execute('INSERT INTO issues(revision,kind,location,text,status) VALUES(?,?,?,?,"open")',(revision,kind,loc,text)); added+=1
        return added
    def get_status(self, project_dir):
        root,db=self._db(project_dir); row=self._project(db); versions=[dict(x) for x in db.execute('SELECT * FROM versions ORDER BY revision')]; cards=[dict(x) for x in db.execute('SELECT * FROM cards ORDER BY created_at')]; jobs=[dict(x) for x in db.execute('SELECT * FROM jobs ORDER BY created_at')]; issues=db.execute('SELECT COUNT(*) FROM issues WHERE status="open"').fetchone()[0]; db.close(); return {'project_dir':str(root),'stage':row['stage'],'versions':versions,'cards':cards,'jobs':jobs,'open_issues':issues}
    def collect_results(self, project_dir, card_ids=None):
        root,db=self._db(project_dir); ids=card_ids or [r['card_id'] for r in db.execute('SELECT card_id FROM cards')]; found=[]
        for cid in ids:
            work=root/'cards'/cid/'work'; paths=list(work.rglob('*.md')) if work.exists() else []
            for p in paths:
                if p.name.lower() in ('report.md','report.markdown','result.md'): found.append({'card_id':cid,'path':str(p),'text':p.read_text(encoding='utf-8',errors='replace')})
        for item in found: db.execute('UPDATE cards SET status="collected",result_path=? WHERE card_id=?',(item['path'],item['card_id']))
        db.commit(); db.close(); return {'collected':found,'count':len(found)}
    def finalize(self, project_dir, revision, confirm=False):
        root,db=self._db(project_dir); row=db.execute('SELECT * FROM versions WHERE revision=?',(revision,)).fetchone();
        if not row: raise ValueError('revision not found')
        open_issues=db.execute('SELECT COUNT(*) FROM issues WHERE status="open" AND revision=?',(revision,)).fetchone()[0]
        if open_issues and not confirm:
            db.close(); raise ValueError(f'{open_issues} open issues remain; pass confirm=true to finalize anyway')
        if not confirm:
            db.close(); raise ValueError('finalize requires confirm=true')
        final=root/'final_article.md'; final.write_text(Path(row['path']).read_text(encoding='utf-8'),encoding='utf-8')
        db.execute('UPDATE project SET stage="finalized",updated_at=? WHERE id=1',(time.time(),)); db.commit(); db.close()
        status=self.get_status(project_dir); status['finalized_with_open_issues']=open_issues
        summary=root/'audit-summary.json'; summary.write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
        return {'final':str(final),'summary':str(summary),'revision':revision,'open_issues':open_issues}
