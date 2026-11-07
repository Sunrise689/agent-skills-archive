"""Claude Messages -> OpenRouter Chat Completions loopback bridge.

This candidate is isolated to CC-U-OR-free. It never accepts a model override,
sets OpenRouter provider fallback off, and logs metadata only (no prompts,
schemas, tool results, headers, or credentials).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROFILE_MODEL = "openrouter/thinkingmachines/inkling-small:free"
API_MODEL = "thinkingmachines/inkling-small:free"
CLIENT_MODEL = "claude-sonnet-4-6"
API_URL = "https://openrouter.ai/api/v1/chat/completions"
EFFORT = "max"
OPENROUTER_API_KEY = ""


def _log(event: str, **fields: object) -> None:
    record = {"ts": round(time.time(), 3), "event": event, "model": PROFILE_MODEL,
              "effort": EFFORT, **fields}
    print(json.dumps(record, separators=(",", ":")), file=__import__("sys").stderr, flush=True)


def _text_content(value: object) -> object:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        pieces = []
        for item in value:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                pieces.append(item["text"])
            elif item.get("type") == "image":
                source = item.get("source") or {}
                if source.get("type") == "base64" and source.get("media_type") and source.get("data"):
                    pieces.append({"type": "image_url", "image_url": {
                        "url": f"data:{source['media_type']};base64,{source['data']}"}})
                elif source.get("type") == "url" and source.get("url"):
                    pieces.append({"type": "image_url", "image_url": {"url": source["url"]}})
        return pieces if any(isinstance(p, dict) for p in pieces) else "\n".join(pieces)
    return ""


def _tool_schema(tool: dict) -> dict:
    name = tool.get("name")
    schema = tool.get("input_schema")
    if not isinstance(name, str) or not name or not isinstance(schema, dict):
        raise ValueError("invalid Anthropic tool schema")
    function = {"name": name, "parameters": schema}
    if isinstance(tool.get("description"), str):
        function["description"] = tool["description"]
    return {"type": "function", "function": function}


def anthropic_to_openai(body: dict) -> dict:
    """Convert messages, tool schemas, and prior tool results without dropping turns."""
    if not isinstance(body, dict):
        raise ValueError("request body must be an object")
    incoming = body.get("model")
    if incoming not in (None, CLIENT_MODEL, PROFILE_MODEL, API_MODEL):
        raise ValueError("model override is disabled for this profile")
    max_tokens = body.get("max_tokens")
    if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or max_tokens < 1:
        raise ValueError("max_tokens must be a positive integer")

    messages: list[dict] = []
    system = body.get("system")
    if system:
        sys_text = _text_content(system)
        if sys_text:
            messages.append({"role": "system", "content": sys_text})

    for item in body.get("messages", []):
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            raise ValueError("invalid Anthropic message")
        role = item["role"]
        content = item.get("content", "")
        blocks = content if isinstance(content, list) else [{"type": "text", "text": content}]
        if role == "user":
            visible: list[object] = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_result":
                    tool_id = block.get("tool_use_id")
                    if not isinstance(tool_id, str) or not tool_id:
                        raise ValueError("tool_result is missing tool_use_id")
                    if visible:
                        messages.append({"role": "user", "content": visible if any(isinstance(v, dict) for v in visible) else "\n".join(map(str, visible))})
                        visible = []
                    result = _text_content(block.get("content", ""))
                    if block.get("is_error"):
                        result = "Tool error: " + (result if isinstance(result, str) else json.dumps(result, ensure_ascii=False))
                    messages.append({"role": "tool", "tool_call_id": tool_id, "content": result})
                elif block.get("type") in ("text", "image"):
                    rendered = _text_content([block])
                    if rendered:
                        visible.extend(rendered if isinstance(rendered, list) else [rendered])
                else:
                    raise ValueError("unsupported user content block")
            if visible:
                messages.append({"role": "user", "content": visible if any(isinstance(v, dict) for v in visible) else "\n".join(map(str, visible))})
        else:
            text_parts = []
            calls = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "text" and isinstance(block.get("text"), str):
                    text_parts.append(block["text"])
                elif kind == "tool_use":
                    tool_id, name = block.get("id"), block.get("name")
                    if not isinstance(tool_id, str) or not isinstance(name, str):
                        raise ValueError("invalid tool_use block")
                    calls.append({"id": tool_id, "type": "function", "function": {
                        "name": name, "arguments": json.dumps(block.get("input", {}), ensure_ascii=False, separators=(",", ":"))}})
                else:
                    raise ValueError("unsupported assistant content block")
            if text_parts or calls:
                message = {"role": "assistant", "content": "\n".join(text_parts) if text_parts else None}
                if calls:
                    message["tool_calls"] = calls
                messages.append(message)

    request = {"model": API_MODEL, "messages": messages, "max_tokens": max_tokens,
               "reasoning": {"effort": EFFORT},
               "provider": {"allow_fallbacks": False}}
    for source, target in (("temperature", "temperature"), ("top_p", "top_p"),
                           ("stop_sequences", "stop")):
        if source in body:
            request[target] = body[source]
    tools = body.get("tools") or []
    if tools:
        if not isinstance(tools, list):
            raise ValueError("tools must be an array")
        request["tools"] = [_tool_schema(tool) for tool in tools]
    choice = body.get("tool_choice")
    if isinstance(choice, dict):
        kind = choice.get("type")
        if kind in ("auto", "none", "any"):
            request["tool_choice"] = {"auto": "auto", "none": "none", "any": "required"}[kind]
        elif kind == "tool" and isinstance(choice.get("name"), str):
            request["tool_choice"] = {"type": "function", "function": {"name": choice["name"]}}
    if body.get("stream") is True:
        request["stream"] = True
        request["stream_options"] = {"include_usage": True}
    return request


def openai_to_anthropic(data: dict, request_id: str | None = None) -> dict:
    choices = data.get("choices") or []
    choice = choices[0] if choices else {}
    message = choice.get("message") or {}
    content = []
    text = message.get("content")
    if isinstance(text, str) and text:
        content.append({"type": "text", "text": text})
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        raw = function.get("arguments", "{}")
        try:
            args = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            raise ValueError("OpenRouter returned invalid tool-call JSON")
        content.append({"type": "tool_use", "id": call.get("id", "toolu_unknown"),
                        "name": function.get("name", "unknown"), "input": args})
    finish = choice.get("finish_reason")
    stop_reason = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}.get(finish, "end_turn")
    usage = data.get("usage") or {}
    return {"id": request_id or data.get("id") or "msg_" + uuid.uuid4().hex,
            "type": "message", "role": "assistant", "model": CLIENT_MODEL,
            "content": content, "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": int(usage.get("prompt_tokens", 0) or 0),
                      "output_tokens": int(usage.get("completion_tokens", 0) or 0)}}


def _sse(event: str, payload: dict) -> bytes:
    return ("event: " + event + "\ndata: " + json.dumps(payload, separators=(",", ":")) + "\n\n").encode()


def stream_openai_to_anthropic(lines, usage_out: dict | None = None):
    """Translate OpenAI SSE deltas to Anthropic Messages SSE events."""
    msg_id = "msg_" + uuid.uuid4().hex
    yield _sse("message_start", {"type": "message_start", "message": {
        "id": msg_id, "type": "message", "role": "assistant", "model": CLIENT_MODEL,
        "content": [], "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 0, "output_tokens": 0}}})
    next_block = 0
    text_index = None
    tools: dict[int, dict] = {}
    finish = "stop"
    usage = {}
    for raw in lines:
        if not raw.startswith(b"data:"):
            continue
        payload = raw[5:].strip()
        if payload == b"[DONE]":
            break
        try:
            chunk = json.loads(payload)
        except (UnicodeError, ValueError):
            continue
        if chunk.get("usage"):
            usage = chunk["usage"]
        choices = chunk.get("choices") or []
        if not choices:
            continue
        delta = choices[0].get("delta") or {}
        reason = choices[0].get("finish_reason")
        if reason:
            finish = reason
        text = delta.get("content")
        if isinstance(text, str) and text:
            if text_index is None:
                text_index = next_block
                next_block += 1
                yield _sse("content_block_start", {"type": "content_block_start", "index": text_index,
                                                       "content_block": {"type": "text", "text": ""}})
            yield _sse("content_block_delta", {"type": "content_block_delta", "index": text_index,
                                                  "delta": {"type": "text_delta", "text": text}})
        for tc in delta.get("tool_calls") or []:
            ix = int(tc.get("index", 0))
            state = tools.setdefault(ix, {"block": None, "id": "", "name": ""})
            fn = tc.get("function") or {}
            state["id"] += tc.get("id", "")
            state["name"] += fn.get("name", "")
            if state["block"] is None and state["name"]:
                state["block"] = next_block
                next_block += 1
                yield _sse("content_block_start", {"type": "content_block_start", "index": state["block"],
                    "content_block": {"type": "tool_use", "id": state["id"] or "toolu_pending",
                                      "name": state["name"], "input": {}}})
            args = fn.get("arguments")
            if isinstance(args, str) and args:
                if state["block"] is None:
                    state["block"] = next_block
                    next_block += 1
                    yield _sse("content_block_start", {"type": "content_block_start", "index": state["block"],
                        "content_block": {"type": "tool_use", "id": state["id"] or "toolu_pending",
                                          "name": state["name"] or "unknown", "input": {}}})
                yield _sse("content_block_delta", {"type": "content_block_delta", "index": state["block"],
                                                      "delta": {"type": "input_json_delta", "partial_json": args}})
    if text_index is not None:
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": text_index})
    for state in tools.values():
        if state["block"] is not None:
            yield _sse("content_block_stop", {"type": "content_block_stop", "index": state["block"]})
    stop = {"length": "max_tokens", "tool_calls": "tool_use"}.get(finish, "end_turn")
    if usage_out is not None:
        usage_out.update({"prompt_tokens": int((usage or {}).get("prompt_tokens", 0) or 0),
                          "completion_tokens": int((usage or {}).get("completion_tokens", 0) or 0)})
    yield _sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
        "usage": {"output_tokens": int((usage or {}).get("completion_tokens", 0) or 0)}})
    yield _sse("message_stop", {"type": "message_stop"})


class Handler(BaseHTTPRequestHandler):
    server_version = "CardLauncherOpenRouterBridge/1.0"

    def log_message(self, _format, *_args):
        return

    def _send(self, status: int, payload: object, content_type: str = "application/json"):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/health":
            self._send(200, {"ok": True, "model": PROFILE_MODEL, "effort": EFFORT})
        else:
            self._send(404, {"error": "not_found"})

    def do_POST(self):
        route = self.path.split("?", 1)[0]
        if route not in ("/v1/messages", "/messages", "/v1/messages/count_tokens", "/messages/count_tokens"):
            self._send(404, {"error": "not_found"})
            return
        started = time.monotonic()
        try:
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            incoming = json.loads(raw)
            if route.endswith("count_tokens"):
                estimate = max(1, len(json.dumps(incoming, ensure_ascii=False)) // 4)
                _log("count_tokens", input_tokens=estimate, duration_ms=round((time.monotonic()-started)*1000))
                self._send(200, {"input_tokens": estimate})
                return
            outgoing = anthropic_to_openai(incoming)
            if not OPENROUTER_API_KEY:
                raise RuntimeError("OpenRouter credential is unavailable")
            request = Request(API_URL, data=json.dumps(outgoing, separators=(",", ":")).encode(),
                headers={"Authorization": "Bearer " + OPENROUTER_API_KEY, "Content-Type": "application/json",
                         "HTTP-Referer": "https://github.com/anthropics/claude-code",
                         "X-OpenRouter-Title": "Claude Code", "X-Title": "Claude Code",
                         "User-Agent": "Claude-Code-OpenRouter-Bridge/1.0"}, method="POST")
            with urlopen(request, timeout=240) as response:
                if incoming.get("stream") is True:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Cache-Control", "no-cache")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    usage = {"prompt_tokens": 0, "completion_tokens": 0}
                    for frame in stream_openai_to_anthropic(iter(response.readline, b""), usage):
                        self.wfile.write(frame)
                        self.wfile.flush()
                    _log("response", status=200, input_tokens=usage["prompt_tokens"], output_tokens=usage["completion_tokens"],
                         duration_ms=round((time.monotonic()-started)*1000), stream=True)
                    return
                data = json.loads(response.read())
            actual = data.get("model")
            if actual and actual not in (API_MODEL, PROFILE_MODEL):
                raise RuntimeError("OpenRouter returned a different model; response rejected")
            result = openai_to_anthropic(data)
            usage = result["usage"]
            _log("response", status=200, input_tokens=usage["input_tokens"], output_tokens=usage["output_tokens"],
                 duration_ms=round((time.monotonic()-started)*1000), stream=False)
            self._send(200, result)
        except HTTPError as exc:
            _log("error", status=exc.code, error="upstream_http_error", duration_ms=round((time.monotonic()-started)*1000))
            self._send(exc.code, {"type": "error", "error": {"type": "upstream_error", "message": f"OpenRouter HTTP {exc.code}"}})
        except URLError as exc:
            kind = type(exc.reason).__name__
            _log("error", status=502, error=kind, duration_ms=round((time.monotonic()-started)*1000))
            self._send(502, {"type": "error", "error": {"type": "upstream_error", "message": "OpenRouter connection failed"}})
        except Exception as exc:
            status = 400 if isinstance(exc, (ValueError, json.JSONDecodeError)) else 502
            _log("error", status=status, error=type(exc).__name__, duration_ms=round((time.monotonic()-started)*1000))
            self._send(status, {"type": "error", "error": {"type": "bridge_error", "message": str(exc)[:240]}})
