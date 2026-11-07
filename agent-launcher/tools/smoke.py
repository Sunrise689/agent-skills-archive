#!/usr/bin/env python3
"""Run the card-launcher end-to-end smoke checks using only the standard library."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True


EXPECTED_TOOLS = [
    "launch_card",
    "launch_group",
    "check_status",
    "collect_report",
    "stop_card",
    "list_cards",
    "list_profiles",
]


class DependencyUnavailable(RuntimeError):
    """A not-yet-landed upstream file or helper makes a scenario inapplicable."""


_SERVER_MODULE = None
_SERVER_IMPORT_FILES = (
    "adapters/claude.py",
    "adapters/claude_minimax.py",
    "adapters/cline.py",
    "adapters/codex.py",
    "adapters/copilot.py",
    "adapters/agy.py",
    "adapters/ollama.py",
    "adapters/opencode.py",
    "adapters/trae.py",
    "adapters/zcode.py",
    "adapters/minimax_anthropic_bridge.py",
    "adapters/minimax_agy_shim.py",
    "adapters/bridge_runner.py",
    "kernel/assembler.py",
    "kernel/launcher.py",
    "kernel/ledger.py",
    "kernel/pools.py",
    "kernel/registry.py",
)


def _configure_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def _missing_server_files(root: Path) -> list[Path]:
    required = [root / "mcp" / "launcher_mcp_server.py"]
    required.extend(root / Path(item) for item in _SERVER_IMPORT_FILES)
    return [path for path in required if not path.is_file()]


def _server_module(root: Path):
    global _SERVER_MODULE
    if _SERVER_MODULE is not None:
        return _SERVER_MODULE

    missing = _missing_server_files(root)
    if missing:
        raise DependencyUnavailable(
            "MCP server import dependency not present: "
            + ", ".join(str(path) for path in missing)
        )
    server_path = root / "mcp" / "launcher_mcp_server.py"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("_card_launcher_smoke_target", server_path)
    if spec is None or spec.loader is None:
        raise DependencyUnavailable(f"cannot load MCP server module: {server_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as error:
        sys.modules.pop(spec.name, None)
        raise DependencyUnavailable(f"MCP import dependency is not ready: {error}") from error
    _SERVER_MODULE = module
    return module


def _scenario_tools(root: Path) -> str:
    missing = _missing_server_files(root)
    if missing:
        raise DependencyUnavailable(
            "MCP server import dependency not present: "
            + ", ".join(str(path) for path in missing)
        )
    server_path = root / "mcp" / "launcher_mcp_server.py"

    request_lines = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "card-launcher-smoke", "version": "1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    request_text = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in request_lines)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    old_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(root) + (os.pathsep + old_pythonpath if old_pythonpath else "")
    try:
        completed = subprocess.run(
            [sys.executable, str(server_path)],
            cwd=str(root),
            input=request_text,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(f"stdio MCP server exceeded 12s timeout: {error}") from error

    responses = {}
    malformed = []
    for line in completed.stdout.splitlines():
        try:
            response = json.loads(line)
        except json.JSONDecodeError:
            malformed.append(line[:160])
            continue
        if isinstance(response, dict) and response.get("id") in {1, 2}:
            responses[response["id"]] = response

    if completed.returncode != 0:
        raise AssertionError(
            f"MCP server exit={completed.returncode}; stderr={completed.stderr[-600:].strip()}"
        )
    if malformed:
        raise AssertionError(f"MCP stdout contained non-JSON lines: {malformed!r}")
    initialized = responses.get(1, {}).get("result", {})
    if not initialized.get("protocolVersion") or not initialized.get("serverInfo"):
        raise AssertionError(f"initialize response is incomplete: {responses.get(1)!r}")
    tool_result = responses.get(2, {}).get("result", {})
    tools = tool_result.get("tools")
    if not isinstance(tools, list):
        raise AssertionError(f"tools/list returned no tools array: {responses.get(2)!r}")
    names = [item.get("name") if isinstance(item, dict) else None for item in tools]
    if names != EXPECTED_TOOLS:
        raise AssertionError(f"expected exact ordered tools {EXPECTED_TOOLS!r}; got {names!r}")
    return f"MCP stdio initialize=OK; tools={len(names)}; order={','.join(names)}"


def _scenario_new_cli_profiles(root: Path) -> str:
    server = _server_module(root)
    profiles = server.assembler.load_profiles(str(server.LIB)).get("profiles", [])
    by_id = {item.get("id"): item for item in profiles if isinstance(item, dict)}
    expected = {
        "CL-U": ("Cline CLI", "MiniMax-M3.1-Flash"),
        "CL-L": ("Cline CLI", "MiniMax-M3.1-Flash"),
        "CP-U": ("GitHub Copilot CLI", "MiniMax-M3.1-Flash"),
        "CP-L": ("GitHub Copilot CLI", "MiniMax-M3.1-Flash"),
        "AG-U": ("Antigravity SDK Wrapper", "MiniMax-M3.1-Flash"),
        "AG-L": ("Antigravity SDK Wrapper", "MiniMax-M3.1-Flash"),
        "ZC-U": ("ZCode CLI", "MiniMax-M3.1-Flash"),
        "ZC-L": ("ZCode CLI", "MiniMax-M3.1-Flash"),
        "CC-U": ("Claude Code via MiniMax Bridge", "MiniMax-M3.1-Flash"),
    }
    for profile_id, (cli, model) in expected.items():
        profile = by_id.get(profile_id)
        if not isinstance(profile, dict) or (profile.get("cli"), profile.get("model")) != (cli, model):
            raise AssertionError(f"profile mismatch for {profile_id}: {profile!r}")
        vehicle, adapter = server._adapter_for_profile(profile)
        selected_model = model or (
            "MiniMax-M3.1-Flash"
            if profile_id in {"AG-U", "AG-L"}
            else "auto" if profile_id.startswith("CP-")
            else "smoke-model-override"
        )
        workdir = str(Path.cwd())
        argv, stdin = server._validated_command(
            adapter, profile, selected_model, None, "smoke", "workspace-write", workdir
        )
        if not argv or not isinstance(argv[0], str):
            raise AssertionError(f"adapter produced an invalid argv for {profile_id}")
        if profile_id in {"AG-U", "AG-L"} and not profile.get("universal_provider"):
            if len(argv) != 3 or argv[1] != "-c":
                raise AssertionError(f"{profile_id} must use a Python bootstrap command: {argv!r}")
            try:
                compile(argv[2], f"<adapter:{profile_id}>", "exec")
            except SyntaxError as exc:
                raise AssertionError(f"{profile_id} produced invalid Python bootstrap: {exc}") from exc
        if profile_id in {"AG-U", "AG-L", "ZC-U", "ZC-L", "CC-U", "CC-L"}:
            try:
                server._validated_command(
                    adapter, profile, "MiniMax-M3", None, "smoke", "workspace-write", workdir
                )
            except ValueError:
                pass
            else:
                raise AssertionError(f"{profile_id} must reject MiniMax M3")
    retired_by_id = {
        item.get("id"): item
        for item in server.assembler.load_profiles(str(server.LIB)).get("retired", [])
        if isinstance(item, dict)
    }
    original_ag = retired_by_id.get("AG-OriginalCLI-U-minimax")
    if not isinstance(original_ag, dict) or not original_ag.get("retired_reason"):
        raise AssertionError("the tool-unavailable original Antigravity CLI must stay retired with a reason")
    families = {
        "CX": ("CX-U", "CX-L"),
        "CC": ("CC-U", "CC-L"),
        "AG": ("AG-U", "AG-L"),
        "FC": ("MINIMAX-U", "MINIMAX-L"),
        "KC": ("KIMI-U", "KIMI-L"),
        "CN": ("CL-U", "CL-L"),
        "TA": ("TRAE-U", "TRAE-L"),
        "CR": ("CR-U", "CR-L"),
        "ZC": ("ZC-U", "ZC-L"),
        "PA": ("PA-U", "PA-L"),
        "CP": ("CP-U", "CP-L"),
    }
    listed = server._list_profiles()
    listed_active = {item.get("id"): item for item in listed.get("profiles", [])}
    listed_retired = {item.get("id"): item for item in listed.get("retired_profiles", [])}
    for shorthand, targets in families.items():
        for role, target in zip(("U", "L"), targets, strict=True):
            alias = f"{shorthand}-{role}"
            if server.assembler.resolve_profile_id(str(server.LIB), alias) != target:
                raise AssertionError(f"profile alias mismatch for {alias}")
            profile = by_id.get(target) or retired_by_id.get(target)
            if not isinstance(profile, dict) or profile.get("role") != role:
                raise AssertionError(f"missing {role} inventory entry for {shorthand}: {target}")
            listed_profile = listed_active.get(target) or listed_retired.get(target)
            if not isinstance(listed_profile, dict):
                raise AssertionError(f"MCP list_profiles omits {target}")
            if alias != target and alias not in listed_profile.get("aliases", []):
                raise AssertionError(f"MCP list_profiles omits alias {alias}")
            if target in by_id:
                resolved = server.assembler.get_profile(str(server.LIB), alias)
                if resolved.get("id") != target:
                    raise AssertionError(f"active profile alias did not resolve for {alias}")
            elif not profile.get("retired_reason"):
                raise AssertionError(f"unavailable profile {target} lacks a user-facing reason")
            if shorthand == 'CR' and target in by_id:
                if profile.get('provider') != 'opencursor-worker':
                    raise AssertionError('CR must use its registered OpenCursor worker provider')
            elif shorthand not in {"CX", "CC"} and profile.get("model") != "MiniMax-M3.1-Flash":
                raise AssertionError(f"{alias} must use MiniMax-M3.1-Flash: {profile.get('model')!r}")
    if "TRAE-U" in by_id or "TRAE-L" in by_id:
        raise AssertionError("TRAE must remain retired until a no-login BYOK task passes")
    for vehicle in ("cline", "copilot", "trae", "agy", "zcode", "claude"):
        record = {
            "card_id": "smoke-card", "vehicle": vehicle, "model": "model",
            "effort": "unset", "taskbook": "tb.md", "pid": None,
            "timestamp": "2026-10-12T00:00:00+08:00", "attempt": 1,
            "status": "starting", "updated_at": "2026-10-12T00:00:00+08:00", "command": [],
        }
        violations = server.registry_module.validate(record)
        if violations:
            raise AssertionError(f"registry rejects {vehicle}: {violations}")
    override_ids = ("CC-U", "CC-L", "AG-U", "AG-L", "MINIMAX-U", "MINIMAX-L",
                    "KIMI-U", "KIMI-L", "CL-U", "CL-L", "CP-U", "CP-L", "ZC-U", "ZC-L")
    override_model = "MiniMax-M2.7"
    for profile_id in override_ids:
        profile = by_id.get(profile_id)
        if not isinstance(profile, dict):
            continue
        _vehicle, adapter = server._adapter_for_profile(profile)
        argv, _stdin = server._validated_command(
            adapter, profile, override_model, None, "smoke", "workspace-write", str(Path.cwd())
        )
        if override_model not in " ".join(argv):
            raise AssertionError(f"model override was not propagated for {profile_id}: {argv!r}")
    return "aliases resolve for all 11 U/L families; unavailable BYOK entries stay retired; non-CX defaults use MiniMax M3.1 Flash; MiniMax-M3 is blocked; MiniMax-M2.7 override propagates through all active BYOK adapters; registry accepts all vehicles"


def _scenario_launch_dry(root: Path) -> str:
    server = _server_module(root)
    required = ("_validate_tool_arguments", "_validated_command", "_default_workdir", "_resolve_workdir")
    missing = [name for name in required if not callable(getattr(server, name, None))]
    if missing:
        raise DependencyUnavailable(f"launch dry-run helpers not ready: {', '.join(missing)}")
    library = Path(server.LIB)
    profiles_path = library / "profiles.json"
    if not profiles_path.is_file():
        raise DependencyUnavailable(f"profile source not present: {profiles_path}")

    profiles = server.assembler.load_profiles(str(library)).get("profiles")
    if not isinstance(profiles, list):
        raise AssertionError("profiles.json has no profiles array")
    profile = next(
        (
            item for item in profiles
            if isinstance(item, dict)
            and item.get("role") == "U"
            and item.get("cli") in server.VEHICLES
            and isinstance(item.get("model"), str)
            and item["model"].strip()
        ),
        None,
    )
    if profile is None:
        raise DependencyUnavailable("no launchable U-card profile is configured")
    profile_id = profile.get("id")
    if not isinstance(profile_id, str) or not profile_id:
        raise AssertionError("selected U-card profile has no id")

    prompt_path = Path(server.assembler.role_prompt_path(str(library), profile_id))
    index_path = library / "knowledge" / "INDEX.md"
    if not prompt_path.is_file() or not index_path.is_file():
        raise DependencyUnavailable(f"role prompt or shared knowledge index is missing: {prompt_path}, {index_path}")

    card_id = "smoke-dry-" + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix="card-launcher-smoke-") as temporary:
        taskbook = Path(temporary) / "taskbook.md"
        task_text = "只做参数构造冒烟；不要启动任何 CLI。\n"
        taskbook.write_text(task_text, encoding="utf-8")
        arguments = {
            "card_id": card_id,
            "profile_id": profile_id,
            "taskbook_path": str(taskbook),
            "write_scope": "workspace-write",
        }
        errors = server._validate_tool_arguments("launch_card", arguments)
        if errors:
            raise AssertionError(f"valid launch_card arguments rejected: {errors!r}")

        adapter = server.VEHICLES[profile["cli"]][1]
        model = profile["model"]
        effort = profile.get("reasoning_effort")
        prompt_text = server.assembler.assemble(str(library), profile_id, task_text)
        expected_workdir = server._default_workdir(card_id).resolve()
        if adapter.shutil.which("codex"):
            resolver = "PATH"
            argv, stdin_text = server._validated_command(
                adapter, profile, model, effort, prompt_text,
                arguments["write_scope"], str(expected_workdir)
            )
        else:
            # Keep this a parameter-only check on hosts where the CLI is not installed.
            # The adapter still builds the real argv; only executable resolution is stubbed.
            from unittest.mock import patch

            resolver = "synthetic codex.CMD (CLI absent from PATH)"
            with patch.object(adapter.shutil, "which", return_value=str(root / "codex.CMD")):
                argv, stdin_text = server._validated_command(
                    adapter, profile, model, effort, prompt_text,
                    arguments["write_scope"], str(expected_workdir)
                )
        actual_workdir = server._resolve_workdir(card_id, None, create_default=False)
        if not argv or any(not isinstance(part, str) for part in argv):
            raise AssertionError(f"adapter did not produce a valid argv: {argv!r}")
        if actual_workdir != expected_workdir:
            raise AssertionError(f"default workdir mismatch: {actual_workdir} != {expected_workdir}")
        if expected_workdir.exists():
            raise AssertionError("dry-run unexpectedly created the default card workspace")
        argv_preview = " ".join(argv[:5])
        stdin_mode = "stdin" if isinstance(stdin_text, str) else "argv"
        return (
            f"arguments=valid; argv_items={len(argv)} ({argv_preview}); input={stdin_mode}; resolver={resolver}; "
            f"default_workdir={actual_workdir}; workspace_created=no; CLI_executed=no"
        )


def _taskbook(root: Path, text: str) -> Path:
    path = root / "taskbook.md"
    path.write_text(text, encoding="utf-8")
    return path


def _scenario_output_blocked(root: Path) -> str:
    server = _server_module(root)
    gate = getattr(server, "_check_deliverables_in_workdir", None)
    if not callable(gate):
        raise DependencyUnavailable("pre-launch deliverable workdir gate is not present")
    with tempfile.TemporaryDirectory(prefix="card-launcher-gate-block-") as temporary:
        temp_root = Path(temporary)
        workdir = temp_root / "workspace"
        workdir.mkdir()
        outside_output = temp_root / "outside" / "deliverable.md"
        outside_output.parent.mkdir()
        text = "# Temporary smoke taskbook\n\n## 产物落盘路径\n- `" + str(outside_output) + "`\n"
        taskbook = _taskbook(temp_root, text)
        try:
            gate(taskbook.read_text(encoding="utf-8"), workdir, "SMOKE-BLOCK")
        except ValueError as error:
            detail = str(error)
            suggestion = f"建议 {outside_output.parent}"
            if "产物路径在当前工作区外" not in detail or suggestion not in detail:
                raise AssertionError(f"gate blocked with an incorrect suggestion: {detail}") from error
            return f"blocked=yes; suggested_workdir={outside_output.parent}; evidence={detail}"
        raise AssertionError("out-of-workdir deliverable was not blocked")


def _scenario_readonly_reference_allowed(root: Path) -> str:
    server = _server_module(root)
    gate = getattr(server, "_check_deliverables_in_workdir", None)
    if not callable(gate):
        raise DependencyUnavailable("pre-launch deliverable workdir gate is not present")
    with tempfile.TemporaryDirectory(prefix="card-launcher-gate-readonly-") as temporary:
        temp_root = Path(temporary)
        workdir = temp_root / "workspace"
        workdir.mkdir()
        reference = temp_root / "reference" / "ammo.md"
        reference.parent.mkdir()
        reference.write_text("read-only smoke reference\n", encoding="utf-8")
        output = workdir / "deliverable.md"
        text = (
            "# Temporary smoke taskbook\n\n## 弹药\n- `" + str(reference) + "`\n"
            + "\n## 产物落盘路径\n- `" + str(output) + "`\n"
        )
        taskbook = _taskbook(temp_root, text)
        gate(taskbook.read_text(encoding="utf-8"), workdir, "SMOKE-READONLY")
        return f"allowed=yes; outside_readonly={reference}; inside_output={output}; false_block=no"


def _scenario_readonly_write_scope_blocked(root: Path) -> str:
    """只读沙箱 + 任务书声明了产物 → 必须发车前拦下。

    2026-10-11 实锤：show-closeout 15 张只读分析卡里 10 张报告落不了盘，
    卡片原话「当前会话文件权限为只读，无法创建或追加」——白跑一整轮才发现。
    闸门必须同时扛住两种写法：`## 交付物` 小节，以及模板里的引用行
    `> **你的报告必须写到**：`…``（只扫小节会漏掉真实模板）。
    """
    server = _server_module(root)
    gate = getattr(server, "_check_write_scope_can_deliver", None)
    if not callable(gate):
        raise DependencyUnavailable("pre-launch write-scope gate is not present")
    cases = [
        ("section", "# T\n\n## 交付物\n- 报告：`C:/smoke/out/report.md`\n", True),
        ("blockquote", "# T\n\n> **你的报告必须写到**：`C:/smoke/out/report.md`（目录不存在就建）\n", True),
        ("no-output", "# T\n\n## 范围\n读 `C:/smoke/out/a.py` 并分析\n", False),
        ("opt-out", "<!-- allow-readonly-no-output -->\n# T\n\n## 交付物\n- 报告：`C:/smoke/out/r.md`\n", False),
    ]
    observed: list[str] = []
    for label, text, should_block in cases:
        try:
            gate(text, "SMOKE-WS", "read-only")
            blocked = False
        except ValueError:
            blocked = True
        if blocked != should_block:
            raise AssertionError(
                f"write-scope gate wrong for {label}: expected block={should_block}, got {blocked}"
            )
        observed.append(f"{label}={'block' if blocked else 'allow'}")
        # 可写时无论有无产物都必须放行
        gate(text, "SMOKE-WS", "workspace-write")
    return "all 4 shapes correct: " + ", ".join(observed)


def _run_content_gate(root: Path, report_path: Path, rules_path: Path):
    gate_script = root / "kernel" / "content_gate.py"
    if not gate_script.is_file():
        raise DependencyUnavailable(f"content gate CLI not present: {gate_script}")
    if not rules_path.is_file():
        raise DependencyUnavailable(f"content gate rule file not present: {rules_path}")
    try:
        return subprocess.run(
            [sys.executable, str(gate_script), str(report_path), "--rules", str(rules_path)],
            cwd=str(root),
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise AssertionError(f"content gate CLI exceeded 12s timeout: {error}") from error


def _scenario_content_gate(root: Path) -> str:
    rules_path = (
        Path.home()
        / "Desktop"
        / "hd"
        / "basic-memory"
        / "记忆库"
        / "user"
        / "dispatch-repair-20261010"
        / "reports"
        / "content_gate_rules.json"
    )
    gate_script = root / "kernel" / "content_gate.py"
    if not gate_script.is_file() or not rules_path.is_file():
        missing = gate_script if not gate_script.is_file() else rules_path
        raise DependencyUnavailable(f"content gate dependency not present: {missing}")

    with tempfile.TemporaryDirectory(prefix="card-launcher-content-gate-") as temporary:
        temp_root = Path(temporary)
        blocked_report = temp_root / "transport-error.md"
        blocked_report.write_text(
            "Transport error\nTransport error\nTransport error\n", encoding="utf-8"
        )
        blocked = _run_content_gate(root, blocked_report, rules_path)
        if blocked.returncode != 2 or "transport-error-cluster" not in blocked.stdout:
            raise AssertionError(
                f"Transport error sample expected rc=2 and rule hit; rc={blocked.returncode}; "
                f"stdout={blocked.stdout[-500:]!r}; stderr={blocked.stderr[-300:]!r}"
            )

        normal_report = temp_root / "normal.md"
        paragraphs = [
            f"验证项 {index:02d} 已完成，结论与预设判据一致，证据编号为 {index:02d}。来源：https://example.com/check/{index:02d}"
            for index in range(1, 41)
        ]
        normal_report.write_text("## 结论\n\n" + "\n\n".join(paragraphs) + "\n", encoding="utf-8")
        normal = _run_content_gate(root, normal_report, rules_path)
        if normal.returncode != 0 or "ok: True" not in normal.stdout:
            raise AssertionError(
                f"normal sample expected rc=0; rc={normal.returncode}; "
                f"stdout={normal.stdout[-500:]!r}; stderr={normal.stderr[-300:]!r}"
            )
        return (
            f"blocked_sample=rc:{blocked.returncode},rule:transport-error-cluster; "
            f"normal_sample=rc:{normal.returncode},chars:{len(normal_report.read_text(encoding='utf-8'))}"
        )


def _scenario_degraded_terminal(root: Path) -> str:
    server = _server_module(root)
    diagnostics = getattr(server, "_terminal_log_diagnostics", None)
    finalize = getattr(server, "_finalize_card", None)
    if not callable(diagnostics) or not callable(finalize):
        raise DependencyUnavailable("terminal diagnostic/finalize helpers are not present")

    with tempfile.TemporaryDirectory(prefix="card-launcher-degraded-") as temporary:
        temp_root = Path(temporary)
        logs_dir = temp_root / "logs"
        logs_dir.mkdir()
        card_id = "smoke-degraded-" + uuid.uuid4().hex[:10]
        (logs_dir / f"{card_id}.log").write_text(
            json.dumps({'type':'error','message':'runner handshake task failed'})+'\n', encoding="utf-8"
        )
        registry_path = temp_root / "cards_registry.jsonl"
        ledger_path = temp_root / "ledger.jsonl"
        record = {
            "card_id": card_id,
            "status": "running",
            "updated_at": __import__("datetime").datetime.now().astimezone().isoformat(),
            "pid": 1,
        }
        previous = {
            "LOGS_DIR": server.LOGS_DIR,
            "REGISTRY_PATH": server.REGISTRY_PATH,
            "LEDGER_PATH": server.LEDGER_PATH,
        }
        try:
            server.LOGS_DIR = logs_dir
            server.REGISTRY_PATH = registry_path
            server.LEDGER_PATH = ledger_path
            server.registry_module.upsert(str(registry_path), record)
            result = finalize(card_id, record, "finished", exit_code=0)
            latest = server.ledger_module.latest_by_card(str(ledger_path)).get(card_id, {})
            if result.get("status") != "degraded":
                raise AssertionError(f"finalizer returned {result.get('status')!r}, expected 'degraded'")
            if latest.get("result") != "degraded" or latest.get("final") is not True:
                raise AssertionError(f"terminal ledger entry is not final/degraded: {latest!r}")
            return f"fake_log=runner handshake task failed; registry={result['status']}; ledger={latest['result']}/final"
        finally:
            server.LOGS_DIR = previous["LOGS_DIR"]
            server.REGISTRY_PATH = previous["REGISTRY_PATH"]
            server.LEDGER_PATH = previous["LEDGER_PATH"]


def _scenario_profile_role_counts(root: Path) -> str:
    server = _server_module(root)
    result = server._list_profiles()
    profiles = result.get("profiles")
    counts = result.get("role_counts")
    if not isinstance(profiles, list) or not isinstance(counts, dict):
        raise AssertionError("list_profiles did not return profiles and computed role_counts")
    expected = {role: sum(p.get("role") == role for p in profiles) for role in ("U", "L", "B")}
    expected["total"] = len(profiles)
    if counts != expected:
        raise AssertionError(f"role counts mismatch: {counts!r} != {expected!r}")
    return f"profiles={len(profiles)}; role_counts={counts}"


def _scenario_report_fail_closed(root: Path) -> str:
    server = _server_module(root)
    with tempfile.TemporaryDirectory(prefix="card-launcher-report-gate-") as temporary:
        report = Path(temporary) / "report.md"
        report.write_text("Smoke report\n\nEvidence recorded.\n", encoding="utf-8")
        previous = {
            "get": server.registry_module.get,
            "find": server._find_card_report,
            "gate": server._content_gate_result,
            "diagnostics": server._terminal_log_diagnostics,
        }
        try:
            server.registry_module.get = lambda *_args: {"card_id": "SMOKE-REPORT-GATE"}
            server._content_gate_result = lambda _text: {"status": "passed", "checks": []}
            server._terminal_log_diagnostics = lambda _card_id: None
            server._find_card_report = lambda *_args: None
            missing = server._collect_report({"card_id": "SMOKE-REPORT-GATE"})
            if missing.get("ok") is not False or missing.get("status") != "no_report":
                raise AssertionError(f"missing report was not blocked: {missing!r}")

            server._find_card_report = lambda *_args: str(report)
            server._terminal_log_diagnostics = lambda _card_id: {"keywords": ["Model creation failed"]}
            model_error = server._collect_report({"card_id": "SMOKE-REPORT-GATE"})
            if model_error.get("ok") is not False or model_error.get("status") != "execution_error":
                raise AssertionError(f"model creation failure was not blocked: {model_error!r}")
            return "no_report=blocked; Model creation failed=blocked despite report file"
        finally:
            server.registry_module.get = previous["get"]
            server._find_card_report = previous["find"]
            server._content_gate_result = previous["gate"]
            server._terminal_log_diagnostics = previous["diagnostics"]


def _scenario_registry_concurrent_upsert(root: Path) -> str:
    """Regression test for simultaneous dispatches from multiple MCP processes."""
    server = _server_module(root)
    worker = (
        "import sys; from kernel import registry; "
        "root,path,prefix=sys.argv[1:4]; "
        "[registry.upsert(path, {'card_id':f'{prefix}-{i:02d}','status':'running'}) "
        "for i in range(12)]"
    )
    environment = os.environ.copy()
    old_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(root) + (os.pathsep + old_pythonpath if old_pythonpath else "")
    environment["PYTHONIOENCODING"] = "utf-8"
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    with tempfile.TemporaryDirectory(prefix="card-launcher-registry-race-") as temporary:
        registry_path = str(Path(temporary) / "cards_registry.jsonl")
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", worker, str(root), registry_path, f"writer-{index}"],
                cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                encoding="utf-8", errors="replace", env=environment,
                creationflags=creationflags,
            )
            for index in range(3)
        ]
        results = []
        for process in processes:
            try:
                stdout, stderr = process.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                raise AssertionError("concurrent registry writer exceeded 30s")
            results.append((process.returncode, stdout, stderr))
        failures = [item for item in results if item[0] != 0]
        if failures:
            raise AssertionError(f"concurrent registry writers failed: {failures!r}")
        records = server.registry_module.all_records(registry_path)
        expected = 36
        if len(records) != expected:
            raise AssertionError(f"lost registry records: expected {expected}, found {len(records)}")
        return f"writers=3; updates={expected}; retained={len(records)}; WinError 5=none"


def _run_scenario(name: str, function, root: Path) -> dict[str, str]:
    try:
        evidence = function(root)
        return {"name": name, "status": "PASS", "evidence": evidence}
    except DependencyUnavailable as error:
        return {"name": name, "status": "SKIP", "evidence": str(error)}
    except Exception as error:
        return {
            "name": name,
            "status": "FAIL",
            "evidence": f"{type(error).__name__}: {error}",
        }


def _self_test_failure() -> list[dict[str, str]]:
    return [
        {
            "name": "injected-failure",
            "status": "FAIL",
            "evidence": "intentional self-test; verifies FAIL produces a nonzero exit code",
        }
    ]


def _emit(results: list[dict[str, str]], as_json: bool) -> int:
    counts = {state: sum(item["status"] == state for item in results) for state in ("PASS", "SKIP", "FAIL")}
    failed = counts["FAIL"] > 0
    summary = {
        "ok": not failed,
        "exit_code": 1 if failed else 0,
        "counts": counts,
        "scenarios": results,
    }
    if as_json:
        print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    else:
        for result in results:
            evidence = " ".join(result["evidence"].splitlines()).strip()
            print(f"{result['status']} {result['name']}: {evidence}")
        state = "FAIL" if failed else "PASS"
        print(f"总判：{state}（PASS={counts['PASS']}, SKIP={counts['SKIP']}, FAIL={counts['FAIL']}）")
    return summary["exit_code"]


def main(argv=None) -> int:
    _configure_streams()
    default_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description="card-launcher end-to-end smoke check")
    parser.add_argument("--root", default=str(default_root), help="project root (defaults to the script's parent)")
    parser.add_argument("--json", action="store_true", help="emit one machine-readable JSON result")
    parser.add_argument("--self-test-failure", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    if args.self_test_failure:
        return _emit(_self_test_failure(), args.json)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        return _emit(
            [{"name": "project-root", "status": "FAIL", "evidence": f"root directory not found: {root}"}],
            args.json,
        )

    scenarios = [
        ("mcp-tools-order", _scenario_tools),
        ("new-cli-profiles-and-bridge-model-guard", _scenario_new_cli_profiles),
        ("launch-card-parameter-dry-run", _scenario_launch_dry),
        ("outside-deliverable-blocked", _scenario_output_blocked),
        ("outside-readonly-reference-allowed", _scenario_readonly_reference_allowed),
        ("readonly-write-scope-blocked", _scenario_readonly_write_scope_blocked),
        ("content-gate-cli", _scenario_content_gate),
        ("degraded-terminal", _scenario_degraded_terminal),
        ("profile-role-counts", _scenario_profile_role_counts),
        ("report-fail-closed", _scenario_report_fail_closed),
        ("registry-concurrent-upsert", _scenario_registry_concurrent_upsert),
    ]
    results = [_run_scenario(name, function, root) for name, function in scenarios]
    return _emit(results, args.json)


if __name__ == "__main__":
    raise SystemExit(main())
