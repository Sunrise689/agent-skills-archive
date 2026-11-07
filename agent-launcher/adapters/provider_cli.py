"""Actual external CLI invocations against a per-card configured supplier gateway."""
import argparse,json,os,runpy,shutil,socket,subprocess,sys,tempfile,time
from pathlib import Path
from urllib.request import urlopen
from provider_config import resolve
from ark_runner import which,spawn_args

ROOT=Path(__file__).resolve().parent

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cli',required=True);ap.add_argument('--model',required=True)
    ap.add_argument('--effort',default='high');ap.add_argument('--full-access',action='store_true')
    a=ap.parse_args();p=resolve(a.model)
    env=dict(os.environ)
    env.update(CARD_LAUNCHER_MODEL=a.model,CARD_LAUNCHER_EFFORT=a.effort,
               CARD_GATEWAY_SCRIPT=str(ROOT/'provider_gateway.py'),CARD_FULL_ACCESS='1' if a.full_access else '0',
               PYTHONUTF8='1',PYTHONIOENCODING='utf-8',NO_PROXY='127.0.0.1,localhost,::1',no_proxy='127.0.0.1,localhost,::1')
    env['CARD_USAGE_FILE']=str(Path.cwd()/'.card_usage'/f'usage_pid{os.getpid()}_{a.cli}.jsonl')
    env['CARD_USAGE_CHANNEL']=a.cli
    if a.cli=='ag':
        os.environ.update(env)
        runpy.run_path(str(ROOT/'agy_sdk_runner.py'),run_name='__main__');return 0
    if a.cli=='cr':
        os.environ.update(env)
        sys.argv=[str(ROOT/'opencursor_runner.py'),'--model',a.model,'--cwd',str(Path.cwd())]
        runpy.run_path(sys.argv[0],run_name='__main__');return 0
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env['CARD_GATEWAY_PORT']=str(port)
    url=f'http://127.0.0.1:{port}/v1'
    logpath=Path.cwd()/'.card_usage/gateway.log';logpath.parent.mkdir(parents=True,exist_ok=True)
    gateway_log=logpath.open('a',encoding='utf-8')
    server=subprocess.Popen([sys.executable,str(ROOT/'provider_gateway.py')],env=env,stdout=gateway_log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    temp=Path(tempfile.mkdtemp(prefix='card-'+a.cli+'-'))
    try:
        for _ in range(100):
            if server.poll() is not None:raise RuntimeError('provider gateway exited')
            try:
                with urlopen(url[:-3]+'/health',timeout=.5):break
            except Exception:time.sleep(.1)
        else:raise TimeoutError('gateway startup timeout')
        prompt=sys.stdin.buffer.read()
        if a.cli=='cc':
            alias='claude-sonnet-4-6'
            for k in ['ANTHROPIC_MODEL','ANTHROPIC_SMALL_FAST_MODEL','ANTHROPIC_DEFAULT_OPUS_MODEL','ANTHROPIC_DEFAULT_SONNET_MODEL','ANTHROPIC_DEFAULT_HAIKU_MODEL','CLAUDE_CODE_SUBAGENT_MODEL']:env[k]=alias
            env.update(ANTHROPIC_BASE_URL=url[:-3],ANTHROPIC_AUTH_TOKEN='local-card',CLAUDE_CODE_DISABLE_TERMINAL_TITLE='1',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
            env.pop('ANTHROPIC_API_KEY',None);env.pop('CLAUDE_CODE_OAUTH_TOKEN',None)
            settings= temp/'settings.json'
            settings.write_text(json.dumps({'env':{k:v for k,v in env.items() if k.startswith(('ANTHROPIC_','CLAUDE_CODE_'))}}),encoding='utf-8')
            args=[which('claude'),'-p','--settings',str(settings),'--no-session-persistence','--model',alias,'--permission-mode','bypassPermissions','--output-format','stream-json','--verbose','--effort',a.effort]
        elif a.cli=='oc':
            env['OPENCODE_CONFIG_CONTENT']=json.dumps({'permission':'allow','provider':{'card':{'npm':'@ai-sdk/openai-compatible','options':{'baseURL':url,'apiKey':'local-card'},'models':{p['model']:{'name':p['model'],'limit':{'context':128000,'output':16384}}}}}})
            args=[which('opencode'),'run','-m','card/'+p['model'],'--auto','--format','json']
        elif a.cli=='cp':
            from minimax_copilot_runner import COPILOT_SCRIPT
            env.update(COPILOT_PROVIDER_TYPE='openai',COPILOT_PROVIDER_BASE_URL=url,COPILOT_PROVIDER_API_KEY='local-card',COPILOT_MODEL=a.model)
            args=[which('node'),str(COPILOT_SCRIPT),'--prompt',prompt.decode('utf-8'),'--model',a.model,'--allow-all-tools','--allow-all-paths','--allow-all-urls','--add-dir',str(Path.cwd()),'-C',str(Path.cwd()),'--silent'];prompt=None
        elif a.cli=='zc':
            import zcode_runner as z
            z.BASE_URL=url;z.PROVIDER='card-provider'
            config=z._write_runtime_config(temp,'local-card',a.model)
            env.update(USERPROFILE=str(temp),HOME=str(temp),ZCODE_DATA_BASE_DIR=str(temp),ZCODE_BUILTIN_PROVIDER_CONFIG_FILE=str(z.BUILTIN_CONFIG),ZCODE_PERSONAL_PROVIDER_CONFIG_FILE=str(config),APPDATA=str(temp/'AppData/Roaming'),LOCALAPPDATA=str(temp/'AppData/Local'))
            args=[str(z.NODE),str(z.ZCODE_CLI),'--prompt',prompt.decode('utf-8'),'--cwd',str(Path.cwd()),'--mode','yolo','--output-format','text','--locale','zh-CN','--no-color'];prompt=None
        elif a.cli=='cl':
            data=temp/'cline';settings=data/'settings';settings.mkdir(parents=True)
            (settings/'providers.json').write_text(json.dumps({'version':1,'lastUsedProvider':'openai-compatible','providers':{'openai-compatible':{'settings':{'provider':'openai-compatible','apiKey':'local-card','model':a.model,'baseUrl':url},'tokenSource':'manual'}}}),encoding='utf-8')
            env.update(CLINE_PROVIDER_SETTINGS_PATH=str(settings/'providers.json'),OPENAI_BASE_URL=url,OPENAI_API_KEY='local-card')
            script=Path.home()/'AppData/Roaming/npm/node_modules/cline/bin/cline'
            auth=[which('node'),str(script),'auth','openai-compatible','--apikey','local-card','--modelid',a.model,'--baseurl',url,'--data-dir',str(data)]
            setup=subprocess.run(auth,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
            if setup.returncode:raise RuntimeError('Cline local provider setup failed: '+setup.stderr.decode(errors='replace')[-500:])
            args=[which('node'),str(script),'--data-dir',str(data),'--provider','openai-compatible','--model',a.model,'--cwd',str(Path.cwd()),'--key','local-card','--auto-approve','true','--timeout','180','--json',prompt.decode('utf-8')];prompt=None
        elif a.cli=='kimi':
            home=temp/'kimi';home.mkdir()
            (home/'config.toml').write_text('default_model = "card"\n[providers.card]\ntype = "openai"\nbase_url = '+json.dumps(url)+'\napi_key_env = "CARD_LOCAL_KEY"\n[models.card]\nprovider = "card"\nmodel = '+json.dumps(a.model)+'\nmax_context_size = 128000\ncapabilities = ["tool_use"]\n',encoding='utf-8')
            env.update(KIMI_CODE_HOME=str(home),CARD_LOCAL_KEY='local-card')
            args=[which('kimi'),'--model','card','--prompt',prompt.decode('utf-8'),'--output-format','stream-json'];prompt=None
        elif a.cli=='mcode':
            home=Path.home()/'.minimax-code';release=(home/'current').read_text().strip()
            cli=home/'releases'/release/'node_modules/@minimax-ai/code/cli.js'
            config=temp/'mcode.json'
            config.write_text(json.dumps({'custom_provider':{'card':{'name':'Configured card supplier','kind':'custom','enabled':True,
                'api':'openai-completions','options':{'apiKey':'local-card','baseURL':url,'authMode':'api-key'},
                'models':{a.model:{'limit':{'context':128000,'output':16384}}}}},
                'defaultModel':'custom_provider:card/'+a.model,'permissionMode':'bypassPermissions'}),encoding='utf-8')
            args=[which('node'),str(cli),'exec','--config',str(config),'--model','custom_provider:card/'+a.model,'--cwd',str(Path.cwd()),'--prompt-mode','coding','--permission','full','--input','-','--input-format','text','--output-format','stream-json']
        else:raise ValueError(a.cli)
        child=subprocess.Popen(spawn_args(args),env=env,stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        child.communicate(prompt);return child.returncode
    finally:
        if a.cli=='zc':
            import zcode_runner as z
            z._collect_usage(temp,Path.cwd(),a.model)
        server.terminate()
        try:server.wait(timeout=3)
        except subprocess.TimeoutExpired:server.kill();server.wait()
        gateway_log.close()
        shutil.rmtree(temp,ignore_errors=True)

if __name__=='__main__':raise SystemExit(main())
