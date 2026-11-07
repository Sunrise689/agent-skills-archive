"""Launch the official ZCode Agent CLI with an ephemeral MiniMax Token Plan config."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


DEFAULT_MODEL = "MiniMax-M3.1-Flash"
BASE_URL = "https://api.minimaxi.com/v1"
PROVIDER = "minimax-token-plan"
NODE = Path(r"C:\Program Files\nodejs\node.exe")
ZCODE_CLI = Path(r"~\Desktop\hd\工具库\card_launcher\external\zcode-cli\zcode.cjs")
BUILTIN_CONFIG = Path(r"~\Desktop\hd\工具库\card_launcher\external\zcode-cli\provider\zcode-builtin.json")
TOKEN_SOURCE = Path.home() / ".pi" / "agent" / "models.json"


def _token_plan_key() -> str:
    try:
        data = json.loads(TOKEN_SOURCE.read_text(encoding="utf-8"))
        provider = data.get("providers", {}).get("minimax", {})
        key = provider.get("apiKey")
        if not isinstance(key, str) or not key.strip():
            raise ValueError
        if provider.get("baseUrl") != BASE_URL:
            raise ValueError
        return key.strip()
    except (OSError, json.JSONDecodeError, AttributeError, TypeError, ValueError):
        raise RuntimeError("MiniMax Token Plan local credential/model config is unavailable") from None


def _write_runtime_config(home: Path, key: str, model: str) -> Path:
    personal_config = home / ".zcode" / "v2" / "provider_config.json"
    personal_config.parent.mkdir(parents=True, exist_ok=True)
    personal_config.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "config": {
                    "providerConfigRules": {
                        "providerRules": [
                            {
                                "providerId": PROVIDER,
                                "providerName": "MiniMax Token Plan",
                                "config": {
                                    "group": "standard-personal",
                                    "access": {"type": "api-key", "apiKey": key},
                                    "api": {
                                        "type": "openai-chat-completions",
                                        "baseUrl": BASE_URL,
                                    },
                                    "personalModelIds": [model],
                                    "modelOrder": [model],
                                },
                            }
                        ]
                    },
                    "modelConfigRules": {
                        "providerModelRules": [],
                        "manualProviderModelRules": [],
                    },
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return personal_config


CARD_USAGE_DIRNAME = ".card_usage"


def _pid_chain(depth: int = 6) -> list:
    """向上收集父进程 pid 链（见 minimax_responses_bridge_upstream.py 同名函数说明）。"""
    out = []
    p = os.getpid()
    for _ in range(depth):
        try:
            p = os.getppid()
        except Exception:
            break
        if not p or p in out:
            break
        out.append(p)
    return out


def _collect_usage(home: Path, workdir: Path, model: str) -> dict:
    """把临时 HOME 里的 zcode 用量证据抢救到卡工作区（只新增文件）。"""
    import datetime
    out_dir = workdir / CARD_USAGE_DIRNAME / "zcode"
    out_dir.mkdir(parents=True, exist_ok=True)
    rolls = sorted(home.rglob("model-io-*.jsonl"))
    agg = {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0,
           "cache_creation_tokens": 0, "total_tokens": 0, "calls": 0}
    per_call = []
    models = set()
    for rp in rolls:
        try:
            with open(rp, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if not line.startswith("{"):
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    u = (o.get("response") or {}).get("usage")
                    if not isinstance(u, dict):
                        continue
                    def g(*names):
                        for k in names:
                            v = u.get(k)
                            if isinstance(v, (int, float)):
                                return v
                        return 0
                    row = {
                        "started_at": o.get("startedAt"),
                        "input_tokens": g("inputTokens", "prompt_tokens", "input_tokens"),
                        "output_tokens": g("outputTokens", "completion_tokens", "output_tokens"),
                        "cache_read_tokens": g("cacheReadTokens", "cache_read_input_tokens", "cached_tokens"),
                        "total_tokens": g("totalTokens", "total_tokens"),
                        "query_source": o.get("querySource"),
                    }
                    agg["calls"] += 1
                    agg["input_tokens"] += row["input_tokens"]
                    agg["output_tokens"] += row["output_tokens"]
                    agg["cache_read_tokens"] += row["cache_read_tokens"]
                    agg["total_tokens"] += row["total_tokens"]
                    m = o.get("model") or {}
                    if isinstance(m, dict) and m.get("modelId"):
                        models.add(m["modelId"])
                    per_call.append(row)
        except OSError:
            continue
    payload = {
        "source": "zcode CLI 通道自报（.zcode/cli/rollout/model-io-*.jsonl，从临时 HOME 抢救）",
        "model_requested": model,
        "models_seen": sorted(models),
        "collected_at": datetime.datetime.now().astimezone().isoformat(),
        # 【2026-10-22】记录卡进程 pid 与祖先链 → 台账可精确对回卡（注册表 pid 是 launcher 层，
        # 与本进程 pid 可能差一层，见 minimax_responses_bridge_upstream.py 的说明）。
        "card_pid": os.getpid(),
        "card_pid_chain": _pid_chain(),
        "usage": agg,
        "per_call": per_call[:2000],
        "rollout_files": [p.name for p in rolls],
    }
    # 【2026-10-22 修正】文件名带 pid —— 固定名会被同通道的后一张卡覆盖
    #   （实测：ZCU3 的 zcode_usage.json 直接盖掉了 ZCU2 的证据，ZCU2 又变回无 token）。
    (out_dir / ("zcode_usage_pid%d.json" % os.getpid())).write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    # 统一约定的逐卡用量文件（文件名带 pid → 台账按派卡注册表的 pid 精确对回卡）
    try:
        pid_file = workdir / CARD_USAGE_DIRNAME / ("usage_pid%d_zc.jsonl" % os.getpid())
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        with pid_file.open("w", encoding="utf-8") as fh:
            for row in per_call:
                fh.write(json.dumps({
                    "ts": row.get("started_at"),
                    "channel": "zcode",
                    "model": model,
                    "stream": False,
                    "self_pid": os.getpid(),
                    "pid_chain": _pid_chain(),
                    "input_tokens": row.get("input_tokens", 0),
                    "output_tokens": row.get("output_tokens", 0),
                    "total_tokens": row.get("total_tokens", 0),
                    "cache_read_tokens": row.get("cache_read_tokens", 0),
                    "reasoning_tokens": 0,
                }, ensure_ascii=False) + "\n")
    except OSError as exc:
        print("[zcode-usage] 逐卡用量文件写入失败: %s" % exc, flush=True)
    for p in rolls:
        try:
            shutil.copy2(p, out_dir / p.name)
        except OSError:
            pass
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--cwd", required=True)
    args = parser.parse_args()
    if not args.model.startswith("MiniMax-") or args.model == "MiniMax-M3":
        raise SystemExit("select an available MiniMax Token Plan model; MiniMax-M3 is disabled")
    if not NODE.is_file() or not ZCODE_CLI.is_file() or not BUILTIN_CONFIG.is_file():
        raise FileNotFoundError("Official ZCode CLI bundle, Node.js runtime, or provider catalog is missing")
    workdir = Path(args.cwd).resolve()
    if not workdir.is_dir():
        raise FileNotFoundError(f"Card workdir is unavailable: {workdir}")

    key = _token_plan_key()
    home = Path(tempfile.mkdtemp(prefix="card-zcode-cli-"))
    try:
        personal_config = _write_runtime_config(home, key, args.model)
        prompt = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        env = os.environ.copy()
        env.update(
            {
                "USERPROFILE": str(home),
                "HOME": str(home),
                "ZCODE_DATA_BASE_DIR": str(home),
                "ZCODE_BUILTIN_PROVIDER_CONFIG_FILE": str(BUILTIN_CONFIG),
                "ZCODE_PERSONAL_PROVIDER_CONFIG_FILE": str(personal_config),
                "APPDATA": str(home / "AppData" / "Roaming"),
                "LOCALAPPDATA": str(home / "AppData" / "Local"),
            }
        )
        argv = [
            str(NODE), str(ZCODE_CLI), "--prompt", prompt, "--cwd", str(workdir),
            "--mode", "yolo", "--output-format", "text", "--locale", "zh-CN", "--no-color",
        ]
        rc = subprocess.run(argv, cwd=str(workdir), env=env, check=False).returncode
        # 先抢救用量证据，再删临时 HOME（否则 token 用量随临时目录一起消失）
        try:
            _collect_usage(home, workdir, args.model)
        except Exception:
            pass
        return rc
    finally:
        key = ""
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
