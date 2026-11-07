"""Per-card, metadata-only Ark gateway. No credential is written to client logs."""
import json
import os
import time
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen
from urllib.error import HTTPError

CONFIG = json.loads(Path(os.environ['ARK_CREDENTIAL_FILE']).read_text(encoding='utf-8-sig'))
MODEL = os.environ.get('CARD_LAUNCHER_MODEL', CONFIG['model'])
EFFORT = os.environ.get('CARD_LAUNCHER_EFFORT', 'high')
PORT = int(os.environ.get('ARK_PORT', os.environ.get('MINIMAX_SHIM_PORT','8765')))

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass
    def reply(self, code, body, content_type='application/json'):
        self.send_response(code)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Connection','close')
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self):
        if self.path.split('?')[0] == '/health':
            self.reply(200,json.dumps({'ok':True,'model':MODEL}).encode())
        else:
            self.reply(404,b'{}')
    def do_POST(self):
        route=self.path.split('?')[0]
        if route not in ['/v1/messages','/messages','/v1/messages/count_tokens','/messages/count_tokens','/v1/chat/completions','/chat/completions']:
            return self.reply(404,b'{}')
        try:
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            alias=body.get('model',MODEL)
            body['model']=MODEL
            body['reasoning_effort']=EFFORT
            anthropic='messages' in route
            if anthropic:
                body['thinking']={'type':'enabled','budget_tokens':10000}
                body.setdefault('output_config',{})['effort']=EFFORT
                url='https://ark.cn-beijing.volces.com/api/plan/v1/messages'
                if route.endswith('/count_tokens'):
                    url += '/count_tokens'
            else:
                url=CONFIG['base_url'].rstrip('/')+'/chat/completions'
            headers={'Authorization':'Bearer '+CONFIG['api_key'],'Content-Type':'application/json','anthropic-version':'2023-06-01'}
            req=Request(url,data=json.dumps(body,ensure_ascii=False).encode(),headers=headers,method='POST')
            print(json.dumps({'ark_event':'request','model':MODEL,'effort':EFFORT,'route':route,'tool_count':len(body.get('tools') or []),'ts':time.time()}),flush=True)
            with urlopen(req,timeout=300) as response:
                data=response.read()
                content=response.headers.get('Content-Type','application/json')
                status=response.status
            if anthropic:
                from minimax_anthropic_bridge import _client_response
                data=_client_response(data,content,alias)
            try:
                decoded=json.loads(data)
                usage=decoded.get('usage')
            except Exception:
                usage=None
            print(json.dumps({'ark_event':'response','status':status,'usage':usage,'bytes':len(data),'ts':time.time()}),flush=True)
            self.reply(status,data,content)
        except HTTPError as exc:
            data=exc.read().replace(CONFIG['api_key'].encode(),b'[redacted]')
            print(json.dumps({'ark_event':'upstream_error','status':exc.code,'detail':data.decode(errors='replace')[:600]}),flush=True)
            self.reply(exc.code,data)
        except Exception as exc:
            print(json.dumps({'ark_event':'gateway_error','type':type(exc).__name__}),flush=True)
            self.reply(502,json.dumps({'error':{'message':'Ark gateway '+type(exc).__name__}}).encode())

if __name__=='__main__':
    ThreadingHTTPServer(('127.0.0.1',PORT),Handler).serve_forever()
