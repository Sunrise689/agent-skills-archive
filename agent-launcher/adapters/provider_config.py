"""Resolve configured suppliers without changing the selected CLI or exposing keys."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def resolve(model):
    pi = json.loads((Path.home()/'.pi/agent/models.json').read_text(encoding='utf-8-sig'))['providers']
    oc_path = Path.home()/'.config/opencode/opencode.json'
    oc = json.loads(oc_path.read_text(encoding='utf-8-sig')).get('provider', {})
    name, actual = '', model
    if model.startswith(('MiniMax-', 'minimax-token-plan/')):
        name, actual = 'minimax', model.rsplit('/', 1)[-1]
    elif model.startswith('ark/') or model.startswith(('glm-', 'ark-code-', 'doubao-', 'deepseek-v4')):
        name, actual = 'ark', model.removeprefix('ark/')
    elif model.startswith('deepseek/') or model == 'deepseek-flash':
        name, actual = 'deepseek', model.removeprefix('deepseek/')
    elif model.startswith(('openrouter/', 'opencode-go/', 'ollama/')):
        name, actual = model.split('/', 1)
    else:
        for n,p in pi.items():
            if model in [m.get('id') for m in p.get('models',[]) if isinstance(m,dict)]:
                name = n
                break
    if not name:
        raise ValueError('No configured supplier for model: '+model+'; qualify as provider/model')
    p = pi.get(name) or oc.get(name)
    if not p:
        raise ValueError('Supplier configuration missing: '+name)
    opts = p.get('options', p)
    base = opts.get('baseUrl') or opts.get('baseURL')
    key = opts.get('apiKey')
    if not key and name in oc:
        auth = Path.home()/'.local/share/opencode/auth.json'
        if auth.exists():
            row=json.loads(auth.read_text(encoding='utf-8-sig')).get(name,{})
            key=row.get('key') or row.get('apiKey')
    if name=='ark':
        secret=json.loads((ROOT/'data/ark-agent-plan.secret.json').read_text(encoding='utf-8-sig'))
        base,key=secret['base_url'],secret['api_key']
    if not base or not key:
        raise ValueError('Supplier endpoint or credential missing: '+name)
    return {'name':name,'model':actual,'base':base.rstrip('/'),'key':key,
            'api':'responses' if name in ('minimax','ark','openrouter') or p.get('api')=='openai-responses' else 'chat'}
