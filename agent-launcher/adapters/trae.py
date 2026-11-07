"""TRAE CLI adapter using the local MiniMax Token Plan custom provider."""
from __future__ import annotations
import sys
from pathlib import Path


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    if model != "MiniMax-M3.1-Flash":
        raise ValueError("TRAE BYOK adapter only permits MiniMax-M3.1-Flash")
    runner = Path(__file__).with_name("trae_runner.py")
    return [sys.executable, str(runner), "--model", model, "--cwd", cwd], prompt_text
