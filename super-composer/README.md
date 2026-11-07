# Super Composer

Super Composer 是一个通过 MCP 调用的创作流程工具。它把项目初始化、素材整理、草稿保存、审阅和润色组织成可复用流程。

## 解决的问题

长文创作经常把资料、初稿、事实核验和润色混在一起，导致事实与观点难以追踪。Super Composer 把这些步骤拆开，并把项目状态保存到项目目录。

## 使用方法

运行环境需要 Python 3.11 或更高版本。

```bash
python server.py
```

在 MCP 客户端注册该服务后，使用 `super-composer` Skill 的触发规则调用。示例配置见 `skill/SKILL.md`。项目目录由调用方传入，工具不会要求固定本机路径。

## 核心优势

- MCP 工具和 Skill 配套提供。
- 项目状态可保存、恢复和复查。
- Composer、Auditor、Polish 角色职责分离。

## 技术架构

核心逻辑使用 Python 标准库和 SQLite。`server.py` 提供 stdio MCP 服务，`core.py` 实现项目与草稿流程，`decision.py` 负责决策与阶段状态，`prompts/` 保存角色提示词，`skill/` 保存触发型 Skill。
