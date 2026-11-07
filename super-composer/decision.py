from __future__ import annotations
import itertools, json, os, re, subprocess, sys, time
from pathlib import Path

LOCAL_MODEL=Path(os.environ.get("SUPER_COMPOSER_JUDGE", ""))
PYTHON=Path(os.environ.get("SUPER_COMPOSER_PYTHON", sys.executable))

def sentences(text):
    body='\n'.join(x for x in text.splitlines() if not x.lstrip().startswith('#'))
    return [x.strip() for x in re.split(r'(?<=[。！？!?])\s*|\n+',body) if len(x.strip())>=8]

def paragraphs(text):
    return [x.strip() for x in re.split(r'\n\s*\n',text) if x.strip() and not x.lstrip().startswith('#')]

def candidates_for_fact(ss):
    return [(i,s) for i,s in enumerate(ss) if re.search(r'\d|[A-Z][a-z]{2,}|[一二三四五六七八九十百千万亿]|年|世纪|首次|最早|唯一|直接|因此|导致|起源|发明|创立',s)]

def pair_candidates(ss, force_all=False):
    pairs=list(itertools.combinations(range(len(ss)),2))
    if force_all or len(ss)<=50: return pairs
    def key(s):
        return set(re.findall(r'[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}|\d+',s.lower()))
    keys=[key(s) for s in ss]; out=set()
    for i in range(len(ss)-1): out.add((i,i+1))
    for i in range(len(ss)):
        scores=sorted(((len(keys[i]&keys[j]),j) for j in range(len(ss)) if i!=j),reverse=True)[:5]
        for score,j in scores:
            if score or abs(i-j)<=2: out.add(tuple(sorted((i,j))))
    return sorted(out)

def jobs_for(article, force_all=False):
    text=article.read_text(encoding='utf-8'); ss=sentences(text); ps=paragraphs(text)
    jobs=[]
    # Every question must be phrased so that "是" means "there is a problem to
    # fix". A positive question ("is it clear?") makes the judge answer 是 for a
    # good sentence, which the caller then reports as a defect. Keep the
    # polarity negative for all five kinds.
    for i,s in enumerate(ss): jobs.append({'state':s,'question':'这句话是否存在语病、生硬堆砌、表达不清或与指定文体不符之处？只回答是或否。','meta':{'kind':'sentence_style','i':i,'sentence':s}})
    for i,s in candidates_for_fact(ss): jobs.append({'state':s,'question':'这句话是否含需核查的事实风险、绝对化或无依据强因果？只回答是或否。','meta':{'kind':'fact_risk','i':i,'sentence':s}})
    for i in range(len(ss)-2): jobs.append({'state':'\n'.join(ss[i:i+3]),'question':'这组三句话是否存在指代、转折、推进或局部矛盾问题？只回答是或否。','meta':{'kind':'window3','start':i,'end':i+2}})
    for i,p in enumerate(ps): jobs.append({'state':p,'question':'这一段是否存在不连贯、未完成叙述任务、反复总结或突然换题的问题？只回答是或否。','meta':{'kind':'paragraph_flow','i':i}})
    for i,j in pair_candidates(ss,force_all): jobs.append({'state':f'句子A：{ss[i]}\n句子B：{ss[j]}','question':'两句话是否表达实质重复的信息？只回答是或否。','meta':{'kind':'duplicate_pair','i':i,'j':j,'a':ss[i],'b':ss[j]}})
    return jobs,{'sentences':len(ss),'paragraphs':len(ps),'pairs':len(pair_candidates(ss,force_all))}

def run_decision_job(article,outdir,parallel=6,force_all_pairs=False):
    jobs,shape=jobs_for(article,force_all_pairs); inp=outdir/'decision.jobs.jsonl'; inp.write_text('\n'.join(json.dumps(x,ensure_ascii=False) for x in jobs),encoding='utf-8')
    cmd=[str(PYTHON),'-X','utf8',str(LOCAL_MODEL) if str(LOCAL_MODEL) else "",'judge-batch','--input',str(inp),'--parallel',str(max(1,parallel))]
    try:
        cp=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=3600)
        if cp.returncode: raise RuntimeError(cp.stderr[-2000:])
        raw=json.loads(cp.stdout); rows=raw.get('rows',[])
    except Exception as exc:
        rows=[{'valid':False,'error':str(exc),'meta':j['meta']} for j in jobs]
    for row,job in zip(rows,jobs): row['meta']=job['meta']
    result={'shape':shape,'requests':len(jobs),'rows':rows,'invalid':sum(1 for x in rows if not x.get('valid')),'hits':[x.get('meta') for x in rows if x.get('valid') and x.get('predicted') is True]}
    (outdir/'decision-results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'shape':shape,'requests':len(jobs),'invalid':result['invalid'],'hits':len(result['hits']),'result_path':str(outdir/'decision-results.json')}
