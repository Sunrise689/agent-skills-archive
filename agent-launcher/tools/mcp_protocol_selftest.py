#!/usr/bin/env python3
# 用途：MCP 协议层机械验收脚本——把 mcp/launcher_mcp_server.py 当子进程拉起，
#       用 stdio 逐行 JSON-RPC 2.0 打 initialize / tools/list / tools/call 三个往返，
#       机械判定协议层是否合法（依据 CONTRACT.md 第 3 节验收第 4 条）。
#       契约修订 2026-10-10：工具清单由 6 项变为 7 项（新增 list_cards，用于追加式
#       registry 的状态对账）。本文件与 CONTRACT 需同步；本次只同步本文件。
#
# 用法：
#   python tools\mcp_protocol_selftest.py                  # 跑默认被测文件
#   python tools\mcp_protocol_selftest.py --server X.py    # 换被测文件（桩自检用）
#   python tools\mcp_protocol_selftest.py --timeout 30     # 每步超时秒数
# 退出码：0 = 三项断言全过；1 = 有失败。
# stdout 只输出一段 JSON 判定摘要 {"ok","passed","failed","details"}；所有诊断信息在 details 里，
# 人读诊断另走 stderr，不污染 stdout 的协议流。
#
# ---------------------------------------------------------------------------
# 桩自检做法（本脚本自身逻辑的验证方式，任务书 A2-C3 判据 2）：
#   写一个 30 行以内的内联“假 MCP”服务器到临时文件，只按行读 JSON 再按行回 JSON：
#     initialize                 -> result.protocolVersion + result.serverInfo
#     tools/list                 -> 若干个工具名（个数由环境变量 STUB_TOOL_COUNT 决定）
#     tools/call(list_profiles)  -> result.content[0].text = json.dumps({...})
#   然后用同一份脚本、同一份桩跑两遍，只改环境变量：
#     set STUB_TOOL_COUNT=6 && python tools\mcp_protocol_selftest.py --server <桩.py>
#         # 期望 ok=true、passed 三项、退出码 0
#     set STUB_TOOL_COUNT=5 && python tools\mcp_protocol_selftest.py --server <桩.py>
#         # 期望 ok=false、failed=["tools_list"]（缺 list_profiles）、退出码 1
#   两遍都符合预期，说明断言逻辑既能判 PASS 也能判 FAIL。桩文件跑完即删。
#   （脚本把父进程环境整体传给子进程，所以 STUB_TOOL_COUNT 能透传到桩里。）
# ---------------------------------------------------------------------------
#
# 说明：严格 MCP 在 initialize 之后客户端要补发 notifications/initialized。本脚本按任务书
# 契约只打三个往返，不额外发通知，避免对最小实现引入非契约要求。

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SERVER = ROOT / "mcp" / "launcher_mcp_server.py"

EXPECTED_TOOLS = (
    "launch_card",
    "launch_group",
    "check_status",
    "collect_report",
    "stop_card",
    "list_profiles",
    "list_cards",
)
PROTOCOL_VERSION = "2025-06-18"
DEFAULT_TIMEOUT = 30.0
STDERR_TAIL_CHARS = 4000
STEP_NAMES = ("initialize", "tools_list", "tools_call_list_profiles")


class _RpcSession:
    """把被测 MCP 服务器当子进程拉起，逐行发/收 JSON-RPC。"""

    def __init__(self, server_path, timeout=DEFAULT_TIMEOUT):
        self.server_path = Path(server_path)
        self.timeout = float(timeout)
        self.proc = None
        self._out = queue.Queue()
        self._err_lines = []
        self._threads = []

    def start(self):
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(ROOT) + (os.pathsep + existing if existing else "")
        self.proc = subprocess.Popen(
            [sys.executable, str(self.server_path)],
            cwd=str(ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
        )
        self._threads = [
            threading.Thread(target=self._pump, args=(self.proc.stdout, self._out), daemon=True),
            threading.Thread(target=self._pump, args=(self.proc.stderr, self._err_lines), daemon=True),
        ]
        for thread in self._threads:
            thread.start()

    @staticmethod
    def _pump(stream, sink):
        try:
            while True:
                line = stream.readline()
                if not line:
                    break
                if isinstance(sink, queue.Queue):
                    sink.put(line)
                else:
                    sink.append(line)
        except Exception:
            pass

    def request(self, payload, timeout=None):
        """发一条 JSON-RPC，返回 {"ok","response","error"}。"""
        timeout = self.timeout if timeout is None else float(timeout)
        if self.proc is None or self.proc.poll() is not None:
            return {"ok": False, "response": None, "error": "子进程未运行或已退出"}
        try:
            self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except Exception as exc:
            return {"ok": False, "response": None, "error": "写入请求失败: %r" % (exc,)}
        deadline = time.monotonic() + timeout
        skipped = 0
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {
                    "ok": False,
                    "response": None,
                    "error": "等待回包超时 %.1fs（已跳过 %d 行 id 不匹配的行）" % (timeout, skipped),
                }
            try:
                line = self._out.get(timeout=remaining)
            except queue.Empty:
                return {
                    "ok": False,
                    "response": None,
                    "error": "等待回包超时 %.1fs（已跳过 %d 行 id 不匹配的行）" % (timeout, skipped),
                }
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except Exception as exc:
                return {
                    "ok": False,
                    "response": None,
                    "error": "回包不是合法 JSON: %s | 原始行=%s" % (exc, line[:300]),
                }
            if not isinstance(resp, dict):
                return {"ok": False, "response": None, "error": "回包不是 JSON 对象: %s" % line[:300]}
            if resp.get("id") != payload.get("id"):
                skipped += 1
                continue
            if "error" in resp and "result" not in resp:
                detail = json.dumps(resp.get("error"), ensure_ascii=False)[:300]
                return {"ok": False, "response": resp, "error": "回包是 JSON-RPC error: %s" % detail}
            return {"ok": True, "response": resp, "error": None}

    def stderr_tail(self, limit=STDERR_TAIL_CHARS):
        return "".join(self._err_lines)[-limit:]

    def close(self):
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(timeout=5)
        except Exception:
            pass
        for thread in self._threads:
            thread.join(timeout=2)


def check_initialize(sess, timeout):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "selftest", "version": "1.0"},
        },
    }
    reply = sess.request(payload, timeout)
    if not reply["ok"]:
        return {"passed": False, "error": reply["error"], "detail": {}}
    resp = reply["response"]
    if resp.get("jsonrpc") != "2.0":
        return {"passed": False, "error": "回包 jsonrpc 字段不是 '2.0': %r" % (resp.get("jsonrpc"),), "detail": {}}
    result = resp.get("result")
    if not isinstance(result, dict):
        return {"passed": False, "error": "回包缺少 result 对象", "detail": {}}
    protocol_version = result.get("protocolVersion")
    server_info = result.get("serverInfo")
    detail = {"protocol_version": protocol_version, "server_info": server_info}
    if not isinstance(protocol_version, str) or not protocol_version:
        return {"passed": False, "error": "result.protocolVersion 缺失或非字符串", "detail": detail}
    if not isinstance(server_info, dict) or not isinstance(server_info.get("name"), str) or not server_info.get("name"):
        return {"passed": False, "error": "result.serverInfo 缺失或缺 name", "detail": detail}
    return {"passed": True, "error": None, "detail": detail}


def check_tools_list(sess, timeout):
    payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    reply = sess.request(payload, timeout)
    if not reply["ok"]:
        return {"passed": False, "error": reply["error"], "detail": {}}
    result = reply["response"].get("result")
    if not isinstance(result, dict):
        return {"passed": False, "error": "回包缺少 result 对象", "detail": {}}
    tools = result.get("tools")
    if not isinstance(tools, list):
        return {"passed": False, "error": "result.tools 缺失或不是数组", "detail": {}}
    names = []
    malformed = 0
    for item in tools:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
        else:
            malformed += 1
    unique = set(names)
    missing = sorted(set(EXPECTED_TOOLS) - unique)
    extra = sorted(unique - set(EXPECTED_TOOLS))
    duplicates = sorted({n for n in unique if names.count(n) > 1})
    detail = {
        "tools_returned": sorted(unique),
        "tools_missing": missing,
        "tools_extra": extra,
        "tools_duplicated": duplicates,
        "tools_count": len(names),
        "tools_malformed": malformed,
    }
    if missing or extra or duplicates or malformed:
        return {
            "passed": False,
            "error": "工具清单不合约：缺 %s / 多 %s / 重复 %s / 缺 name 的项 %d"
            % (missing or "无", extra or "无", duplicates or "无", malformed),
            "detail": detail,
        }
    return {"passed": True, "error": None, "detail": detail}


def check_tools_call_list_profiles(sess, timeout):
    payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {"name": "list_profiles", "arguments": {}},
    }
    reply = sess.request(payload, timeout)
    if not reply["ok"]:
        return {"passed": False, "error": reply["error"], "detail": {}}
    result = reply["response"].get("result")
    if not isinstance(result, dict):
        return {"passed": False, "error": "回包缺少 result 对象", "detail": {}}
    content = result.get("content")
    if not isinstance(content, list) or not content:
        return {"passed": False, "error": "result.content 缺失或为空数组", "detail": {}}
    first = content[0]
    if not isinstance(first, dict) or not isinstance(first.get("text"), str):
        return {"passed": False, "error": "result.content[0].text 缺失或非字符串", "detail": {}}
    text = first["text"]
    try:
        parsed = json.loads(text)
    except Exception as exc:
        return {"passed": False, "error": "result.content[0].text 不能被 json.loads：%s" % exc, "detail": {}}
    if not isinstance(parsed, (list, dict)):
        return {
            "passed": False,
            "error": "解析结果既不是 profile 列表也不是字典，实际类型 %s" % type(parsed).__name__,
            "detail": {},
        }
    detail = {
        "list_profiles_type": type(parsed).__name__,
        "list_profiles_size": len(parsed),
    }
    return {"passed": True, "error": None, "detail": detail}


def run_checks(server_path, timeout=DEFAULT_TIMEOUT):
    passed = []
    failed = []
    details = {}
    path = Path(server_path)
    details["server"] = str(path)
    details["python"] = sys.executable
    details["expected_tools"] = sorted(EXPECTED_TOOLS)
    details["timeout_sec"] = float(timeout)

    if not path.is_file():
        message = "被测文件不存在：%s（待被测文件就绪后运行）" % path
        for name in STEP_NAMES:
            failed.append(name)
            details[name] = {"passed": False, "error": message}
        return {"ok": False, "passed": passed, "failed": failed, "details": details}

    sess = _RpcSession(path, timeout)
    steps = (
        ("initialize", check_initialize),
        ("tools_list", check_tools_list),
        ("tools_call_list_profiles", check_tools_call_list_profiles),
    )
    started = time.monotonic()
    harness_error = None
    try:
        sess.start()
        for name, func in steps:
            if sess.proc.poll() is not None:
                failed.append(name)
                details[name] = {
                    "passed": False,
                    "error": "子进程已退出（returncode=%s），跳过后续检查" % sess.proc.returncode,
                }
                continue
            try:
                result = func(sess, timeout)
            except Exception as exc:
                result = {"passed": False, "error": "检查函数异常：%r" % (exc,), "detail": {}}
            step_detail = dict(result["detail"])
            step_detail["passed"] = bool(result["passed"])
            step_detail["error"] = result["error"]
            details[name] = step_detail
            (passed if result["passed"] else failed).append(name)
    except Exception as exc:
        harness_error = repr(exc)
    finally:
        sess.close()
        details["elapsed_sec"] = round(time.monotonic() - started, 3)
        details["stderr_tail"] = sess.stderr_tail()

    # 没跑到的步骤一律计 FAIL，绝不因为“没报错”而算过
    for name in STEP_NAMES:
        if name not in passed and name not in failed:
            failed.append(name)
            details.setdefault(name, {"passed": False, "error": harness_error or "步骤未执行"})
    if harness_error:
        details["harness_error"] = harness_error

    return {"ok": not failed and harness_error is None, "passed": passed, "failed": failed, "details": details}


def main(argv=None):
    # 摘要固定按 UTF-8 输出：Windows 下 stdout 重定向到管道时默认是 cp936，
    # 中文 error 字段会变成 GBK 字节，外部按 UTF-8 读就崩。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = argparse.ArgumentParser(
        description="派卡内核 MCP 服务器协议层机械验收（initialize / tools/list / tools/call）"
    )
    parser.add_argument("--server", default=str(DEFAULT_SERVER), help="被测 MCP 服务器脚本路径")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="每一步等待回包的秒数")
    args = parser.parse_args(argv)
    try:
        summary = run_checks(args.server, args.timeout)
    except Exception as exc:
        summary = {
            "ok": False,
            "passed": [],
            "failed": list(STEP_NAMES),
            "details": {"harness_error": repr(exc)},
        }
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    sys.stdout.flush()
    if not summary["ok"]:
        for name in summary["failed"]:
            sys.stderr.write("FAIL %s: %s\n" % (name, summary["details"].get(name, {}).get("error")))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
