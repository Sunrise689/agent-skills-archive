#!/usr/bin/env python3
"""Local OpenAI-compatible gateway for agy -> MiniMax.

Reads MiniMax credentials from Pi's user models.json at runtime. Credentials,
request bodies, and response bodies are never logged.
Upstream requests are non-streaming, then converted to canonical OpenAI SSE
chunks so agy's stream parser sees ordered tool-call indexes and string args.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_PI_CONFIG = Path.home() / ".pi" / "agent" / "models.json"
# 上游协议：responses（默认，MiniMax 原生）/ chat（回退，保持旧行为）
UPSTREAM_API = os.environ.get("MINIMAX_SHIM_UPSTREAM", "responses").lower()
HOST = os.environ.get("MINIMAX_SHIM_HOST", "127.0.0.1")
PORT = int(os.environ.get("MINIMAX_SHIM_PORT", "8765"))
UPSTREAM_TIMEOUT = float(os.environ.get("MINIMAX_SHIM_TIMEOUT", "120"))
UPSTREAM_ATTEMPTS = int(os.environ.get("MINIMAX_SHIM_ATTEMPTS", "3"))
# 【2026-10-22 晚】urlopen(timeout=) 只是 socket 读超时，**不是总时长上限**：
#   流式下上游只要偶尔吐点字节（心跳/空事件）就永远不超时 → 卡挂死（实测 AGU6 第一个请求挂了 5 分多钟不回不报）。
# 所以这里自己管两道闸：首事件超时（连首个字节都没有）和总时长上限。
FIRST_EVENT_TIMEOUT = float(os.environ.get("MINIMAX_SHIM_FIRST_EVENT_TIMEOUT", "90"))
TOTAL_TIMEOUT = float(os.environ.get("MINIMAX_SHIM_TOTAL_TIMEOUT", "600"))


def _dump_request(body: dict) -> None:
    """请求体收到即落盘（取证）：<workdir>/.card_usage/last_request_pid<pid>.json（覆盖写）。"""
    try:
        d = Path.cwd() / ".card_usage"
        d.mkdir(parents=True, exist_ok=True)
        p = d / ("last_request_pid%d.json" % os.getpid())
        p.write_text(json.dumps({"ts": time.time(), "body": body},
                                ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass


def _dump_failed_request(url: str, body: dict, err: str) -> None:
    """失败请求体落盘（取证用）：不含密钥（key 在 header 里），只存 body 与错误类型。"""
    try:
        d = Path.cwd() / ".card_usage"
        d.mkdir(parents=True, exist_ok=True)
        p = d / ("failed_request_pid%d.json" % os.getpid())
        p.write_text(json.dumps({
            "url": url, "error": err, "ts": time.time(),
            "body": body,
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        print("[shim] failed_request_saved=%s" % p, file=sys.stderr, flush=True)
    except Exception:
        pass


def _parse_sse_block(block: bytes):
    """切出一个 SSE 块 → (event_type, data_obj)；不是合法 JSON 就返回 (None, None)。"""
    text = block.decode("utf-8", "replace").strip()
    if not text:
        return None, None
    event_type = None
    data_txt = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_txt = line[5:].strip()
    if not data_txt or data_txt == "[DONE]":
        return event_type, None
    try:
        return event_type, json.loads(data_txt)
    except Exception:
        return event_type, None


def _post_upstream_streaming(url: str, body: dict) -> bytes:
    """上游**流式** POST，聚合成一个完整 response JSON 返回。

    【2026-10-22 晚 · AG 通道的真病根】
    AG 的 shim 原来对上游发**非流式**请求（stream=False）：整个响应生成完才有第一个字节。
    上游在长生成期没有字节流动 → 连接被掐断（RemoteDisconnected，**无任何 HTTP 错误码**），
    5 次重试连续同样失败 → 可复现的结构性问题，不是网络抖动。
    CL/CR 走的是 `minimax_responses_bridge_upstream.py`，那里 `request_body["stream"] = True`，
    全程有字节流动 → 从不撞这个问题。今晚 AG 连挂 4 张卡（AGU2~AGU5）、CL/CP/ZC 全部交付，
    唯一差异就是这一条。
    这里改成和桥一样走上游流式：边收边解析 SSE，`response.completed` 里带完整 response，
    聚合后返回，后面的 responses_to_chat 流程完全不变。
    """
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + UPSTREAM_KEY,
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    req = Request(url, data=payload, headers=headers, method="POST")
    completed = None
    items = []
    text_parts = []
    t0 = time.time()
    got_any = False
    with urlopen(req, timeout=UPSTREAM_TIMEOUT) as response:
        buf = b""
        while True:
            chunk = response.read1(65536)
            if not chunk:
                break
            if not got_any:
                got_any = True
                print("[shim] upstream_first_byte_s=%.1f" % (time.time() - t0),
                      file=sys.stderr, flush=True)
            buf += chunk
            # 【2026-10-22 23:0x · AG 通道挂死的真正根因】SSE 分块循环必须**逐块推进**。
            # 原写法在循环外算一次 norm，循环内只更新 buf 不更新 norm →
            # `while b"\n\n" in norm` 永远为真，同一个块被无限重复解析 → 死循环：
            # 首字节到了（upstream_first_byte_s 有值）但永远读不到 response.completed，
            # 整张卡挂死到被 stop。AGU2~AGU7 连挂 6 张全是这一个 bug。
            # Responses 桥（minimax_responses_bridge_upstream.py）写法是对的：
            #     while b"\n\n" in buf.replace(...):  条件每轮重算
            #         norm = buf.replace(...)
            #         block, buf = norm.split(b"\n\n", 1)   ← buf 被推进
            # 这里照抄桥的正确写法。
            while b"\n\n" in buf.replace(b"\r\n", b"\n"):
                norm = buf.replace(b"\r\n", b"\n")
                block, buf = norm.split(b"\n\n", 1)
                etype, obj = _parse_sse_block(block)
                if obj is None:
                    continue
                t = obj.get("type") or etype
                if t == "response.completed":
                    completed = obj.get("response")
                elif t == "response.output_item.done":
                    it = obj.get("item") or {}
                    if it:
                        items.append(it)
                elif t == "response.output_text.delta":
                    d = obj.get("delta") or ""
                    if d:
                        text_parts.append(d)
            # 两道闸：首事件超时 / 总时长上限（socket timeout 管不到这两种）
            if not got_any and (time.time() - t0) > FIRST_EVENT_TIMEOUT:
                raise TimeoutError("upstream first event timeout after %.0fs" % (time.time() - t0))
            if (time.time() - t0) > TOTAL_TIMEOUT:
                raise TimeoutError("upstream total timeout after %.0fs" % (time.time() - t0))
    if completed:
        return json.dumps(completed, ensure_ascii=False).encode("utf-8")
    # 兜底：没有 response.completed 就用已收到的 item 拼一个最小 response
    out = list(items)
    if text_parts and not any(i.get("type") == "message" for i in out):
        out.insert(0, {"type": "message", "role": "assistant",
                       "content": [{"type": "output_text", "text": "".join(text_parts)}]})
    return json.dumps({"id": "resp_manual", "model": body.get("model"),
                       "output": out}, ensure_ascii=False).encode("utf-8")


def _post_upstream_nonstream(url: str, body: dict) -> bytes:
    """上游非流式 POST（保留作回退；开关 MINIMAX_SHIM_UPSTREAM_STREAM=0 走这里）。"""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + UPSTREAM_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    req = Request(url, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=UPSTREAM_TIMEOUT) as response:
        return response.read()


def _post_upstream(url: str, body: dict) -> bytes:
    """上游 POST，带瞬时故障重试。

    【2026-10-22 实测】AGU2 在第 5 轮工具调用后撞上 RemoteDisconnected（上游把连接断了），
    不重试就把 502 直接抛给 Antigravity SDK → 整张卡 exit 1（产物只写了一半）。
    这里对「断连 / 超时 / 5xx」做有限次退避重试；4xx 直接抛（重试无意义）。
    """
    streaming = os.environ.get("MINIMAX_SHIM_UPSTREAM_STREAM", "1").lower() not in ("0", "false", "no")
    last = None
    for attempt in range(UPSTREAM_ATTEMPTS):
        try:
            if streaming:
                return _post_upstream_streaming(url, body)
            return _post_upstream_nonstream(url, body)
        except HTTPError as exc:
            last = exc
            if exc.code < 500:
                _dump_failed_request(url, body, "HTTPError %s" % exc.code)
                raise
        except (URLError, OSError) as exc:
            # RemoteDisconnected / ConnectionReset / timeout 都落在这里
            last = exc
            _dump_failed_request(url, body, type(exc).__name__)
        if attempt + 1 < UPSTREAM_ATTEMPTS:
            print(
                "[shim] upstream_retry attempt=%d/%d last=%s" % (
                    attempt + 2, UPSTREAM_ATTEMPTS, type(last).__name__),
                file=sys.stderr, flush=True,
            )
            time.sleep(1.5 * (attempt + 1))
    raise last


# ---------- 通道自报用量落盘（2026-10-22） ----------
# 我们自己的桥是唯一收口点：上游每次调用的 usage 只有这里看得到。
# 落盘成 <卡工作区>/.card_usage/usage_pid<pid>_<通道>.jsonl，
# 文件名带 pid → 台账可按派卡注册表的 pid 精确对回卡（多卡共用工作区也不串）。
CARD_USAGE_FILE = os.environ.get("CARD_USAGE_FILE")


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


def record_usage(channel: str, model: str, usage: dict, stream: bool) -> None:
    if not CARD_USAGE_FILE:
        return
    try:
        details_in = (usage.get("input_tokens_details") or {}) if isinstance(usage, dict) else {}
        details_out = (usage.get("output_tokens_details") or {}) if isinstance(usage, dict) else {}
        row = {
            "ts": time.time(),
            "channel": channel,
            "model": model,
            "stream": stream,
            "self_pid": os.getpid(),
            "pid_chain": _pid_chain(),
            "input_tokens": int((usage or {}).get("input_tokens", 0) or 0),
            "output_tokens": int((usage or {}).get("output_tokens", 0) or 0),
            "total_tokens": int((usage or {}).get("total_tokens", 0) or 0),
            "cache_read_tokens": int(details_in.get("cached_tokens", 0) or 0),
            "reasoning_tokens": int(details_out.get("reasoning_tokens", 0) or 0),
        }
        if not row["total_tokens"]:
            row["total_tokens"] = row["input_tokens"] + row["output_tokens"]
        path = Path(CARD_USAGE_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass


def load_provider() -> tuple[str, str, str]:
    path = Path(os.environ.get("PI_MODELS_JSON", str(DEFAULT_PI_CONFIG)))
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    provider = data["providers"]["minimax"]
    base_url = provider.get("baseUrl") or provider.get("baseURL")
    api_key = provider.get("apiKey")
    configured_model = os.environ.get("MINIMAX_MODEL", "MiniMax-M3.1-Flash")
    if not base_url or not api_key:
        raise RuntimeError("Pi minimax provider must contain baseUrl and apiKey")
    return base_url.rstrip("/"), str(api_key), str(configured_model)


BASE_URL, UPSTREAM_KEY, CONFIGURED_MODEL = load_provider()


def _responses_helpers():
    """复用 Responses 桥的 chat<->responses 转换，避免两处各写一遍。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "minimax_responses_bridge_upstream",
        str(Path(__file__).with_name("minimax_responses_bridge_upstream.py")),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.chat_to_responses, module.responses_to_chat
print(
    f"[shim] listening target={HOST}:{PORT}; upstream={BASE_URL}; "
    f"model={CONFIGURED_MODEL}",
    file=sys.stderr,
    flush=True,
)


def as_arguments(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


def sse_chunk(chunk_id: str, created: int, model: str, delta: dict, finish: str | None = None) -> bytes:
    payload = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return ("data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n\n").encode("utf-8")


def to_openai_stream(result: dict, requested_model: str) -> bytes:
    choices = result.get("choices") or []
    if not choices:
        raise ValueError("upstream response has no choices")
    choice = choices[0]
    message = choice.get("message") or {}
    calls = message.get("tool_calls") or []
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    content = content or ""
    # MiniMax may return internal reasoning fields; only forward user-visible content.
    chunk_id = str(result.get("id") or ("chatcmpl-" + uuid.uuid4().hex))
    created = int(result.get("created") or time.time())
    model = str(result.get("model") or requested_model)
    frames = [sse_chunk(chunk_id, created, model, {"role": "assistant"})]
    if content:
        frames.append(sse_chunk(chunk_id, created, model, {"content": content}))
    for index, call in enumerate(calls):
        function = call.get("function") or {}
        call_id = str(call.get("id") or ("call_" + uuid.uuid4().hex[:20]))
        # Emit the function header and arguments as separate deltas. Some OpenAI
        # gateway clients fail to dispatch a complete tool call carried in one delta.
        frames.append(sse_chunk(chunk_id, created, model, {"tool_calls": [{
            "index": index, "id": call_id, "type": "function",
            "function": {"name": str(function.get("name") or ""), "arguments": ""},
        }]}))
        arguments = as_arguments(function.get("arguments", "{}"))
        frames.append(sse_chunk(chunk_id, created, model, {"tool_calls": [{
            "index": index, "function": {"arguments": arguments},
        }]}))
    finish = choice.get("finish_reason")
    if calls:
        finish = "tool_calls"
    elif finish not in ("stop", "length", "content_filter"):
        finish = "stop"
    frames.append(sse_chunk(chunk_id, created, model, {}, finish))
    usage = result.get("usage")
    if isinstance(usage, dict):
        payload = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [],
            "usage": usage,
        }
        frames.append(("data: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n\n").encode("utf-8"))
    frames.append(b"data: [DONE]\n\n")
    return b"".join(frames)


class Handler(BaseHTTPRequestHandler):
    server_version = "MiniMaxAgyShim/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        # Request bodies and headers can contain prompts or credentials: do not log them.
        return

    def send_json(self, status: int, body: dict) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/health":
            self.send_json(200, {"ok": True, "model": CONFIGURED_MODEL})
        else:
            self.send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        route = self.path.split("?", 1)[0]
        if route not in ("/v1/chat/completions", "/chat/completions"):
            self.send_json(404, {"error": "unsupported route"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            request_body = json.loads(self.rfile.read(length))
            # 【2026-10-22 晚】请求体**收到即落盘**（取证用）：
            #   AG 通道连续多张卡挂在同一个请求上，需要真实 body 才能离线复现与比对。
            #   body 里不含密钥（key 在 header）。
            _dump_request(request_body)
            tool_names = [
                item.get("function", {}).get("name", "")
                for item in request_body.get("tools", [])
                if isinstance(item, dict)
            ]
            print(
                f"[shim] request stream={bool(request_body.get('stream'))} "
                f"tool_choice={request_body.get('tool_choice')} tools={len(tool_names)} "
                f"names={','.join(str(name) for name in tool_names[:20])}",
                file=sys.stderr, flush=True,
            )
            stream_requested = bool(request_body.get("stream"))
            requested_model = str(request_body.get("model") or CONFIGURED_MODEL)
            request_body["model"] = CONFIGURED_MODEL
            # Request a single authoritative JSON result; canonical SSE is generated here.
            request_body["stream"] = False
            request_body.pop("stream_options", None)
            if UPSTREAM_API == "responses":
                # 对内走 MiniMax 原生 /responses；对外仍输出 chat 协议（AG SDK 只认 chat）。
                chat_to_responses, responses_to_chat = _responses_helpers()
                resp_body = chat_to_responses(request_body)
                resp_body["model"] = CONFIGURED_MODEL
                # 【2026-10-22 晚】上游必须流式：非流式时上游整段生成完才有第一个字节，
                # 长生成期连接被掐断（RemoteDisconnected，无 HTTP 错误码）→ 整张卡 exit 1。
                # CL/CR 走 Responses 桥（那里就是 stream=True）从不撞这个问题。
                _stream_up = os.environ.get("MINIMAX_SHIM_UPSTREAM_STREAM", "1").lower() \
                    not in ("0", "false", "no")
                resp_body["stream"] = bool(_stream_up)
                # 【2026-10-22 晚】夹紧 max_completion_tokens：
                #   AG SDK 默认带 65535 → 上游按 65535 token 的输出空间生成 → 每轮要好几分钟
                #   （实测 AGU7 流式下首字节 5.4 秒就有了，但一轮迟迟不结束）。
                #   探针/派卡任务远用不到这么多，夹到 16384 能把每轮耗时压下来。
                _cap = int(os.environ.get("MINIMAX_SHIM_MAX_COMPLETION_TOKENS", "16384"))
                _orig_cap = resp_body.get("max_output_tokens")
                if _cap > 0 and (not isinstance(_orig_cap, int) or _orig_cap > _cap):
                    resp_body["max_output_tokens"] = _cap
                print(
                    f"[shim] upstream=responses stream={bool(_stream_up)} "
                    f"max_output_tokens={resp_body.get('max_output_tokens')} (原 {_orig_cap})",
                    file=sys.stderr, flush=True,
                )
                upstream_url = BASE_URL + "/responses"
                raw_bytes = _post_upstream(upstream_url, resp_body)
                raw_result = json.loads(raw_bytes)
                result = responses_to_chat(raw_result)
                print(
                    f"[shim] upstream=responses stream={bool(_stream_up)} out_types="
                    f"{[i.get('type') for i in (raw_result.get('output') or [])]}",
                    file=sys.stderr, flush=True,
                )
            else:
                upstream_url = BASE_URL + "/chat/completions"
                raw_bytes = _post_upstream(upstream_url, request_body)
                result = json.loads(raw_bytes)
            choice = (result.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            # 通道自报用量落盘（2026-10-22）：AG 的会话存储是 protobuf、没有 token 键，
            # 桥/上游这一层是唯一能拿到 usage 的地方 → 落到卡工作区，台账按 pid 精确对回卡。
            _u = result.get("usage")
            if isinstance(_u, dict):
                record_usage(os.environ.get("CARD_USAGE_CHANNEL", "agy"),
                             CONFIGURED_MODEL,
                             {"input_tokens": _u.get("prompt_tokens", _u.get("input_tokens", 0)) or 0,
                              "output_tokens": _u.get("completion_tokens", _u.get("output_tokens", 0)) or 0,
                              "total_tokens": _u.get("total_tokens", 0) or 0,
                              "input_tokens_details": _u.get("prompt_tokens_details") or {},
                              "output_tokens_details": _u.get("completion_tokens_details") or {}},
                             stream_requested)
            print(
                f"[shim] response finish={choice.get('finish_reason')} "
                f"tool_calls={len(message.get('tool_calls') or [])} "
                f"content_chars={len(str(message.get('content') or ''))}",
                file=sys.stderr, flush=True,
            )
            if stream_requested:
                payload = to_openai_stream(result, requested_model)
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            # Non-streaming clients get a standard Chat Completions response without reasoning fields.
            for item in result.get("choices", []):
                message = item.get("message") or {}
                message.pop("reasoning_content", None)
                message.pop("reasoning", None)
            self.send_json(200, result)
        except HTTPError as exc:
            # Do not log the upstream response body; return only status for safe diagnosis.
            print(f"[shim] upstream_http_status={exc.code}", file=sys.stderr, flush=True)
            self.send_json(502, {"error": {"message": f"MiniMax returned HTTP {exc.code}", "type": "upstream_error"}})
        except URLError as exc:
            reason = getattr(exc, "reason", "connection error")
            print(f"[shim] upstream_connection_error={type(reason).__name__}", file=sys.stderr, flush=True)
            self.send_json(502, {"error": {"message": "MiniMax connection failed", "type": "upstream_error"}})
        except Exception as exc:
            print(f"[shim] request_error={type(exc).__name__}", file=sys.stderr, flush=True)
            self.send_json(502, {"error": {"message": "Gateway request failed", "type": "shim_error"}})


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
