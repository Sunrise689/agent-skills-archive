"""Smart Agent S Card MCP server.

This is the only active S Card MCP entry.  It exposes Smart Agent's native
cruise, exploration, and one-shot S Card operations; the former
ShowSupervisor tool names are intentionally not retained.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
NODE = Path(os.environ.get("SMART_AGENT_NODE", r"C:\Program Files\nodejs\node.exe"))
CLI = ROOT / "src" / "cli.mjs"
STATE_ROOT = Path(os.environ.get("SMART_AGENT_MCP_STATE", os.path.join(os.environ.get("LOCALAPPDATA", str(Path.home())), "smart-agent-mcp")))
LOG_ROOT = STATE_ROOT / "logs"
STATE_ROOT.mkdir(parents=True, exist_ok=True)
LOG_ROOT.mkdir(parents=True, exist_ok=True)


def _job_id(prefix: str = "scard") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _run(args: list[str], *, cwd: str | None = None, timeout: int = 120) -> Any:
    completed = subprocess.run(
        [str(NODE), str(CLI), *args],
        cwd=cwd or str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        raise RuntimeError(detail)
    output = completed.stdout.strip()
    if not output:
        return {"ok": True}
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return {"ok": True, "text": output}


def _spawn(args: list[str], *, cwd: str, job_id: str) -> dict[str, Any]:
    log_path = LOG_ROOT / f"{job_id}.log"
    log = log_path.open("w", encoding="utf-8")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    process = subprocess.Popen(
        [str(NODE), str(CLI), *args],
        cwd=cwd,
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    log.close()
    return {"jobId": job_id, "pid": process.pid, "logPath": str(log_path), "workspace": str(Path(cwd).resolve())}


def _workspace(value: str | None) -> str:
    path = Path(value or os.getcwd()).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"workspace 不存在或不是目录: {path}")
    return str(path)


TOOLS = [
    {
        "name": "smart_agent_scard_run",
        "description": "启动一次 Smart Agent S 卡任务，使用最新版 S 卡系统提示词；返回进程和日志位置。",
        "inputSchema": {"type": "object", "properties": {"goal": {"type": "string"}, "workspace": {"type": "string"}, "attachments": {"type": "array", "items": {"type": "string"}}}, "required": ["goal"], "additionalProperties": False},
    },
    {
        "name": "smart_agent_cruise_start",
        "description": "启动可暂停、可恢复、可定时唤醒的 Smart Agent S 卡巡航任务。",
        "inputSchema": {"type": "object", "properties": {"goal": {"type": "string"}, "workspace": {"type": "string"}, "job_id": {"type": "string"}, "exploration_id": {"type": "string"}}, "required": ["goal"], "additionalProperties": False},
    },
    {
        "name": "smart_agent_cruise_status",
        "description": "读取 S 卡巡航的持久化 checkpoint。",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"], "additionalProperties": False},
    },
    {
        "name": "smart_agent_cruise_pause",
        "description": "暂停 S 卡巡航并写入 checkpoint。",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"], "additionalProperties": False},
    },
    {
        "name": "smart_agent_cruise_stop",
        "description": "停止 S 卡巡航并标记为不可自动恢复。",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"], "additionalProperties": False},
    },
    {
        "name": "smart_agent_cruise_resume",
        "description": "从持久化 checkpoint 恢复 S 卡巡航。",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"], "additionalProperties": False},
    },
    {
        "name": "smart_agent_cruise_wake",
        "description": "由外部定时任务唤醒 S 卡巡航，沿用原 runId 和 graph checkpoint。",
        "inputSchema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"], "additionalProperties": False},
    },
    {
        "name": "smart_agent_explore_start",
        "description": "创建 Smart Agent exploration-mode 的长期探索状态。",
        "inputSchema": {"type": "object", "properties": {"question": {"type": "string"}, "workspace": {"type": "string"}, "max_rounds": {"type": "integer", "minimum": 1}}, "required": ["question"], "additionalProperties": False},
    },
    {
        "name": "smart_agent_explore_add_round",
        "description": "向探索状态追加一轮事实、假设、实验、结果、下一步和证据。",
        "inputSchema": {"type": "object", "properties": {"exploration_id": {"type": "string"}, "facts": {"type": "array", "items": {"type": "string"}}, "hypothesis": {"type": "string"}, "experiment": {"type": "string"}, "result": {"type": "string"}, "next_action": {"type": "string"}, "evidence": {"type": "array", "items": {"type": "string"}}}, "required": ["exploration_id", "facts", "hypothesis", "experiment", "result", "next_action", "evidence"], "additionalProperties": False},
    },
    {
        "name": "smart_agent_explore_status",
        "description": "读取 exploration-mode 状态。",
        "inputSchema": {"type": "object", "properties": {"exploration_id": {"type": "string"}}, "required": ["exploration_id"], "additionalProperties": False},
    },
    {
        "name": "smart_agent_explore_update",
        "description": "暂停、恢复、停止或完成 exploration-mode。",
        "inputSchema": {"type": "object", "properties": {"exploration_id": {"type": "string"}, "status": {"type": "string", "enum": ["active", "paused", "stopped", "completed"]}, "reason": {"type": "string"}}, "required": ["exploration_id", "status"], "additionalProperties": False},
    },
]


def call(name: str, args: dict[str, Any]) -> Any:
    if name == "smart_agent_scard_run":
        goal = str(args["goal"]).strip()
        if not goal:
            raise ValueError("goal 不能为空")
        workspace = _workspace(args.get("workspace"))
        job_id = _job_id("scard")
        command = ["s-card", "run", "--goal", goal]
        for attachment in args.get("attachments", []):
            command.extend(["--attach", str(attachment)])
        return {"mode": "s-card", **_spawn(command, cwd=workspace, job_id=job_id)}
    if name == "smart_agent_cruise_start":
        goal = str(args["goal"]).strip()
        if not goal:
            raise ValueError("goal 不能为空")
        workspace = _workspace(args.get("workspace"))
        job_id = str(args.get("job_id") or _job_id("cruise"))
        command = ["s-card", "cruise", "start", "--goal", goal, "--workspace", workspace, "--job-id", job_id]
        if args.get("exploration_id"):
            command.extend(["--exploration-id", str(args["exploration_id"])])
        return {"mode": "s-card-cruise", **_spawn(command, cwd=workspace, job_id=job_id)}
    if name == "smart_agent_cruise_status":
        return _run(["cruise", "status", str(args["job_id"])])
    if name == "smart_agent_cruise_pause":
        return _run(["cruise", "pause", str(args["job_id"])])
    if name == "smart_agent_cruise_stop":
        return _run(["cruise", "stop", str(args["job_id"])])
    if name in {"smart_agent_cruise_resume", "smart_agent_cruise_wake"}:
        return _run(["s-card", "cruise", "wake" if name.endswith("wake") else "resume", str(args["job_id"])], timeout=600)
    if name == "smart_agent_explore_start":
        command = ["explore", "start", "--question", str(args["question"]), "--workspace", _workspace(args.get("workspace"))]
        if args.get("max_rounds") is not None:
            command.extend(["--max-rounds", str(args["max_rounds"])])
        return _run(command)
    if name == "smart_agent_explore_add_round":
        command = ["explore", "add-round", str(args["exploration_id"]), "--facts", "|".join(args["facts"]), "--hypothesis", str(args["hypothesis"]), "--experiment", str(args["experiment"]), "--result", str(args["result"]), "--next-action", str(args["next_action"]), "--evidence", "|".join(args["evidence"])]
        return _run(command)
    if name == "smart_agent_explore_status":
        return _run(["explore", "status", str(args["exploration_id"])])
    if name == "smart_agent_explore_update":
        action = {"active": "resume", "paused": "pause", "stopped": "stop", "completed": "complete"}[args["status"]]
        command = ["explore", action, str(args["exploration_id"])]
        if args.get("reason"):
            command.extend(["--reason", str(args["reason"])])
        return _run(command)
    raise ValueError(f"unknown Smart Agent tool: {name}")


def handle(message: dict[str, Any]) -> dict[str, Any] | None:
    if message.get("id") is None:
        return None
    method = message.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": message["id"], "result": {"protocolVersion": message.get("params", {}).get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}}, "serverInfo": {"name": "smart-agent-s-card", "version": "0.2.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": message["id"], "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params", {})
        try:
            value = call(str(params.get("name")), params.get("arguments") or {})
            return {"jsonrpc": "2.0", "id": message["id"], "result": {"content": [{"type": "text", "text": _json_text(value)}], "isError": False}}
        except Exception as exc:
            return {"jsonrpc": "2.0", "id": message["id"], "result": {"content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}], "isError": True}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": message["id"], "result": {}}
    return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": f"Method not found: {method}"}}


def main() -> None:
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            response = handle(json.loads(line))
            if response is not None:
                print(json.dumps(response, ensure_ascii=False), flush=True)
        except json.JSONDecodeError:
            print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}), flush=True)


if __name__ == "__main__":
    main()
