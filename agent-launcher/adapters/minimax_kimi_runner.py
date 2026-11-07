"""Run Kimi Code with an isolated OpenAI-compatible MiniMax Token Plan config."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

MODELS_JSON = Path.home() / ".pi" / "agent" / "models.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    if not args.model.startswith("MiniMax-") or args.model == "MiniMax-M3":
        raise SystemExit("select an available MiniMax Token Plan model; MiniMax-M3 is disabled")

    data = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    provider = data.get("providers", {}).get("minimax", {})
    key = provider.get("apiKey")
    base_url = provider.get("baseUrl")
    if not isinstance(key, str) or not key or not isinstance(base_url, str) or not base_url:
        raise RuntimeError("MiniMax Token Plan credentials are missing from Pi's local model config")

    prompt = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    home = Path.cwd() / ".kimi-code-runtime"
    home.mkdir(parents=True, exist_ok=True)
    alias = f"minimax/{args.model}"
    config = (
        f'default_model = "{alias}"\n'
        f'\n[providers.minimax]\n'
        f'type = "openai"\n'
        f'base_url = "{base_url.rstrip("/")}"\n'
        f'api_key_env = "MINIMAX_TOKEN_PLAN_API_KEY"\n'
        f'\n[models."{alias}"]\n'
        f'provider = "minimax"\n'
        f'model = "{args.model}"\n'
        f'max_context_size = 131072\n'
        f'capabilities = ["tool_use"]\n'
    )
    (home / "config.toml").write_text(config, encoding="utf-8")

    exe = shutil.which("kimi")
    if not exe:
        raise FileNotFoundError("Kimi Code CLI executable 'kimi' is not on PATH")
    env = os.environ.copy()
    env["KIMI_CODE_HOME"] = str(home)
    env["MINIMAX_TOKEN_PLAN_API_KEY"] = key
    command = [exe, "--model", alias, "--prompt", prompt, "--output-format", "stream-json"]
    return subprocess.run(command, cwd=str(Path.cwd()), env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
