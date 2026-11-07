"""Run Copilot CLI in temporary MiniMax Token Plan BYOK mode without storing its key."""
from __future__ import annotations

import json
import os
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

COPILOT_SCRIPT = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@github" / "copilot" / "npm-loader.js"
MODELS_JSON = Path.home() / ".pi" / "agent" / "models.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    if not args.model.startswith("MiniMax-") or args.model == "MiniMax-M3":
        raise SystemExit("select an available MiniMax Token Plan model; MiniMax-M3 is disabled")
    node = shutil.which("node") or r"C:\Program Files\nodejs\node.exe"
    if not Path(node).is_file() or not COPILOT_SCRIPT.is_file():
        raise FileNotFoundError("Copilot CLI or Node.js runtime is unavailable")
    data = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    provider = data.get("providers", {}).get("minimax", {})
    key = provider.get("apiKey")
    base_url = provider.get("baseUrl")
    if not isinstance(key, str) or not key or not isinstance(base_url, str) or not base_url:
        raise RuntimeError("MiniMax Token Plan credentials are missing from Pi's local model config")
    prompt = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    env = os.environ.copy()
    env.update({
        "COPILOT_PROVIDER_TYPE": "openai",
        "COPILOT_PROVIDER_BASE_URL": base_url.rstrip("/"),
        "COPILOT_PROVIDER_API_KEY": key,
        "COPILOT_MODEL": args.model,
    })
    argv = [str(Path(node).resolve()), str(COPILOT_SCRIPT), "--prompt", prompt,
            "--model", args.model, "--allow-all-tools", "--add-dir", str(Path.cwd()),
            "-C", str(Path.cwd()), "--silent"]
    return subprocess.run(argv, cwd=str(Path.cwd()), env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
