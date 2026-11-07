"""Profile-specific adapter for CC-U-OR-free; vehicle remains Claude Code."""
from __future__ import annotations

import json
import sys
from pathlib import Path

CHANNEL = "claude"
RUNNER = Path(__file__).with_name("openrouter_claude_runner.py")
PROFILE_ID = "CC-U-OR-free"
MODEL = "openrouter/thinkingmachines/inkling-small:free"
EFFORT = "max"


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    if profile.get("id") not in (None, PROFILE_ID, "CC-U-OR-free-nemotron"):
        raise ValueError("OpenRouter Claude adapter is reserved for CC-U-OR-free")
    choices = {MODEL: "max", "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free": "high"}
    if model not in choices:
        raise ValueError("CC-U-OR-free pins openrouter/thinkingmachines/inkling-small:free")
    selected_effort = choices[model]
    if effort not in (None, selected_effort):
        raise ValueError("CC-U-OR-free pins the highest supported effort: max")
    bootstrap = (
        "import os,runpy,sys; os.environ['CARD_LAUNCHER_MODEL']=" + json.dumps(model) + "; "
        "os.environ['CARD_LAUNCHER_EFFORT']=" + json.dumps(selected_effort) + "; "
        "sys.argv=['openrouter_claude_runner.py']; runpy.run_path(r'" + str(RUNNER) + "',run_name='__main__')"
    )
    return [sys.executable, "-c", bootstrap], prompt_text
