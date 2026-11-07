import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath, pathToFileURL } from "node:url";
import { ensureDirectory, defaultRunRoot, defaultSpiralRoot } from "./paths.mjs";
import { SpiralStore, sanitizeSpiralValue } from "../core/spiral-store.mjs";
import { loadAttachments } from "./attachments.mjs";
import { createBaseSession, latestAssistantError, loadPi, outputTokenBudget, toolRegistry, piCapabilityCatalog, providerForModelSelection } from "./pi-runtime.mjs";
import { loadExtensionManifest, digest as extensionDigest } from "../core/extension-contract.mjs";
import { extractSeedIds, methodContractErrors } from "../core/method-contract.mjs";
import { promptWithTimeout } from "../core/prompt-lifecycle.mjs";
import { RUNTIME_LIMITS } from "./runtime-policy.mjs";
import { graphErrors } from "../core/orchestration.mjs";
import { runInstantNode, runGraph } from "./executors.mjs";
import { explorationSummary } from "./exploration.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const EXTENSION = path.join(ROOT, "core", "product-control.ts");
const STEP_TOOLS = { inspect: ["read", "ls", "grep", "find"], patch: ["write", "edit"], verify: ["bash", "read"], review: ["review_work"], revise: ["write", "edit"], submit: ["finish_task"] };
const digest = (value) => crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex").slice(0, 16);

function traceMatchesDesign(toolTrace, steps) {
  let cursor = 0;
  let phaseHasEvidence = false;
  for (const item of toolTrace) {
    if (item.tool === "dispatch_card") continue;
    if (item.isError || (item.tool === "review_work" && item.details?.reviewed !== true) || (item.tool === "finish_task" && item.details?.finished !== true)) continue;
    const currentTools = STEP_TOOLS[steps[cursor]] || [];
    if (currentTools.includes(item.tool)) {
      phaseHasEvidence = true;
      continue;
    }
    const next = steps.findIndex((step, index) => index > cursor && STEP_TOOLS[step]?.includes(item.tool));
    if (!phaseHasEvidence || next !== cursor + 1) return false;
    cursor = next;
    phaseHasEvidence = true;
  }
  return cursor === steps.length - 1 && phaseHasEvidence && STEP_TOOLS[steps.at(-1)]?.includes(toolTrace.filter((item) => !item.isError).at(-1)?.tool);
}
const clean = (value) => JSON.parse(JSON.stringify(value, (key, item) => ["apiKey", "authorization", "headers", "token", "secret"].includes(key) ? "[REDACTED]" : item));

function throwIfCruisePaused(jobId, spiralRoot) {
  if (!jobId) return;
  const checkpoint = new SpiralStore(spiralRoot).getCheckpoint(jobId);
  if (["paused", "stopped"].includes(checkpoint?.status)) throw new Error(`Cruise ${checkpoint.status} by user`);
}

function saveCruiseCheckpointSafe(spiralRoot, jobId, next) {
  if (!jobId) return null;
  const store = new SpiralStore(spiralRoot);
  const current = store.getCheckpoint(jobId) || {};
  const controlled = ["paused", "stopped"].includes(current.status);
  const merged = controlled ? { ...current, ...next, status: current.status, wakeSource: current.wakeSource || next.wakeSource || null } : { ...current, ...next };
  store.saveCheckpoint(jobId, merged);
  return merged;
}

function classifyFailure(error, { record = {}, externalCheckpoint = null } = {}) {
  if (externalCheckpoint?.status === "paused" || externalCheckpoint?.status === "stopped") return "controlled-stop";
  const text = String(error || "").toLowerCase();
  if (/quota|rate.?limit|credit|429|usage|limit exceeded|额度/.test(text)) return "quota";
  if (/invalid design|manager produced|schema|workflow|graph stalled|design failed/.test(text)) return "design";
  if (/finish_task|evidence|verify|report|artifact|receipt|产物|证据/.test(text)) return "evidence-insufficient";
  if (/tool|permission|blocked|not available|command|enoent|spawn/.test(text)) return "tool";
  if (/timeout|abort|network|http|gateway|incompleteread|connection|provider/.test(text)) return "provider-cli";
  if (/model|context|token|assistant/.test(text)) return "model";
  if (record.workerAttempts?.some((item) => item.timedOut)) return "environment";
  return "environment";
}

function evidenceLayers(runDir, designFile, recordFile, record) {
  const toolTrace = Array.isArray(record.toolTrace) ? record.toolTrace : [];
  return {
    execution: { runConfig: fs.existsSync(path.join(runDir, "run-config.json")), record: fs.existsSync(recordFile), endedAt: record.endedAt || null },
    tool: { count: toolTrace.length, successful: toolTrace.filter((item) => !item.isError).length, failed: toolTrace.filter((item) => item.isError).length },
    artifact: { design: fs.existsSync(designFile), receipts: toolTrace.filter((item) => item.details || item.tool === "dispatch_card").length, dispatchReceipts: toolTrace.filter((item) => item.tool === "dispatch_card").length },
    verification: { designExecutionMatched: record.designExecutionMatched === true, reviewCalled: record.reviewCalled === true, finishReceipt: toolTrace.some((item) => item.tool === "finish_task" && !item.isError && item.details?.finished === true) },
    report: { status: record.status || null, failureClass: record.failureClass || null, error: record.error || null },
  };
}

async function loadAgentsLauncher() {
  const override = process.env.SMART_AGENT_SUB_AGENTS_MODULE;
  if (override) {
    const specifier = fs.existsSync(override) ? pathToFileURL(path.resolve(override)).href : override;
    return import(specifier);
  }
  try {
    return await import("sub-agents-launcher");
  } catch (error) {
    const localModule = path.join(ROOT, "packages", "sub-agents", "src", "index.mjs");
    if (error?.code === "ERR_MODULE_NOT_FOUND" && fs.existsSync(localModule)) return import(pathToFileURL(localModule).href);
    if (error?.code === "ERR_MODULE_NOT_FOUND") throw new Error("Sub Agents 已启用，但未安装 sub-agents-launcher；请先安装独立插件或设置 SMART_AGENT_SUB_AGENTS_MODULE");
    throw error;
  }
}

function validDesign(design, model, seedIds, capabilities = { models: [] }) {
  if (!design) return false;
  const available = new Set((capabilities.models || []).flatMap((item) => [item.ref, item.id]));
  if (!available.size) available.add(model);
  const validModel = (selection) => {
    if (String(selection || "").includes("/")) return (capabilities.models || []).some((item) => item.ref === selection);
    if (capabilities.native) return (capabilities.models || []).some((item) => item.id === selection && (!capabilities.defaultProvider || item.provider === capabilities.defaultProvider));
    return available.has(selection);
  };
  const validEffort = (effort) => effort === undefined || ["off", "minimal", "low", "medium", "high", "xhigh"].includes(effort);
  if (!validModel(design.worker_model) || (design.reviewer_model !== "none" && !validModel(design.reviewer_model)) || !validEffort(design.worker_effort) || !validEffort(design.reviewer_effort)) return false;
  if (!Array.isArray(design.steps) || design.steps[0] !== "inspect" || design.steps.at(-1) !== "submit" || !design.steps.includes("verify")) return false;
  if (!design.steps.includes("patch") && !design.steps.includes("revise")) return false;
  if (design.steps.includes("review") !== (design.reviewer_model !== "none")) return false;
  if (!["instant", "vertical", "horizontal", "hybrid"].includes(design.task_type)) return false;
  if (graphErrors(design).length) return false;
  if (!design.risk || !design.stop_rule || !Array.isArray(design.acceptance) || !design.acceptance.length || !Array.isArray(design.tool_plan)) return false;
  if (design.subagent_request && !["codex", "pi", "opencode"].includes(design.subagent_request.agent)) return false;
  return methodContractErrors(design, seedIds).length === 0;
}

export async function runSmart({ goal, workspace, provider, attachments = [], seedManifest, runRoot = defaultRunRoot(), spiralRoot = defaultSpiralRoot(), jobId = null, runId: requestedRunId = null, resume = false, explorationId = null, maxWorkerTurns = RUNTIME_LIMITS.maxWorkerTurns, maxManagerAttempts = RUNTIME_LIMITS.maxManagerAttempts, timeoutMs = RUNTIME_LIMITS.promptTimeoutMs, plugins = {}, systemPrompt = "", controlPlane = "smart" }) {
  const extension = loadExtensionManifest(ROOT, seedManifest);
  const spiral = new SpiralStore(spiralRoot);
  const catalog = fs.readFileSync(extension.entrypoint, "utf8");
  const seedIds = extractSeedIds(catalog);
  const previousCheckpoint = jobId ? spiral.getCheckpoint(jobId) : null;
  const runId = requestedRunId || previousCheckpoint?.runId || `smart-${new Date().toISOString().replaceAll(":", "-")}`;
  const runDir = ensureDirectory(path.join(runRoot, runId));
  const priorRecordFile = path.join(runDir, "record.json");
  const priorDesignFile = path.join(runDir, "design.json");
  const startedAt = new Date().toISOString();
  const providerRef = sanitizeSpiralValue({
    type: provider.type,
    piProvider: provider.piProvider,
    providerName: provider.providerName,
    model: provider.model,
    thinkingLevel: provider.thinkingLevel,
    input: provider.input,
    baseUrl: provider.baseUrl,
    apiKeyEnv: provider.apiKeyEnv,
    contextWindow: provider.contextWindow,
    maxTokens: provider.maxTokens,
  });
  spiral.startRun(runId, { mode: "smart", goal, workspace, provider: providerRef, startedAt, jobId });
  if (jobId && !resume) spiral.saveCheckpoint(jobId, { ...(previousCheckpoint || {}), status: "designing", runId, goal, workspace, stage: "manager", provider: providerRef, attachments, seedManifest });
  const designFile = path.join(runDir, "design.json");
  const recordFile = path.join(runDir, "record.json");
  const initial = { steps: ["inspect", "patch", "verify", "submit"], worker_model: provider.model, reviewer_model: "none", rationale: "initial minimal Loop", method_refs: [], method_composition: [], integration_requests: [] };
  const priorStrategies = spiral.listStrategies().map((item) => ({ strategyId: item.strategyId, current: item.current, currentVersion: item.current ? item.versions[item.current] : null }));
  const priorFeedback = spiral.state.feedback.slice(-8).map((item) => ({ runId: item.runId, feedback: item.feedback, at: item.at }));
  const runConfig = {
    schema: "smart-agent-run-v1", runId, mode: "smart", goal, workspace,
    createdAt: new Date().toISOString(),
    provider: providerRef,
    toolRegistry: [...toolRegistry(workspace), ...(controlPlane.startsWith("s-card") ? [{ name: "dispatch_card", capability: "card-dispatch", workspace, requiresDesign: false, evidence: ["receipt", "exit", "report"] }] : [])],
    extension: { id: extension.id, version: extension.version, manifestHash: extension.manifest_hash, catalogHash: extensionDigest(catalog), seedIds },
    plugins: { subAgents: plugins["sub-agents"]?.enabled === true, required: false },
    attachments: attachments.map((file) => path.resolve(workspace, file)),
    parentHash: digest(initial),
  };
  fs.writeFileSync(path.join(runDir, "run-config.json"), JSON.stringify(runConfig, null, 2), "utf8");
  const record = resume && fs.existsSync(priorRecordFile) ? JSON.parse(fs.readFileSync(priorRecordFile, "utf8")) : { runId, mode: "smart", goal, status: "designing", managerAttempts: [], workerAttempts: [], events: [], design: null };
  record.runId = runId;
  record.goal = goal;
  record.mode = controlPlane;
  record.resume = Boolean(resume);
  record.events ||= [];
  record.managerAttempts ||= [];
  record.workerAttempts ||= [];
  const exploration = explorationId ? explorationSummary(explorationId) : null;
  const save = () => fs.writeFileSync(recordFile, JSON.stringify(record, null, 2), "utf8");
  let manager;
  let worker;
  try {
    const { fileProcessor } = await loadPi();
    const capabilities = await piCapabilityCatalog(provider);
    runConfig.capabilities = capabilities;
    fs.writeFileSync(path.join(runDir, "run-config.json"), JSON.stringify(runConfig, null, 2), "utf8");
    const attachment = await loadAttachments(attachments, workspace, fileProcessor.processFileArguments);
    const env = {
      SMART_AGENT_MODEL: provider.model,
      SMART_AGENT_GOAL: goal,
      SMART_AGENT_WORKSPACE: workspace,
      SMART_AGENT_PROVIDER_URL: provider.baseUrl || "",
      SMART_AGENT_API_KEY_ENV: provider.apiKeyEnv || "",
      SMART_AGENT_PROVIDER_JSON: JSON.stringify(sanitizeSpiralValue(provider)),
      SMART_AGENT_CAPABILITIES_JSON: JSON.stringify(capabilities),
      SMART_AGENT_SEED_IDS: JSON.stringify(seedIds),
      SMART_AGENT_MAX_OUTPUT_TOKENS: String(outputTokenBudget(provider)),
      SMART_AGENT_REVIEWER_TIMEOUT_MS: String(RUNTIME_LIMITS.reviewerTimeoutMs),
      SMART_AGENT_CONTROL_PLANE: controlPlane,
      SMART_AGENT_EXPLORATION_JSON: JSON.stringify(exploration || null),
    };
    Object.assign(process.env, env);
    const catalogIndex = catalog.split(/\r?\n/).filter((line) => /^##\s+Seed/.test(line) || /^- (适用场景|步骤骨架)：/.test(line)).join("\n");
    const availableTools = `read, bash, edit, write, grep, find, ls${controlPlane.startsWith("s-card") ? ", dispatch_card" : ""}`;
    const guidance = `You are the Manager, not the implementer. Design a Workflow/Loop for this goal: ${goal}\nWorkspace: ${workspace}\nAttachments: ${attachment.text}\nExploration summary (if any): ${JSON.stringify(exploration)}\nPrior promoted method versions (reuse only when justified by the current task): ${JSON.stringify(priorStrategies)}\nRecent public execution feedback (no hidden scores): ${JSON.stringify(priorFeedback)}\nAvailable pi-native models (canonical provider/model references): ${JSON.stringify(capabilities.models)}. Default model is ${provider.model}; for native pi you may choose any listed worker_model/reviewer_model and worker_effort/reviewer_effort when the task justifies it. Legacy mode permits only the configured model. Available pi-native tools: ${availableTools}. Phases: inspect, patch, verify, review, revise, submit. inspect first, submit last, verify and patch/revise required; review requires a reviewer_model other than none. tool_plan must contain only available pi-native tools. dispatch_card is an S-card control-plane action and is optional; it does not replace verification and its receipt must be captured. Use zero or more catalog methods; method_refs may be [] when the standard Loop is sufficient. Set strategy_id and loop_policy when a reusable method or explicit recovery policy is justified; do not invent a strategy change merely for variety. Optional method_composition records order/role/dependencies. Do not require Sub Agents: plugin enabled=${runConfig.plugins.subAgents}; core has no dependency on it. Only if plugin enabled=true and a Codex/pi/OpenCode subtask is genuinely useful, optionally include subagent_request={agent,goal,rationale}; otherwise omit it. For low-risk mechanical tasks use the minimal inspect, patch, verify, submit Loop with reviewer_model=none, method_refs=[] and method_composition=[]; omit review and revise unless a concrete risk justifies them. Include every acceptance criterion and rationale needed for the task; do not truncate required design fields. Do not quote or restate the catalog; emit the submit_design call immediately with every required field.\nCatalog index ${extension.id}@${extension.version}:\n${catalogIndex}`;
    let design = null;
    if (resume && fs.existsSync(priorDesignFile)) {
      try {
        const candidate = JSON.parse(fs.readFileSync(priorDesignFile, "utf8"));
        if (validDesign(candidate, provider.model, seedIds, capabilities)) design = candidate;
      } catch {}
    }
    for (let attempt = 1; attempt <= maxManagerAttempts && !design; attempt += 1) {
      if (fs.existsSync(designFile)) fs.unlinkSync(designFile);
      Object.assign(process.env, { SMART_AGENT_PHASE: "design", SMART_AGENT_DESIGN_FILE: designFile });
      manager = await createBaseSession({
        cwd: workspace,
        agentDir: ensureDirectory(path.join(runDir, "agent", `manager-${attempt}`)),
        provider,
        tools: ["submit_design"],
        additionalExtensionPaths: [EXTENSION],
        systemPrompt: `${systemPrompt ? `${systemPrompt}\n\n` : ""}You are the project Manager and Agent architect. Do not implement the task. Call submit_design with a complete, valid design.`,
      });
      const events = [];
      manager.subscribe((event) => { if (["message_end", "turn_end", "agent_end"].includes(event.type)) { events.push(clean(event)); record.events.push({ role: "manager", attempt, ...clean(event) }); } });
      const prompt = attempt === 1 ? guidance : `Call submit_design now with every required field. Goal: ${goal}. Choose worker_model and reviewer_model only from ${JSON.stringify(capabilities.models.map((item) => item.ref))} (legacy configured model: ${provider.model}); use reviewer_model=none when no review is needed. Inspect first, submit last, verify and patch/revise required. Include every acceptance criterion needed; do not truncate required fields. Prefer reviewer_model=none, method_refs=[] and method_composition=[] for low-risk tasks. Any method reference must use exact catalog IDs ${JSON.stringify(seedIds)}. Sub Agents plugin enabled=${runConfig.plugins.subAgents}; when it is false, omit subagent_request entirely and execute with the built-in Worker. No implementation.`;
      const result = await promptWithTimeout(manager, prompt, timeoutMs, `manager attempt ${attempt}`);
      record.managerAttempts.push({ attempt, ...result, designFileWritten: fs.existsSync(designFile), eventCount: events.length });
      const modelError = latestAssistantError(events);
      if (modelError) {
        record.managerAttempts.at(-1).modelError = modelError;
        throw new Error(modelError);
      }
      if (fs.existsSync(designFile)) {
        try {
          const candidate = JSON.parse(fs.readFileSync(designFile, "utf8"));
          if (!validDesign(candidate, provider.model, seedIds, capabilities)) {
            record.managerAttempts.at(-1).designError = "Design failed schema, model, phase or method contract validation";
          } else if (candidate.subagent_request && !runConfig.plugins.subAgents) {
            // A model may still request an optional integration despite the prompt.
            // Treat that as a recoverable design error, not as a task failure.
            record.managerAttempts.at(-1).designError = "Sub Agent requested while the optional plugin is disabled; omit subagent_request";
          } else {
            design = candidate;
          }
        } catch (error) {
          record.managerAttempts.at(-1).designError = error instanceof Error ? error.message : String(error);
        }
      } else {
        record.managerAttempts.at(-1).designError = "Manager did not write a design";
      }
      await manager.dispose(); manager = undefined;
    }
    if (!design) throw new Error(`Manager produced no valid design after ${maxManagerAttempts} recovery attempts`);
    design.parent_hash = runConfig.parentHash;
    design.hash = digest({ ...design, parent_hash: design.parent_hash });
    fs.writeFileSync(designFile, JSON.stringify(design, null, 2), "utf8");
    record.design = design;
    const workerProvider = providerForModelSelection(provider, design.worker_model, design.worker_effort);
    record.workerProvider = sanitizeSpiralValue({ model: workerProvider.model, piProvider: workerProvider.piProvider, thinkingLevel: workerProvider.thinkingLevel });
    const strategyId = String(design.strategy_id || "manager-loop");
    const currentStrategy = spiral.getStrategy(strategyId);
    const strategy = {
      strategyId,
      version: Number(currentStrategy?.version || 0) + 1,
      parentHash: currentStrategy?.hash || null,
      steps: design.steps,
      taskType: design.task_type,
      loopPolicy: design.loop_policy || null,
      methodRefs: design.method_refs || [],
      methodComposition: design.method_composition || [],
      modelPolicy: { workerModel: design.worker_model, workerEffort: design.worker_effort || null, reviewerModel: design.reviewer_model, reviewerEffort: design.reviewer_effort || null },
      rationale: design.rationale,
      source: "manager-design",
    };
    const sameAsPromoted = currentStrategy && JSON.stringify({ steps: currentStrategy.steps, taskType: currentStrategy.taskType, loopPolicy: currentStrategy.loopPolicy, methodRefs: currentStrategy.methodRefs, methodComposition: currentStrategy.methodComposition, modelPolicy: currentStrategy.modelPolicy || null }) === JSON.stringify({ steps: strategy.steps, taskType: strategy.taskType, loopPolicy: strategy.loopPolicy, methodRefs: strategy.methodRefs, methodComposition: strategy.methodComposition, modelPolicy: strategy.modelPolicy || null });
    if (sameAsPromoted) {
      record.strategy = { ...currentStrategy, reused: true, runId };
      record.strategyReuse = true;
    } else {
      const candidateEvent = spiral.candidate(strategy, runId);
      record.strategy = candidateEvent.strategy;
      record.strategyReuse = false;
    }
    record.status = "executing";
    saveCruiseCheckpointSafe(spiralRoot, jobId, { status: "executing", runId, goal, workspace, stage: "worker", strategy: record.strategy, provider: providerRef, attachments, seedManifest });
    save();
    if (design.subagent_request) {
      if (!runConfig.plugins.subAgents) throw new Error("Manager requested a Sub Agent while the optional plugin is disabled");
      const { AgentsLauncher } = await loadAgentsLauncher();
      const launcher = new AgentsLauncher();
      record.subagentReceipt = await launcher.run({ ...design.subagent_request, mode: "subagent", cwd: workspace });
      fs.writeFileSync(path.join(runDir, "subagent-receipt.json"), JSON.stringify(record.subagentReceipt, null, 2), "utf8");
      if (record.subagentReceipt.status !== "completed") throw new Error(`Sub Agent did not complete: ${record.subagentReceipt.status}`);
      save();
    }
    if (design.task_type === "instant") {
      const instant = await runInstantNode({ goal, workspace, provider: workerProvider, runDir, attachment, timeoutMs });
      record.instant = instant;
      record.events.push(...(instant.events || []).map((event) => ({ role: "worker", ...event })));
      record.toolTrace = instant.toolTrace || [];
      record.designExecutionMatched = instant.ok === true;
      record.reviewCalled = false;
      record.status = instant.ok ? "completed" : "failed";
      if (!instant.ok) record.error = instant.error;
    } else if (design.graph?.nodes?.length && (design.task_type === "horizontal" || design.task_type === "hybrid")) {
      const graph = await runGraph({ design, goal, workspace, provider: workerProvider, runDir, attachment, timeoutMs, checkpoint: jobId ? spiral.getCheckpoint(jobId) : null, beforeNode: () => throwIfCruisePaused(jobId, spiralRoot), onEvent: (event) => {
        record.events.push({ role: "orchestrator", ...clean(event) });
        if (jobId && event.checkpoint) saveCruiseCheckpointSafe(spiralRoot, jobId, { status: "executing", runId, goal, workspace, stage: "graph", strategy: record.strategy, provider: providerRef, attachments, seedManifest, orchestration: event.checkpoint });
        save();
      } });
      record.orchestration = graph;
      record.designExecutionMatched = graph.status === "completed";
      record.status = graph.status;
      record.toolTrace = Object.values(graph.receipts || {}).flatMap((receipt) => receipt.toolTrace || []);
      if (graph.status !== "completed") record.error = "Graph execution or consistency check failed";
    } else {
    Object.assign(process.env, { SMART_AGENT_PHASE: "worker", SMART_AGENT_DESIGN_FILE: designFile });
    worker = await createBaseSession({
      cwd: workspace,
      agentDir: ensureDirectory(path.join(runDir, "agent", "worker")),
      provider: workerProvider,
      tools: [...toolRegistry(workspace).map((tool) => tool.name), ...(controlPlane.startsWith("s-card") ? ["dispatch_card"] : []), "review_work", "finish_task"],
      additionalExtensionPaths: [EXTENSION],
      systemPrompt: `${systemPrompt ? `${systemPrompt}\n\n` : ""}You are the Worker. Execute this Manager design exactly: ${JSON.stringify(design)}. Goal: ${goal}. Optional Sub Agent receipt: ${JSON.stringify(record.subagentReceipt || null)}. Exploration summary: ${JSON.stringify(exploration)}. inspect uses read/ls/grep/find; patch/revise uses write/edit; verify uses bash/read; review uses review_work; submit uses finish_task. ${controlPlane.startsWith("s-card") ? "dispatch_card is a control-plane action; use it only when required and keep its receipt." : ""} You may use multiple tools within the current phase, then proceed only when its evidence is complete. A blocked call must be replaced with an expected current-phase tool. A failed tool does not advance the phase. Do not require or invent Sub Agents. Finish only after real verification evidence.`,
    });
    let currentAttempt = 0;
    worker.subscribe((event) => {
      if (["message_end", "turn_end", "agent_end"].includes(event.type)) record.events.push({ role: "worker", attempt: currentAttempt, ...clean(event) });
    });
    const finished = () => record.events.some((event) => event.role === "worker" && event.type === "message_end" && event.message?.role === "toolResult" && event.message?.toolName === "finish_task" && !event.message.isError && event.message.details?.finished === true);
    for (let turn = 1; turn <= maxWorkerTurns && !finished(); turn += 1) {
      throwIfCruisePaused(jobId, spiralRoot);
      currentAttempt = turn;
      const prompt = turn === 1
        ? `Execute the design for goal: ${goal}. Start with the inspect phase. Attachments:\n${attachment.text}`
        : "Continue the same design. Read the latest tool result, do not repeat successful phases, and call only currently expected phase tools. If verification failed, recover honestly within the existing design; do not report success without evidence.";
      const result = await promptWithTimeout(worker, prompt, timeoutMs, `worker attempt ${turn}`, RUNTIME_LIMITS.abortTimeoutMs, turn === 1 && attachment.images.length ? { images: attachment.images } : undefined);
      record.workerAttempts.push({ attempt: turn, ...result });
      if (result.abortError) throw new Error(result.abortError);
      if (result.error && !result.timedOut) throw new Error(result.error);
      const modelError = latestAssistantError(record.events, "worker");
      if (modelError) throw new Error(modelError);
      save();
    }
    if (!finished()) throw new Error(`Worker did not finish after ${maxWorkerTurns} recovery turns`);
    const toolResults = record.events.filter((event) => event.role === "worker" && event.type === "message_end" && event.message?.role === "toolResult");
    record.toolTrace = toolResults.map((event) => ({ tool: event.message.toolName, isError: Boolean(event.message.isError), text: (event.message.content || []).filter((item) => item.type === "text").map((item) => item.text).join("\n").slice(0, RUNTIME_LIMITS.maxTraceExcerptChars), details: event.message.details || null }));
    record.designExecutionMatched = traceMatchesDesign(record.toolTrace, design.steps);
    record.reviewCalled = record.toolTrace.some((item) => item.tool === "review_work" && !item.isError && item.details?.reviewed);
    record.status = record.designExecutionMatched ? "completed" : "failed";
    if (!record.designExecutionMatched) record.error = "Worker tool trace did not match the Manager design";
    }
    throwIfCruisePaused(jobId, spiralRoot);
    if (record.status === "completed" && record.strategy?.hash) {
      if (!record.strategyReuse) spiral.promote(record.strategy.strategyId, record.strategy.hash, runId, {
        designExecutionMatched: true,
        reviewCalled: record.reviewCalled === true,
        toolCount: record.toolTrace.length,
      });
      spiral.recordFeedback(runId, {
        status: "completed",
        strategyId: record.strategy.strategyId,
        versionHash: record.strategy.hash,
        reused: record.strategyReuse === true,
        designExecutionMatched: true,
        reviewCalled: record.reviewCalled === true,
      });
      saveCruiseCheckpointSafe(spiralRoot, jobId, { status: "completed", runId, goal, workspace, stage: "finished", strategy: record.strategy, provider: providerRef, attachments, seedManifest, orchestration: record.orchestration || null });
    }
  } catch (error) {
    const externalCheckpoint = jobId ? new SpiralStore(spiralRoot).getCheckpoint(jobId) : null;
    const controlledStop = ["paused", "stopped"].includes(externalCheckpoint?.status);
    record.status = controlledStop ? externalCheckpoint.status : "failed";
    record.error = error instanceof Error ? error.message : String(error);
    record.failureClass = classifyFailure(record.error, { record, externalCheckpoint });
    record.evidenceLayers = evidenceLayers(runDir, designFile, recordFile, record);
    spiral.recordFeedback(runId, {
      status: record.status,
      failureClass: controlledStop ? null : record.failureClass,
      error: record.error,
      strategyId: record.strategy?.strategyId || null,
      versionHash: record.strategy?.hash || null,
    });
    if (jobId) saveCruiseCheckpointSafe(spiralRoot, jobId, { status: controlledStop ? externalCheckpoint.status : "failed", runId, goal, workspace, stage: controlledStop ? externalCheckpoint.stage : "failed", error: record.error, failureClass: record.failureClass || null, strategy: record.strategy || externalCheckpoint?.strategy || null, provider: providerRef, attachments, seedManifest, orchestration: externalCheckpoint?.orchestration || null });
  } finally {
    if (record.status !== "completed" && !record.failureClass) record.failureClass = classifyFailure(record.error || "execution failed", { record, externalCheckpoint: jobId ? new SpiralStore(spiralRoot).getCheckpoint(jobId) : null });
    spiral.finishRun(runId, record.status, { endedAt: new Date().toISOString(), strategyId: record.strategy?.strategyId || null, strategyHash: record.strategy?.hash || null });
    if (manager) await manager.dispose();
    if (worker) await worker.dispose();
    record.endedAt = new Date().toISOString();
    record.evidenceLayers = evidenceLayers(runDir, designFile, recordFile, record);
    save();
    const summary = {
      schema: "smart-agent-summary-v1", runId, runDir, mode: controlPlane, goal,
      status: record.status,
      designFirst: Boolean(record.design?.hash),
      designExecutionMatched: record.designExecutionMatched === true,
      methodDecisionRecorded: Boolean(record.design && Array.isArray(record.design.method_refs) && Array.isArray(record.design.integration_requests)),
      methodUsed: Boolean(record.design?.method_refs?.length),
      methodComposition: record.design?.method_composition || [],
      strategyId: record.strategy?.strategyId || null,
      strategyHash: record.strategy?.hash || null,
      strategyReuse: record.strategyReuse === true,
      workerProvider: record.workerProvider || null,
      reviewCalled: record.reviewCalled === true,
      subAgentsUsed: Boolean(record.subagentReceipt),
      subAgentsRequired: false,
      evidenceComplete: fs.existsSync(path.join(runDir, "run-config.json")) && fs.existsSync(designFile) && fs.existsSync(recordFile),
      failureClass: record.failureClass || null,
      evidenceLayers: record.evidenceLayers,
      exploration: exploration || null,
      error: record.error || null,
    };
    fs.writeFileSync(path.join(runDir, "summary.json"), JSON.stringify(summary, null, 2), "utf8");
  }
  const summary = JSON.parse(fs.readFileSync(path.join(runDir, "summary.json"), "utf8"));
  if (summary.status !== "completed") throw new Error(`${summary.error || "Smart run failed"}\nRun: ${runDir}`);
  return summary;
}
