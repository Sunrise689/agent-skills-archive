"""Run MiniMax Code with a temporary MiniMax Token Plan key from Pi config."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import urllib.error
import urllib.request

MODEL = "MiniMax-M3.1-Flash"
PROVIDER = "custom_provider:minimax-token-plan-byok"
MODELS_JSON = Path.home() / ".pi" / "agent" / "models.json"
MCODE_HOME = Path.home() / ".minimax-code"
NODE = Path(r"C:\Program Files\nodejs\node.exe")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--cwd", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9._:-]+", args.model):
        raise SystemExit("Model ID contains unsupported characters")
    release = (MCODE_HOME / "current").read_text(encoding="utf-8").strip()
    if not release or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for ch in release):
        raise RuntimeError("MiniMax Code current release pointer is invalid")
    mcode = MCODE_HOME / "releases" / release / "node_modules" / "@minimax-ai" / "code" / "cli.js"
    if not mcode.is_file() or not NODE.is_file():
        raise FileNotFoundError("MiniMax Code CLI or Windows PowerShell is unavailable")

    data = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    token_plan = data.get("providers", {}).get("minimax", {})
    key = token_plan.get("apiKey")
    if not isinstance(key, str) or not key:
        raise RuntimeError("MiniMax Token Plan credentials are missing from Pi's local model config")
    base_url = token_plan.get("baseUrl") or token_plan.get("baseURL") or "https://api.minimaxi.com/v1"
    request = urllib.request.Request(
        base_url.rstrip("/") + "/models",
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            catalog = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise RuntimeError("MiniMax Token Plan model catalog is unavailable; dispatch stopped") from error
    available = {
        item.get("id") for item in catalog.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if args.model not in available:
        raise RuntimeError(f"Model {args.model!r} is not available on this MiniMax Token Plan")

    prompt = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    env = os.environ.copy()
    env["MINIMAX_TOKEN_PLAN_API_KEY"] = key
    argv = [str(NODE), str(mcode),
        "exec", "--model", f"{PROVIDER}/{args.model}", "--cwd", args.cwd,
        "--prompt-mode", "coding", "--permission", "full", "--timeout", "3600s",
        "--input", "-", "--input-format", "text", "--output-format", "stream-json"]
    return subprocess.run(argv, cwd=args.cwd, env=env, input=prompt, text=True,
        encoding="utf-8", errors="replace", check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
