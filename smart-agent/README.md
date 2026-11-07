# Smart Agent

Smart Agent 是一个可独立运行的任务编排 CLI。它把任务设计、执行、恢复和证据记录组合在一起，适合需要多步骤处理的 AI 工作流。

## 解决的问题

普通 Agent 适合一次性任务。任务需要拆分、并行、暂停、恢复或检查结果时，过程容易丢失。Smart Agent 为这些步骤提供统一的运行入口和状态记录。

## 使用方法

需要 Node.js 22 或更高版本，并准备一个 pi 支持的模型供应商。

```bash
npm install
node smart-agent.mjs --help
node smart-agent.mjs run --traditional --goal "总结当前目录的说明文件" --workspace ./work
node smart-agent.mjs run --goal "检查项目并修复指定问题" --workspace ./work
```

配置通过环境变量或 pi 的原生配置完成。密钥只放在本机环境变量或认证存储中。

## 核心优势

- 支持简单执行和 Smart 编排两种模式。
- 支持方法复用、checkpoint、暂停、恢复和审计记录。
- 不绑定单一模型供应商。

## 技术架构

核心代码使用 Node.js ES modules。CLI 位于 `src/cli.mjs`，运行控制位于 `src/run.mjs` 与 `src/smart-run.mjs`，MCP 接口位于 `mcp/`。模型和工具由 pi 运行时提供，配置通过环境变量和用户配置目录注入。

## 目录内容

`src/` 是 CLI 与运行时，`mcp/` 是 MCP 接口，`tests/` 是已有测试，`fixtures/` 和 `prompts/` 是示例材料。
