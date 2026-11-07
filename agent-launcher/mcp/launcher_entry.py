"""Stable MCP transport; each request executes the current on-disk backend."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "mcp/launcher_mcp_server.py"

def main():
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    for line in sys.stdin:
        if not line.strip():
            continue
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        try:
            completed = subprocess.run([sys.executable, str(BACKEND)], input=line, text=True, encoding="utf-8", errors="replace", stdout=subprocess.PIPE, stderr=sys.stderr, env=env, cwd=str(ROOT), timeout=540, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if completed.returncode:
                raise RuntimeError("backend exited " + str(completed.returncode))
            if completed.stdout:
                sys.stdout.write(completed.stdout)
                sys.stdout.flush()
        except Exception as exc:
            try:
                request_id = json.loads(line).get("id")
            except ValueError:
                request_id = None
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": type(exc).__name__}}) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
