"""opencode adapter — CHANNEL / resolve_exe / build.

T8 第一幕 P 卡产物。只用 Python 3.12 标准库，Windows 兼容。
build 约定（本卡任务书细则，优先于契约第 2 节的二选一描述）：
  argv   = [opencode, run, -m, <model>, --auto] + ([--variant, <effort>] 若 effort 非空)
  prompt 经 stdin 传递：stdin_text = prompt_text

集成期修正（2026-10-09，user 收尾幕）：补 `--auto`。opencode 默认 auto-reject
外部目录读；不放开权限时卡读不到卡库知识文件而失败（见 HANDOFF.md 坑 2）。
函数签名 CHANNEL/resolve_exe/build 未变。effort 传 None 时不加 --variant（OC profile 的
reasoning_effort 是说明串，不是合法 variant 值，调用方须传 None）。
可执行入口用 shutil.which('opencode') 定位；.cmd/.bat 由调用方包 cmd /c。
"""

from __future__ import annotations

import shutil
from pathlib import Path

CHANNEL = "opencode"

# 2026-10-09 集成期修正：只放行真实存在的 variant 值；
# OC profile 的 reasoning_effort 是说明串（如 medium_if_supported_else_unset），
# 原样传给 --variant 会让 opencode 报错。非白名单值一律忽略。
_VALID_VARIANTS = {"minimal", "low", "medium", "high", "xhigh", "max"}


def resolve_exe(name: str) -> str:
    """shutil.which 定位可执行入口；返回绝对路径（找不到抛 FileNotFoundError）。

    .cmd/.bat 的 cmd /c 包裹由调用方处理，此处只回原始绝对路径。
    2026-10-22：卡进程 PATH 可能不含 npm 全局目录（与 codex.py 同款兜底），
    此时回落到 %APPDATA%\Roaming\npm 下的 native 可执行文件。
    """
    path = shutil.which(name)
    if not path and name == CHANNEL:
        npm = Path.home() / "AppData" / "Roaming" / "npm"
        candidates = [
            npm / "node_modules/opencode-ai/bin/opencode.exe",
            npm / "opencode.CMD",
        ]
        path = next((str(c) for c in candidates if c.is_file()), None)
    if not path:
        raise FileNotFoundError(f"executable not found on PATH (nor npm fallback): {name}")
    return path


def build(profile: dict, model: str, effort: str | None,
          prompt_text: str, cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    """构造 opencode 启动命令。

    返回 (argv, stdin_text)；prompt 经 stdin（stdin_text=prompt_text）。
    profile / cwd / write_scope 在 opencode 通道下不参与命令构造，
    仅为跨 adapter 统一签名保留。
    """
    exe = resolve_exe(CHANNEL)
    argv: list[str] = [exe, "run", "-m", model, "--auto"]
    if effort and effort in _VALID_VARIANTS:
        argv += ["--variant", effort]
    return argv, prompt_text


if __name__ == "__main__":
    import json
    import sys

    profile = {"profile_id": "CX-U-04"}
    argv, stdin_text = build(profile, "opencode/poolside/laguna-s-2.1:free",
                             None, "hello prompt", "C:\\", "read-only")
    assert isinstance(argv, list) and all(isinstance(x, str) for x in argv)
    assert stdin_text == "hello prompt"
    assert argv[1:4] == ["run", "-m", "opencode/poolside/laguna-s-2.1:free"]
    assert argv[4] == "--auto"
    assert "--variant" not in argv

    argv2, stdin2 = build(profile, "m", "xhigh", "p2", "C:\\", "read-only")
    assert argv2[4:] == ["--auto", "--variant", "xhigh"], argv2
    assert stdin2 == "p2"

    print(json.dumps({"argv": argv, "stdin": stdin_text}, ensure_ascii=False))
    print("OK")
    sys.exit(0)
