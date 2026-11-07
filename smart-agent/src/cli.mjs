#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { configPath, loadConfig, redactConfig, saveConfig, validateProvider, runtimeProvider, effectiveRuntimeConfig } from "./config.mjs";
import { ensureDirectory, resolvePiRoot, defaultSpiralRoot } from "./paths.mjs";
import { SpiralStore } from "../core/spiral-store.mjs";
import { startCruise, cruiseStatus, pauseCruise, stopCruise, resumeCruise } from "./cruise.mjs";
import { sCardSystemPrompt } from "./s-card-system-prompt.mjs";
import { createExploration, readExploration, addExplorationRound, updateExplorationStatus } from "./exploration.mjs";
import { runTraditional } from "./run.mjs";
import { runSmart } from "./smart-run.mjs";
import { RUNTIME_LIMITS } from "./runtime-policy.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_MANIFEST = path.join(ROOT, "extensions", "loop-seeds", "extension.json");
const HELP = `Smart Agent CLI

smart-agent run --goal "目标" [--traditional] [--workspace 目录] [--attach 文件]
smart-agent config init
smart-agent config show
smart-agent config set provider.baseUrl https://provider.example/v1   # 旧版兼容路径
smart-agent config set provider.model model-id                     # 旧版兼容路径
smart-agent config set provider.apiKeyEnv ENV_NAME                 # 旧版兼容路径
smart-agent config set pi.provider provider-id                    # pi 原生路径
smart-agent config set pi.model provider/model-id                 # pi 原生路径
smart-agent config set pi.thinkingLevel low                       # pi 原生 effort
smart-agent methods list
smart-agent methods rollback <strategy-id> <version-hash>
smart-agent cruise start --goal "目标" [--workspace 目录]
smart-agent cruise status <job-id>
smart-agent cruise pause <job-id>
smart-agent cruise stop <job-id>
smart-agent cruise resume <job-id>
smart-agent cruise wake <job-id>                         # 外部定时任务唤醒
smart-agent s-card run --goal "目标"                    # S 卡系统提示词
smart-agent s-card cruise start --goal "目标"           # S 卡巡航
smart-agent explore start --question "问题"             # 探索状态
smart-agent explore add-round <id> --facts "事实" --hypothesis "假设" --experiment "实验" --result "结果"
smart-agent explore status|pause|resume|stop|complete <id>
smart-agent doctor
smart-agent extensions list
smart-agent plugins list
smart-agent plugins enable sub-agents
smart-agent plugins disable sub-agents

run 参数：
  --goal <text>          自然语言目标；省略时从 stdin 读取
  --traditional          使用 pi 标准 Agent Loop，不启用 Manager
  --workspace <dir>      工作目录，默认当前目录
  --attach <file>        附加文本或图片，可重复；也可用 @file
  --seed-manifest <path> 可替换 Loop Seed manifest
  --timeout-ms <ms>      单次模型运行安全超时，默认 86400000（24 小时）
  --max-manager-attempts <n> Manager 设计恢复上限，默认 32
  --max-worker-turns <n> Worker 恢复回合上限，默认 4096
  --help                 显示帮助

pi 原生 Provider、models.json、auth.json 和工具由 pi 负责；Smart Agent 不重复实现。
旧版 provider.* 仅为兼容 shim。pi 原生路径可用 config.set pi.provider/model，或命令行 --provider/--model/--thinking 覆盖。
密钥只在 pi 原生认证链或旧版兼容环境变量中流转，不写入 config.json、日志或报告。
Sub Agents 是独立可选插件，默认关闭；Traditional/Smart 核心均不依赖它。
`;

function parse(args) {
  const positional = [];
  const options = { attachments: [] };
  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--help" || arg === "-h") options.help = true;
    else if (arg === "--traditional") options.traditional = true;
    else if (arg === "--provider" || arg === "-p") options.provider = args[++index];
    else if (arg === "--model" || arg === "-m") options.model = args[++index];
    else if (arg === "--thinking" || arg === "--thinking-level") options.thinkingLevel = args[++index];
    else if (arg === "--goal" || arg === "-g") options.goal = args[++index];
    else if (arg.startsWith("--goal=")) options.goal = arg.slice(7);
    else if (arg === "--workspace" || arg === "-w") options.workspace = args[++index];
    else if (arg === "--attach") options.attachments.push(args[++index]);
    else if (arg.startsWith("--attach=")) options.attachments.push(arg.slice(9));
    else if (arg.startsWith("@") && arg.length > 1) options.attachments.push(arg.slice(1));
    else if (arg === "--seed-manifest") options.seedManifest = args[++index];
    else if (arg === "--job-id") options.jobId = args[++index];
    else if (arg === "--max-worker-turns") options.maxWorkerTurns = args[++index];
    else if (arg === "--max-manager-attempts") options.maxManagerAttempts = args[++index];
    else if (arg === "--timeout-ms") options.timeoutMs = args[++index];
    else if (arg === "--s-card") options.sCard = true;
    else if (arg === "--question") options.question = args[++index];
    else if (arg === "--max-rounds") options.maxRounds = args[++index];
    else if (arg === "--facts") options.facts = args[++index];
    else if (arg === "--hypothesis") options.hypothesis = args[++index];
    else if (arg === "--experiment") options.experiment = args[++index];
    else if (arg === "--result") options.result = args[++index];
    else if (arg === "--next-action") options.nextAction = args[++index];
    else if (arg === "--evidence") options.evidence = args[++index];
    else if (arg === "--exploration-id") options.explorationId = args[++index];
    else if (arg === "--reason") options.reason = args[++index];
    else if (!arg.startsWith("-")) positional.push(arg);
    else throw new Error(`未知参数: ${arg}`);
  }
  return { positional, options };
}

function splitList(value) {
  return String(value || "").split("|").map((item) => item.trim()).filter(Boolean);
}

async function readStdin() {
  let value = "";
  for await (const chunk of process.stdin) value += chunk.toString();
  return value.trim();
}

function requireWorkspace(workspace) {
  if (!fs.existsSync(workspace) || !fs.statSync(workspace).isDirectory()) throw new Error(`workspace 不存在或不是目录: ${workspace}`);
}

async function configCommand(args) {
  const action = args[0] || "show";
  if (action === "init") {
    const file = saveConfig(loadConfig({ required: false }));
    console.log(`配置已初始化: ${file}`);
    console.log("下一步设置 provider.baseUrl、provider.model，并通过环境变量提供凭证。");
    return;
  }
  const config = loadConfig();
  if (action === "show") {
    console.log(JSON.stringify(redactConfig(config), null, 2));
    return;
  }
  if (action === "set") {
    const [key, ...rest] = args.slice(1);
    const value = rest.join(" ").trim();
    if (!key || !value) throw new Error("用法: smart-agent config set provider.baseUrl <url>");
    const allowed = new Set(["provider.baseUrl", "provider.model", "provider.apiKeyEnv", "provider.contextWindow", "provider.maxTokens", "pi.provider", "pi.model", "pi.thinkingLevel"]);
    if (!allowed.has(key)) throw new Error(`只允许设置: ${[...allowed].join(", ")}`);
    const [group, field] = key.split(".");
    if (group === "pi") {
      config.pi ||= {};
      config.pi[field] = value;
      saveConfig(config);
      console.log(`已更新 ${key}（未保存密钥；模型认证仍由 pi 原生链负责）`);
      return;
    }
    if (["contextWindow", "maxTokens"].includes(field) && (!/^\d+$/.test(value) || Number(value) <= 0 || !Number.isSafeInteger(Number(value)))) {
      throw new Error(`${key} 必须是正整数`);
    }
    config.provider[field] = ["contextWindow", "maxTokens"].includes(field) ? Number(value) : value;
    saveConfig(config);
    console.log(`已更新 ${key}（未保存密钥；该字段属于旧版兼容 shim）`);
    return;
  }
  throw new Error(`未知 config 操作: ${action}`);
}

function pluginCommand(args) {
  const action = args[0] || "list";
  const config = loadConfig();
  if (action === "list") {
    console.log(JSON.stringify({ name: "sub-agents", required: false, enabled: config.plugins["sub-agents"]?.enabled === true, adapters: ["codex", "pi", "opencode"] }, null, 2));
    return;
  }
  if (!["enable", "disable"].includes(action) || args[1] !== "sub-agents") throw new Error("用法: smart-agent plugins enable|disable sub-agents");
  config.plugins["sub-agents"] = { enabled: action === "enable" };
  saveConfig(config);
  console.log(`Sub Agents 已${action === "enable" ? "启用" : "关闭"}；核心 Traditional/Smart 能力不变。`);
}

async function main() {
  let [command, ...rest] = process.argv.slice(2);
  if (command?.startsWith("-") && !["--help", "-h"].includes(command)) {
    rest = process.argv.slice(2);
    command = "run";
  }
  const { positional, options } = parse(rest);
  if (!command || options.help || command === "--help" || command === "-h") {
    console.log(HELP);
    return 0;
  }
  if (command === "config") { await configCommand(positional); return 0; }
  if (command === "s-card") {
    const subcommand = positional.shift() || "run";
    options.sCard = true;
    if (subcommand === "cruise") command = "cruise";
    else if (subcommand === "run") command = "run";
    else throw new Error("用法: smart-agent s-card run|cruise ...");
  }
  if (command === "explore") {
    const action = positional[0] || "status";
    if (action === "start") {
      const question = String(options.question || options.goal || "").trim();
      if (!question) throw new Error("explore start 必须提供 --question");
      const workspace = path.resolve(options.workspace || process.cwd());
      requireWorkspace(workspace);
      console.log(JSON.stringify(createExploration({ question, workspace, maxRounds: options.maxRounds }), null, 2));
      return 0;
    }
    const explorationId = positional[1];
    if (!explorationId) throw new Error(`explore ${action} 需要 exploration-id`);
    if (action === "status") console.log(JSON.stringify(readExploration(explorationId), null, 2));
    else if (action === "add-round") console.log(JSON.stringify(addExplorationRound(explorationId, { facts: splitList(options.facts), hypothesis: options.hypothesis, experiment: options.experiment, result: options.result, nextAction: options.nextAction, evidence: splitList(options.evidence) }), null, 2));
    else if (action === "pause" || action === "resume" || action === "stop" || action === "complete") {
      const status = action === "resume" ? "active" : action === "complete" ? "completed" : action === "pause" ? "paused" : "stopped";
      console.log(JSON.stringify(updateExplorationStatus(explorationId, status, options.reason || ""), null, 2));
    } else throw new Error(`未知 explore 操作: ${action}`);
    return 0;
  }
  if (command === "methods") {
    const store = new SpiralStore(defaultSpiralRoot());
    const action = positional[0] || "list";
    if (action === "list") {
      console.log(JSON.stringify(store.listStrategies(), null, 2));
      return 0;
    }
    if (action === "rollback") {
      const [, strategyId, versionHash] = positional;
      if (!strategyId || !versionHash) throw new Error("用法: smart-agent methods rollback <strategy-id> <version-hash>");
      const target = store.getStrategy(strategyId);
      if (!target && !store.state.strategies[strategyId]?.versions?.[versionHash]) throw new Error(`未知方法版本: ${strategyId}/${versionHash}`);
      const event = store.rollback(strategyId, versionHash, `manual-${Date.now()}`, "user requested rollback");
      console.log(JSON.stringify({ rolledBack: true, strategyId, versionHash, eventId: event.eventId }, null, 2));
      return 0;
    }
    throw new Error(`未知 methods 操作: ${action}`);
  }
  if (command === "cruise") {
    const action = positional[0] || "status";
    if (action === "start") {
      const goal = String(options.goal || "").trim() || (process.stdin.isTTY ? "" : await readStdin());
      if (!goal) throw new Error("cruise start 必须提供 --goal，或通过 stdin 输入目标");
      const workspace = path.resolve(options.workspace || process.cwd());
      requireWorkspace(workspace);
      const config = loadConfig();
      const provider = runtimeProvider(config, options);
      const errors = validateProvider(effectiveRuntimeConfig(config, options), { requireKey: !provider.native });
      if (errors.length) throw new Error(errors.join("；"));
      const result = await startCruise({ goal, workspace, provider, attachments: options.attachments, seedManifest: path.resolve(options.seedManifest || DEFAULT_MANIFEST), jobId: options.jobId, maxWorkerTurns: options.maxWorkerTurns, maxManagerAttempts: options.maxManagerAttempts, timeoutMs: options.timeoutMs, explorationId: options.explorationId, plugins: config.plugins, systemPrompt: options.sCard ? sCardSystemPrompt() : "", controlPlane: options.sCard ? "s-card-cruise" : "smart" });
      console.log(JSON.stringify(result, null, 2));
      return 0;
    }
    const jobId = positional[1];
    if (!jobId) throw new Error(`cruise ${action} 需要 job-id`);
    if (action === "status" || action === "inspect") console.log(JSON.stringify(cruiseStatus(jobId), null, 2));
    else if (action === "pause") console.log(JSON.stringify(pauseCruise(jobId), null, 2));
    else if (action === "stop") console.log(JSON.stringify(stopCruise(jobId), null, 2));
    else if (action === "resume" || action === "wake") console.log(JSON.stringify(await resumeCruise(jobId, { wakeSource: action, plugins: loadConfig().plugins, systemPrompt: options.sCard ? sCardSystemPrompt() : "", controlPlane: options.sCard ? "s-card-cruise" : "smart" }), null, 2));
    else throw new Error(`未知 cruise 操作: ${action}`);
    return 0;
  }
  if (command === "extensions") {
    if (positional[0] && positional[0] !== "list") throw new Error("用法: smart-agent extensions list");
    const manifest = JSON.parse(fs.readFileSync(DEFAULT_MANIFEST, "utf8"));
    console.log(JSON.stringify({ id: manifest.id, version: manifest.version, entrypoint: manifest.entrypoint, required: false }, null, 2));
    return 0;
  }
  if (command === "plugins") { pluginCommand(positional); return 0; }
  if (command === "doctor") {
    const config = loadConfig({ required: false });
    const errors = validateProvider(config, { requireKey: false });
    const checks = {
      node: process.version,
      platform: process.platform,
      pi: resolvePiRoot(),
      config: configPath(),
      providerConfigured: errors.length === 0,
      nativePiConfigured: Boolean(config.pi?.model),
      credentialEnvironmentPresent: Boolean(config.provider.apiKeyEnv && process.env[config.provider.apiKeyEnv]),
      spiralState: defaultSpiralRoot(),
      subAgentsRequired: false,
      subAgentsEnabled: config.plugins["sub-agents"]?.enabled === true,
    };
    console.log(JSON.stringify(checks, null, 2));
    if (errors.length) console.log(`待配置: ${errors.join("；")}`);
    return errors.length ? 1 : 0;
  }
  if (command !== "run") throw new Error(`未知命令: ${command}\n${HELP}`);
  const goal = String(options.goal || "").trim() || (process.stdin.isTTY ? "" : await readStdin());
  if (!goal) throw new Error("必须提供 --goal，或通过 stdin 输入目标");
  const workspace = path.resolve(options.workspace || process.cwd());
  requireWorkspace(workspace);
  const config = loadConfig();
  const provider = runtimeProvider(config, options);
  const errors = validateProvider(effectiveRuntimeConfig(config, options), { requireKey: !provider.native });
  if (errors.length) throw new Error(errors.join("；"));
  const ceilings = { timeoutMs: RUNTIME_LIMITS.promptTimeoutMs, maxManagerAttempts: RUNTIME_LIMITS.maxManagerAttempts, maxWorkerTurns: RUNTIME_LIMITS.maxWorkerTurns };
  for (const [field, ceiling] of Object.entries(ceilings)) {
    if (options[field] === undefined) continue;
    const value = Number(options[field]);
    if (!Number.isSafeInteger(value) || value <= 0 || value > ceiling) throw new Error(`--${field.replace(/[A-Z]/g, (letter) => `-${letter.toLowerCase()}`)} 必须是 1 到 ${ceiling} 之间的整数`);
    options[field] = value;
  }
  if (options.traditional) {
    const summary = await runTraditional({ goal, workspace, provider, attachments: options.attachments, timeoutMs: options.timeoutMs || RUNTIME_LIMITS.promptTimeoutMs });
    console.log(JSON.stringify(summary, null, 2));
    return 0;
  }
  const seedManifest = path.resolve(options.seedManifest || DEFAULT_MANIFEST);
  if (!fs.existsSync(seedManifest)) throw new Error(`seed manifest 不存在: ${seedManifest}`);
  const summary = await runSmart({ goal, workspace, provider, attachments: options.attachments, seedManifest, explorationId: options.explorationId, maxWorkerTurns: options.maxWorkerTurns || RUNTIME_LIMITS.maxWorkerTurns, maxManagerAttempts: options.maxManagerAttempts || RUNTIME_LIMITS.maxManagerAttempts, timeoutMs: options.timeoutMs || RUNTIME_LIMITS.promptTimeoutMs, plugins: config.plugins, systemPrompt: options.sCard ? sCardSystemPrompt() : "", controlPlane: options.sCard ? "s-card" : "smart" });
  console.log(JSON.stringify(summary, null, 2));
  return 0;
}

try {
  process.exitCode = await main();
} catch (error) {
  console.error(`Smart Agent CLI 错误: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 2;
}
