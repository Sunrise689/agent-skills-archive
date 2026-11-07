"""Kimi Code CLI adapter; model selection is mandatory at dispatch time."""
from __future__ import annotations

import sys
from pathlib import Path


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    if not model:
        raise ValueError("Kimi Code card requires a model selected at dispatch time")
    runner = Path(__file__).with_name("minimax_kimi_runner.py")
    return [sys.executable, str(runner), "--model", model], prompt_text
