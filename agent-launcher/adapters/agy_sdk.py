"""Antigravity SDK wrapper adapter for MiniMax bridge dispatch."""
from __future__ import annotations

import json
from pathlib import Path

MODEL = "MiniMax-M3.1-Flash"
ADAPTER_DIR = Path(__file__).resolve().parent
RUNNER = ADAPTER_DIR / "agy_sdk_runner.py"
VENV_PYTHON = ADAPTER_DIR / ".agy-sdk-venv" / "Scripts" / "python.exe"


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    if not model or model.rsplit("/", 1)[-1] == "MiniMax-M3":
        raise ValueError("AG SDK requires a selected MiniMax model; MiniMax-M3 is disabled")
    if not VENV_PYTHON.is_file():
        raise FileNotFoundError(f"Antigravity SDK runtime is not installed: {VENV_PYTHON}")
    bootstrap = (
        "import os,runpy,sys; os.environ['CARD_LAUNCHER_MODEL']=" + json.dumps(model) +
        "; sys.argv=['agy_sdk_runner.py']; runpy.run_path(r'" + str(RUNNER) +
        "',run_name='__main__')"
    )
    return [str(VENV_PYTHON), "-c", bootstrap], prompt_text
