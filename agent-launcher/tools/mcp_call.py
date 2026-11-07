"""Call the current MCP implementation without relying on a stale client host."""
import json
from pathlib import Path
import subprocess
import sys

def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    if len(sys.argv) != 3:
        raise SystemExit("usage: mcp_call.py TOOL ARGUMENTS_JSON_FILE")
    root = Path(__file__).resolve().parent.parent
    args = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
    messages = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "current-card-launcher", "version": "20261013"}}}, {"jsonrpc": "2.0", "method": "notifications/initialized"}, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": args}}]
    data = "".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages)
    result = subprocess.run([sys.executable, str(root / "mcp/launcher_entry.py")], input=data, text=True, encoding="utf-8", stdout=subprocess.PIPE, stderr=sys.stderr, timeout=570, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for line in result.stdout.splitlines():
        value = json.loads(line)
        if value.get("id") == 2:
            print(json.dumps(value, ensure_ascii=False))
            return 1 if value.get("error") or value.get("result", {}).get("isError") else 0
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
