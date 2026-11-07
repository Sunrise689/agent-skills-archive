"""Stdout-clean stdio JSON-RPC/MCP shell for the card launcher."""

from __future__ import annotations

from datetime import datetime
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
LIB = Path(os.environ.get("AGENT_LAUNCHER_CONFIG_DIR", str(ROOT / "config")))
REGISTRY_PATH = ROOT / "data" / "cards_registry.jsonl"
LEDGER_PATH = ROOT / "data" / "ledger.jsonl"
FREE_CHAINS_PATH = ROOT / "data" / "free_chains.json"
PROBE_SEC_DEFAULT = 25.0
LOGS_DIR = ROOT / "logs"
REPORTS_DIR = ROOT / "reports"
POOLS_PATH = ROOT / "data" / "pools.json"
OVERRIDES_PATH = ROOT / "data" / "overrides.json"
PROBE_CACHE_PATH = ROOT / "data" / "probe_cache.json"
CAPABILITIES_PATH = ROOT / "data" / "capabilities.json"
CONTENT_GATE_PATH = ROOT / "kernel" / "content_gate.py"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from adapters import provider_adapter
from adapters import ark as ark_adapter
from adapters import claude as claude_adapter  # noqa: E402
from adapters import claude_minimax as claude_minimax_adapter  # noqa: E402
from adapters import claude_openrouter as claude_openrouter_adapter  # noqa: E402
from adapters import cline as cline_adapter  # noqa: E402
from adapters import codex as codex_adapter  # noqa: E402
from adapters import copilot as copilot_adapter  # noqa: E402
from adapters import grok as grok_adapter  # noqa: E402
from adapters import kimi as kimi_adapter  # noqa: E402
from adapters import minimax_code as minimax_code_adapter  # noqa: E402
from adapters import agy as agy_adapter  # noqa: E402
from adapters import agy_sdk as agy_sdk_adapter  # noqa: E402
from adapters import ollama as ollama_adapter  # noqa: E402
from adapters import opencode as opencode_adapter
from adapters import opencursor as opencursor_adapter  # noqa: E402
from adapters import trae as trae_adapter  # noqa: E402
from adapters import zcode as zcode_adapter  # noqa: E402
from kernel import assembler, launcher, ledger as ledger_module  # noqa: E402
from kernel import pools as pools_module  # noqa: E402
from kernel import registry as registry_module  # noqa: E402
from kernel import routing  # noqa: E402


SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
SERVER_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]
CARD_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
VEHICLES = {
    "Codex CLI": ("codex", codex_adapter),
    "Claude Code": ("claude", claude_adapter),
    "OpenCode CLI": ("opencode", opencode_adapter),
    "Ollama": ("ollama", ollama_adapter),
    "Cline CLI": ("cline", cline_adapter),
    "GitHub Copilot CLI": ("copilot", copilot_adapter),
    "Kimi Code CLI": ("kimi", kimi_adapter),
    "MiniMax Code CLI": ("mcode", minimax_code_adapter),
    "TRAE CLI": ("trae", trae_adapter),
    "ZCode CLI": ("zcode", zcode_adapter),
    "Antigravity CLI": ("agy", agy_adapter),
    "Antigravity SDK Wrapper": ("agy", agy_sdk_adapter),
    "Claude Code via MiniMax Bridge": ("claude", claude_minimax_adapter),
    "Claude Code via OpenRouter Bridge": ("claude", claude_openrouter_adapter),
    "OpenCursor Worker": ("opencursor", opencursor_adapter),
    "Grok Build CLI": ("grok", grok_adapter),
}


def _card_properties(include_pool: bool = True) -> dict[str, Any]:
    properties = {
        "card_id": {
            "type": "string",
            "minLength": 1,
            "description": "Unique card ID used in the registry and log filename.",
        },
        "profile_id": {
            "type": "string",
            "minLength": 1,
            "description": "Profile ID from the configured U-card profiles.json.",
        },
        "taskbook_path": {
            "type": "string",
            "minLength": 1,
            "description": "Path to the UTF-8 Markdown taskbook to launch.",
        },
        "soft_time_limit_minutes": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1440,
            "description": (
                "Optional soft deadline in minutes. At the deadline the card should stop new work, "
                "save what it has, write a partial report, and exit. This never kills the process."
            ),
        },
        "model": {
            "type": "string",
            "minLength": 1,
            "description": "Optional model override; omitted uses the profile model.",
        },
        "effort": {
            "type": "string",
            "minLength": 1,
            "description": "Optional reasoning effort override; omitted uses the profile setting.",
        },
        "write_scope": {
            "type": "string",
            "enum": ["read-only", "workspace-write"],
            "description": "Optional Codex write scope; omitted defaults to read-only.",
        },
        "workdir": {
            "type": "string",
            "minLength": 1,
            "description": (
                "Optional working directory the card runs in. Workspace-write sandboxes are rooted "
                "at this path, so deliverables outside it will be rejected as unwritable. Omitted "
                "creates and uses <launcher-root>/cards/<card_id>/work."
            ),
        },
    }
    if include_pool:
        properties["pool"] = {
            "type": ["string", "null"],
            "default": None,
            "description": "Optional model pool name used for ordered model fallback.",
        }
    return properties


def _card_schema(include_pool: bool = True) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": _card_properties(include_pool),
        "required": ["card_id", "profile_id", "taskbook_path"],
        "additionalProperties": False,
    }


def _id_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "card_id": {
                "type": "string",
                "minLength": 1,
                "description": "Unique card ID to inspect, collect, or stop.",
            }
        },
        "required": ["card_id"],
        "additionalProperties": False,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "launch_card",
        "description": (
            "Launch one profile-configured card with the taskbook and return its PID, "
            "selected model, command, and status. Use when one card needs to run."
        ),
        "inputSchema": _card_schema(),
    },
    {
        "name": "launch_group",
        "description": (
            "Launch a list of cards sequentially with a configurable delay and return "
            "each launch result. Use when several cards should start in one request."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "cards": {
                    "type": "array",
                    "items": _card_schema(include_pool=False),
                    "description": "Card launch objects using the launch_card fields.",
                },
                "stagger_seconds": {
                    "type": "number",
                    "minimum": 0,
                    "default": 0.5,
                    "description": "Non-negative delay between launches; defaults to 0.5 seconds.",
                },
            },
            "required": ["cards"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_status",
        "description": (
            "Read a card's registry state, process liveness, runtime, and last 200 log "
            "characters. Use when checking whether a launched card has finished."
        ),
        "inputSchema": _id_schema(),
    },
    {
        "name": "collect_report",
        "description": (
            "Find this card's Markdown report by its own workspace, declared deliverable, then "
            "card-scoped legacy paths; run the content gate when available."
        ),
        "inputSchema": _id_schema(),
    },
    {
        "name": "stop_card",
        "description": (
            "Stop a card process and its child processes, then persist its terminal "
            "state. Use when a running card must be stopped."
        ),
        "inputSchema": _id_schema(),
    },
    {
        "name": "list_cards",
        "description": (
            "Return every registered card with its true live state: the registry record is "
            "reconciled against process liveness and terminal log markers first, so a card "
            "that died is reported as finished or degraded even if nobody called check_status. "
            "Use this as the single source of "
            "truth after launching a group, instead of reading cards_registry.jsonl by hand "
            "(that file holds upserted history and can look stale)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status_filter": {
                    "type": "string",
                    "enum": ["all", "running", "finished", "failed", "degraded"],
                    "default": "all",
                    "description": "Optional status filter; omitted returns every card.",
                }
            },
            "required": [],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_profiles",
        "description": (
            "List configured card profiles with role, CLI, model, effort, and state. "
            "Use when selecting a profile before launching."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
    },
]


class ArgumentValidationError(ValueError):
    """Raised only for malformed tool arguments, before any side effects."""


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _validate_card_arguments(arguments: Any, where: str = "arguments",
                             include_pool: bool = True) -> list[str]:
    errors: list[str] = []
    if not isinstance(arguments, dict):
        return [f"{where} must be an object"]

    required = {"card_id", "profile_id", "taskbook_path"}
    allowed = required | {"model", "effort", "write_scope", "workdir", "soft_time_limit_minutes"}
    if include_pool:
        allowed.add("pool")
    for name in sorted(required - arguments.keys()):
        errors.append(f"{where}.{name} is required")
    for name in sorted(arguments.keys() - allowed):
        errors.append(f"{where}.{name} is not allowed")

    for name in ("card_id", "profile_id", "taskbook_path"):
        if name not in arguments:
            continue
        value = arguments[name]
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{where}.{name} must be a non-empty string")
        elif name == "card_id" and not CARD_ID_RE.fullmatch(value):
            errors.append(f"{where}.card_id may contain only letters, digits, '.', '_' and '-'")

    for name in ("model", "effort"):
        if name in arguments and (
            not isinstance(arguments[name], str) or not arguments[name].strip()
        ):
            errors.append(f"{where}.{name} must be a non-empty string when provided")

    if "soft_time_limit_minutes" in arguments:
        limit = arguments["soft_time_limit_minutes"]
        if type(limit) is not int or not 1 <= limit <= 1440:
            errors.append(f"{where}.soft_time_limit_minutes must be an integer from 1 to 1440")

    if "write_scope" in arguments:
        scope = arguments["write_scope"]
        if not isinstance(scope, str) or scope not in {"read-only", "workspace-write"}:
            errors.append(f"{where}.write_scope must be 'read-only' or 'workspace-write'")
    if include_pool and "pool" in arguments and arguments["pool"] is not None and not isinstance(arguments["pool"], str):
        errors.append(f"{where}.pool must be a string or null")
    return errors


def _validate_tool_arguments(name: str, arguments: Any) -> list[str]:
    if not isinstance(arguments, dict):
        return ["arguments must be an object"]

    if name == "launch_card":
        return _validate_card_arguments(arguments)
    if name == "launch_group":
        errors: list[str] = []
        extra = arguments.keys() - {"cards", "stagger_seconds"}
        missing = {"cards"} - arguments.keys()
        errors.extend(f"arguments.{key} is not allowed" for key in sorted(extra))
        errors.extend(f"arguments.{key} is required" for key in sorted(missing))
        cards = arguments.get("cards")
        if "cards" in arguments and not isinstance(cards, list):
            errors.append("arguments.cards must be an array")
        elif isinstance(cards, list):
            for index, card in enumerate(cards):
                errors.extend(
                    _validate_card_arguments(
                        card, f"arguments.cards[{index}]", include_pool=False
                    )
                )
        if "stagger_seconds" in arguments:
            delay = arguments["stagger_seconds"]
            finite_number = False
            if isinstance(delay, (int, float)) and not isinstance(delay, bool):
                try:
                    finite_number = math.isfinite(float(delay))
                except (OverflowError, ValueError):
                    finite_number = False
            if (
                isinstance(delay, bool)
                or not isinstance(delay, (int, float))
                or not finite_number
                or delay < 0
            ):
                errors.append("arguments.stagger_seconds must be a finite non-negative number")
        return errors
    if name in {"check_status", "collect_report", "stop_card"}:
        errors = []
        for key in sorted(arguments.keys() - {"card_id"}):
            errors.append(f"arguments.{key} is not allowed")
        if "card_id" not in arguments:
            errors.append("arguments.card_id is required")
        else:
            card_id = arguments["card_id"]
            if not isinstance(card_id, str) or not card_id.strip():
                errors.append("arguments.card_id must be a non-empty string")
            elif not CARD_ID_RE.fullmatch(card_id):
                errors.append("arguments.card_id may contain only letters, digits, '.', '_' and '-'")
        return errors
    if name == "list_profiles":
        return [f"arguments.{key} is not allowed" for key in sorted(arguments)]
    if name == "list_cards":
        errors = []
        allowed_keys = {"status_filter"}
        for key in sorted(arguments.keys() - allowed_keys):
            errors.append(f"arguments.{key} is not allowed")
        if "status_filter" in arguments:
            value = arguments["status_filter"]
            if value not in {"all", "running", "finished", "failed", "degraded"}:
                errors.append(
                    "arguments.status_filter must be one of all/running/finished/failed/degraded"
                )
        return errors
    return [f"unknown tool: {name}"]


def _adapter_for_profile(profile: dict[str, Any]) -> tuple[str, Any]:
    cli = profile.get("cli")
    if profile.get("universal_provider"):
        return VEHICLES[cli][0], provider_adapter
    if profile.get("provider") == "ark-agent-plan":
        return VEHICLES[cli][0], ark_adapter
    if cli not in VEHICLES:
        raise ValueError(f"unsupported profile CLI: {cli!r}")
    return VEHICLES[cli]


_ABS_PATH_RE = re.compile(
    r"[A-Za-z]:[\\/][^\r\n<>`\"|*?]*?\.(?:md|json|jsonl|csv|txt|html|htm)",
    re.IGNORECASE,
)
_DELIVERABLE_SUFFIXES = {".md", ".json", ".jsonl", ".csv", ".txt", ".html", ".htm"}
_READONLY_SECTION_HINTS = ("弹药", "权威输入", "背景", "参考", "只读")
_OUTPUT_SECTION_HINTS = ("产物", "交付", "落盘", "输出")
# 任务书里这些路径是「弹药」（只读参考资料），卡只需要读得到，不要求能写
_READONLY_HINTS = (
    os.sep + ".agents" + os.sep,
    os.sep + ".codex" + os.sep,
    os.sep + ".claude" + os.sep,
    os.sep + ".pi" + os.sep + "agent" + os.sep + "skills" + os.sep,
    "skills" + os.sep,
    "skill" + os.sep,
)


def _check_deliverables_in_workdir(task_text: str, workdir: Path, card_id: str) -> None:
    """发车前拦截「交付物在沙箱之外」这类注定失败的派单。

    背景：2026-10-10 的 T1:10，10 张卡全部报完成，但 8 张的报告没落盘，
    卡片原话是「未写入 ...，原因是该路径超出当前工作区写入权限」。
    Codex 的 workspace-write 沙箱以 cwd 为根，任务书里的绝对产物路径若不在 cwd 内，
    写盘必然被拒。烧掉一整轮编排才发现，属于完全可以预防的错误。
    这里在派单那一刻就把这类路径捞出来报错，并明确告知该传什么 workdir。
    """
    declared, readonly, mode = _taskbook_path_declarations(task_text)
    workdir = workdir.resolve()
    offenders: dict[str, Path] = {}
    for raw in declared:
        try:
            resolved = Path(raw).resolve()
        except (OSError, ValueError):
            continue
        try:
            resolved.relative_to(workdir)
        except ValueError:
            # Explicit deliverable sections are authoritative even before the file exists.
            # The legacy fallback retains the old existence guard to avoid example-path false positives.
            if mode != "fallback" or resolved.exists() or resolved.parent.is_dir():
                offenders[str(resolved)] = resolved
    if offenders:
        uniq = sorted(offenders)
        try:
            suggested_workdir = Path(os.path.commonpath([str(path.parent) for path in offenders.values()]))
        except ValueError:
            suggested_workdir = offenders[uniq[0]].parent
        skipped = "; ".join(readonly) if readonly else "未识别到只读引用"
        raise ValueError(
            f"card {card_id}: 产物路径在当前工作区外：{'; '.join(uniq)}。"
            f"请把 workdir 设为至少包含全部产物的目录（建议 {suggested_workdir}），"
            f"或把产物路径改到当前 workdir 内。已跳过的只读引用：{skipped}。"
        )


def _check_write_scope_can_deliver(task_text: str, card_id: str, write_scope: str) -> None:
    """发车前拦截「沙箱只读、却要求交产物」这类注定白跑的派单。

    背景：2026-10-11 的 show-closeout，15 张只读分析卡里有 10 张落地报告失败，
    卡片原话是「当前会话文件权限为只读，无法创建或追加报告文件」。
    而同批 OpenCode 的 read-only 不挡写入 —— 所以这个坑只在 Codex 通道暴露，
    更隐蔽：不看日志就会以为是卡没干活。

    判据：任务书里**声明了产物路径**（交付物小节或 <!-- deliverable: --> 标记）
    而 write_scope 是 read-only → 直接拒，并告知正确姿势。
    只读取材（不交产物）的卡不受影响。
    """
    if write_scope != "read-only":
        return
    if "<!-- allow-readonly-no-output -->" in task_text:
        return
    declared, _readonly, _mode = _taskbook_path_declarations(task_text)
    if not declared:
        declared = _scan_inline_output_paths(task_text)
    if not declared:
        return
    shown = "; ".join(declared[:4])
    more = f" 等 {len(declared)} 条" if len(declared) > 4 else ""
    raise ValueError(
        f"card {card_id}: 任务书声明了产物（{shown}{more}），但 write_scope=read-only，"
        f"沙箱会拒绝写盘，这张卡注定白跑。二选一："
        f"① 若这张卡要交产物 → 传 write_scope=\"workspace-write\"，并把 workdir 设为本卡专属目录"
        f"（这样报告能落盘、产品目录仍在可写根之外，靠沙箱强制隔离）；"
        f"② 若这张卡确实不该交产物 → 把任务书里声明产物的那一段删掉，或加 "
        f"<!-- allow-readonly-no-output --> 标记显式声明无产物。"
    )


_OUTPUT_VERB_RE = re.compile(
    r"(?:必须写到|写到|写入|落盘|产出|保存到|输出到|交付到)"
    r"[\s\u3000：:`\"'*_\[\]()#>-]*"
    r"([A-Za-z]:[\\/][^\s`\"'<>|*?)\]]*\.(?:md|json|jsonl|csv|txt|html?|py|patch|diff))",
    re.IGNORECASE,
)


def _scan_inline_output_paths(task_text: str) -> list[str]:
    """扫「写到/落盘/产出 …」这类行内声明里的产物路径。

    为什么单独做：任务书模板把报告路径写在**引用行**（`> **你的报告必须写到**：`…``）
    或正文句子里，而不是放在 `## 交付物` 小节下——只靠小节扫描会漏掉真实模板，
    闸门就会变成摆设（2026-10-11 实测：合成用例能拦，真任务书全漏网）。
    """
    found: list[str] = []
    for match in _OUTPUT_VERB_RE.finditer(task_text):
        candidate = _clean_task_path(match.group(1))
        if candidate and candidate not in found:
            found.append(candidate)
    return found


def _clean_task_path(raw: str) -> str:
    return raw.strip().strip("`\"'<>[](){} ").rstrip(".,;:，。；：、")


def _task_sections(task_text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    title: str | None = None
    body: list[str] = []
    heading_stack: list[tuple[int, str]] = []
    for line in task_text.splitlines():
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if heading:
            if title is not None:
                sections.append((title, "\n".join(body)))
            level = len(heading.group(1))
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, heading.group(2).strip()))
            title = " ".join(item[1] for item in heading_stack)
            body = []
        elif title is not None:
            body.append(line)
    if title is not None:
        sections.append((title, "\n".join(body)))
    return sections


def _task_paths(text: str) -> list[str]:
    paths: list[str] = []
    for match in _ABS_PATH_RE.finditer(text):
        candidate = _clean_task_path(match.group(0))
        if Path(candidate).suffix.lower() in _DELIVERABLE_SUFFIXES:
            paths.append(candidate)
    return list(dict.fromkeys(paths))


def _taskbook_path_declarations(task_text: str) -> tuple[list[str], list[str], str]:
    """Return output paths, explicitly read-only paths, and the detection mode."""
    sections = _task_sections(task_text)
    readonly: list[str] = []
    output_sections: list[str] = []
    precise_output_sections: list[str] = []
    for title, body in sections:
        lowered = title.casefold()
        paths = _task_paths(body)
        if any(hint in lowered for hint in _READONLY_SECTION_HINTS):
            readonly.extend(paths)
            continue
        if any(hint in lowered for hint in _OUTPUT_SECTION_HINTS):
            output_sections.append(body)
            if "产物落盘路径" in lowered:
                precise_output_sections.append(body)

    marked: list[str] = []
    for match in re.finditer(r"<!--\s*deliverable\s*:\s*(.*?)\s*-->", task_text, re.IGNORECASE | re.DOTALL):
        value = _clean_task_path(match.group(1))
        if re.match(r"^[A-Za-z]:[\\/]", value) and Path(value).suffix.lower() in _DELIVERABLE_SUFFIXES:
            marked.append(value)

    precise_paths = marked + [path for body in precise_output_sections for path in _task_paths(body)]
    if precise_paths:
        outputs = list(dict.fromkeys(precise_paths))
        mode = "explicit"
    elif output_sections:
        outputs = list(dict.fromkeys(path for body in output_sections for path in _task_paths(body)))
        mode = "sections"
    else:
        # Backward compatibility for older taskbooks without output/read-only section headings.
        readonly_norm = {path.casefold() for path in readonly}
        outputs = []
        for path in _task_paths(task_text):
            normalized = path.replace("/", "\\").casefold()
            if path.casefold() in readonly_norm or any(h.casefold() in normalized for h in _READONLY_HINTS):
                continue
            outputs.append(path)
        mode = "fallback"
    return list(dict.fromkeys(outputs)), list(dict.fromkeys(readonly)), mode


def _declared_capabilities(task_text: str) -> list[str]:
    dimensions = {
        "需要联网": "net",
        "需要网络": "net",
        "需要视觉": "vision",
        "需要图像": "vision",
        "需要推理档": "effort",
        "需要模型": "model",
        "需要指定模型": "model",
    }
    found: list[str] = []
    for line in task_text.splitlines():
        normalized = re.sub(r"^\s*(?:#{1,6}\s*|[-*+]\s*|\d+[.)]\s*)", "", line).strip()
        for phrase, dimension in dimensions.items():
            if normalized.startswith(phrase) and not normalized.startswith("不" + phrase):
                found.append(dimension)
    return list(dict.fromkeys(found))


def _check_capabilities(task_text: str, channel: str) -> dict[str, Any]:
    requirements = _declared_capabilities(task_text)
    try:
        payload = json.loads(CAPABILITIES_PATH.read_text(encoding="utf-8"))
        rows = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("capabilities.json results must be an array of objects")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return {
            "status": "skipped",
            "reason": f"能力数据不可用：{type(exc).__name__}: {exc}",
            "requirements": requirements,
        }

    if not requirements:
        return {"status": "not_required", "requirements": []}
    for dimension in requirements:
        matches = [
            row for row in rows
            if row.get("channel") == channel and row.get("dimension") == dimension
        ]
        status = matches[-1].get("status") if matches else "unknown"
        detail = matches[-1].get("detail") if matches else "no matching capability row"
        if status != "pass":
            return {
                "status": "blocked",
                "channel": channel,
                "dimension": dimension,
                "capability_status": status if isinstance(status, str) else "unknown",
                "detail": detail,
                "requirements": requirements,
            }
    return {"status": "passed", "channel": channel, "requirements": requirements}


def _default_workdir(card_id: str) -> Path:
    """Use the launcher root as the session root for per-card workspaces."""
    return ROOT / "cards" / card_id / "work"


def _resolve_workdir(card_id: str, raw_workdir: Any, create_default: bool = True) -> Path:
    if isinstance(raw_workdir, str) and raw_workdir.strip():
        candidate = Path(raw_workdir.strip())
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        try:
            workdir = candidate.resolve(strict=True)
        except OSError as exc:
            raise ValueError(f"workdir does not exist or is not accessible: {candidate}") from exc
        if not workdir.is_dir():
            raise ValueError(f"workdir must identify a directory: {workdir}")
        return workdir

    candidate = _default_workdir(card_id)
    if create_default:
        candidate.mkdir(parents=True, exist_ok=True)
    return candidate.resolve(strict=create_default)


def _content_gate_result(markdown: str) -> dict[str, Any]:
    if not CONTENT_GATE_PATH.is_file():
        return {"status": "skipped", "reason": f"内容闸文件不存在：{CONTENT_GATE_PATH}"}
    try:
        gate = importlib.import_module("kernel.content_gate")
    except Exception as exc:
        return {"status": "skipped", "reason": f"内容闸无法导入：{type(exc).__name__}: {exc}"}
    try:
        result = gate.evaluate(markdown)
    except Exception as exc:
        return {"status": "skipped", "reason": f"内容闸未能评估：{type(exc).__name__}: {exc}"}
    if not isinstance(result, dict) or not isinstance(result.get("ok"), bool):
        return {"status": "skipped", "reason": "内容闸返回格式无效"}
    return {"status": "passed" if result["ok"] else "blocked", **result}


def _validated_command(adapter: Any, profile: dict[str, Any], model: str,
                       effort: str | None, prompt_text: str,
                       write_scope: str, workdir: str) -> tuple[list[str], str | None]:
    argv, stdin_text = adapter.build(
        profile,
        model,
        effort,
        prompt_text,
        workdir,
        write_scope,
    )
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(part, str) for part in argv)
        or (stdin_text is not None and not isinstance(stdin_text, str))
    ):
        raise TypeError("adapter.build returned an invalid command")
    if argv[0].lower().endswith((".cmd", ".bat")):
        argv = ["cmd", "/c", *argv]
    return argv, stdin_text


def _elapsed_seconds(start_value: Any) -> float | None:
    if not isinstance(start_value, str):
        return None
    try:
        start_time = datetime.fromisoformat(start_value.replace("Z", "+00:00"))
        if start_time.tzinfo is None:
            start_time = start_time.astimezone()
        return max(0.0, (datetime.now().astimezone() - start_time).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _probe_sec() -> float:
    """A3 集成期修正：探针默认 10s 对 opencode 冷启动太紧（实测冷启 >10s），
    会误判前两个候选已死、白丢好模型。改为从 free_chains.json 的 rules.probe_sec 读，
    缺省 25s。
    """
    try:
        rules = json.loads(FREE_CHAINS_PATH.read_text(encoding="utf-8")).get("rules", {})
        value = rules.get("probe_sec", PROBE_SEC_DEFAULT)
        return float(value)
    except Exception:
        return PROBE_SEC_DEFAULT


_TERMINAL_LOG_MARKERS = (
    ("Model creation failed", re.compile(r"Model creation failed", re.IGNORECASE)),
    ("unrecognized_model", re.compile(r"unrecognized_model", re.IGNORECASE)),
    ("runner handshake task failed", re.compile(r"runner handshake task failed", re.IGNORECASE)),
    ("task N was cancelled", re.compile(r"task\s+(?:N|\d+)\s+was cancelled", re.IGNORECASE)),
    (
        "Failed to create unified exec process",
        re.compile(r"Failed to create unified exec process", re.IGNORECASE),
    ),
)


def _terminal_log_diagnostics(card_id: str) -> dict[str, Any] | None:
    """Only real runtime error events; source/code/taskbook quotations are not errors."""
    log_path = (LOGS_DIR / f"{card_id}.log").resolve()
    try:content=log_path.read_text(encoding='utf-8',errors='replace')
    except OSError:return None
    errors=[]
    for line in content.splitlines():
        try:d=json.loads(line)
        except ValueError:continue
        if not isinstance(d,dict):continue
        if d.get('type') in ('error','turn.failed') or d.get('is_error') is True or 'card_process_error' in d:
            errors.append(json.dumps(d,ensure_ascii=False))
    matched=[label for label,pattern in _TERMINAL_LOG_MARKERS if any(pattern.search(e) for e in errors)]
    if errors and not matched:matched=['runtime_error_event']
    return {'keywords':matched,'log_path':str(log_path)} if matched else None

def _finalize_card(card_id: str, record: dict[str, Any], result: str,
                   exit_code: int | None = None) -> dict[str, Any]:
    if result == "finished":
        try:
            log = (LOGS_DIR / f"{card_id}.log").read_text(encoding="utf-8", errors="replace")
            exits = re.findall(r'\{"card_process_exit":\s*(-?\d+)\}', log)
            if exits:exit_code=int(exits[-1])
            elif exit_code is None:exit_code=record.get('exit')
            if exit_code is None:
                result='degraded'
                record=dict(record,degradation={'keywords':['missing_process_exit'],'log_path':str(LOGS_DIR / f'{card_id}.log')})
            elif exit_code != 0:result='failed'
        except OSError:
            pass
        if result == 'finished' and exit_code is None:
            result = 'degraded'
            record = dict(record, degradation={'keywords': ['missing_process_exit'], 'log_path': str(LOGS_DIR / f'{card_id}.log')})
        taskbook_value = record.get("taskbook")
        if result == "finished" and isinstance(taskbook_value, str) and _declared_deliverables(task_text_of(Path(taskbook_value))) and not _find_card_report(record, card_id):
            result = "degraded"
            record = dict(record, degradation={"keywords": ["missing_declared_report"], "log_path": str(LOGS_DIR / f"{card_id}.log")})
    seconds = _elapsed_seconds(record.get("updated_at"))
    diagnostics = _terminal_log_diagnostics(card_id)
    if diagnostics is None and isinstance(record.get("degradation"), dict):
        diagnostics = record["degradation"]
    # 台账 24（2026-10-10）：exec 故障标记会误伤「撞过故障但最终交付成功」的卡。
    # 实测：CXU5-lu6-h 日志里有 Failed to create unified exec process，但它确实交付了
    # 合格产物（内容闸门通过 3/3）。判据改为「撞过故障 **且** 找不到产物」才降级；
    # 有产物时保留 finished/stopped，但把诊断信息附到记录里备查。
    if diagnostics and result == "finished":
        report_path = _find_card_report(record, card_id)
        has_deliverable = bool(report_path) and Path(report_path).is_file()
        if has_deliverable:
            record = dict(record)
            record["exec_diagnostics"] = {
                "keywords": diagnostics.get("keywords"),
                "log_path": diagnostics.get("log_path"),
                "note": "撞过 exec 故障但产物已落盘，终态不降级（台账 24）",
            }
        else:
            result = "degraded"

    latest = ledger_module.latest_by_card(str(LEDGER_PATH))
    last_entry = latest.get(card_id) if isinstance(latest, dict) else None
    if result == "degraded":
        if not (
            isinstance(last_entry, dict)
            and last_entry.get("final") is True
            and last_entry.get("result") == "degraded"
        ):
            ledger_module.append(
                str(LEDGER_PATH),
                {
                    "ts": _now_iso(),
                    "card_id": card_id,
                    "exit": exit_code,
                    "seconds": seconds,
                    "result": "degraded",
                    "final": True,
                    "degradation": diagnostics,
                },
            )
        finalized = registry_module.set_status(
            str(REGISTRY_PATH),
            card_id,
            "degraded",
            exit=exit_code,
            seconds=seconds,
            finished_at=_now_iso(),
            degradation=diagnostics,
        )
    else:
        if not isinstance(last_entry, dict) or last_entry.get("final") is not True:
            ledger_module.finalize(str(LEDGER_PATH), card_id, exit_code, seconds, result)
        finalized = registry_module.finalize_record(
            str(REGISTRY_PATH), card_id, exit_code, seconds, result
        )

    if isinstance(finalized, dict):
        if diagnostics and result != "degraded":
            updated = registry_module.set_status(
                str(REGISTRY_PATH),
                card_id,
                str(finalized.get("status", result)),
                degradation=diagnostics,
            )
            finalized = updated if isinstance(updated, dict) else {**finalized, "degradation": diagnostics}
        return finalized
    refreshed = registry_module.get(str(REGISTRY_PATH), card_id)
    if isinstance(refreshed, dict):
        if diagnostics and result != "degraded":
            updated = registry_module.set_status(
                str(REGISTRY_PATH),
                card_id,
                str(refreshed.get("status", result)),
                degradation=diagnostics,
            )
            refreshed = updated if isinstance(updated, dict) else {**refreshed, "degradation": diagnostics}
        return refreshed
    return record


def _launch_card(arguments: dict[str, Any]) -> dict[str, Any]:
    # Per-ID cross-process lock protects check -> launch -> register as one action.
    import hashlib
    key = hashlib.sha256(arguments['card_id'].strip().encode('utf-8')).hexdigest()
    lock_path = Path(REGISTRY_PATH).parent / 'dispatch_locks' / key
    with registry_module._registry_lock(str(lock_path)):
        return _launch_card_unlocked(arguments)


def _launch_card_unlocked(arguments: dict[str, Any]) -> dict[str, Any]:
    card_id = arguments["card_id"].strip()
    profile_id = arguments["profile_id"].strip()
    existing = registry_module.get(str(REGISTRY_PATH), card_id)

    if existing and existing.get("status") in {"starting", "running"} and _completed_exit(card_id) is not None:
        existing = _finalize_card(card_id, existing, "finished")
    if existing and existing.get('status') not in {'starting','running'}:
        return {'ok':False,'status':'already_registered','card_id':card_id,
                'existing_status':existing.get('status'),
                'instruction':'Inspect existing work. An authorized retry requires a new unique card ID.'}

    if existing and existing.get("status") in {"starting", "running"}:
        pid = existing.get("pid")
        alive = (
            isinstance(pid, int)
            and not isinstance(pid, bool)
            and pid > 0
            and launcher.is_alive_now(pid)
        )
        if alive:
            return {
                "ok": False,
                "status": "already_running",
                "card_id": card_id,
                "pid": pid,
            }
        existing["updated_at"] = _now_iso()
        if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
            existing["status"] = "finished"
            existing["finished_at"] = existing.get("finished_at") or existing["updated_at"]
        else:
            existing["status"] = "failed"
            existing["error"] = "stale starting record had no process ID"
        registry_module.upsert(str(REGISTRY_PATH), existing)
        previous = _finalize_card(card_id, existing, existing['status'])
        return {'ok':False,'status':'already_registered','card_id':card_id,
                'existing_status':previous.get('status'),
                'instruction':'Previous process exited; collect it. Use a new unique card ID for an authorized retry.'}

    profile = assembler.get_profile(str(LIB), profile_id)
    model = arguments.get("model", profile.get("model"))
    profile_default = profile.get("model")
    effort = arguments.get("effort", profile.get("reasoning_effort"))
    if not isinstance(model, str) or not model.strip():
        raise ValueError("profile has no model; provide a model override")
    model = model.strip()
    if not re.fullmatch(r"[A-Za-z0-9._:/-]+", model):
        raise ValueError("model must contain only letters, digits, dot, underscore, colon, slash, or hyphen")
    if model.rsplit("/", 1)[-1].casefold() == "minimax-m3":
        raise ValueError("MiniMax-M3 is disabled; use MiniMax-M3.1-Flash or another selected model")
    requested_model = model
    profile, model, routing_reason = routing.resolve(profile, model)
    vehicle, adapter = _adapter_for_profile(profile)
    if effort is not None and (not isinstance(effort, str) or not effort.strip()):
        raise ValueError("effort must be a non-empty string or unset in the profile")

    pool_name = arguments.get("pool")
    candidates: list[str] | None = None
    if pool_name is not None:
        if not isinstance(profile_default, str) or not profile_default.strip():
            raise ValueError("profile has no default model")
        pool_map = pools_module.load_pools(str(POOLS_PATH))
        if pool_name not in pool_map:
            available = ", ".join(sorted(pool_map)) or "(none)"
            return {
                "ok": False,
                "status": "invalid_pool",
                "card_id": card_id,
                "error": f"unknown pool {pool_name!r}; available pools: {available}",
            }
        overrides = pools_module.load_overrides(str(OVERRIDES_PATH))
        probe_cache = pools_module.load_probe_cache(str(PROBE_CACHE_PATH))
        candidates = pools_module.resolve_chain(
            pool_name, profile_default, pool_map, overrides, probe_cache
        )
        if not isinstance(candidates, list) or any(
            not isinstance(candidate, str) or not candidate for candidate in candidates
        ):
            raise ValueError("resolve_chain returned an invalid candidate list")
        if not candidates:
            candidates = [profile_default]
        if "free" in pool_name and any(not (candidate.endswith(":free") or candidate.endswith("-free")) for candidate in candidates):
            raise ValueError("Free pool has no eligible free model; refusing a paid fallback")
        profile, _, routing_reason = routing.resolve(profile, candidates[0])
        vehicle, adapter = _adapter_for_profile(profile)
        if any(routing.resolve(profile, candidate)[0]["cli"] != profile["cli"] for candidate in candidates):
            raise ValueError("A model pool must use one actual CLI; use separate dispatches for mixed channels")
        candidates = [routing.resolve(profile, candidate)[1] for candidate in candidates]

    taskbook = Path(arguments["taskbook_path"].strip())
    if not taskbook.is_absolute():
        taskbook = ROOT / taskbook
    taskbook = taskbook.resolve(strict=True)
    if not taskbook.is_file():
        raise ValueError("taskbook_path must identify a file")
    task_text = taskbook.read_text(encoding="utf-8")
    prompt_text = assembler.assemble(str(LIB), profile_id, task_text, profile_override=profile)
    soft_limit = arguments.get("soft_time_limit_minutes")
    if soft_limit is not None:
        if type(soft_limit) is not int or not 1 <= soft_limit <= 1440:
            raise ValueError("soft_time_limit_minutes must be an integer from 1 to 1440")
        prompt_text += (
            f"\n\n# Optional soft time limit\n"
            f"The user set a soft time limit of {soft_limit} minutes for this task. "
            "This is not a process-kill deadline. When the time is reached, stop starting new work, "
            "save completed and partial results, write a concise report that clearly labels unfinished "
            "items, then exit. Do not claim unfinished work is complete.\n"
        )
    write_scope = arguments.get("write_scope", "read-only")

    # Validate against the target path first. Create an automatic card workspace only
    # after the launch gates allow dispatch to proceed.
    workdir = _resolve_workdir(card_id, arguments.get("workdir"), create_default=False)

    # 交付物路径守门：任务书里出现的绝对产物路径若不在 workdir 内，
    # workspace-write 沙箱必然拒写。与其烧一张卡再回收日志，不如发车前就报错。
    if write_scope == "workspace-write" and not profile.get("full_access"):
        _check_deliverables_in_workdir(task_text, workdir, card_id)

    # 可写性守门：只读沙箱 + 任务书声明产物 = 注定白跑，发车前直接拒。
    _check_write_scope_can_deliver(task_text, card_id, write_scope)

    capability = _check_capabilities(task_text, vehicle)
    if capability["status"] == "blocked":
        return {
            "ok": False,
            "card_id": card_id,
            "profile_id": profile_id,
            "status": "capability_blocked",
            "capability_gate": "blocked",
            "capability": capability,
            "error": (
                f"通道 {capability['channel']} 的 {capability['dimension']} 能力实测为 "
                f"{capability['capability_status']}，不能满足任务书要求。"
            ),
        }

    workdir = _resolve_workdir(card_id, arguments.get("workdir"), create_default=True)

    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = (LOGS_DIR / f"{card_id}.log").resolve()
    attempts: list[dict[str, Any]] | None = None
    if pool_name is None:
        argv, stdin_text = _validated_command(
            adapter, profile, model, effort, prompt_text, write_scope, str(workdir)
        )
        pid = launcher.launch(argv, str(workdir), stdin_text, str(log_path))
        launch_status = "running"
        model_used: str | None = model
    else:
        assert candidates is not None
        built_commands: dict[str, list[str]] = {}
        stdin_holder: list[str | None] = []

        def make_argv(candidate: str) -> list[str]:
            candidate_argv, candidate_stdin = _validated_command(
                adapter, profile, candidate, effort, prompt_text, write_scope, str(workdir)
            )
            if not stdin_holder:
                stdin_holder.append(candidate_stdin)
            elif candidate_stdin != stdin_holder[0]:
                raise ValueError("adapter.build returned model-dependent stdin for one pool")
            built_commands[candidate] = candidate_argv
            return candidate_argv

        first_candidate = candidates[0]
        first_argv = make_argv(first_candidate)
        first_pending = True

        def cached_make_argv(candidate: str) -> list[str]:
            nonlocal first_pending
            if first_pending and candidate == first_candidate:
                first_pending = False
                return first_argv
            return make_argv(candidate)

        launch_result = launcher.launch_chain(
            cached_make_argv,
            candidates,
            str(workdir),
            stdin_holder[0],
            str(log_path),
            probe_sec=_probe_sec(),
        )
        launch_status = launch_result.get("status")
        model_used = launch_result.get("model_used")
        pid = launch_result.get("pid")
        attempts = launch_result.get("attempts")
        argv = built_commands.get(model_used) if isinstance(model_used, str) else None
        if argv is None:
            argv = built_commands.get(candidates[-1], first_argv)
        if launch_status == "running" and (
            not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0
        ):
            raise ValueError("launcher.launch_chain returned running without a valid PID")
        if launch_status not in {"running", "failed"}:
            raise ValueError(f"launcher.launch_chain returned invalid status: {launch_status!r}")

    now = _now_iso()
    prior_attempt = existing.get("attempt", 0) if existing else 0
    attempt = prior_attempt + 1 if isinstance(prior_attempt, int) and not isinstance(prior_attempt, bool) else 1
    record = {
        "card_id": card_id,
        "profile_id": profile_id,
        "vehicle": vehicle,
        "routing_reason": routing_reason,
        "supplier": profile.get("supplier"),
        "upstream_api": profile.get("upstream_api"),
        "full_access": bool(profile.get("full_access")),
        "model_requested": requested_model,
        "model": model_used or model,
        "effort": effort or "unset",
        "taskbook": str(taskbook),
        "cwd": str(workdir),
        "provider": profile.get("supplier", profile.get("provider", "profile-default")),
        "pid": pid,
        "timestamp": now,
        "attempt": attempt,
        "status": "running" if launch_status == "running" else "failed",
        "updated_at": now,
        "command": argv,
    }
    violations = registry_module.validate(record)
    if violations:
        launcher.stop_tree(pid)
        raise ValueError("invalid card record: " + "; ".join(violations))
    registry_module.upsert(str(REGISTRY_PATH), record)
    ledger_module.append(
        str(LEDGER_PATH),
        {
            "ts": now,
            "card_id": card_id,
            "profile": profile_id,
            "pool": pool_name if pool_name is not None else profile.get("pool"),
            "model_requested": model,
            "model_used": model_used,
            "effort": effort or "unset",
            "cwd": str(workdir),
            "pid": pid,
            "exit": None,
            "seconds": 0.0,
            "result": "running" if launch_status == "running" else "failed",
        },
    )
    if launch_status == "failed":
        _finalize_card(card_id, record, "failed")
        return {
            "ok": False,
            "card_id": card_id,
            "profile_id": profile_id,
            "vehicle": vehicle,
            "model_requested": model,
            "model_used": None,
            "effort": effort,
            "pid": None,
            "status": "failed",
            "command": argv,
            "attempts": attempts or [],
            "capability_gate": capability["status"],
            "capability": capability,
        }

    assert isinstance(pid, int) and not isinstance(pid, bool)
    if not launcher.probe_alive(pid, 0):
        record = _finalize_card(card_id, record, "finished")
        result_status = record.get("status", "finished")
    else:
        result_status = "running"
    result = {
        "ok": True,
        "card_id": card_id,
        "profile_id": profile_id,
        "vehicle": vehicle,
        "model_requested": requested_model,
        "routing_reason": routing_reason,
        "supplier": profile.get("supplier"),
        "upstream_api": profile.get("upstream_api"),
        "full_access": bool(profile.get("full_access")),
        "model_used": model_used,
        "effort": effort,
        "pid": pid,
        "status": result_status,
        "command": argv,
        "capability_gate": capability["status"],
        "capability": capability,
    }
    if attempts is not None:
        result["attempts"] = attempts
    return result


def _launch_group(arguments: dict[str, Any]) -> dict[str, Any]:
    cards = arguments["cards"]
    delay = arguments.get("stagger_seconds", 0.5)
    results: list[dict[str, Any]] = []
    for index, card in enumerate(cards):
        try:
            selected_profile = assembler.get_profile(str(LIB), card["profile_id"])
            effective, _, _ = routing.resolve(selected_profile, card.get("model", selected_profile["model"]))
            channel, _ = _adapter_for_profile(effective)
            results.append(_launch_card(card))
        except Exception as exc:
            _diagnostic(f"launch_group card failed: {type(exc).__name__}: {exc}")
            results.append({"ok": False, "card_id": card.get("card_id"), "error": str(exc)})
        if delay and index + 1 < len(cards):
            time.sleep(delay)
    return {"ok": all(item.get("ok") is True for item in results), "results": results}


def _runtime_seconds(record: dict[str, Any], alive: bool) -> float | None:
    start = record.get("timestamp")
    if not isinstance(start, str):
        return None
    try:
        start_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_text = record.get("finished_at") or record.get("stopped_at")
        end_time = (
            datetime.fromisoformat(end_text.replace("Z", "+00:00"))
            if not alive and isinstance(end_text, str)
            else datetime.now().astimezone()
        )
        if start_time.tzinfo is None:
            start_time = start_time.astimezone()
        if end_time.tzinfo is None:
            end_time = end_time.astimezone()
        return max(0.0, (end_time - start_time).total_seconds())
    except (TypeError, ValueError, OverflowError):
        return None


def _completed_exit(card_id: str) -> int | None:
    # A reused Windows PID must never make a completed card alive or be tree-killed.
    try:
        lines = (LOGS_DIR / f"{card_id}.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try: value = json.loads(line)
        except ValueError: continue
        if isinstance(value, dict) and type(value.get("card_process_exit")) is int:
            return value["card_process_exit"]
    return None


def _check_status(arguments: dict[str, Any]) -> dict[str, Any]:
    card_id = arguments["card_id"].strip()
    record = registry_module.get(str(REGISTRY_PATH), card_id)
    if record is None:
        return {"ok": False, "status": "not_found", "card_id": card_id}

    pid = record.get("pid")
    alive = (
        isinstance(pid, int)
        and not isinstance(pid, bool)
        and pid > 0
        and launcher.is_alive_now(pid)
    )
    if _completed_exit(card_id) is not None:
        alive = False
    if record.get("status") in {"starting", "running"} and not alive:
        record = _finalize_card(card_id, record, "finished")

    log_path = LOGS_DIR / f"{card_id}.log"
    try:
        log_tail = log_path.read_text(encoding="utf-8", errors="replace")[-200:]
    except OSError:
        log_tail = ""
    response = {
        "ok": True,
        "status": record.get("status"),
        "alive": alive,
        "pid": pid,
        "runtime_seconds": _runtime_seconds(record, alive),
        "exit_code": record.get("exit"),
        "log_tail": log_tail,
        "card": record,
    }
    if isinstance(record.get("degradation"), dict):
        response["degradation"] = record["degradation"]
    return response


def _first_paragraph(markdown: str) -> str:
    paragraph: list[str] = []
    in_fence = False
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line:
            if paragraph:
                break
            continue
        if line.startswith("#"):
            continue
        paragraph.append(line)
    if paragraph:
        return " ".join(paragraph)[:1000]
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if line:
            return line[:1000]
    return ""


def _card_report_dirs(record: dict[str, Any], card_id: str) -> list[Path]:
    """Return only directories owned by this card, in workspace-first order."""
    directories: list[Path] = []
    try:
        entries = ledger_module.read_all(str(LEDGER_PATH))
    except Exception:
        entries = []
    for entry in reversed(entries):
        if entry.get("card_id") != card_id:
            continue
        cwd = entry.get("cwd")
        if isinstance(cwd, str) and cwd:
            try:
                candidate = Path(cwd).resolve()
                # The exact-card ledger launch record is the workspace authority;
                # a user-selected folder need not repeat the runtime card ID.
                directories.append(candidate)
            except (OSError, ValueError):
                pass
            break
    directories.extend([_default_workdir(card_id), ROOT / "cards" / card_id])
    taskbook = record.get("taskbook")
    if isinstance(taskbook, str) and taskbook:
        taskbook_parent = Path(taskbook).parent
        # Retry/fallback runtime IDs append suffixes (for example ``-R1`` or
        # ``-fb1-OCU``) while keeping the original taskbook and workdir. Treat
        # that registered taskbook directory as owned when the runtime ID is
        # exactly the card ID or has it as a delimited prefix.
        owner_id = taskbook_parent.name.casefold()
        runtime_id = card_id.casefold()
        if runtime_id == owner_id or runtime_id.startswith(owner_id + "-"):
            workdir = taskbook_parent / "work"
            directories.insert(0, workdir if workdir.is_dir() else taskbook_parent)
            directories.append(taskbook_parent)
    return list(dict.fromkeys(path.resolve() for path in directories))


def _legacy_card_report_dirs(record: dict[str, Any], card_id: str) -> list[Path]:
    """Old report locations, used only as a card-ID-filtered last resort."""
    directories = [
        REPORTS_DIR / card_id,
        ROOT / "artifacts" / card_id,
        ROOT / card_id,
        REPORTS_DIR,
    ]
    taskbook = record.get("taskbook")
    if isinstance(taskbook, str) and taskbook:
        taskbook_parent = Path(taskbook).parent
        candidate_sibling = taskbook_parent.parent / "reports"
        if candidate_sibling.is_dir():
            directories.append(candidate_sibling)
    return list(dict.fromkeys(path.resolve() for path in directories))


_DELIVERABLE_LINE_RE = re.compile(r"[^\s`\"'<>|*?\)\]}]+\.(?:md|json|jsonl|csv|txt|html|htm)")


def _declared_deliverables(task_text: str) -> list[str]:
    """Extract declared output paths without treating read-only references as outputs."""
    outputs, _, mode = _taskbook_path_declarations(task_text)
    if outputs:
        return outputs
    if mode != "fallback":
        return []
    names: list[str] = []
    for line in task_text.splitlines():
        low = line.lower()
        if not any(k in low for k in ("写入", "落盘", "产物", "产出", "写到", "保存", "输出")):
            continue
        for m in _DELIVERABLE_LINE_RE.finditer(line):
            names.append(_clean_task_path(m.group(0)))
    return list(dict.fromkeys(names))


def _markdown_candidates(directories: list[Path], taskbook: Path | None) -> list[Path]:
    candidates: dict[str, Path] = {}
    for directory in directories:
        if not directory.is_dir():
            continue
        try:
            paths = directory.rglob("*.md")
            for candidate in paths:
                if not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                if taskbook is not None and resolved == taskbook:
                    continue
                candidates[str(resolved)] = resolved
        except OSError:
            continue
    return list(candidates.values())


def _declared_report_paths(
    declared: list[str], record: dict[str, Any], card_id: str
) -> list[Path]:
    taskbook = record.get("taskbook")
    taskbook_parent = Path(taskbook).parent if isinstance(taskbook, str) and taskbook else ROOT
    workdir = _card_report_dirs(record, card_id)[0]
    resolved_paths: list[Path] = []
    for value in declared:
        path = Path(value)
        variants = [path] if path.is_absolute() else [workdir / path, taskbook_parent / path, ROOT / path]
        for candidate in variants:
            try:
                resolved = candidate.resolve()
            except (OSError, ValueError):
                continue
            if resolved.suffix.lower() == ".md" and resolved.is_file():
                resolved_paths.append(resolved)
                break
    return list(dict.fromkeys(resolved_paths))


def _find_card_report(record: dict[str, Any], card_id: str) -> str | None:
    directories = _card_report_dirs(record, card_id)
    taskbook = record.get("taskbook")
    try:
        taskbook_resolved = Path(taskbook).resolve() if isinstance(taskbook, str) and taskbook else None
    except OSError:
        taskbook_resolved = None

    # Prefer the conventional deliverable over unrelated Markdown files found
    # recursively in the same card workspace. This also prevents an old
    # card-scoped global report from winning for a retried runtime ID.
    for directory in directories:
        candidate = directory / "report.md"
        if candidate.is_file():
            try:
                resolved = candidate.resolve()
            except (OSError, ValueError):
                continue
            if taskbook_resolved is None or resolved != taskbook_resolved:
                return str(resolved)

    own_candidates = [path.resolve() for directory in directories if directory.is_dir()
                      for path in directory.glob("*.md") if path.is_file()
                      and path.resolve() != taskbook_resolved
                      and (path.stem.casefold() in {"report", "final_report", "result"}
                      or path.stem.casefold().endswith("_report") or "报告" in path.stem)]
    if own_candidates:
        return str(max(own_candidates, key=lambda path: path.stat().st_mtime_ns))

    declared = _declared_deliverables(task_text_of(taskbook_resolved))
    exact = _declared_report_paths(declared, record, card_id)
    if exact:
        return str(max(exact, key=lambda path: path.stat().st_mtime_ns))

    # Last-resort legacy search is constrained to paths or filenames naming this card.
    card_key = card_id.casefold()
    # Some historical reports are named with the stable card number only
    # (for example CXU15_并发压测.md), while registry IDs may include a
    # launch suffix such as -lu6-xh. Match that number as a delimited prefix.
    card_number = card_key.split("-", 1)[0]
    legacy = [
        path for path in _markdown_candidates(_legacy_card_report_dirs(record, card_id), taskbook_resolved)
        if card_key in path.stem.casefold()
        or re.match(rf"^{re.escape(card_number)}(?:$|[_\-.])", path.stem.casefold())
        or any(part.casefold() == card_key for part in path.parts)
    ]
    if legacy:
        return str(max(legacy, key=lambda path: path.stat().st_mtime_ns))
    return None


def task_text_of(taskbook_resolved: Path | None) -> str:
    if taskbook_resolved is None or not taskbook_resolved.is_file():
        return ""
    try:
        return taskbook_resolved.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _collect_report(arguments: dict[str, Any]) -> dict[str, Any]:
    card_id = arguments["card_id"].strip()
    record = registry_module.get(str(REGISTRY_PATH), card_id)
    if record is None:
        return {"ok": False, "status": "not_found", "card_id": card_id}

    found_path = _find_card_report(record, card_id)
    if not found_path:
        return {
            "ok": False,
            "card_id": card_id,
            "status": "no_report",
            "message": f"这张卡 {card_id} 没产物。",
        }
    report = Path(found_path)
    try:
        markdown = report.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"ok": False, "card_id": card_id, "status": "read_error", "error": str(exc)}
    content_gate = _content_gate_result(markdown)
    blocked = content_gate.get("status") == "blocked"
    diagnostics = _terminal_log_diagnostics(card_id)
    checked=_check_status({'card_id':card_id})
    execution_failed=checked.get('status') != 'finished' or checked.get('alive') is True or checked.get('exit_code') != 0
    return {
        "ok": not blocked and not execution_failed,
        "card_id": card_id,
        "status": "execution_error" if execution_failed else "quality_blocked" if blocked else "found",
        "report_path": str(report),
        "summary": _first_paragraph(markdown),
        "content_gate": content_gate["status"],
        "content_gate_result": content_gate,
        "execution_diagnostics": diagnostics,
    }


def _stop_card(arguments: dict[str, Any]) -> dict[str, Any]:
    card_id = arguments["card_id"].strip()
    record = registry_module.get(str(REGISTRY_PATH), card_id)
    if record is None:
        return {"ok": False, "status": "not_found", "card_id": card_id}
    if record.get('status') in ('starting','running') and _completed_exit(card_id) is not None:
        record = _finalize_card(card_id, record, 'finished')
    if record.get('status') not in ('starting','running'):
        return {'ok':True,'card_id':card_id,'status':record.get('status'),'instruction':'Already terminal; no process was stopped.'}

    pid = record.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return {"ok": False, "status": record.get("status"), "card_id": card_id, "pid": pid}

    terminal = launcher.stop_tree(pid)
    record = _finalize_card(card_id, record, terminal)
    if terminal == "stop_failed":
        record["error"] = record.get("error") or "failed to stop process tree"
        registry_module.upsert(str(REGISTRY_PATH), record)
    response = {
        "ok": terminal != "stop_failed",
        "card_id": card_id,
        "pid": pid,
        "status": record.get("status", terminal),
    }
    if isinstance(record.get("degradation"), dict):
        response["degradation"] = record["degradation"]
    return response


def _list_cards(arguments: dict[str, Any]) -> dict[str, Any]:
    """Return every card reconciled against process liveness.

    2026-10-10 事故：卡在运行期间就被当作终态判读，事后才发现多数没写进交付物。
    这里把 liveness 对账提前到一个工具里，避免靠手读 jsonl 判断。
    """
    wanted = arguments.get("status_filter", "all")
    try:
        records = registry_module.all_records(str(REGISTRY_PATH))
    except FileNotFoundError:
        return {"ok": True, "count": 0, "cards": [], "note": "registry 尚未初始化"}

    out: list[dict[str, Any]] = []
    for rec in records:
        card_id = rec.get("card_id")
        if not isinstance(card_id, str) or not card_id:
            continue
        pid = rec.get("pid")
        alive = (
            isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
            and launcher.is_alive_now(pid)
        )
        if _completed_exit(card_id) is not None:
            alive = False
        status = rec.get("status")
        if status in {"starting", "running"} and not alive:
            rec = _finalize_card(card_id, rec, "finished")
            status = rec.get("status")
        if wanted != "all" and status != wanted:
            continue
        report = _find_card_report(rec, card_id)
        out.append({
            "card_id": card_id,
            "profile_id": rec.get("profile_id"),
            "model": rec.get("model"),
            "effort": rec.get("effort"),
            "status": status,
            "alive": alive,
            "pid": pid,
            "runtime_seconds": _runtime_seconds(rec, alive),
            "report_path": report,
            "degradation": rec.get("degradation"),
            "updated_at": rec.get("updated_at"),
        })
    out.sort(key=lambda r: str(r.get("card_id")))
    running = sum(1 for r in out if r.get("status") in {"starting", "running"})
    return {
        "ok": True,
        "count": len(out),
        "running": running,
        "with_report": sum(1 for r in out if r.get("report_path")),
        "cards": out,
    }


def _code_fingerprint() -> dict[str, Any]:
    """记录本进程启动时加载的代码指纹，用来暴露「改了代码没重启」。

    2026-10-11 血账：CXL15 把 collect_report 的路径 bug 改对了，直接调函数返回正确结果，
    但通过 MCP 调仍报 no_report —— 因为这个 server 是常驻 stdio 进程，
    跑的是**启动那一刻加载的旧代码**。表现为「修了没效果」，会诱使人反复改代码越改越乱。

    做法：启动时把关键文件的 sha256 与 mtime 记下来；list_profiles 回显启动时的指纹，
    指挥层拿它跟磁盘上的当前指纹一比，就知道该不该重启。
    """
    files = (
        "mcp/launcher_mcp_server.py",
        "adapters/provider_adapter.py",
        "adapters/provider_config.py",
        "adapters/provider_cli.py",
        "adapters/provider_gateway.py",
        "adapters/agy.py",
        "adapters/agy_sdk.py",
        "adapters/codex.py",
        "adapters/codex_minimax_runner.py",
        "adapters/minimax_responses_bridge.py",
        "kernel/routing.py",
        "adapters/claude_minimax.py",
        "adapters/cline.py",
        "adapters/copilot.py",
        "adapters/agy.py",
        "adapters/agy_sdk.py",
        "adapters/agy_sdk_runner.py",
        "adapters/claude_minimax.py",
        "adapters/minimax_copilot_runner.py",
        "adapters/kimi.py",
        "adapters/minimax_kimi_runner.py",
        "adapters/minimax_code.py",
        "adapters/minimax_code_runner.py",
        "adapters/trae.py",
        "adapters/minimax_anthropic_bridge.py",
        "adapters/minimax_agy_shim.py",
        "adapters/bridge_runner.py",
        "adapters/opencode.py",
        "adapters/zcode.py",
        "adapters/zcode_runner.py",
        "kernel/assembler.py",
        "kernel/launcher.py",
        "kernel/process_runner.py",
        "kernel/registry.py",
        "kernel/ledger.py",
    )
    digest = hashlib.sha256()
    stamps: dict[str, str] = {}
    for rel in files:
        path = ROOT / rel
        try:
            data = path.read_bytes()
        except OSError:
            stamps[rel] = "missing"
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(data)
        stamp = datetime.fromtimestamp(path.stat().st_mtime).strftime("%H:%M:%S")
        stamps[rel] = f"{hashlib.sha256(data).hexdigest()[:12]}@{stamp}"
    return {"fingerprint": digest.hexdigest()[:12], "files": stamps}


_STARTUP_CODE = _code_fingerprint()


def _code_staleness() -> dict[str, Any]:
    """当前磁盘上的代码指纹 vs 本进程启动时的指纹。"""
    current = _code_fingerprint()
    changed = [
        rel for rel, stamp in current["files"].items()
        if _STARTUP_CODE["files"].get(rel) != stamp
    ]
    return {
        "loaded_at_start": _STARTUP_CODE["fingerprint"],
        "on_disk_now": current["fingerprint"],
        "stale": bool(changed),
        "changed_files": sorted(changed),
        "advice": (
            "代码已改但本进程跑的是旧版本 —— 重启 MCP server（或重启 Pi）后才生效。"
            if changed else "已是最新。"
        ),
    }


def _list_profiles() -> dict[str, Any]:
    profile_data = assembler.load_profiles(str(LIB))
    profiles = profile_data.get("profiles")
    if not isinstance(profiles, list):
        raise ValueError("profiles.json must contain a profiles array")
    fields = ("id", "role", "cli", "model", "reasoning_effort", "state", "universal_provider", "full_access", "verified_scope")
    retired_fields = ("id", "role", "cli", "model", "state", "retired_reason")
    actual_role_counts = {
        role: sum(1 for profile in profiles if isinstance(profile, dict) and profile.get("role") == role)
        for role in ("U", "L", "B")
    }
    actual_role_counts["total"] = len(profiles)
    return {
        "ok": True,
        "role_counts": actual_role_counts,
        "routing_policy": {"version": "20261023", "default_model": profile_data.get("defaults", {}).get("model"), "free_model": profile_data.get("defaults", {}).get("free_model"), "free_cli": "selected profile CLI (non-CX)", "entry": str(ROOT / "mcp/launcher_entry.py")},
        "profiles": [
            {
                **{field: profile.get(field) for field in fields},
                "aliases": assembler.aliases_for_profile(str(LIB), str(profile.get("id", ""))),
            }
            for profile in profiles
        ],
        "retired_profiles": [
            {
                **{field: profile.get(field) for field in retired_fields},
                "aliases": assembler.aliases_for_profile(str(LIB), str(profile.get("id", ""))),
            }
            for profile in profile_data.get("retired", [])
            if isinstance(profile, dict)
        ],
        "code": _code_staleness(),
    }


def _diagnostic(message: str) -> None:
    try:
        sys.stderr.write(f"launcher_mcp_server: {message}\n")
        sys.stderr.flush()
    except Exception:
        pass


def _execute_tool(name: str, arguments: Any) -> tuple[dict[str, Any], bool]:
    if name in {"launch_card", "launch_group"} and _code_staleness()["stale"]:
        return {"ok": False, "status": "stale_code_blocked", "error": "Use mcp/launcher_entry.py or tools/mcp_call.py; refusing to dispatch with old code."}, True
    errors = _validate_tool_arguments(name, arguments)
    if errors:
        return {"ok": False, "status": "invalid_arguments", "errors": errors}, True
    try:
        if name == "launch_card":
            result = _launch_card(arguments)
        elif name == "launch_group":
            result = _launch_group(arguments)
        elif name == "check_status":
            result = _check_status(arguments)
        elif name == "collect_report":
            result = _collect_report(arguments)
        elif name == "stop_card":
            result = _stop_card(arguments)
        elif name == "list_profiles":
            result = _list_profiles()
        elif name == "list_cards":
            result = _list_cards(arguments)
        else:
            return {"ok": False, "error": f"unknown tool: {name}"}, True
    except Exception as exc:
        _diagnostic(f"tool {name} failed: {type(exc).__name__}: {exc}")
        return {"ok": False, "error": str(exc)}, True
    return result, result.get("ok") is False


def _jsonrpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _valid_request_id(value: Any) -> bool:
    return value is None or (
        isinstance(value, (str, int, float))
        and not isinstance(value, bool)
        and (not isinstance(value, float) or math.isfinite(value))
    )


def _handle_message(message: Any) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return _jsonrpc_error(None, -32600, "Invalid Request")

    has_id = "id" in message
    request_id = message.get("id")
    if has_id and not _valid_request_id(request_id):
        return _jsonrpc_error(None, -32600, "Invalid Request")
    if message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _jsonrpc_error(request_id if has_id else None, -32600, "Invalid Request")

    method = message["method"]
    params = message.get("params", {})
    if method == "notifications/initialized":
        return None
    if not has_id:
        return None

    if method == "initialize":
        if not isinstance(params, dict):
            return _jsonrpc_error(request_id, -32602, "Invalid params")
        protocol_version = params.get("protocolVersion")
        capabilities = params.get("capabilities")
        client_info = params.get("clientInfo")
        if (
            not isinstance(protocol_version, str)
            or not protocol_version
            or not isinstance(capabilities, dict)
            or not isinstance(client_info, dict)
            or not isinstance(client_info.get("name"), str)
            or not isinstance(client_info.get("version"), str)
        ):
            return _jsonrpc_error(request_id, -32602, "Invalid params")
        negotiated = (
            protocol_version
            if protocol_version in SUPPORTED_PROTOCOL_VERSIONS
            else SERVER_PROTOCOL_VERSION
        )
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": negotiated,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "card-launcher", "version": "2026.10.13"},
            },
        }

    if method == "ping":
        if not isinstance(params, dict):
            return _jsonrpc_error(request_id, -32602, "Invalid params")
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}

    if method == "tools/list":
        if not isinstance(params, dict):
            return _jsonrpc_error(request_id, -32602, "Invalid params")
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        if not isinstance(params, dict) or not isinstance(params.get("name"), str):
            return _jsonrpc_error(request_id, -32602, "Invalid params")
        name = params["name"]
        arguments = params.get("arguments", {})
        result, is_error = _execute_tool(name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False, separators=(",", ":")),
                    }
                ],
                "isError": is_error,
            },
        }

    return _jsonrpc_error(request_id, -32601, "Method not found")


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _write_message(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, ensure_ascii=False, separators=(",", ":"), allow_nan=False))
    sys.stdout.write("\n")
    sys.stdout.flush()


def main() -> None:
    # 2026-10-09 集成期修正：stdio MCP 必须走 UTF-8。Windows 默认 cp936 会把中文
    # JSON 编成非法 UTF-8，令客户端按 UTF-8 解码时崩溃。
    for stream, kwargs in (
        (sys.stdin, {"encoding": "utf-8", "errors": "replace"}),
        (sys.stdout, {"encoding": "utf-8", "errors": "replace", "newline": "\n"}),
        (sys.stderr, {"encoding": "utf-8", "errors": "replace"}),
    ):
        try:
            stream.reconfigure(**kwargs)
        except (AttributeError, ValueError, OSError):
            pass
    for line_number, line in enumerate(sys.stdin, start=1):
        if not line.strip():
            continue
        try:
            message = json.loads(line, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, ValueError) as exc:
            _diagnostic(f"line {line_number}: JSON parse error: {exc}")
            _write_message(_jsonrpc_error(None, -32700, "Parse error"))
            continue
        try:
            response = _handle_message(message)
            if response is not None:
                _write_message(response)
        except Exception as exc:
            _diagnostic(f"line {line_number}: request failed: {type(exc).__name__}: {exc}")
            request_id = message.get("id") if isinstance(message, dict) else None
            _write_message(_jsonrpc_error(request_id, -32603, "Internal error"))


if __name__ == "__main__":
    main()
