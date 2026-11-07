import crypto from "node:crypto";
import path from "node:path";
import { defaultSpiralRoot } from "./paths.mjs";
import { runSmart } from "./smart-run.mjs";
import { SpiralStore, sanitizeSpiralValue } from "../core/spiral-store.mjs";

const makeJobId = () => `job-${new Date().toISOString().replaceAll(":", "-")}-${crypto.randomUUID().slice(0, 8)}`;

function storeFor(root = defaultSpiralRoot()) {
  return new SpiralStore(root);
}

export async function startCruise({ goal, workspace, provider, attachments = [], seedManifest, runRoot, spiralRoot = defaultSpiralRoot(), maxWorkerTurns, maxManagerAttempts, timeoutMs, explorationId = null, plugins = {}, jobId = makeJobId(), systemPrompt = "", controlPlane = "smart" }) {
  const store = storeFor(spiralRoot);
  const safeProvider = sanitizeSpiralValue(provider);
  store.saveCheckpoint(jobId, {
    status: "queued",
    jobId,
    goal,
    workspace: path.resolve(workspace),
    provider: safeProvider,
    attachments,
    seedManifest,
    createdAt: new Date().toISOString(),
    wakeSource: null,
    explorationId,
  });
  try {
    const summary = await runSmart({ goal, workspace, provider, attachments, seedManifest, runRoot, spiralRoot, jobId, explorationId, maxWorkerTurns, maxManagerAttempts, timeoutMs, plugins, systemPrompt, controlPlane });
    return { jobId, status: "completed", summary };
  } catch (error) {
    const current = new SpiralStore(spiralRoot).getCheckpoint(jobId) || {};
    const controlledStop = ["paused", "stopped"].includes(current.status);
    store.saveCheckpoint(jobId, { ...current, status: controlledStop ? current.status : "failed", jobId, error: error instanceof Error ? error.message : String(error), failedAt: controlledStop ? current.failedAt : new Date().toISOString() });
    throw error;
  }
}

export function cruiseStatus(jobId, spiralRoot = defaultSpiralRoot()) {
  const store = storeFor(spiralRoot);
  const checkpoint = store.getCheckpoint(jobId);
  if (!checkpoint) throw new Error(`Cruise job 不存在: ${jobId}`);
  return checkpoint;
}

export function pauseCruise(jobId, spiralRoot = defaultSpiralRoot()) {
  const store = storeFor(spiralRoot);
  const checkpoint = store.getCheckpoint(jobId);
  if (!checkpoint) throw new Error(`Cruise job 不存在: ${jobId}`);
  if (["completed", "failed", "stopped"].includes(checkpoint.status)) return checkpoint;
  const paused = { ...checkpoint, status: "paused", pausedAt: new Date().toISOString() };
  store.saveCheckpoint(jobId, paused);
  return paused;
}

export function stopCruise(jobId, spiralRoot = defaultSpiralRoot()) {
  const store = storeFor(spiralRoot);
  const checkpoint = store.getCheckpoint(jobId);
  if (!checkpoint) throw new Error(`Cruise job 不存在: ${jobId}`);
  const stopped = { ...checkpoint, status: "stopped", stoppedAt: new Date().toISOString(), wakeSource: null };
  store.saveCheckpoint(jobId, stopped);
  return stopped;
}

export async function resumeCruise(jobId, { spiralRoot = defaultSpiralRoot(), runRoot, maxWorkerTurns, maxManagerAttempts, timeoutMs, plugins = {}, systemPrompt = "", controlPlane = "smart", wakeSource = "manual" } = {}) {
  const store = storeFor(spiralRoot);
  const checkpoint = store.getCheckpoint(jobId);
  if (!checkpoint) throw new Error(`Cruise job 不存在: ${jobId}`);
  if (checkpoint.status === "completed") return { jobId, status: "completed", summary: null, resumed: false };
  if (checkpoint.status === "stopped") throw new Error(`Cruise 已明确停止，禁止自动 wake/resume: ${jobId}`);
  if (!checkpoint.goal || !checkpoint.workspace || !checkpoint.provider) throw new Error(`Cruise job 缺少恢复所需的目标、工作区或 pi Provider 引用: ${jobId}`);
  store.saveCheckpoint(jobId, { ...checkpoint, status: "resuming", resumedAt: new Date().toISOString(), wakeSource: { type: wakeSource, at: new Date().toISOString() } });
  try {
    const summary = await runSmart({
      goal: checkpoint.goal,
      workspace: checkpoint.workspace,
      provider: checkpoint.provider,
      attachments: checkpoint.attachments || [],
      seedManifest: checkpoint.seedManifest,
      explorationId: checkpoint.explorationId || null,
      runRoot,
      spiralRoot,
      jobId,
      maxWorkerTurns,
      maxManagerAttempts,
      timeoutMs,
      plugins,
      systemPrompt,
      controlPlane,
      runId: checkpoint.runId || null,
      resume: true,
    });
    return { jobId, status: "completed", summary, resumed: true };
  } catch (error) {
    const current = new SpiralStore(spiralRoot).getCheckpoint(jobId) || checkpoint;
    const controlledStop = ["paused", "stopped"].includes(current.status);
    store.saveCheckpoint(jobId, { ...current, status: controlledStop ? current.status : "failed", error: error instanceof Error ? error.message : String(error), failedAt: controlledStop ? current.failedAt : new Date().toISOString() });
    throw error;
  }
}
