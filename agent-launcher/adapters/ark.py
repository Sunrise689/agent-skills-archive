"""Ark Agent Plan provider using each profile's actual external CLI."""
import sys
from pathlib import Path

def build(profile, model, effort, prompt_text, cwd, write_scope):
    kinds = {'Claude Code':'cc','OpenCode CLI':'oc','GitHub Copilot CLI':'cp','ZCode CLI':'zc','Antigravity SDK Wrapper':'ag'}
    kind = kinds[profile['cli']]
    runtime = str(Path(__file__).parent/'.agy-sdk-venv/Scripts/python.exe') if kind == 'ag' else sys.executable
    return [runtime,str(Path(__file__).with_name('ark_runner.py')),'--cli',kind,'--model',model,'--effort',effort or 'high'], prompt_text
