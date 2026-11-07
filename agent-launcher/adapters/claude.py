"""claude adapter — CHANNEL / resolve_exe / build.

T7 第一幕 P 卡产物。只用 Python 3.12 标准库，Windows 兼容。
build 约定（契约第 0 节 CC_SETTINGS + 第 2 节 claude 行）：
  argv        = [<claude>, -p, --settings, CC_SETTINGS, --model, <model>, ...]
  stdin_text  = prompt_text
统一前置兜底：角色提示词已由 assembler 并入 prompt_text，通道不再注入
--append-system-prompt-file，避免两处系统提示词拼装顺序漂移。
可执行入口用 shutil.which('claude') 定位；.cmd/.bat 由调用方包 cmd /c。

build() 使用 profile.settings_file 指定的桥配置（缺省为 8902），并在派卡时
只做 TCP 预检；桥需由用户预先启动，本适配器不会在派卡路径上自动拉起进程。
--permission-mode bypassPermissions 用于非交互 -p 调用：工具权限提示无法通过
已关闭的 stdin 获得人工确认，否则文件写入可能以 Command aborted 结束。
--output-format stream-json 与 --verbose 配套，避免 print 模式只留下最终文本，
并让调用器重定向的日志保留流式事件和工具调用过程。
"""

from __future__ import annotations

import shutil
import json
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

CHANNEL = "claude"

CC_SETTINGS = r"~\Desktop\hd\工具库\cc_go_8902.json"  # 向后兼容缺省值；可由 profile.settings_file 覆盖。


def _bridge_endpoint(settings_file: str | Path) -> tuple[Path, str, int]:
    """Read the bridge endpoint from a Claude settings JSON file."""
    path = Path(settings_file).expanduser().resolve()
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
        base_url = settings["env"]["ANTHROPIC_BASE_URL"]
        parsed = urlsplit(base_url)
        host = parsed.hostname
        port = parsed.port
        if not host or port is None:
            raise ValueError("env.ANTHROPIC_BASE_URL must include a host and port")
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        # A missing/unreadable file cannot reveal its configured port; retain that
        # limitation explicitly rather than silently selecting the default bridge.
        port_text = "未知（配置文件不可读或无有效地址）"
        raise ValueError(
            f"Claude 桥配置无效：配置文件 {path}，端口 {port_text}；"
            f"这个桥可能没启动。原因：{exc}"
        ) from exc
    return path, host, port


def _probe_bridge(settings_file: str | Path) -> tuple[bool, str]:
    """Probe only TCP connectivity to the bridge configured in settings_file."""
    path, host, port = _bridge_endpoint(settings_file)
    endpoint = f"{host}:{port}"
    try:
        with socket.create_connection((host, port), timeout=2):
            return True, f"{endpoint} 在线"
    except (OSError, TimeoutError) as exc:
        return False, (
            f"{endpoint} 连不上（ConnectionRefused / 超时；{exc}），"
            f"配置 {path}，请先启动对应桥"
        )


def resolve_exe(name: str) -> str:
    """shutil.which 定位可执行入口；返回绝对路径（找不到抛 FileNotFoundError）。

    .cmd/.bat 的 cmd /c 包裹由调用方处理，此处只回原始绝对路径。
    """
    path = shutil.which(name)
    if not path and name == CHANNEL:
        # 2026-10-22：卡进程 PATH 可能不含 npm 全局目录（同 codex.py 兜底）
        npm = Path.home() / "AppData" / "Roaming" / "npm"
        candidates = [
            npm / "node_modules/@anthropic-ai/claude-code/bin/claude.exe",
            npm / "claude.CMD",
        ]
        path = next((str(c) for c in candidates if c.is_file()), None)
    if not path:
        raise FileNotFoundError(f"executable not found on PATH (nor npm fallback): {name}")
    return path


def build(profile: dict, model: str, effort: str | None,
          prompt_text: str, cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    """构造 claude 启动命令。

    返回 (argv, stdin_text)；prompt 全部经 stdin（stdin_text=prompt_text）。
    profile.settings_file 指定桥配置；缺省时使用 CC_SETTINGS。
    effort / cwd / write_scope 为跨 adapter 统一签名保留；
    cwd 由调用方传给进程启动器，权限与事件输出由下列 CLI 参数控制。
    """
    exe = resolve_exe(CHANNEL)
    settings_file = profile.get("settings_file") or CC_SETTINGS
    settings_path, _, port = _bridge_endpoint(settings_file)
    online, message = _probe_bridge(settings_path)
    if not online:
        raise ConnectionError(
            f"CC 桥预检失败：配置文件 {settings_path}，端口 {port}；{message}"
        )
    argv: list[str] = [
        exe,
        "-p",
        "--settings", str(settings_path),
        "--model", model,
        "--permission-mode", "bypassPermissions",
        "--output-format", "stream-json",
        "--verbose",
    ]
    return argv, prompt_text


if __name__ == "__main__":
    import json
    import sys
    from unittest.mock import patch

    profile = {"profile_id": "CC-U-04"}
    with patch.object(sys.modules[__name__], "resolve_exe", return_value="claude-test"), \
         patch.object(sys.modules[__name__], "_probe_bridge", return_value=(True, "127.0.0.1:8902 在线")):
        argv, stdin_text = build(profile, "claude-sonnet-5", "high",
                                 "hello prompt", "C:\\", "read-only")
    assert isinstance(argv, list) and all(isinstance(x, str) for x in argv)
    assert stdin_text == "hello prompt"
    assert argv[1:] == [
        "-p", "--settings", CC_SETTINGS, "--model", "claude-sonnet-5",
        "--permission-mode", "bypassPermissions",
        "--output-format", "stream-json", "--verbose",
    ]
    assert argv[0] == "claude-test"
    assert argv[3] == str(Path(CC_SETTINGS).resolve())
    assert CC_SETTINGS.endswith(r"cc_go_8902.json")
    assert "--append-system-prompt-file" not in argv

    # A profile without settings_file preserves the historical default bridge.
    assert argv[3] == str(Path(CC_SETTINGS).resolve())
    custom_settings = r"~\Desktop\hd\工具库\cc_or_settings.json"
    with patch.object(sys.modules[__name__], "resolve_exe", return_value="claude-test"), \
         patch.object(sys.modules[__name__], "_probe_bridge", return_value=(True, "127.0.0.1:8903 在线")):
        custom_argv, _ = build({"settings_file": custom_settings}, "m", None, "p", "C:\\", "read-only")
    assert custom_argv[3] == str(Path(custom_settings).resolve())

    print(json.dumps({"argv": argv, "stdin": stdin_text}, ensure_ascii=True))
    print("OK")
    sys.exit(0)
