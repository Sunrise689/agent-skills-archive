"""GitHub Copilot CLI adapter; model is supplied at dispatch time."""
from __future__ import annotations
import shutil
import sys
from pathlib import Path

CHANNEL = "copilot"
NODE = Path(r"C:\Program Files\nodejs\node.exe")
SCRIPT = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@github" / "copilot" / "npm-loader.js"


def resolve_exe() -> str:
    node = shutil.which("node") or str(NODE)
    if not Path(node).is_file() or not SCRIPT.is_file():
        raise FileNotFoundError(f"GitHub Copilot CLI or Node runtime missing: {SCRIPT}")
    return str(Path(node).resolve())


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    if model.startswith("MiniMax-"):
        if model == "MiniMax-M3":
            raise ValueError("MiniMax-M3 is disabled for BYOK cards")
        runner = Path(__file__).with_name("minimax_copilot_runner.py")
        return [sys.executable, str(runner), "--model", model], prompt_text
    argv = [resolve_exe(), str(SCRIPT), "--prompt", prompt_text, "--model", model,
            "--allow-all-tools", "--add-dir", cwd, "-C", cwd, "--silent"]
    if effort:
        argv += ["--reasoning-effort", effort]
    return argv, None
