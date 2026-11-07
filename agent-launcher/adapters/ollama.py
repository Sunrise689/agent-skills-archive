"""Ollama adapter for the local model channel.

Local models have no sandbox and no reasoning effort setting. Concurrency is
managed by the Ollama server through ``OLLAMA_NUM_PARALLEL``, not by this
adapter.
"""

from __future__ import annotations

import os
import shutil

CHANNEL = "ollama"


def _candidate_paths(name: str) -> list[str]:
    """PATH first, then the default Windows install locations."""
    found = shutil.which(name)
    paths = [found] if found else []
    local = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("PROGRAMFILES", r"C:\Program Files")
    for base in (local and os.path.join(local, "Programs", "Ollama"),
                 os.path.join(program_files, "Ollama")):
        if base:
            paths.append(os.path.join(base, "ollama.exe"))
    return paths


def resolve_exe(name: str = "ollama") -> str:
    r"""Return the Ollama executable path, or raise FileNotFoundError.

    2026-10-09 A3 集成期修正：本机 ollama.exe 装在
    ``%LOCALAPPDATA%\Programs\Ollama\ollama.exe``，但**不在 PATH 上**，
    shutil.which 找不到；补上默认安装位置兜底。
    """
    for path in _candidate_paths(name):
        if path and os.path.isfile(path):
            return path
    raise FileNotFoundError(
        f"executable not found on PATH or default install dirs: {name}"
    )


def build(profile: dict, model: str, effort: str | None,
          prompt_text: str, cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    """Build an Ollama CLI invocation; the prompt is supplied on stdin."""
    exe = os.path.abspath(resolve_exe())
    argv: list[str] = [exe, "run", model]
    return argv, prompt_text


if __name__ == "__main__":
    import sys

    model = "qwen3:4b-instruct-2507-q4_K_M"
    try:
        argv, stdin_text = build({}, model, None, "hello prompt", "C:\\", "read-only")
    except FileNotFoundError:
        print("OK (ollama not installed)")
        sys.exit(0)

    assert isinstance(argv, list) and all(isinstance(item, str) for item in argv)
    assert stdin_text is None or isinstance(stdin_text, str)
    assert argv[1:3] == ["run", model]
    assert os.path.isabs(argv[0])
    assert os.path.splitext(os.path.basename(argv[0]))[0].lower().endswith("ollama")
    assert stdin_text == "hello prompt"
    print("OK")
