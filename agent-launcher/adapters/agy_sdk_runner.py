"""Run the Antigravity SDK as a tool-capable agent over the local MiniMax bridge."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from typing import Any

from google.antigravity import Agent, CapabilitiesConfig, LocalOpenAIAgentConfig, types


ROOT = Path(__file__).resolve().parent
SHIM = Path(os.environ.get("CARD_GATEWAY_SCRIPT", str(ROOT / "minimax_agy_shim.py")))
MODEL = os.environ.get("CARD_LAUNCHER_MODEL", "MiniMax-M3.1-Flash")
SKILLS_ROOT = Path.home() / ".agents" / "skills"
KNOWLEDGE_ROOT = (
    Path.home() / "Desktop" / "hd" / "basic-memory" / "记忆库" / "user"
    / "U卡标准库" / "knowledge"
)
SMI_ROOT = (
    Path.home() / "Desktop" / "hd" / "basic-memory" / "记忆库" / "user" / "SMI"
)
SMI_REGISTRY = SMI_ROOT / "registry_networked.jsonl"
SKILL_SOURCE_ROOT = Path.home() / "Desktop" / "hd" / "工具库" / "skills_armory" / "raw"
MAX_SMI_RESULTS = 10
MAX_SMI_SKILL_CHARS = 24000


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_healthy(proc: subprocess.Popen, url: str) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("MiniMax bridge exited before becoming healthy")
        try:
            with urllib.request.urlopen(url, timeout=0.5) as response:
                data = json.loads(response.read())
                if data.get("ok") and data.get("model") == MODEL:
                    return
        except Exception:
            time.sleep(0.2)
    raise TimeoutError("MiniMax bridge health check timed out")


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _stage_readonly_references(prompt: str, workdir: Path) -> tuple[str, dict[str, str]]:
    """Copy only this card's selected base skill and SMI guide into its workspace."""
    reference_root = workdir / ".card_reference"
    staged: dict[str, str] = {}
    match = re.search(
        r"(?m)^# BASE SKILL \(read before work\)\s*\n([^\r\n]+)", prompt
    )
    if not match:
        raise RuntimeError("AG SDK prompt does not declare its selected BASE SKILL path")
    source = Path(match.group(1).strip())
    if not source.is_file() or not _path_is_within(source, SKILLS_ROOT):
        raise RuntimeError(f"selected BASE SKILL is missing or outside the installed skills root: {source}")

    base_target = reference_root / "base_skill" / "SKILL.md"
    base_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, base_target)
    staged["base_skill_source"] = str(source)
    staged["base_skill_workspace_copy"] = str(base_target)

    guide_source = KNOWLEDGE_ROOT / "03-SMI与知识装载.md"
    guide_target = reference_root / "knowledge" / guide_source.name
    guide_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(guide_source, guide_target)
    staged["smi_guide_source"] = str(guide_source)
    staged["smi_guide_workspace_copy"] = str(guide_target)

    index_source = KNOWLEDGE_ROOT / "INDEX.md"
    if index_source.is_file():
        index_target = reference_root / "knowledge" / index_source.name
        shutil.copyfile(index_source, index_target)
        staged["knowledge_index_workspace_copy"] = str(index_target)

    note = (
        "\n\n# Workspace-readable user references\n"
        "The AG SDK workspace is isolated. The card-launcher staged byte-for-byte, read-only "
        "copies of the selected base skill and card-side SMI guide from their canonical sources. "
        f"Read the base skill at `{base_target}` and the SMI guide at `{guide_target}`. "
        "For targeted SMI discovery, call the read-only SDK tools `search_smi(query, max_results)` "
        "and then `load_smi_skill(skill_name)`. These tools read the canonical SMI registry and "
        "a selected skill file under the verified skill-source roots. The card-launcher lifecycle "
        "MCP is not exposed to this card.\n"
    )
    return prompt + note, staged


def read_local_file(path: str) -> str:
    """Read exact UTF-8 contents through the explicitly authorized full-access host tool."""
    if os.environ.get("CARD_FULL_ACCESS") != "1":
        raise PermissionError("full-access host tools were not authorized")
    return Path(path).resolve().read_text(encoding="utf-8-sig")


def write_local_file(path: str, content: str) -> str:
    """Write exact UTF-8 contents, including authorized paths outside the SDK workspace."""
    if os.environ.get("CARD_FULL_ACCESS") != "1":
        raise PermissionError("full-access host tools were not authorized")
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def run_local_command(command: str) -> str:
    """Execute an authorized PowerShell command with the card's full user access."""
    if os.environ.get("CARD_FULL_ACCESS") != "1":
        raise PermissionError("full-access host tools were not authorized")
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return json.dumps({"exit": result.returncode, "stdout": result.stdout[-16000:], "stderr": result.stderr[-4000:]})


def search_smi(query: str, max_results: int = 5) -> str:
    """Search the canonical SMI registry by task terms; returns at most 10 skill entries."""
    query = str(query or "").strip()
    if not query:
        return json.dumps({"ok": False, "error": "query must not be empty"}, ensure_ascii=False)
    limit = max(1, min(int(max_results), MAX_SMI_RESULTS))
    terms = [term.casefold() for term in re.findall(r"[a-zA-Z0-9_+.-]+|[\u3400-\u9fff]{2,}", query)]
    if not terms:
        terms = [query.casefold()]
    rows: list[tuple[int, dict[str, Any]]] = []
    try:
        with SMI_REGISTRY.open("r", encoding="utf-8") as source:
            for line in source:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                fields = [item.get(key, []) for key in ("name", "aliases", "tags", "free", "domains", "paths")]
                searchable = json.dumps(fields, ensure_ascii=False).casefold()
                score = sum(1 for term in terms if term in searchable)
                if score:
                    rows.append((score, item))
    except OSError as exc:
        return json.dumps({"ok": False, "error": f"cannot read canonical SMI registry: {exc}"}, ensure_ascii=False)
    rows.sort(key=lambda row: (-row[0], str(row[1].get("name", ""))))
    results = []
    for score, item in rows[:limit]:
        results.append({
            "name": item.get("name"),
            "aliases": item.get("aliases", []),
            "paths": item.get("paths", []),
            "tags": item.get("tags", []),
            "free": item.get("free", []),
            "domains": item.get("domains", []),
            "match_score": score,
        })
    return json.dumps({"ok": True, "query": query, "count": len(results), "results": results}, ensure_ascii=False)


def load_smi_skill(skill_name: str) -> str:
    """Read one exact SMI skill by registered name; rejects paths outside approved read-only roots."""
    wanted = str(skill_name or "").strip().casefold()
    if not wanted:
        return json.dumps({"ok": False, "error": "skill_name must not be empty"}, ensure_ascii=False)
    matches: list[dict[str, Any]] = []
    try:
        with SMI_REGISTRY.open("r", encoding="utf-8") as source:
            for line in source:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                names = [item.get("name", ""), *item.get("aliases", [])]
                if any(str(name).casefold() == wanted for name in names):
                    matches.append(item)
    except OSError as exc:
        return json.dumps({"ok": False, "error": f"cannot read canonical SMI registry: {exc}"}, ensure_ascii=False)
    if len(matches) != 1:
        return json.dumps({"ok": False, "error": "skill name must resolve to exactly one SMI entry", "matches": len(matches)}, ensure_ascii=False)

    item = matches[0]
    for raw_path in item.get("paths", []):
        candidate = Path(str(raw_path))
        if not candidate.is_absolute():
            candidate = SKILL_SOURCE_ROOT / candidate
        try:
            candidate = candidate.resolve(strict=True)
        except (OSError, ValueError):
            continue
        if not candidate.is_file() or candidate.name.casefold() != "skill.md":
            continue
        if not (_path_is_within(candidate, SKILL_SOURCE_ROOT) or _path_is_within(candidate, SKILLS_ROOT)):
            continue
        try:
            content = candidate.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        truncated = len(content) > MAX_SMI_SKILL_CHARS
        if truncated:
            content = content[:MAX_SMI_SKILL_CHARS] + "\n\n[truncated by the read-only SMI loader]"
        return json.dumps({
            "ok": True,
            "name": item.get("name"),
            "source_path": str(candidate),
            "truncated": truncated,
            "content": content,
        }, ensure_ascii=False)
    return json.dumps({"ok": False, "name": item.get("name"), "error": "no registered skill file found under approved read-only roots"}, ensure_ascii=False)


async def _run(prompt: str) -> int:
    workdir = Path.cwd().resolve()
    prompt, staged = _stage_readonly_references(prompt, workdir)
    print("AG_SDK_REFERENCE_STAGING", json.dumps(staged, ensure_ascii=False), flush=True)
    port = _free_port()
    env = os.environ.copy()
    env.update({
        "CARD_USAGE_FILE": str(Path.cwd() / ".card_usage" / ("usage_pid%d_ag.jsonl" % os.getpid())),
        "CARD_USAGE_CHANNEL": "agy",
        "MINIMAX_SHIM_HOST": "127.0.0.1",
        "MINIMAX_SHIM_PORT": str(port),
        "MINIMAX_SHIM_TIMEOUT": "240",
        # 【2026-10-22 晚】上游 MiniMax 侧持续抖动时，3 次重试不够用
        # （AGU2/AGU3/AGU4 连续三轮都被 RemoteDisconnected 打死）→ 提到 5 次。
        "MINIMAX_SHIM_ATTEMPTS": "5",
        "MINIMAX_MODEL": MODEL,
        "PI_MODELS_JSON": str(Path.home() / ".pi" / "agent" / "models.json"),
    })
    server = subprocess.Popen(
        [sys.executable, str(SHIM)], cwd=str(workdir), env=env,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=None,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        _wait_healthy(server, f"http://127.0.0.1:{port}/health")
        cfg = LocalOpenAIAgentConfig(
            model=MODEL,
            base_url=f"http://127.0.0.1:{port}/v1",
            workspaces=[str(workdir)],
            tools=[search_smi, load_smi_skill] + ([read_local_file, write_local_file, run_local_command] if os.environ.get("CARD_FULL_ACCESS") == "1" else []),
            capabilities=CapabilitiesConfig(enabled_tools=[
                types.BuiltinTools.LIST_DIR,
                types.BuiltinTools.SEARCH_DIR,
                types.BuiltinTools.FIND_FILE,
                types.BuiltinTools.EDIT_FILE,
                types.BuiltinTools.RUN_COMMAND,
                types.BuiltinTools.CREATE_FILE,
                types.BuiltinTools.VIEW_FILE,
                types.BuiltinTools.FINISH,
            ]),
        )
        if os.environ.get("CARD_FULL_ACCESS") == "1":
            prompt += "\nFull access is explicitly authorized for the task. Use read_local_file / write_local_file for exact file contents and authorized paths outside the SDK workspace. These host tools have no SDK artifact-directory restriction. run_local_command is the full-access PowerShell tool. Respect the taskbook scope.\n"
        async with Agent(cfg) as agent:
            response = await agent.chat(prompt)
            print("AG_SDK_RESPONSE", await response.text(), flush=True)
            calls = []
            async for call in response.tool_calls:
                calls.append(call.name)
            print("AG_SDK_TOOL_CALLS", json.dumps(calls), flush=True)
            if not calls:
                raise RuntimeError("model did not invoke any SDK tools")
        return 0
    finally:
        if server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


def main() -> int:
    if os.environ.get("CARD_LAUNCHER_MODEL") != MODEL:
        raise SystemExit(f"AG SDK bridge is pinned to {MODEL}")
    prompt = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    return asyncio.run(_run(prompt))


if __name__ == "__main__":
    raise SystemExit(main())
