"""Run a bridge-dependent CLI and keep its loopback bridge in the same process tree."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = "MiniMax-M3.1-Flash"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _exe(name: str, fallbacks: tuple[str, ...] = ()) -> str:
    for candidate in (shutil.which(name), *fallbacks):
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise FileNotFoundError(f"CLI executable not found: {name}")


def _spawn_args(args: list[str]) -> list[str]:
    if args[0].lower().endswith((".cmd", ".bat")):
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", subprocess.list2cmdline(args)]
    return args


def _health(url: str, proc: subprocess.Popen, seconds: float = 12,
            expected_model: str = DEFAULT_MODEL) -> None:
    deadline = time.monotonic() + seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("local MiniMax bridge exited before becoming healthy")
        try:
            with urllib.request.urlopen(url, timeout=0.8) as response:
                data = json.loads(response.read())
                if data.get("ok") and data.get("model") == expected_model:
                    return
                last_error = ValueError("bridge health payload did not match the expected model")
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    detail = f"; last probe error: {type(last_error).__name__}" if last_error else ""
    raise TimeoutError("local MiniMax bridge health check timed out" + detail)


def _run_bridge_cli(kind: str, prompt: str) -> int:
    model = os.environ.get("CARD_LAUNCHER_MODEL", DEFAULT_MODEL)
    if not model or model.rsplit("/", 1)[-1] == "MiniMax-M3":
        raise ValueError("Bridge requires a selected MiniMax model; MiniMax-M3 is disabled")
    # 默认 prompt 走 stdin；只有 CLI 从位置参数取 prompt 时才覆盖成 b""。
    stdin_bytes: bytes | None = None
    if kind == "agy":
        port = _free_port()
        shim = ROOT / "minimax_agy_shim.py"
        env = dict(os.environ)
        env.update({
            "MINIMAX_SHIM_HOST": "127.0.0.1",
            "MINIMAX_SHIM_PORT": str(port),
            "MINIMAX_SHIM_TIMEOUT": "240",
            "MINIMAX_MODEL": model,
            "PI_MODELS_JSON": str(Path.home() / ".pi" / "agent" / "models.json"),
            "AGY_LLM_GATEWAY_URL": f"http://127.0.0.1:{port}/v1",
            "AGY_LLM_GATEWAY_API_KEY": "local-bridge",
            "AGY_LLM_GATEWAY_MODELS": model,
            "AGY_LLM_GATEWAY_WIRE_PROTOCOL": "openai",
            "AGY_LLM_GATEWAY_HEADERS": "",
            "AGY_LLM_GATEWAY_CA_CERT": "",
            "AGY_LLM_GATEWAY_PROXY_URL": "",
        })
        health = f"http://127.0.0.1:{port}/health"
        server_args = [sys.executable, str(shim)]
        cli = _exe("agy", (str(Path(os.environ.get("LOCALAPPDATA", "")) / "agy" / "bin" / "agy.exe"),))
        command = [cli, "--dangerously-skip-permissions", "--model", model, "--print-timeout", "240s",
                   "--add-dir", str(Path.cwd()), "-p", prompt]
    elif kind == "claude":
        port = _free_port()
        shim = ROOT / "minimax_anthropic_bridge.py"
        env = dict(os.environ)
        env["MINIMAX_CC_BRIDGE_PORT"] = str(port)
        env["MINIMAX_CC_MODEL"] = model
        env["MINIMAX_CC_EFFORT"] = os.environ.get("CARD_LAUNCHER_EFFORT", "max")
        # Claude SDK needs a recognized client-side ID. The bridge routes every
        # request to the selected actual model and echoes this alias back.
        client_model = "claude-sonnet-4-6"
        # Claude Code reads these independently for session titles, fast
        # requests, and subagents. Pin them to the selected bridged model so
        # global ~/.claude/settings.json cannot send side requests to another
        # provider (for example DeepSeek/GLM) during a MiniMax card run.
        for key in (
            "ANTHROPIC_MODEL",
            "ANTHROPIC_SMALL_FAST_MODEL",
            "ANTHROPIC_DEFAULT_OPUS_MODEL",
            "ANTHROPIC_DEFAULT_SONNET_MODEL",
            "ANTHROPIC_DEFAULT_HAIKU_MODEL",
            "CLAUDE_CODE_SUBAGENT_MODEL",
        ):
            env[key] = client_model
        # Skip Claude Code's terminal-title side request: some compatible
        # gateways reject it as an unrecognized model even when the main
        # task and every model route are pinned correctly.
        env["CLAUDE_CODE_DISABLE_TERMINAL_TITLE"] = "1"
        env["PI_MODELS_JSON"] = str(Path.home() / ".pi" / "agent" / "models.json")
        health = f"http://127.0.0.1:{port}/health"
        server_args = [sys.executable, str(shim)]
        cli = _exe("claude", (str(Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd"),))
        env.update({"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}", "ANTHROPIC_AUTH_TOKEN": "local-bridge", "NO_PROXY": "127.0.0.1,localhost,::1", "no_proxy": "127.0.0.1,localhost,::1"})
        settings_path = Path.cwd() / ".card-launcher-cc-settings.json"
        settings_path.write_text(json.dumps({"env": {
            "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{port}",
            "ANTHROPIC_AUTH_TOKEN": "local-bridge",
            "ANTHROPIC_MODEL": client_model,
            "ANTHROPIC_SMALL_FAST_MODEL": client_model,
            "ANTHROPIC_DEFAULT_OPUS_MODEL": client_model,
            "ANTHROPIC_DEFAULT_SONNET_MODEL": client_model,
            "ANTHROPIC_DEFAULT_HAIKU_MODEL": client_model,
            "CLAUDE_CODE_SUBAGENT_MODEL": client_model,
            "CLAUDE_CODE_DISABLE_TERMINAL_TITLE": "1",
            "NO_PROXY": "127.0.0.1,localhost,::1",
            "no_proxy": "127.0.0.1,localhost,::1",
        }}), encoding="utf-8")
        command = [cli, "-p", "--no-session-persistence", "--settings", str(settings_path), "--model", client_model,
                   "--permission-mode", "bypassPermissions", "--output-format", "stream-json", "--verbose"]
        command += ["--effort", env["MINIMAX_CC_EFFORT"]]
    elif kind == "cline":
        # Cline 只懂 OpenAI Chat Completions 协议，但 MiniMax 原生支持 /v1/responses
        # （function tools / streaming / reasoning.effort / service_tier 均实测可用）。
        # 用本地 Responses 桥把 chat 协议转成 Responses，让 Cline 走原生 Responses 链路。
        port = _free_port()
        bridge = ROOT / "minimax_responses_bridge_upstream.py"
        env = dict(os.environ)
        usage_file = Path.cwd() / ".card_usage" / ("usage_pid%d_cl.jsonl" % os.getpid())
        env.update({
            "CARD_USAGE_FILE": str(usage_file),
            "CARD_USAGE_CHANNEL": "cline",
            "MINIMAX_RESP_HOST": "127.0.0.1",
            "MINIMAX_RESP_PORT": str(port),
            "MINIMAX_RESP_TIMEOUT": "300",
            "CARD_LAUNCHER_MODEL": model,
            "PI_MODELS_JSON": str(Path.home() / ".pi" / "agent" / "models.json"),
        })
        health = f"http://127.0.0.1:{port}/health"
        server_args = [sys.executable, str(bridge)]
        cli = _exe("node", (r"C:\Program Files\nodejs\node.exe",))
        cline_script = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "cline" / "bin" / "cline"
        if not cline_script.is_file():
            raise FileNotFoundError(f"Cline CLI is missing: {cline_script}")
        data_dir = Path.home() / "AppData" / "Local" / "card_launcher" / "cline-minimax-data"
        # provider settings 必须同时带 apiKey + baseUrl，否则 Cline 退回 platform.openai.com。
        # baseUrl 指向本地桥；apiKey 只是占位符（桥不校验），真实密钥不落盘。
        providers_path = data_dir / "settings" / "providers.json"
        providers_path.parent.mkdir(parents=True, exist_ok=True)
        settings_data = {}
        if providers_path.is_file():
            try:
                settings_data = json.loads(providers_path.read_text(encoding="utf-8"))
            except Exception:
                settings_data = {}
        entry = settings_data.setdefault("providers", {}).setdefault("openai-compatible", {})
        entry["settings"] = {
            "provider": "openai-compatible",
            "apiKey": "local-bridge",
            "model": model,
            "baseUrl": f"http://127.0.0.1:{port}/v1",
        }
        entry["tokenSource"] = "manual"
        settings_data["lastUsedProvider"] = "openai-compatible"
        settings_data.setdefault("version", 1)
        providers_path.write_text(json.dumps(settings_data, ensure_ascii=False, indent=2), encoding="utf-8")
        effort = os.environ.get("CARD_LAUNCHER_EFFORT", "max")
        # Cline 的 --thinking 只接受 none|low|medium|high|xhigh（max 不接受，实测会直接报错退出）。
        # 把派卡器的 max 档映射到 xhigh，其余按原档位透传。
        cline_thinking = {"max": "xhigh", "xhigh": "xhigh", "high": "high",
                          "medium": "medium", "low": "low", "none": "none"}.get(
                              str(effort).lower(), "high")
        command = [cli, str(cline_script), "--data-dir", str(data_dir),
                   "--provider", "openai-compatible", "--model", model,
                   "--cwd", str(Path.cwd()), "--auto-approve", "true", "--json"]
        command[2:2] = ["--thinking", cline_thinking]
        command.append(prompt)
        # Cline 从位置参数取 prompt；stdin 不能再灌一遍，否则 prompt 重复两次。
        stdin_bytes = b""
    else:
        raise ValueError(f"unsupported bridge CLI: {kind}")

    server = subprocess.Popen(server_args, cwd=str(Path.cwd()), env=env,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=None,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        _health(health, server, expected_model=model)
        child = subprocess.Popen(_spawn_args(command), cwd=str(Path.cwd()), env=env,
                                 stdin=subprocess.PIPE, stdout=None, stderr=None,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            child.communicate(stdin_bytes if stdin_bytes is not None else prompt.encode("utf-8", errors="replace"), timeout=3600)
            return child.returncode
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            return 124
        except BaseException:
            if child.poll() is None:
                child.kill()
                child.communicate()
            raise
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()


if __name__ == "__main__":
    SUPPORTED_KINDS = {"agy", "claude", "cline"}
    if len(sys.argv) != 2 or sys.argv[1] not in SUPPORTED_KINDS:
        raise SystemExit("usage: bridge_runner.py " + "|".join(sorted(SUPPORTED_KINDS)))
    if not os.environ.get("CARD_LAUNCHER_MODEL", DEFAULT_MODEL):
        raise SystemExit("MiniMax model is not selected")
    # The parent card launcher writes UTF-8 bytes; Windows' OEM code page may
    # otherwise decode Chinese prompt text into surrogate-escaped fragments.
    prompt_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    raise SystemExit(_run_bridge_cli(sys.argv[1], prompt_text))
