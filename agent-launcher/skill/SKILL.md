---
name: agent-launcher
description: Launch and manage configurable sub-agents through the Agent Launcher MCP.
---

# Agent Launcher

Agent Launcher 是子智能体派发器。它把任务书、角色提示词、模型、CLI、桥接器和运行回执连接起来，让用户可以按任务选择轻量型、通用型或突破型子智能体。

## 三种类型

- L 型适合轻量侦查、资料整理和快速确认。
- U 型适合通用执行和多步骤任务。
- Breakthrough 型适合单一高难度瓶颈。

## 使用方法

1. 准备一份自包含任务书。
2. 在 `profiles.json` 中配置 CLI 和模型，格式参考 `profiles.example.json`。
3. 启动 `mcp/launcher_entry.py` 或 `mcp/launcher_mcp_server.py`。
4. 通过 MCP 调用 profile 查询、启动、查询状态和收集回执。

默认可挂载 `deep-search`、`workflow-harness` 和 `daybreaker` 等通用 Skill。每个外部 CLI 的认证和模型配置由用户自己提供。

## 模型桥接

桥接层把不同 CLI 的调用统一到同一套任务接口，允许用户为 Claude Code、Antigravity、Codex、OpenCode 等 CLI 配置任意兼容模型。桥接器只读取用户本机已有凭证，不把密钥写入任务书、回执或日志。

## 技术架构

`mcp/` 提供 MCP 服务，`kernel/` 负责配置、路由、任务状态和回执，`adapters/` 负责 CLI 与模型供应商桥接，`tools/` 提供命令行辅助工具。系统通过 JSON 配置 profile，通过 JSONL 或 JSON 回执记录派发结果。
