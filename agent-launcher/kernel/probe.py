"""kernel/probe.py — 并行探测 opencode 免费模型可用性。

只用 Python 3.12 标准库，Windows 兼容。
"""

from __future__ import annotations

import concurrent.futures as cf
import re
import shutil
import subprocess
import sys
import time
from typing import Any

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CANDIDATE_MODELS = [
    "opencode/big-pickle",
    "opencode/ling-3.1-flash-free",
    "opencode/longcat-2.5-preview-free",
    "opencode/mimo-v2.6-flash-free",
    "opencode/nemotron-3-ultra-free",
    "opencode/nemotron-3.5-lightning-free",
    "opencode/space-bunny-free",
    "opencode/step-5-preview-free",
]

PROMPT = "只回复两个字：收到"
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _resolve_opencode() -> str:
    path = shutil.which("opencode")
    if not path:
        raise FileNotFoundError("opencode not found on PATH")
    return path


def _run_one(model: str, timeout: int) -> dict[str, Any]:
    t0 = time.time()
    exe = _resolve_opencode()
    base = [exe, "run", "-m", model, PROMPT]
    args = ["cmd", "/c", *base] if exe.lower().endswith((".cmd", ".bat")) else base

    p = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    try:
        out, _ = p.communicate(timeout=timeout)
        dt = time.time() - t0
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(p.pid)],
                capture_output=True,
                timeout=15,
            )
        except Exception:
            pass
        try:
            out, _ = p.communicate(timeout=10)
        except Exception:
            out = ""
        dt = time.time() - t0
        return {"model": model, "ok": False, "latency": dt, "note": "TIMEOUT"}

    dt = time.time() - t0
    clean = ANSI_RE.sub("", out or "")
    lines = [ln.strip() for ln in clean.splitlines() if ln.strip()]
    body = [ln for ln in lines if not ln.startswith("> ") and ln != "build"]
    text = " ".join(body).strip()
    low = text.lower()

    if "error" in low or "deprecated" in low or "not available" in low:
        return {"model": model, "ok": False, "latency": dt, "note": text[:110] or "FAIL"}
    if not text:
        return {"model": model, "ok": False, "latency": dt, "note": "EMPTY"}
    if "收到" in text:
        return {"model": model, "ok": True, "latency": dt, "note": text[:110]}

    return {"model": model, "ok": False, "latency": dt, "note": text[:110] or "UNEXPECTED"}


def probe_opencode_free(timeout: int = 75) -> list[dict]:
    """并行探测 opencode/* 免费模型。

    Returns:
        list[dict]: 每项 {"model": str, "ok": bool, "latency": float, "note": str}
    """
    results: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=len(CANDIDATE_MODELS)) as ex:
        futures = [ex.submit(_run_one, m, timeout) for m in CANDIDATE_MODELS]
        for f in cf.as_completed(futures):
            results.append(f.result())
    results.sort(key=lambda r: (not r["ok"], r["latency"]))
    return results


def probe_all(timeout: int = 75) -> dict:
    """探测所有通道，返回汇总字典。"""
    return {"opencode_free": probe_opencode_free(timeout)}


if __name__ == "__main__":
    import json

    print("probe_opencode_free 自测（并行，timeout=30s）...")
    res = probe_opencode_free(timeout=30)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    ok_count = sum(1 for r in res if r["ok"])
    print(f"\n可用模型: {ok_count}/{len(res)}")
    print("OK")
    sys.exit(0)
