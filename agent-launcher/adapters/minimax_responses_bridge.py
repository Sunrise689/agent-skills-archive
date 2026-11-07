"""Loopback Responses -> MiniMax Chat Completions adapter for Codex cards."""
from __future__ import annotations
import json
import os
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

MODEL = os.environ.get("CARD_LAUNCHER_MODEL", "MiniMax-M3.1-Flash")


def convert(body: dict) -> tuple[dict, set[str]]:
    messages = []
    if body.get("instructions"):
        messages.append({"role": "system", "content": body["instructions"]})
    inputs = body.get("input", [])
    if isinstance(inputs, str):
        inputs = [{"role": "user", "content": inputs}]
    custom = set()
    tools = []
    for tool in body.get("tools", []):
        if tool.get("type") == "function":
            tools.append({"type": "function", "function": {"name": tool["name"], "description": tool.get("description", ""), "parameters": tool.get("parameters", {"type": "object", "properties": {}})}})
        elif tool.get("type") == "custom":
            custom.add(tool["name"])
            tools.append({"type": "function", "function": {"name": tool["name"], "description": tool.get("description", ""), "parameters": {"type": "object", "properties": {"input": {"type": "string"}}, "required": ["input"]}}})
    for item in inputs:
        kind = item.get("type", "message")
        if kind in ("function_call", "custom_tool_call"):
            arguments = item.get("arguments", "{}") if kind == "function_call" else json.dumps({"input": item.get("input", "")})
            call = {"id": item["call_id"], "type": "function", "function": {"name": item["name"], "arguments": arguments}}
            if messages and messages[-1].get("tool_calls"):
                messages[-1]["tool_calls"].append(call)
            else:
                messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        elif kind in ("function_call_output", "custom_tool_call_output"):
            output = item.get("output", "")
            messages.append({"role": "tool", "tool_call_id": item["call_id"], "content": output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)})
        elif kind == "message" or "role" in item:
            content = item.get("content", "")
            if isinstance(content, list):
                if any(part.get("type") not in ("input_text", "output_text", "text") for part in content):
                    raise ValueError("Responses bridge supports text content only")
                content = "\n".join(part.get("text", "") for part in content if part.get("type") in ("input_text", "output_text", "text"))
            role = item.get("role", "user")
            messages.append({"role": "system" if role == "developer" else role, "content": content})
        elif kind == "reasoning":
            continue
        else:
            raise ValueError("Unsupported Responses input type: " + str(kind))
    request = {"model": MODEL, "messages": messages, "stream": False, "max_tokens": min(body.get("max_output_tokens") or 8192, 16384)}
    if tools:
        request["tools"] = tools
        request["tool_choice"] = "auto"
    return request, custom


def response_events(result: dict, custom: set[str]) -> tuple[dict, bytes]:
    response_id = "resp_" + uuid.uuid4().hex
    usage = result.get("usage", {})
    base = {"id": response_id, "object": "response", "created_at": int(time.time()), "status": "in_progress", "model": MODEL, "output": [], "error": None, "incomplete_details": None, "usage": {"input_tokens": usage.get("prompt_tokens", 0), "output_tokens": usage.get("completion_tokens", 0), "total_tokens": usage.get("total_tokens", 0)}}
    events = []
    def emit(kind, **fields):
        payload = {"type": kind, "sequence_number": len(events), **fields}
        events.append("event: " + kind + "\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n")
    emit("response.created", response=dict(base))
    emit("response.in_progress", response=dict(base))
    choices = result.get("choices") or []
    if not choices:
        raise ValueError("MiniMax response has no choices")
    message = choices[0].get("message", {})
    output = []
    content = message.get("content") or ""
    if content:
        item = {"id": "msg_" + uuid.uuid4().hex, "type": "message", "role": "assistant", "status": "in_progress", "content": []}
        emit("response.output_item.added", output_index=0, item=dict(item))
        part = {"type": "output_text", "text": "", "annotations": []}
        emit("response.content_part.added", item_id=item["id"], output_index=0, content_index=0, part=dict(part))
        emit("response.output_text.delta", item_id=item["id"], output_index=0, content_index=0, delta=content)
        emit("response.output_text.done", item_id=item["id"], output_index=0, content_index=0, text=content)
        part["text"] = content
        emit("response.content_part.done", item_id=item["id"], output_index=0, content_index=0, part=part)
        item.update(status="completed", content=[part])
        emit("response.output_item.done", output_index=0, item=item)
        output.append(item)
    for call in message.get("tool_calls") or []:
        f = call["function"]
        is_custom = f["name"] in custom
        args = f.get("arguments") or "{}"
        if is_custom:
            args = json.loads(args).get("input", "")
        item = {"id": "fc_" + uuid.uuid4().hex, "type": "custom_tool_call" if is_custom else "function_call", "call_id": call["id"], "name": f["name"], "status": "in_progress", "input" if is_custom else "arguments": ""}
        index = len(output)
        emit("response.output_item.added", output_index=index, item=dict(item))
        event_prefix = "response.custom_tool_call_input" if is_custom else "response.function_call_arguments"
        emit(event_prefix + ".delta", item_id=item["id"], output_index=index, delta=args)
        emit(event_prefix + ".done", item_id=item["id"], output_index=index, **{"input" if is_custom else "arguments": args})
        item.update(status="completed")
        item["input" if is_custom else "arguments"] = args
        emit("response.output_item.done", output_index=index, item=item)
        output.append(item)
    base.update(status="incomplete" if choices[0].get("finish_reason") == "length" else "completed", output=output)
    if base["status"] == "incomplete":
        base["incomplete_details"] = {"reason": "max_output_tokens"}
    emit("response." + base["status"], response=base)
    return base, "".join(events).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass
    def reply(self, status, data, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.path == "/health":
            self.reply(200, json.dumps({"ok": True, "model": MODEL}).encode())
        else:
            self.reply(404, b'{}')
    def do_POST(self):
        if self.path.split("?", 1)[0] not in ("/v1/responses", "/responses"):
            self.reply(404, b'{}')
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            request_body, custom = convert(body)
            config = json.loads((Path.home() / ".pi/agent/models.json").read_text(encoding="utf-8-sig"))["providers"]["minimax"]
            base = config.get("baseUrl") or config.get("baseURL")
            req = Request(base.rstrip("/") + "/chat/completions", data=json.dumps(request_body, ensure_ascii=False).encode(), headers={"Authorization": "Bearer " + config["apiKey"], "Content-Type": "application/json"})
            with urlopen(req, timeout=240) as response:
                result = json.load(response)
            payload, stream = response_events(result, custom)
            print(json.dumps({"bridge_event": "responses", "model": MODEL, "tools": len(request_body.get("tools", [])), "output_types": [i["type"] for i in payload["output"]]}), flush=True)
            self.reply(200, stream if body.get("stream") else json.dumps(payload, ensure_ascii=False).encode(), "text/event-stream" if body.get("stream") else "application/json")
        except HTTPError as exc:
            self.reply(exc.code, exc.read())
        except ValueError as exc:
            self.reply(400, json.dumps({"error": {"type": "invalid_request_error", "message": str(exc)}}).encode())
        except Exception as exc:
            self.reply(502, json.dumps({"error": {"type": "api_error", "message": "Responses bridge failed: " + type(exc).__name__}}).encode())


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", int(os.environ["CARD_RESPONSES_PORT"])), Handler).serve_forever()
