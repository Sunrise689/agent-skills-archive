import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { performance } from "node:perf_hooks";
import { loadConfig, validateProvider } from "../src/config.mjs";
import { runTraditional } from "../src/run.mjs";
import { runSmart } from "../src/smart-run.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const suite = JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "comparison-suite.json"), "utf8"));
const config = loadConfig();
const providerErrors = validateProvider(config);
if (providerErrors.length) throw new Error(providerErrors.join("；"));
const outputArg = process.argv.indexOf("--output");
const outputRoot = outputArg >= 0 ? path.resolve(process.argv[outputArg + 1]) : path.join(ROOT, "runs", `product-comparison-${new Date().toISOString().replaceAll(":", "-")}`);
fs.mkdirSync(outputRoot, { recursive: true });
fs.copyFileSync(path.join(ROOT, "tests", "comparison-suite.json"), path.join(outputRoot, "frozen-suite.json"));

function usageFrom(record) {
  const usage = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, totalTokens: 0 };
  for (const event of record.events || []) {
    if (event.type !== "message_end" || event.message?.role !== "assistant") continue;
    for (const key of Object.keys(usage)) usage[key] += Number(event.message.usage?.[key] || 0);
  }
  return usage;
}

function latestRun(runRoot) {
  if (!fs.existsSync(runRoot)) return {};
  const candidates = fs.readdirSync(runRoot).map((id) => path.join(runRoot, id)).filter((dir) => fs.existsSync(path.join(dir, "summary.json")));
  const runDir = candidates.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
  if (!runDir) return {};
  return {
    runDir,
    summary: JSON.parse(fs.readFileSync(path.join(runDir, "summary.json"), "utf8")),
    record: JSON.parse(fs.readFileSync(path.join(runDir, "record.json"), "utf8")),
  };
}

async function runArm(task, arm) {
  const workspace = path.join(outputRoot, task.id, arm, "workspace");
  const runRoot = path.join(outputRoot, task.id, arm, "runs");
  fs.mkdirSync(workspace, { recursive: true });
  for (const [name, content] of Object.entries(task.inputs)) fs.writeFileSync(path.join(workspace, name), content, "utf8");
  const started = performance.now();
  let thrown = null;
  try {
    if (arm === "traditional") {
      await runTraditional({ goal: task.goal, workspace, provider: config.provider, runRoot, timeoutMs: suite.conditions.timeoutMs });
    } else {
      await runSmart({ goal: task.goal, workspace, provider: config.provider, runRoot, timeoutMs: suite.conditions.timeoutMs, maxWorkerTurns: suite.conditions.maxWorkerTurns, seedManifest: path.join(ROOT, "extensions", "loop-seeds", "extension.json"), plugins: {} });
    }
  } catch (error) {
    thrown = error instanceof Error ? error.message : String(error);
  }
  const wallMs = Math.round(performance.now() - started);
  const { runDir, summary, record } = latestRun(runRoot);
  const artifacts = Object.fromEntries(Object.entries(task.expectedFiles).map(([name, expected]) => {
    const file = path.join(workspace, name);
    const actual = fs.existsSync(file) ? fs.readFileSync(file, "utf8") : null;
    return [name, { expected, actual, passed: actual === expected }];
  }));
  const artifactsPassed = Object.values(artifacts).every((item) => item.passed);
  return {
    arm,
    runDir: runDir || null,
    status: summary?.status || "failed",
    wallMs,
    success: summary?.status === "completed" && artifactsPassed,
    artifacts,
    toolResults: (record?.events || []).filter((event) => event.type === "message_end" && event.message?.role === "toolResult").length,
    usage: usageFrom(record),
    designFirst: summary?.designFirst ?? null,
    designExecutionMatched: summary?.designExecutionMatched ?? null,
    error: thrown || summary?.error || null,
  };
}

const report = { schema: "smart-agent-comparison-report-v1", createdAt: new Date().toISOString(), provider: { type: config.provider.type, baseUrl: config.provider.baseUrl, model: config.provider.model }, conditions: suite.conditions, tasks: [] };
for (const task of suite.tasks) {
  console.log(`Comparison ${task.id}: traditional`);
  const traditional = await runArm(task, "traditional");
  console.log(`Comparison ${task.id}: smart`);
  const smart = await runArm(task, "smart");
  report.tasks.push({ id: task.id, traditional, smart, bothSucceeded: traditional.success && smart.success, smartOverheadMs: smart.wallMs - traditional.wallMs });
  fs.writeFileSync(path.join(outputRoot, "report.json"), JSON.stringify(report, null, 2), "utf8");
}
report.totals = {
  traditionalSucceeded: report.tasks.filter((task) => task.traditional.success).length,
  smartSucceeded: report.tasks.filter((task) => task.smart.success).length,
  bothSucceeded: report.tasks.filter((task) => task.bothSucceeded).length,
  taskCount: report.tasks.length,
};
report.interpretation = "Single-run engineering smoke only. No significance, generalization, or model-superiority conclusion.";
fs.writeFileSync(path.join(outputRoot, "report.json"), JSON.stringify(report, null, 2), "utf8");
console.log(JSON.stringify({ outputRoot, totals: report.totals }, null, 2));
