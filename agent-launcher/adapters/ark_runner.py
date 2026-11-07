"""Launch the selected CLI with an isolated Ark configuration and local credential access."""
import argparse
import json
import os
import runpy
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parent
_NPM_BIN=Path.home()/"AppData"/"Roaming"/"npm"

# 2026-10-22：卡进程 PATH 可能不含 npm 全局目录（与 adapters/codex.py 同款问题）。
# 现象：shutil.which('claude'/'opencode'/'node') 返回 None → spawn_args 里 args[0].lower()
#       抛 AttributeError → 卡 exit 1（日志里只看到这一个异常，真正的病根是 PATH）。
# 修法：which 找不到时回落到 npm 全局目录下的 native 可执行文件（优先 .exe，免 cmd 包裹）。
_FALLBACKS={
    "claude":[_NPM_BIN/"node_modules/@anthropic-ai/claude-code/bin/claude.exe",_NPM_BIN/"claude.CMD"],
    "opencode":[_NPM_BIN/"node_modules/opencode-ai/bin/opencode.exe",_NPM_BIN/"opencode.CMD"],
    "codex":[_NPM_BIN/"node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe",_NPM_BIN/"codex.CMD"],
    "node":[Path(r"C:\Program Files\nodejs\node.exe")],
}

def which(name):
    path=shutil.which(name)
    if path:
        return path
    for c in _FALLBACKS.get(name,[]):
        if c.is_file():
            return str(c)
    raise FileNotFoundError(f"executable not found on PATH (nor npm fallback): {name}")

def spawn_args(args):
    if not args or not args[0]:
        raise RuntimeError("empty argv: CLI executable was not resolved")
    if args[0].lower().endswith(('.cmd','.bat')):
        return [os.environ.get('COMSPEC','cmd.exe'),'/d','/s','/c',subprocess.list2cmdline(args)]
    return args

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cli',required=True)
    p.add_argument('--model',required=True)
    p.add_argument('--effort',default='high')
    a=p.parse_args()
    env=os.environ.copy()
    env.update(ARK_CREDENTIAL_FILE=str(ROOT.parent/'data/ark-agent-plan.secret.json'),CARD_LAUNCHER_MODEL=a.model,CARD_LAUNCHER_EFFORT=a.effort,NO_PROXY='127.0.0.1,localhost,::1',no_proxy='127.0.0.1,localhost,::1')
    if a.cli=='ag':
        os.environ.update(env)
        os.environ['CARD_GATEWAY_SCRIPT']=str(ROOT/'ark_gateway.py')
        runpy.run_path(str(ROOT/'agy_sdk_runner.py'),run_name='__main__')
        return 0
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    env['ARK_PORT']=str(port)
    url=f'http://127.0.0.1:{port}'
    gateway=subprocess.Popen([sys.executable,str(ROOT/'ark_gateway.py')],env=env,stdout=None,stderr=None,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    temporary=None
    try:
        for _ in range(40):
            if gateway.poll() is not None: raise RuntimeError('Ark gateway exited')
            try:
                with urlopen(url+'/health',timeout=.4): break
            except Exception: time.sleep(.1)
        prompt=sys.stdin.buffer.read()
        if a.cli=='cc':
            alias='claude-sonnet-4-6'
            for name in ['ANTHROPIC_MODEL','ANTHROPIC_SMALL_FAST_MODEL','ANTHROPIC_DEFAULT_OPUS_MODEL','ANTHROPIC_DEFAULT_SONNET_MODEL','ANTHROPIC_DEFAULT_HAIKU_MODEL','CLAUDE_CODE_SUBAGENT_MODEL']:
                env[name]=alias
            env.update(ANTHROPIC_BASE_URL=url,ANTHROPIC_AUTH_TOKEN='local-ark',CLAUDE_CODE_DISABLE_TERMINAL_TITLE='1',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
            settings=Path.cwd()/'.ark-cc-settings.json'
            safe_names=['ANTHROPIC_BASE_URL','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_MODEL','ANTHROPIC_SMALL_FAST_MODEL','ANTHROPIC_DEFAULT_OPUS_MODEL','ANTHROPIC_DEFAULT_SONNET_MODEL','ANTHROPIC_DEFAULT_HAIKU_MODEL','CLAUDE_CODE_SUBAGENT_MODEL','CLAUDE_CODE_DISABLE_TERMINAL_TITLE','CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC']
            settings.write_text(json.dumps({'env':{k:env[k] for k in safe_names if k in env}}),encoding='utf-8')
            env.pop('ANTHROPIC_API_KEY',None)
            env.pop('CLAUDE_CODE_OAUTH_TOKEN',None)
            args=[which('claude'),'-p','--no-session-persistence','--settings',str(settings),'--model',alias,'--effort',a.effort,'--permission-mode','bypassPermissions','--output-format','stream-json','--verbose']
        elif a.cli=='oc':
            config={'permission':'allow','provider':{'ark-plan':{'npm':'@ai-sdk/openai-compatible','name':'Ark Agent Plan','options':{'baseURL':url+'/v1','apiKey':'local-ark'},'models':{a.model:{'name':a.model,'limit':{'context':200000,'output':32000},'options':{'reasoningEffort':a.effort},'variants':{a.effort:{'reasoningEffort':a.effort}}}}}}}
            env['OPENCODE_CONFIG_CONTENT']=json.dumps(config)
            args=[which('opencode'),'run','-m','ark-plan/'+a.model,'--auto','--variant',a.effort,'--format','json']
        elif a.cli=='cp':
            from minimax_copilot_runner import COPILOT_SCRIPT
            env.update(COPILOT_PROVIDER_TYPE='openai',COPILOT_PROVIDER_BASE_URL=url+'/v1',COPILOT_PROVIDER_API_KEY='local-ark',COPILOT_MODEL=a.model)
            args=[which('node'),str(COPILOT_SCRIPT),'--prompt',prompt.decode('utf-8'),'--model',a.model,'--reasoning-effort',a.effort,'--allow-all-tools','--add-dir',str(Path.cwd()),'-C',str(Path.cwd()),'--silent']
            prompt=None
        elif a.cli=='zc':
            import zcode_runner as z
            temporary=Path(tempfile.mkdtemp(prefix='ark-zcode-'))
            z.BASE_URL=url+'/v1'; z.PROVIDER='ark-agent-plan'
            config=z._write_runtime_config(temporary,'local-ark',a.model)
            env.update(USERPROFILE=str(temporary),HOME=str(temporary),ZCODE_DATA_BASE_DIR=str(temporary),ZCODE_BUILTIN_PROVIDER_CONFIG_FILE=str(z.BUILTIN_CONFIG),ZCODE_PERSONAL_PROVIDER_CONFIG_FILE=str(config),APPDATA=str(temporary/'AppData/Roaming'),LOCALAPPDATA=str(temporary/'AppData/Local'))
            args=[str(z.NODE),str(z.ZCODE_CLI),'--prompt',prompt.decode('utf-8'),'--cwd',str(Path.cwd()),'--mode','yolo','--output-format','text','--locale','zh-CN','--no-color']
            prompt=None
        else: raise ValueError(a.cli)
        child=subprocess.Popen(spawn_args(args),env=env,stdin=subprocess.PIPE if prompt is not None else subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        child.communicate(prompt)
        return child.returncode
    finally:
        gateway.terminate()
        try: gateway.wait(timeout=3)
        except subprocess.TimeoutExpired: gateway.kill()
        # 【2026-10-22】zcode 分支用的是临时 HOME（用量写在 .zcode/cli/rollout/model-io-*.jsonl）。
        #   不抢救就 rmtree → 通道自报用量永久丢失（zcode_runner 同病已修，这里同步补上）。
        if temporary:
            try:
                import zcode_runner as _z
                _z._collect_usage(temporary, Path.cwd(), a.model)
            except Exception as _e:
                print('[ark-usage] zcode 用量抢救失败: %s' % _e, flush=True)
            shutil.rmtree(temporary,ignore_errors=True)

if __name__=='__main__':
    raise SystemExit(main())
