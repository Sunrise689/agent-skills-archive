"""Run native Codex against an isolated MiniMax Responses bridge."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from adapters import codex
from adapters.bridge_runner import _free_port, _health, _spawn_args

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", default="high")
    parser.add_argument("--scope", default="read-only")
    args = parser.parse_args()
    prompt = sys.stdin.buffer.read().decode("utf-8")
    port = _free_port()
    env = dict(os.environ, CARD_LAUNCHER_MODEL=args.model, CARD_RESPONSES_PORT=str(port))
    bridge = subprocess.Popen([sys.executable, str(Path(__file__).with_name("minimax_responses_bridge.py"))], env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        _health(f"http://127.0.0.1:{port}/health", bridge, expected_model=args.model)
        argv, _ = codex.build({"local_exec_mcp": False, "responses_bridge_active": True}, args.model, args.effort, prompt, str(Path.cwd()), args.scope)
        native = Path.home() / "AppData/Roaming/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe"
        if native.is_file():
            argv[0] = str(native)
        argv.extend(["-c", 'model_provider="card_minimax"', "-c", 'model_providers.card_minimax.name="MiniMax Token Plan"', "-c", f'model_providers.card_minimax.base_url="http://127.0.0.1:{port}/v1"', "-c", 'model_providers.card_minimax.wire_api="responses"', "-c", "model_providers.card_minimax.requires_openai_auth=false", "-c", "model_supports_reasoning=false", "-c", 'tools.web_search=false'])
        return subprocess.run(_spawn_args(argv), input=prompt.encode(), env=env, creationflags=subprocess.CREATE_NO_WINDOW).returncode
    finally:
        bridge.terminate()
        bridge.wait(timeout=5)

if __name__ == "__main__":
    raise SystemExit(main())
