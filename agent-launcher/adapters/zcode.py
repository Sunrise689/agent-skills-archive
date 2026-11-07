"""ZCode Agent CLI adapter. Uses the official headless CLI through an isolated BYOK runner."""
from __future__ import annotations

import sys
from pathlib import Path


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    if not model or model.rsplit("/", 1)[-1] == "MiniMax-M3":
        raise ValueError("ZCode BYOK requires a selected MiniMax model; MiniMax-M3 is disabled")
    runner = Path(__file__).with_name("zcode_runner.py")
    return [sys.executable, str(runner), "--model", model, "--cwd", cwd], prompt_text
