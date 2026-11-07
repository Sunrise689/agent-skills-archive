"""Claude Code card pinned to the local MiniMax Anthropic-compatible bridge."""
from __future__ import annotations
import json
import sys
from pathlib import Path

CHANNEL = "claude"
RUNNER = Path(__file__).with_name("bridge_runner.py")
MODEL = "MiniMax-M3.1-Flash"


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    if not model or model.rsplit("/", 1)[-1] == "MiniMax-M3":
        raise ValueError("Claude bridge requires a selected MiniMax model; MiniMax-M3 is disabled")
    bootstrap = (
        "import os,runpy,sys; os.environ['CARD_LAUNCHER_MODEL']=" + json.dumps(model) + "; "
        "os.environ['CARD_LAUNCHER_EFFORT']=" + json.dumps(effort or "max") + "; "
        "sys.argv=['bridge_runner.py','claude']; runpy.run_path(r'" + str(RUNNER) + "',run_name='__main__')"
    )
    return [sys.executable, "-c", bootstrap], prompt_text
