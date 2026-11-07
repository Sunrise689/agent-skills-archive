"""Run TRAE CLI non-interactively with a process-scoped MiniMax Token Plan key."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

MODEL = "MiniMax-M3.1-Flash"
MODELS_JSON = Path.home() / ".pi" / "agent" / "models.json"
KEY_ENV = "MINIMAX_TOKEN_PLAN_API_KEY"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--cwd", required=True)
    args = parser.parse_args()
    if args.model != MODEL:
        raise SystemExit(f"This TRAE BYOK adapter only permits {MODEL}")
    config = json.loads(MODELS_JSON.read_text(encoding="utf-8"))
    key = config.get("providers", {}).get("minimax", {}).get("apiKey")
    if not isinstance(key, str) or not key:
        raise RuntimeError("MiniMax Token Plan credentials are missing from Pi's local model config")
    exe = str(Path(os.environ.get("LOCALAPPDATA", "")) / "trae-cli" / "bin" / "traecli.exe")
    if not Path(exe).is_file():
        exe = shutil.which("traecli") or ""
    if not Path(exe).is_file():
        raise FileNotFoundError(f"TRAE CLI not found: {exe}")
    prompt = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    runtime_root = Path(tempfile.mkdtemp(prefix="trae-minimax-byok-"))
    appdata = runtime_root / "AppData" / "Roaming"
    # TRAE's documented Windows config is %USERPROFILE%\AppData\Roaming\trae_cli\trae_cli.yaml.
    # Isolate that exact path per card so the Token Plan key is never written to the
    # user's persistent profile or the MCP card registry.
    config_path = appdata / "trae_cli" / "trae_cli.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    yaml_key = json.dumps(key, ensure_ascii=False)
    config_path.write_text(
        "model:\n"
        f"  name: {MODEL}\n"
        "models:\n"
        f"  - name: {MODEL}\n"
        "    open_ai:\n"
        f"      model: {MODEL}\n"
        "      base_url: https://api.minimaxi.com/v1\n"
        f"      api_key: {yaml_key}\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    local_appdata = runtime_root / "AppData" / "Local"
    local_appdata.mkdir(parents=True, exist_ok=True)
    env["APPDATA"] = str(appdata)
    env["LOCALAPPDATA"] = str(local_appdata)
    env["USERPROFILE"] = str(runtime_root)
    env["HOME"] = str(runtime_root)
    argv = [exe, "--print", "--permission-mode", "bypass_permissions",
            "--query-timeout", "5m", "--bash-tool-timeout", "2m",
            "--config", f"model.name={MODEL}", prompt]
    try:
        result = subprocess.run(argv, cwd=args.cwd, env=env, check=False,
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        stdout = result.stdout.replace(key, "[REDACTED]")
        stderr = result.stderr.replace(key, "[REDACTED]")
        if stdout:
            sys.stdout.write(stdout)
        if stderr:
            sys.stderr.write(stderr)
        return result.returncode
    finally:
        shutil.rmtree(runtime_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
