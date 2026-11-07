"""OpenCursor Worker adapter（社区复刻，evaluate 模式，2026-10-18 接入）。

OpenCursor = PawanOsman/OpenCursor（MIT），非 Cursor 官方。
apiBaseUrl 用方舟 Agent Plan 的 OpenAI 兼容端点（连通性已实测 2026-10-18）。
"""
from __future__ import annotations

import sys
from pathlib import Path

CHANNEL = "opencursor"


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    if not model:
        raise ValueError("OpenCursor card requires a model selected at dispatch time")
    if write_scope != "workspace-write":
        raise ValueError("OpenCursor evaluate mode requires workspace-write scope")
    runner = Path(__file__).with_name("opencursor_runner.py")
    return [sys.executable, str(runner), "--model", model, "--cwd", cwd], prompt_text
