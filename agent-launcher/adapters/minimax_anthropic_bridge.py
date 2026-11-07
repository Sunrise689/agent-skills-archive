"""Small, secret-safe Anthropic-compatible MiniMax Token Plan loopback bridge."""
from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MODEL = os.environ.get("MINIMAX_CC_MODEL", "MiniMax-M3.1-Flash")
EFFORT = os.environ.get("MINIMAX_CC_EFFORT")
HOST = "127.0.0.1"
PORT = int(os.environ.get("MINIMAX_CC_BRIDGE_PORT", "8766"))
UPSTREAM = os.environ.get("MINIMAX_ANTHROPIC_URL", "https://api.minimaxi.com/anthropic").rstrip("/")
CONFIG = Path(os.environ.get("PI_MODELS_JSON", str(Path.home() / ".pi" / "agent" / "models.json")))


def _diag(event: str, **fields: object) -> None:
    """Log request metadata only; never log prompts, headers, or credentials."""
    record = {"bridge_event": event, "ts": round(time.time(), 3), **fields}
    print(json.dumps(record, ensure_ascii=False, separators=(",", ":")), file=sys.stderr, flush=True)


def _key() -> str:
    provider = json.loads(CONFIG.read_text(encoding="utf-8-sig")).get("providers", {}).get("minimax", {})
    value = provider.get("apiKey")
    if not isinstance(value, str) or not value:
        raise RuntimeError("MiniMax credential is missing in Pi models.json")
    return value


def _client_response(data: bytes, content_type: str, client_model: str) -> bytes:
    """Keep client model metadata consistent without changing actual routing."""
    def fix(value: dict) -> dict:
        if "model" in value:
            value["model"] = client_model
        if isinstance(value.get("message"), dict) and "model" in value["message"]:
            value["message"]["model"] = client_model
        return value
    if "text/event-stream" in content_type:
        lines = []
        for line in data.decode("utf-8").splitlines(keepends=True):
            if line.startswith("data: "):
                try:
                    value = json.loads(line[6:])
                    if isinstance(value, dict):
                        line = "data: " + json.dumps(fix(value), ensure_ascii=False) + "\n"
                except ValueError:
                    pass
            lines.append(line)
        return "".join(lines).encode("utf-8")
    value = json.loads(data)
    return json.dumps(fix(value), ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "MiniMaxAnthropicBridge/1.0"

    def log_message(self, _fmt: str, *_args: object) -> None:
        # Prompts and credentials never enter logs.
        return

    def _reply(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] == "/health":
            self._reply(200, json.dumps({"ok": True, "model": MODEL}).encode(), "application/json")
        else:
            self._reply(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        route = self.path.split("?", 1)[0]
        if route not in ("/v1/messages", "/messages", "/v1/messages/count_tokens", "/messages/count_tokens"):
            self._reply(404, b"not found", "text/plain")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length))
            incoming_model = body.get("model")
            body["model"] = MODEL
            if EFFORT:
                if EFFORT not in {"low", "medium", "high", "xhigh", "max"}:
                    raise ValueError("Unsupported MiniMax effort")
                body.setdefault("output_config", {})["effort"] = EFFORT
                body["thinking"] = {"type": "adaptive"}
            messages = body.get("messages")
            tools = body.get("tools")
            _diag(
                "request",
                route=route,
                incoming_model=incoming_model,
                routed_model=MODEL,
                routed_effort=body.get("output_config", {}).get("effort"),
                stream=body.get("stream"),
                max_tokens=body.get("max_tokens"),
                message_count=len(messages) if isinstance(messages, list) else None,
                tool_count=len(tools) if isinstance(tools, list) else None,
                anthropic_beta_present=bool(self.headers.get("anthropic-beta")),
            )
            headers = {
                "x-api-key": _key(),
                "anthropic-version": self.headers.get("anthropic-version", "2023-06-01"),
                "content-type": "application/json",
                "accept": self.headers.get("accept", "application/json"),
            }
            if self.headers.get("anthropic-beta"):
                headers["anthropic-beta"] = self.headers["anthropic-beta"]
            upstream_route = "/v1/messages/count_tokens" if route.endswith("/count_tokens") else "/v1/messages"
            request = Request(UPSTREAM + upstream_route, data=json.dumps(body, ensure_ascii=False).encode(), method="POST", headers=headers)
            try:
                with urlopen(request, timeout=240) as response:
                    response_body = response.read()
                    content_type = response.headers.get("Content-Type", "application/json")
                    response_body = _client_response(response_body, content_type, str(incoming_model or MODEL))
                    _diag("response", status=response.status,
                          content_type=response.headers.get("Content-Type", "application/json"),
                          byte_count=len(response_body))
                    self._reply(response.status, response_body, content_type)
            except HTTPError as exc:
                # Forward the original diagnostic, but log only its safe error fields.
                response_body = exc.read()
                try:
                    payload = json.loads(response_body)
                    detail = payload.get("error", {}) if isinstance(payload, dict) else {}
                except Exception:
                    detail = {}
                message = detail.get("message") if isinstance(detail, dict) else None
                if isinstance(message, str):
                    message = message.replace("\n", " ")[:240]
                _diag("upstream_error", status=exc.code,
                      error_type=detail.get("type") if isinstance(detail, dict) else None,
                      error_code=detail.get("code") if isinstance(detail, dict) else None,
                      error_message=message)
                self._reply(exc.code, response_body, exc.headers.get("Content-Type", "application/json"))
        except (OSError, ValueError, RuntimeError, URLError) as exc:
            _diag("bridge_error", error_type=type(exc).__name__)
            body = json.dumps({"type": "error", "error": {"type": "api_error", "message": f"Local MiniMax bridge failed ({type(exc).__name__})"}}).encode()
            self._reply(502, body, "application/json")


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
