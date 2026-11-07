#!/usr/bin/env python3
"""Chat Completions -> MiniMax Responses 桥（供 Cline / OpenCursor 等只懂 chat 协议的 CLI 使用）。

为什么需要：
  MiniMax 官方端点原生支持 /v1/responses（function tools、streaming、reasoning.effort、
  service_tier 全部实测可用），但很多第三方 CLI 只发 /chat/completions。
  本桥对外暴露 OpenAI Chat Completions 协议，对内改打 MiniMax 原生 Responses API。

凭据：运行时从 Pi 的 ~/.pi/agent/models.json 读取，绝不写日志、绝不在响应里回显。
"""
from __future__ import annotations

import json
import os
import time
import uuid
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = os.environ.get("CARD_LAUNCHER_MODEL", "MiniMax-M3.1-Flash")
HOST = os.environ.get("MINIMAX_RESP_HOST", "127.0.0.1")
PORT = int(os.environ.get("MINIMAX_RESP_PORT", "8791"))
TIMEOUT = float(os.environ.get("MINIMAX_RESP_TIMEOUT", "300"))
DEFAULT_PI_CONFIG = Path.home() / ".pi" / "agent" / "models.json"


# ---------- 通道自报用量落盘（2026-10-22） ----------
# 我们自己的桥是唯一收口点：上游每次调用的 usage 只有这里看得到。
# 落盘成 <卡工作区>/.card_usage/usage_pid<pid>_<通道>.jsonl，
# 文件名带 pid → 台账可按派卡注册表的 pid 精确对回卡（多卡共用工作区也不串）。
CARD_USAGE_FILE = os.environ.get("CARD_USAGE_FILE")


def _pid_chain(depth: int = 6) -> list:
    """向上收集父进程 pid 链。

    【2026-10-22 实测】注册表里记的是「卡 launcher 进程」的 pid，而桥是它的孙子进程
    （中间隔了 launcher 自己的 shell 层）→ 光看 os.getpid() 对不回卡。
    解决办法：把整条祖先链写进用量行，台账侧只要链上任一 pid 命中注册表即可精确对回卡。
    """
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


def load_provider() -> tuple[str, str]:
    path = Path(os.environ.get("PI_MODELS_JSON", str(DEFAULT_PI_CONFIG)))
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    provider = data["providers"]["minimax"]
    base_url = (provider.get("baseUrl") or provider.get("baseURL")).rstrip("/")
    api_key = provider.get("apiKey")
    if not base_url or not api_key:
        raise RuntimeError("Pi minimax provider must contain baseUrl and apiKey")
    return base_url, str(api_key)


BASE_URL, UPSTREAM_KEY = load_provider()

# 上游瞬时断连重试（2026-10-22 实测踩坑）：
#   AG 通道 AGU1 在第 13 轮工具调用后，shim 收到 RemoteDisconnected → 502 → SDK 抛
#   AntigravityExecutionError，整张卡 exit 1（但产物已写完）。
#   CR 通道 CRU2 也撞上 ConnectionAbortedError。
#   这类是连接层的瞬时故障，不是请求内容问题，重试即可恢复。
RETRY_ATTEMPTS = int(os.environ.get("MINIMAX_RESP_RETRIES", "3"))
RETRY_BACKOFF = float(os.environ.get("MINIMAX_RESP_RETRY_BACKOFF", "1.5"))
RETRYABLE = (
    ConnectionError,          # 含 ConnectionResetError / ConnectionAbortedError
    TimeoutError,
    http.client.RemoteDisconnected,
    http.client.IncompleteRead,
)


def _call_upstream(request_body: dict) -> dict:
    """打 MiniMax 原生 /responses；对瞬时断连做有限重试。"""
    payload = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        upstream = Request(
            BASE_URL + "/responses",
            data=payload,
            headers={"Authorization": "Bearer " + UPSTREAM_KEY,
                     "Content-Type": "application/json",
                     "Accept": "application/json"},
            method="POST",
        )
        try:
            with urlopen(upstream, timeout=TIMEOUT) as response:
                return json.loads(response.read())
        except HTTPError:
            raise
        except RETRYABLE as exc:
            last_error = exc
            print("[resp-bridge] retryable_upstream_error=%s attempt=%d/%d"
                  % (type(exc).__name__, attempt, RETRY_ATTEMPTS), flush=True)
            if attempt >= RETRY_ATTEMPTS:
                break
            time.sleep(RETRY_BACKOFF * attempt)
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            last_error = reason
            print("[resp-bridge] upstream_connection_error=%s attempt=%d/%d"
                  % (type(reason).__name__, attempt, RETRY_ATTEMPTS), flush=True)
            if attempt >= RETRY_ATTEMPTS:
                break
            time.sleep(RETRY_BACKOFF * attempt)
    raise last_error if last_error else RuntimeError("upstream call failed")


def chat_to_responses(body: dict) -> dict:
    """把 Chat Completions 请求体转成 Responses 请求体。"""
    messages = []
    if body.get("instructions"):
        messages.append({"role": "system", "content": body["instructions"]})
    for msg in body.get("messages") or []:
        role = msg.get("role", "user")
        content = msg.get("content")
        if isinstance(content, list):
            parts = []
            for part in content:
                if not isinstance(part, dict):
                    parts.append({"type": "input_text", "text": str(part)})
                    continue
                ptype = part.get("type")
                if ptype in ("text", "input_text", "output_text"):
                    parts.append({"type": "input_text", "text": part.get("text", "")})
                elif ptype == "image_url":
                    url = (part.get("image_url") or {}).get("url")
                    if url:
                        parts.append({"type": "input_image", "image_url": url})
            content = parts
        item = {"role": role, "content": content}
        calls = msg.get("tool_calls") or []
        if calls:
            item["content"] = content if content else None
            item["tool_calls"] = [
                {"id": c.get("id"), "type": "function",
                 "function": {"name": (c.get("function") or {}).get("name", ""),
                              "arguments": (c.get("function") or {}).get("arguments", "{}")}}
                for c in calls
            ]
        if role == "tool":
            item = {"role": "tool", "tool_call_id": msg.get("tool_call_id", ""),
                    "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)}
        messages.append(item)

    # Responses 的历史输入用 input 数组；tool 结果用 function_call_output
    inputs = []
    for msg in messages:
        role = msg.get("role")
        if role in ("system", "developer"):
            continue
        if role == "tool":
            inputs.append({"type": "function_call_output",
                           "call_id": msg.get("tool_call_id", ""),
                           "output": msg.get("content", "")})
            continue
        if msg.get("tool_calls"):
            inputs.append({"role": "assistant", "content": msg.get("content")})
            for c in msg["tool_calls"]:
                inputs.append({"type": "function_call", "call_id": c["id"],
                               "name": c["function"]["name"],
                               "arguments": c["function"].get("arguments", "{}")})
            continue
        inputs.append({"role": role, "content": msg.get("content", "")})

    request = {"model": MODEL, "input": inputs}
    system_text = "\n\n".join(str(m.get("content")) for m in messages if m.get("role") in ("system", "developer"))
    if system_text:
        request["instructions"] = system_text
    tools = []
    for tool in body.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function":
            fn = tool.get("function") or {}
            tools.append({"type": "function", "name": fn.get("name", ""),
                          "description": fn.get("description", ""),
                          "parameters": fn.get("parameters", {"type": "object", "properties": {}})})
    if tools:
        request["tools"] = tools
        request["tool_choice"] = body.get("tool_choice", "auto") or "auto"
    max_out = body.get("max_tokens") or body.get("max_completion_tokens")
    if max_out:
        request["max_output_tokens"] = min(int(max_out), 32768)
    if body.get("reasoning_effort"):
        request["reasoning"] = {"effort": body["reasoning_effort"]}
    if body.get("stream"):
        request["stream"] = True
    return request


def responses_to_chat(result: dict) -> dict:
    """把 Responses 结果转回 Chat Completions 响应。"""
    text_parts = []
    tool_calls = []
    for item in result.get("output") or []:
        itype = item.get("type")
        if itype == "message":
            for part in item.get("content") or []:
                if part.get("type") in ("output_text", "text"):
                    text_parts.append(str(part.get("text", "")))
        elif itype == "function_call":
            tool_calls.append({
                "id": item.get("call_id") or ("call_" + uuid.uuid4().hex[:20]),
                "type": "function",
                "function": {"name": item.get("name", ""),
                             "arguments": item.get("arguments") or "{}"},
            })
    usage = result.get("usage") or {}
    input_tokens = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    prompt_details = usage.get("input_tokens_details") or {}
    completion_details = usage.get("output_tokens_details") or {}
    message = {"role": "assistant", "content": "".join(text_parts) or None}
    if tool_calls:
        message["tool_calls"] = tool_calls
    finish = "tool_calls" if tool_calls else ("length" if result.get("status") == "incomplete" else "stop")
    return {
        "id": "chatcmpl-" + uuid.uuid4().hex,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": result.get("model") or MODEL,
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": input_tokens,
            "completion_tokens": output_tokens,
            "total_tokens": usage.get("total_tokens", input_tokens + output_tokens),
            "prompt_tokens_details": {"cached_tokens": prompt_details.get("cached_tokens", 0) or 0},
            "completion_tokens_details": {"reasoning_tokens": completion_details.get("reasoning_tokens", 0) or 0},
        },
    }


def chat_stream(result: dict) -> bytes:
    """把 Responses 结果转成 canonical OpenAI chat SSE。"""
    chat = responses_to_chat(result)
    choice = chat["choices"][0]
    message = choice["message"]
    cid, created = chat["id"], chat["created"]

    def chunk(delta: dict, finish=None) -> bytes:
        payload = {"id": cid, "object": "chat.completion.chunk", "created": created,
                   "model": chat["model"], "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
        return ("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8")

    frames = [chunk({"role": "assistant", "content": ""})]
    if message.get("content"):
        frames.append(chunk({"content": message["content"]}))
    for index, call in enumerate(message.get("tool_calls") or []):
        frames.append(chunk({"tool_calls": [{"index": index, "id": call["id"], "type": "function",
                                             "function": {"name": call["function"]["name"], "arguments": ""}}]}))
        frames.append(chunk({"tool_calls": [{"index": index,
                                             "function": {"arguments": call["function"]["arguments"]}}]}))
    frames.append(chunk({}, choice["finish_reason"]))
    usage_payload = {"id": cid, "object": "chat.completion.chunk", "created": created,
                     "model": chat["model"], "choices": [], "usage": chat["usage"]}
    frames.append(("data: " + json.dumps(usage_payload, ensure_ascii=False) + "\n\n").encode("utf-8"))
    frames.append(b"data: [DONE]\n\n")
    return b"".join(frames)


def chat_stream_events(result: dict) -> bytes:
    """把 Responses 结果转成 canonical OpenAI chat SSE（非流式上游的结果，供兼容路径使用）。"""
    return chat_stream(result)


def _sse_blocks(raw: bytes):
    """把 Responses 的 SSE 原始字节切成 (event_type, data_obj) 序列。"""
    for block in raw.replace(b"\r\n", b"\n").split(b"\n\n"):
        text = block.decode("utf-8", "replace").strip()
        if not text:
            continue
        event_type = None
        data_txt = None
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_txt = line[5:].strip()
        if not data_txt or data_txt == "[DONE]":
            continue
        try:
            yield event_type, json.loads(data_txt)
        except Exception:
            continue


def _call_upstream_stream(request_body: dict):
    """打 MiniMax 原生 /responses 的流式接口，产出 (event_type, data_obj) 序列。

    必须真流式：客户端（如 OpenCursor）有 120 秒首事件超时，
    若等上游整段跑完再一次性吐 SSE，客户端会先超时判失败。
    """
    payload = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    upstream = Request(
        BASE_URL + "/responses",
        data=payload,
        headers={"Authorization": "Bearer " + UPSTREAM_KEY,
                 "Content-Type": "application/json",
                 "Accept": "text/event-stream"},
        method="POST",
    )
    with urlopen(upstream, timeout=TIMEOUT) as response:
        buf = b""
        while True:
            chunk = response.read1(65536)
            if not chunk:
                break
            buf += chunk
            while b"\n\n" in buf.replace(b"\r\n", b"\n"):
                norm = buf.replace(b"\r\n", b"\n")
                block, buf = norm.split(b"\n\n", 1)
                text = block.decode("utf-8", "replace").strip()
                if not text:
                    continue
                event_type = None
                data_txt = None
                for line in text.splitlines():
                    line = line.strip()
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_txt = line[5:].strip()
                if not data_txt or data_txt == "[DONE]":
                    continue
                try:
                    yield event_type, json.loads(data_txt)
                except Exception:
                    continue


class Handler(BaseHTTPRequestHandler):
    server_version = "MiniMaxResponsesBridge/1.0"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def send_json(self, status: int, payload: dict) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            # 客户端提前断开（如 CLI 自行关闭流）：不是桥的故障，不记错误。
            pass

    def do_GET(self) -> None:
        route = self.path.split("?", 1)[0]
        if route == "/health":
            self.send_json(200, {"ok": True, "model": MODEL, "upstream": "minimax-responses"})
        elif route in ("/v1/models", "/models"):
            # 部分 CLI 会先列模型再发请求；不实现会让它们直接判连接失败。
            self.send_json(200, {"object": "list", "data": [
                {"id": MODEL, "object": "model", "created": int(time.time()), "owned_by": "minimax"}
            ]})
        else:
            self.send_json(404, {"error": {"message": "not found"}})

    def do_POST(self) -> None:
        route = self.path.split("?", 1)[0]
        if route not in ("/v1/chat/completions", "/chat/completions"):
            self.send_json(404, {"error": {"message": "unsupported route"}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            want_stream = bool(body.get("stream"))
            request_body = chat_to_responses(body)
            if want_stream:
                self._serve_stream(request_body)
                return
            request_body["stream"] = False
            request_body.pop("stream", None)
            result = _call_upstream(request_body)
            print("[resp-bridge] tools=%d out=%s" % (
                len(request_body.get("tools") or []),
                [i.get("type") for i in (result.get("output") or [])]), flush=True)
            _u = (result.get("usage") or {})
            record_usage(os.environ.get("CARD_USAGE_CHANNEL", "resp-bridge"),
                         result.get("model") or MODEL, _u, False)
            self.send_json(200, responses_to_chat(result))
        except HTTPError as exc:
            print("[resp-bridge] upstream_http_status=%s" % exc.code, flush=True)
            self.send_json(exc.code, {"error": {"message": "upstream HTTP %s" % exc.code,
                                                "type": "upstream_error"}})
        except URLError as exc:
            reason = getattr(exc, "reason", exc)
            print("[resp-bridge] upstream_connection_error=%s" % type(reason).__name__, flush=True)
            self.send_json(502, {"error": {"message": "upstream connection failed", "type": "upstream_error"}})
        except Exception as exc:
            print("[resp-bridge] request_error=%s" % type(exc).__name__, flush=True)
            self.send_json(502, {"error": {"message": "Responses bridge failed: " + type(exc).__name__,
                                           "type": "bridge_error"}})

    def _serve_stream(self, request_body: dict) -> None:
        """真流式：上游 /responses 逐事件收，逐条转成 chat SSE 实时下发。

        为什么必须真流式：客户端（OpenCursor）有 120 秒首事件超时。
        若等上游整段跑完再一次性吐 SSE，客户端会先超时判 failed。
        """
        request_body["stream"] = True
        cid = "chatcmpl-" + uuid.uuid4().hex
        created = int(time.time())

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def emit(delta: dict, finish=None) -> None:
            payload = {"id": cid, "object": "chat.completion.chunk", "created": created,
                       "model": MODEL, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            self.wfile.write(("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.flush()

        usage_payload = None
        tool_index = 0
        pending_call = {}
        text_started = False
        try:
            emit({"role": "assistant", "content": ""})
            for event_type, obj in _call_upstream_stream(request_body):
                etype = obj.get("type") or event_type
                if etype == "response.output_text.delta":
                    delta = obj.get("delta") or ""
                    if delta:
                        emit({"content": delta})
                        text_started = True
                elif etype == "response.output_item.added":
                    item = obj.get("item") or {}
                    if item.get("type") == "function_call":
                        call_id = item.get("call_id") or ("call_" + uuid.uuid4().hex[:20])
                        pending_call = {"id": call_id, "name": item.get("name", "")}
                        emit({"tool_calls": [{"index": tool_index, "id": call_id, "type": "function",
                                              "function": {"name": pending_call["name"], "arguments": ""}}]})
                elif etype == "response.function_call_arguments.delta":
                    delta = obj.get("delta") or ""
                    if delta:
                        pending_call["_sent_any"] = True
                        emit({"tool_calls": [{"index": tool_index,
                                              "function": {"arguments": delta}}]})
                elif etype == "response.output_item.done":
                    item = obj.get("item") or {}
                    if item.get("type") == "function_call" and pending_call:
                        # 收尾补齐：有些上游只在 done 里给全量 arguments。
                        # 但如果 delta 事件已经流过内容，这里再补一遍会让客户端
                        # 收到两遍参数（实测出现 '{"text":"hello"}{"text":"hello"}'），
                        # 所以只在 delta 一个字都没收到时才补。
                        full = item.get("arguments")
                        if full and not pending_call.get("_sent_any"):
                            emit({"tool_calls": [{"index": tool_index,
                                                  "function": {"arguments": full}}]})
                        tool_index += 1
                        pending_call = {}
                elif etype == "response.completed":
                    resp = obj.get("response") or {}
                    usage_payload = resp.get("usage")
                    status = resp.get("status")
                    finish = "tool_calls" if tool_index > 0 else ("length" if status == "incomplete" else "stop")
                    emit({}, finish)
                elif etype == "response.failed" or etype == "response.error":
                    print("[resp-bridge] upstream_stream_error=%s" % etype, flush=True)
                    emit({}, "stop")
            if usage_payload:
                record_usage(os.environ.get("CARD_USAGE_CHANNEL", "resp-bridge"),
                             MODEL, usage_payload, True)
                payload = {"id": cid, "object": "chat.completion.chunk", "created": created,
                           "model": MODEL, "choices": [], "usage": {
                               "prompt_tokens": usage_payload.get("input_tokens", 0) or 0,
                               "completion_tokens": usage_payload.get("output_tokens", 0) or 0,
                               "total_tokens": usage_payload.get("total_tokens", 0) or 0,
                               "prompt_tokens_details": {"cached_tokens": (usage_payload.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0},
                               "completion_tokens_details": {"reasoning_tokens": (usage_payload.get("output_tokens_details") or {}).get("reasoning_tokens", 0) or 0},
                           }}
                self.wfile.write(("data: " + json.dumps(payload, ensure_ascii=False) + "\n\n").encode("utf-8"))
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            print("[resp-bridge] stream done tools=%d text=%s" % (tool_index, text_started), flush=True)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            print("[resp-bridge] client_disconnected_during_stream", flush=True)


if __name__ == "__main__":
    print("[resp-bridge] listening %s:%d upstream=%s model=%s" % (HOST, PORT, BASE_URL + "/responses", MODEL), flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
