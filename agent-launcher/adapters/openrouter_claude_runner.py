"""Own a per-card loopback bridge and invoke the real Claude Code CLI."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import openrouter_anthropic_bridge as bridge  # noqa: E402

MODEL = "openrouter/thinkingmachines/inkling-small:free"
EFFORT = "max"
CLIENT_MODEL = bridge.CLIENT_MODEL


def _key() -> str:
    # Use the exact credential of the functioning OC control group.
    auth_path = Path.home() / ".local" / "share" / "opencode" / "auth.json"
    if auth_path.exists():
        auth_data = json.loads(auth_path.read_text(encoding="utf-8-sig"))
        auth_key = auth_data.get("openrouter", {}).get("key")
        if auth_key:
            return auth_key
    value = os.environ.get("OPENROUTER_API_KEY")
    if value:
        return value
    candidates = []
    if os.environ.get("PI_MODELS_JSON"):
        candidates.append(Path(os.environ["PI_MODELS_JSON"]))
    candidates += [Path.home() / ".pi" / "agent" / "models.json", Path.home() / ".local" / "share" / "opencode" / "auth.json",
                   Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "opencode" / "auth.json"]
    for path in dict.fromkeys(candidates):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError):
            continue
        providers = data.get("providers", data) if isinstance(data, dict) else {}
        entry = providers.get("openrouter", {}) if isinstance(providers, dict) else {}
        value = entry.get("apiKey") or entry.get("key") if isinstance(entry, dict) else None
        if isinstance(value, str) and value:
            return value
    raise RuntimeError("OpenRouter credential not found in environment or existing local provider files")


def _cli_args(args: list[str]) -> list[str]:
    if args[0].lower().endswith((".cmd", ".bat")):
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", subprocess.list2cmdline(args)]
    return args


def main() -> int:
    model = os.environ.get("CARD_LAUNCHER_MODEL", MODEL)
    effort = os.environ.get("CARD_LAUNCHER_EFFORT", EFFORT)
    choices = {MODEL: "max", "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free": "high"}
    if model not in choices or effort != choices[model]:
        raise SystemExit("CC-U-OR-free fixed model/effort guard rejected override")
    bridge.PROFILE_MODEL = model
    bridge.API_MODEL = model.removeprefix("openrouter/")
    bridge.EFFORT = effort
    bridge.OPENROUTER_API_KEY = _key()
    server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.Handler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, name="cc-or-free-bridge", daemon=True)
    thread.start()
    cwd = Path.cwd().resolve()
    settings = cwd / ".card-launcher-cc-or-settings.json"
    settings.write_text(json.dumps({"env": {
        "ANTHROPIC_BASE_URL": f"http://{host}:{port}",
        "ANTHROPIC_AUTH_TOKEN": "local-bridge",
        "ANTHROPIC_MODEL": CLIENT_MODEL,
        "ANTHROPIC_SMALL_FAST_MODEL": CLIENT_MODEL,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": CLIENT_MODEL,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": CLIENT_MODEL,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": CLIENT_MODEL,
        "CLAUDE_CODE_SUBAGENT_MODEL": CLIENT_MODEL,
        "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "no_proxy": "127.0.0.1,localhost,::1",
    }}), encoding="utf-8")
    prompt = sys.stdin.buffer.read()
    cli = shutil.which("claude")
    if not cli:
        server.shutdown()
        raise SystemExit("Claude Code CLI executable not found on PATH")
    args = [cli, "-p", "--no-session-persistence", "--settings", str(settings),
            "--model", CLIENT_MODEL, "--effort", effort,
            "--permission-mode", "bypassPermissions", "--output-format", "stream-json", "--verbose"]
    child_env = os.environ.copy()
    child_env.pop("ANTHROPIC_API_KEY", None)
    child_env.pop("CLAUDECODE", None)
    child_env.update({
        "ANTHROPIC_BASE_URL": f"http://{host}:{port}",
        "ANTHROPIC_AUTH_TOKEN": "local-bridge",
        "ANTHROPIC_MODEL": CLIENT_MODEL,
        "ANTHROPIC_SMALL_FAST_MODEL": CLIENT_MODEL,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": CLIENT_MODEL,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": CLIENT_MODEL,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": CLIENT_MODEL,
        "CLAUDE_CODE_SUBAGENT_MODEL": CLIENT_MODEL,
        "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
        "NO_PROXY": "127.0.0.1,localhost,::1",
        "no_proxy": "127.0.0.1,localhost,::1",
    })
    child = None
    try:
        child = subprocess.Popen(_cli_args(args), cwd=str(cwd), stdin=subprocess.PIPE,
                                 stdout=None, stderr=None, env=child_env)
        child.communicate(prompt, timeout=3600)
        return int(child.returncode or 0)
    finally:
        if child is not None and child.poll() is None:
            child.kill()
            child.communicate()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
