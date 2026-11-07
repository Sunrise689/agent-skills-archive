import path from "node:path";
import { createBaseSession, latestAssistantError, toolRegistry } from "./pi-runtime.mjs";
import { promptWithTimeout } from "../core/prompt-lifecycle.mjs";
import { GraphOrchestrator } from "../core/orchestration.mjs";
import { ensureDirectory } from "./paths.mjs";
import { RUNTIME_LIMITS } from "./runtime-policy.mjs";

const safe = (value) => JSON.parse(JSON.stringify(value, (key, item) => ["apiKey", "authorization", "headers", "token", "secret"].includes(key) ? "[REDACTED]" : item));

export async function runPiNode({ goal, workspace, provider, runDir, nodeId = "node", attachment = { text: "", images: [] }, timeoutMs = RUNTIME_LIMITS.promptTimeoutMs, tools = undefined, systemPrompt = "" }) {
  const events = [];
  const agentDir = ensureDirectory(path.join(runDir, "agent", nodeId));
  let session;
  try {
    session = await createBaseSession({ cwd: workspace, agentDir, provider, tools: tools || toolRegistry(workspace).map((tool) => tool.name), systemPrompt: systemPrompt || `You are a pi Worker executing one node. Goal: ${goal}. Work only on this node, use pi-native tools, verify the result, and report the concrete receipt.` });
    session.subscribe((event) => {
      if (["message_end", "turn_end", "agent_end"].includes(event.type)) events.push(safe(event));
    });
    const prompt = `Node: ${nodeId}\nGoal: ${goal}\n${attachment.text}`;
    const result = await promptWithTimeout(session, prompt, timeoutMs, `pi node ${nodeId}`, RUNTIME_LIMITS.abortTimeoutMs, attachment.images.length ? { images: attachment.images } : undefined);
    const modelError = latestAssistantError(events);
    if (modelError || result.error || result.abortError) throw new Error(modelError || result.error || result.abortError);
    const toolTrace = events.filter((event) => event.type === "message_end" && event.message?.role === "toolResult").map((event) => ({ tool: event.message.toolName, isError: Boolean(event.message.isError), details: event.message.details || null }));
    const text = events.filter((event) => event.type === "message_end" && event.message?.role === "assistant").flatMap((event) => event.message.content || []).filter((item) => item.type === "text").map((item) => item.text).join("\n");
    return { ok: true, nodeId, text, toolTrace, events, result };
  } catch (error) {
    return { ok: false, nodeId, error: error instanceof Error ? error.message : String(error), events, toolTrace: [] };
  } finally {
    if (session) await session.dispose();
  }
}

export async function runInstantNode({ goal, workspace, provider, runDir, attachment, timeoutMs }) {
  return runPiNode({ goal, workspace, provider, runDir, nodeId: "instant", attachment, timeoutMs, systemPrompt: `You are Smart Agent's Instant executor. This is a low-risk single task. Use the normal pi-native Agent Loop and tools, avoid unnecessary Manager/Worker ceremony, complete the goal, and report the concrete result. Goal: ${goal}` });
}

export async function runGraph({ design, goal, workspace, provider, runDir, attachment, timeoutMs, onEvent, checkpoint = null, beforeNode = null }) {
  const orchestrator = checkpoint?.orchestration ? GraphOrchestrator.restore(checkpoint.orchestration) : new GraphOrchestrator(design);
  return orchestrator.run(async (node) => {
    if (beforeNode) await beforeNode(node);
    const nodeGoal = node.goal || `${goal}\nNode step: ${node.step || node.kind}\nAcceptance: ${JSON.stringify(node.acceptance)}`;
    const result = await runPiNode({ goal: nodeGoal, workspace, provider, runDir, nodeId: node.id, attachment, timeoutMs, systemPrompt: `You are a pi Worker node. Execute only node ${node.id}. The Manager graph and dependencies are authoritative. Do not claim completion without tool evidence. Node: ${JSON.stringify(node)}` });
    if (beforeNode) await beforeNode(node);
    return { ...result, consistent: node.kind === "join" || node.kind === "merge" ? result.ok : undefined };
  }, { onEvent });
}
