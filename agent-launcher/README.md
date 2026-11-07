# Agent Launcher

Agent Launcher 是一个子智能体派发器。它把任务书、角色提示词、模型、CLI、桥接器和运行回执连接起来，让用户按任务选择轻量型、通用型或突破型子智能体。

## 三种类型

- L 型用于轻量侦查和资料整理。
- U 型用于通用执行和多步骤任务。
- Breakthrough 型用于单一高难度瓶颈。

## 使用方法

1. 在 `config/profiles.json` 配置 CLI、模型和角色。
2. 根据 `profiles.example.json` 增加自己的 profile。
3. 启动 `mcp/launcher_entry.py`。
4. 通过 MCP 调用 profile 查询、启动、状态查询和回执收集。

## 模型桥接

桥接层统一不同 CLI 的调用格式，支持 Claude Code、Antigravity、Codex、OpenCode 等 CLI 接入兼容模型。认证和模型配置由用户自己提供。

## 默认 Skill

配置目录提供 `deep-search`、`workflow-harness` 和 `daybreaker` 三个默认 Skill。系统提示词位于 `config/`，不依赖个人记忆或 SMI。

## 技术架构

`mcp/` 提供 MCP 服务，`kernel/` 负责配置、路由、任务状态和回执，`adapters/` 负责 CLI 与模型桥接，`data/` 保存通用运行状态文件。
