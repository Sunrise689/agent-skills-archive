"""MiniMax Code CLI adapter using the per-dispatch model override."""
from __future__ import annotations

import sys
from pathlib import Path


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    if not model:
        raise ValueError("MiniMax Code card requires a model selected at dispatch time")
    runner = Path(__file__).with_name("minimax_code_runner.py")
    return [sys.executable, str(runner), "--model", model, "--cwd", cwd], prompt_text
