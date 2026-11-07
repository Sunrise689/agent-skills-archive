"""Cline CLI adapter over the local MiniMax Responses bridge.

为什么必须走本地桥（2026-10-22 实测）：
  Cline 的 provider settings 必须同时带 apiKey + baseUrl，缺任一项就退回
  platform.openai.com，报 "You didn't provide an API key"。
  但把真实 MiniMax 密钥写进 settings/providers.json 等于明文落盘，违反凭证纪律。

本适配器（沿用 bridge_runner.py 既有模式，不新造机制）：
  1. bridge_runner 起本地 Responses 桥（chat 协议进 -> MiniMax 原生 /v1/responses 出）。
  2. Cline 的 baseUrl 指向 127.0.0.1 桥，apiKey 填占位串（桥不校验）。
  3. 真实 MiniMax 密钥只存在桥进程内存（从 Pi 的 models.json 读），全程不落盘。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


CHANNEL = "cline"
RUNNER = Path(__file__).with_name("bridge_runner.py")
MODEL = "MiniMax-M3.1-Flash"


def build(profile: dict, model: str, effort: str | None, prompt_text: str,
          cwd: str, write_scope: str) -> tuple[list[str], str | None]:
    selected_model = model or profile.get("model") or MODEL
    if not selected_model:
        raise ValueError("Cline card requires a model selected at dispatch time")
    bootstrap = (
        "import os,runpy,sys; os.environ['CARD_LAUNCHER_MODEL']=" + json.dumps(selected_model) + "; "
        "os.environ['CARD_LAUNCHER_EFFORT']=" + json.dumps(effort or "max") + "; "
        "sys.argv=['bridge_runner.py','cline']; runpy.run_path(r'" + str(RUNNER) + "',run_name='__main__')"
    )
    return [sys.executable, "-c", bootstrap], prompt_text
