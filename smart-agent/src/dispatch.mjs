import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { ensureDirectory, defaultConfigDir } from "./paths.mjs";

const ROOT = process.env.SMART_AGENT_LAUNCHER_ROOT || path.join(os.homedir(), ".agent-launcher");
const PROFILE_FILE = process.env.SMART_AGENT_CARD_PROFILES || path.join(ROOT, "profiles.json");
const MCP_CALL = process.env.SMART_AGENT_CARD_MCP_CALL || path.join(ROOT, "tools", "mcp_call.py");
const PYTHON = process.env.SMART_AGENT_PYTHON || (process.platform === "win32" ? "C:\\Python312\\python.exe" : "python3");
const ALLOWED = new Set(["MINIMAX-U", "MINIMAX-L", "GK-U", "GK-L", "CX-U-OFFICIAL"]);
const MODEL_BY_PROFILE = { "MINIMAX-U": "MiniMax-M3.1-Flash", "MINIMAX-L": "MiniMax-M3.1-Flash", "GK-U": "grok-4.7", "GK-L": "grok-4.7", "CX-U-OFFICIAL": "gpt-6-luna" };

function readProfiles() {
  const data = JSON.parse(fs.readFileSync(PROFILE_FILE, "utf8"));
  const profiles = Array.isArray(data) ? data : data.profiles;
  if (!Array.isArray(profiles)) throw new Error(`profiles.json 缺少 profiles 数组: ${PROFILE_FILE}`);
  return profiles;
}

function budgetFile() {
  return process.env.SMART_AGENT_DISPATCH_BUDGET || path.join(defaultConfigDir(), "dispatch-budget.json");
}

function budgetSnapshot(now = Date.now()) {
  const file = budgetFile();
  let value = {};
  try { value = JSON.parse(fs.readFileSync(file, "utf8")); } catch {}
  if (!value.windowStartedAt || now - Date.parse(value.windowStartedAt) >= 5 * 60 * 60 * 1000) {
    value = { windowStartedAt: new Date(now).toISOString(), minimaxCount: 0 };
  }
  return { file, value };
}

function saveBudget(file, value) {
  ensureDirectory(path.dirname(file));
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`, "utf8");
}

function redact(value) {
  return JSON.parse(JSON.stringify(value, (key, item) => /token|secret|authorization|api.?key/i.test(key) ? "[REDACTED]" : item));
}

export function validateDispatchRequest(request) {
  const profileId = String(request.profile_id || "").trim();
  if (!ALLOWED.has(profileId)) throw new Error(`S 卡派卡只允许当前白名单 profile: ${[...ALLOWED].join(", ")}`);
  const taskbookPath = path.resolve(String(request.taskbook_path || ""));
  if (!taskbookPath || !fs.existsSync(taskbookPath) || !fs.statSync(taskbookPath).isFile()) throw new Error(`taskbook_path 必须是现存文件: ${taskbookPath}`);
  const workdir = path.resolve(String(request.workdir || path.dirname(taskbookPath)));
  ensureDirectory(workdir);
  const cardId = String(request.card_id || "").trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(cardId)) throw new Error("card_id 必须是安全的非空标识符");
  const profiles = readProfiles();
  const profile = profiles.find((item) => item.id === profileId);
  if (!profile) throw new Error(`profiles.json 中不存在 profile: ${profileId}`);
  const expected = MODEL_BY_PROFILE[profileId];
  const actualModel = String(request.model || profile.model || "");
  if (profileId.startsWith("MINIMAX") && actualModel !== expected) throw new Error(`MiniMax profile 必须使用 ${expected}`);
  if (profileId.startsWith("GK-") && actualModel !== expected) throw new Error(`Grok profile 必须使用 ${expected}（短码 go4.7）`);
  if (profileId === "CX-U-OFFICIAL" && actualModel !== expected) throw new Error(`CX-U-OFFICIAL 必须使用 ${expected}`);
  return { ...request, card_id: cardId, profile_id: profileId, taskbook_path: taskbookPath, workdir, model: request.model || undefined, profile, expectedModel: expected };
}

export function dispatchCard(request, { receiptPath = null } = {}) {
  const checked = validateDispatchRequest(request);
  const startedAt = new Date().toISOString();
  const isMiniMax = checked.profile_id.startsWith("MINIMAX-");
  const budget = budgetSnapshot();
  if (isMiniMax && budget.value.minimaxCount >= Number(process.env.SMART_AGENT_MINIMAX_MAX_CARDS || 10)) {
    throw new Error(`MiniMax 5 小时预算护栏已达到 ${budget.value.minimaxCount} 张；等待窗口刷新或改派允许通道`);
  }
  const args = {
    card_id: checked.card_id,
    profile_id: checked.profile_id,
    taskbook_path: checked.taskbook_path,
    workdir: checked.workdir,
    write_scope: checked.write_scope || "workspace-write",
  };
  for (const key of ["model", "effort", "soft_time_limit_minutes"]) if (checked[key] !== undefined) args[key] = checked[key];
  const argsFile = path.join(checked.workdir, `.smart-agent-dispatch-${checked.card_id}.json`);
  fs.writeFileSync(argsFile, `${JSON.stringify(args, null, 2)}\n`, "utf8");
  let result;
  try {
    result = spawnSync(PYTHON, ["-X", "utf8", MCP_CALL, "launch_card", argsFile], { cwd: checked.workdir, encoding: "utf8", timeout: 570_000, windowsHide: true, maxBuffer: 4 * 1024 * 1024 });
  } finally {
    try { fs.rmSync(argsFile, { force: true }); } catch {}
  }
  const stdout = String(result?.stdout || "").trim();
  const stderr = String(result?.stderr || "").trim();
  let response = null;
  try { response = stdout ? JSON.parse(stdout.split(/\r?\n/).filter(Boolean).at(-1)) : null; } catch (error) { response = { parseError: String(error) }; }
  if (isMiniMax && result && result.status === 0 && !response?.error && !response?.result?.isError) {
    budget.value.minimaxCount += 1;
    saveBudget(budget.file, budget.value);
  }
  const receipt = redact({
    schema: "smart-agent-dispatch-receipt-v1",
    startedAt,
    endedAt: new Date().toISOString(),
    cardId: checked.card_id,
    profileId: checked.profile_id,
    modelRequested: checked.model || checked.profile.model,
    modelExpected: checked.expectedModel,
    effort: checked.effort || checked.profile.reasoning_effort || null,
    cli: checked.profile.cli,
    taskbookPath: checked.taskbook_path,
    workdir: checked.workdir,
    writeScope: args.write_scope,
    budget: isMiniMax ? { windowStartedAt: budget.value.windowStartedAt, minimaxCount: budget.value.minimaxCount, max: Number(process.env.SMART_AGENT_MINIMAX_MAX_CARDS || 10) } : null,
    processExit: result?.status ?? null,
    signal: result?.signal ?? null,
    response,
    stdout: stdout.slice(-12000),
    stderr: stderr.slice(-12000),
    ok: result?.status === 0 && !response?.error && !response?.result?.isError,
  });
  const out = receiptPath ? path.resolve(receiptPath) : path.join(checked.workdir, "dispatch-receipt.json");
  ensureDirectory(path.dirname(out));
  fs.writeFileSync(out, `${JSON.stringify(receipt, null, 2)}\n`, "utf8");
  return { ...receipt, receiptPath: out };
}

if (import.meta.url === `file://${process.argv[1]?.replaceAll("\\", "/")}`) {
  try {
    const file = process.argv[2];
    if (!file) throw new Error("用法: node src/dispatch.mjs <request.json>");
    const request = JSON.parse(fs.readFileSync(path.resolve(file), "utf8"));
    console.log(JSON.stringify(dispatchCard(request), null, 2));
  } catch (error) {
    console.error(`dispatch failed: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 2;
  }
}
