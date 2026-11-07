import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { ensureDirectory, defaultRunRoot } from "./paths.mjs";
import { loadAttachments } from "./attachments.mjs";
import { createBaseSession, latestAssistantError, toolRegistry } from "./pi-runtime.mjs";
import { promptWithTimeout } from "../core/prompt-lifecycle.mjs";
import { loadPi } from "./pi-runtime.mjs";
import { RUNTIME_LIMITS } from "./runtime-policy.mjs";

const digest = (value) => crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex").slice(0, 16);

function cleanEvent(event) {
  return JSON.parse(JSON.stringify(event, (key, value) => ["apiKey", "authorization", "headers", "token", "secret"].includes(key) ? "[REDACTED]" : value));
}

export async function runTraditional({ goal, workspace, provider, attachments = [], runRoot = defaultRunRoot(), timeoutMs = RUNTIME_LIMITS.promptTimeoutMs, promptOptions = undefined }) {
  const runId = `traditional-${new Date().toISOString().replaceAll(":", "-")}`;
  const runDir = ensureDirectory(path.join(runRoot, runId));
  const agentDir = ensureDirectory(path.join(runDir, "agent"));
  const startedAt = new Date().toISOString();
  const config = {
    schema: "smart-agent-run-v1",
    runId,
    mode: "traditional",
    goal,
    workspace,
    startedAt,
    provider: { type: provider.type, baseUrl: provider.baseUrl, model: provider.model, input: provider.input },
    plugins: { subAgents: false },
    toolRegistry: toolRegistry(workspace),
    attachments: attachments.map((file) => path.resolve(workspace, file)),
    sourceHash: digest({ goal, workspace, tools: toolRegistry(workspace), provider: provider.model }),
  };
  fs.writeFileSync(path.join(runDir, "run-config.json"), JSON.stringify(config, null, 2), "utf8");
  const record = { runId, mode: "traditional", goal, startedAt, events: [], attempts: [], status: "running" };
  let session;
  try {
    const { fileProcessor } = await loadPi();
    const attachment = await loadAttachments(attachments, workspace, fileProcessor.processFileArguments);
    session = await createBaseSession({
      cwd: workspace,
      agentDir,
      provider,
      systemPrompt: "You are Smart Agent in traditional mode. Use the normal pi Agent Loop and the available workspace tools. Complete the user's task directly. Do not require a Manager design or any Sub Agents plugin. Verify concrete results before reporting success; report failures honestly.",
    });
    session.subscribe((event) => {
      if (["message_end", "turn_end", "agent_end"].includes(event.type)) record.events.push(cleanEvent(event));
    });
    const prompt = `${goal}\n\n${attachment.text}`;
    record.attempts.push(await promptWithTimeout(session, prompt, timeoutMs, "traditional prompt", RUNTIME_LIMITS.abortTimeoutMs, attachment.images.length ? { images: attachment.images } : promptOptions));
    const modelError = latestAssistantError(record.events);
    if (modelError) throw new Error(modelError);
    record.status = record.attempts.at(-1).error ? "failed" : "completed";
    if (record.attempts.at(-1).abortError) throw new Error(record.attempts.at(-1).abortError);
  } catch (error) {
    record.status = "failed";
    record.error = error instanceof Error ? error.message : String(error);
  } finally {
    if (session) await session.dispose();
    record.endedAt = new Date().toISOString();
    fs.writeFileSync(path.join(runDir, "record.json"), JSON.stringify(record, null, 2), "utf8");
    const summary = {
      schema: "smart-agent-summary-v1",
      runId,
      runDir,
      mode: "traditional",
      goal,
      status: record.status,
      subAgentsUsed: false,
      baseTools: toolRegistry(workspace).map((tool) => tool.name),
      evidenceComplete: fs.existsSync(path.join(runDir, "run-config.json")) && fs.existsSync(path.join(runDir, "record.json")),
      error: record.error || null,
    };
    fs.writeFileSync(path.join(runDir, "summary.json"), JSON.stringify(summary, null, 2), "utf8");
  }
  const summary = JSON.parse(fs.readFileSync(path.join(runDir, "summary.json"), "utf8"));
  if (summary.status !== "completed") throw new Error(`${summary.error || "Traditional run failed"}\nRun: ${runDir}`);
  return summary;
}
