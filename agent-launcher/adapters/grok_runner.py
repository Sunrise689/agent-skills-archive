"""Run a Grok Build single-turn task with the card prompt on stdin."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"), default="low")
    parser.add_argument("--cwd", required=True)
    args = parser.parse_args()
    prompt = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    exe = shutil.which("grok")
    if not exe:
        raise FileNotFoundError("Grok Build executable 'grok' is not on PATH")
    env = os.environ.copy()
    command = [
        exe,
        "--single",
        prompt,
        "--cwd",
        args.cwd,
        "--model",
        args.model,
        "--reasoning-effort",
        args.effort,
        "--always-approve",
        "--output-format",
        "plain",
    ]
    return subprocess.run(command, cwd=args.cwd, env=env, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
