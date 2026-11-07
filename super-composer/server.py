import json
from core import SuperComposer

SERVER = {"name":"super-composer","version":"0.1.0"}
TOOLS = [
 {"name":"create_project","description":"Create a Super Composer project with style brief and optional materials.","inputSchema":{"type":"object","required":["project_dir","style_brief"],"properties":{"project_dir":{"type":"string"},"style_brief":{"type":"object"},"materials":{"type":"array","items":{"type":"string"}},"policy":{"type":"object"}}}},
 {"name":"save_draft","description":"Save an immutable caller-owned draft revision.","inputSchema":{"type":"object","required":["project_dir","text"],"properties":{"project_dir":{"type":"string"},"text":{"type":"string"},"label":{"type":"string"}}}},
 {"name":"launch_role_cards","description":"Create self-contained C/A/P taskbooks and launch cards on the configured MiniMax and OpenRouter lanes; CX is rejected.","inputSchema":{"type":"object","required":["project_dir","role"],"properties":{"project_dir":{"type":"string"},"role":{"type":"string","enum":["C","A","P"]},"responsibility":{"type":"string"},"spans":{"type":"array","items":{"type":"string"}},"count":{"type":"integer","minimum":1},"lanes":{"type":"array","items":{"type":"object","required":["name"],"properties":{"name":{"type":"string","enum":["minimax","openrouter"]},"profile_id":{"type":"string"},"model":{"type":"string"},"effort":{"type":"string"},"count":{"type":"integer","minimum":1}}}}}}},
 {"name":"run_decision_audit","description":"Run local D3 sentence, risk, window, paragraph and duplicate checks as a background job.","inputSchema":{"type":"object","required":["project_dir"],"properties":{"project_dir":{"type":"string"},"revision":{"type":"integer"},"parallel":{"type":"integer","minimum":1},"force_all_pairs":{"type":"boolean"}}}},
 {"name":"get_status","description":"Read project state, cards, jobs and issue counts.","inputSchema":{"type":"object","required":["project_dir"],"properties":{"project_dir":{"type":"string"}}}},
 {"name":"collect_results","description":"Collect declared card reports and map findings to the current draft.","inputSchema":{"type":"object","required":["project_dir"],"properties":{"project_dir":{"type":"string"},"card_ids":{"type":"array","items":{"type":"string"}}}}},
 {"name":"finalize","description":"Finalize a caller-approved manuscript with audit summary and version chain.","inputSchema":{"type":"object","required":["project_dir","revision"],"properties":{"project_dir":{"type":"string"},"revision":{"type":"integer"},"confirm":{"type":"boolean"}}}}
]

def handle_line(line):
    req=json.loads(line); rid=req.get('id'); method=req.get('method')
    if method=='initialize': return {"jsonrpc":"2.0","id":rid,"result":{"protocolVersion":"2025-06-18","capabilities":{"tools":{}},"serverInfo":SERVER}}
    if method=='notifications/initialized': return {"jsonrpc":"2.0","id":rid,"result":{}}
    if method=='tools/list': return {"jsonrpc":"2.0","id":rid,"result":{"tools":TOOLS}}
    if method!='tools/call': return {"jsonrpc":"2.0","id":rid,"error":{"code":-32601,"message":"method not found"}}
    name=req.get('params',{}).get('name'); args=req.get('params',{}).get('arguments') or {}
    fn=getattr(SuperComposer(), name, None)
    if not fn or name not in {t['name'] for t in TOOLS}: return {"jsonrpc":"2.0","id":rid,"error":{"code":-32601,"message":"tool not found"}}
    try: result=fn(**args)
    except (ValueError, FileNotFoundError) as exc: return {"jsonrpc":"2.0","id":rid,"error":{"code":-32602,"message":str(exc)}}
    return {"jsonrpc":"2.0","id":rid,"result":{"content":[{"type":"text","text":json.dumps(result,ensure_ascii=False)}]}}
