"""Provider-neutral adapter preserving the selected external CLI."""
import sys
from pathlib import Path
KINDS={'Claude Code':'cc','Claude Code via MiniMax Bridge':'cc','Claude Code via OpenRouter Bridge':'cc',
       'OpenCode CLI':'oc','Cline CLI':'cl','GitHub Copilot CLI':'cp','ZCode CLI':'zc',
       'Kimi Code CLI':'kimi','MiniMax Code CLI':'mcode','OpenCursor Worker':'cr','Antigravity SDK Wrapper':'ag'}
def build(profile,model,effort,prompt_text,cwd,write_scope):
    if model.rsplit('/',1)[-1]=='MiniMax-M3':raise ValueError('MiniMax-M3 is disabled')
    kind=KINDS[profile['cli']]
    root=Path(__file__).resolve().parent
    runtime=str(root/'.agy-sdk-venv/Scripts/python.exe') if kind=='ag' else sys.executable
    args=[runtime,str(root/'provider_cli.py'),'--cli',kind,'--model',model,'--effort',effort or 'high']
    if profile.get('full_access'):args.append('--full-access')
    return args,prompt_text
