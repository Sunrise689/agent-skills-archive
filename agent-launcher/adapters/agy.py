"""Antigravity CLI card using the local OpenAI-compatible MiniMax bridge."""
from __future__ import annotations
import json
import sys
from pathlib import Path

RUNNER = Path(__file__).with_name("bridge_runner.py")
MODEL = "MiniMax-M3.1-Flash"


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    if not model or model.rsplit("/", 1)[-1] == "MiniMax-M3":
        raise ValueError("Antigravity bridge requires a selected MiniMax model; MiniMax-M3 is disabled")
    # Bridge runner receives the override in its environment so it can refuse M3 or other models.
    return [sys.executable, "-c", (
        "import os,runpy,sys; os.environ['CARD_LAUNCHER_MODEL']=" + json.dumps(model) + "; "
        "sys.argv=['bridge_runner.py','agy']; runpy.run_path(r'" + str(RUNNER) + "',run_name='__main__')"
    )], prompt_text
