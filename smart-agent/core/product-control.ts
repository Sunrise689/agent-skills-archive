import fs from "node:fs";
import path from "node:path";
import { Type } from "typebox";
import { methodContractErrors } from "./method-contract.mjs";
import { RUNTIME_LIMITS } from "../src/runtime-policy.mjs";
import { createBaseSession, latestAssistantError, providerForModelSelection } from "../src/pi-runtime.mjs";
import { promptWithTimeout } from "./prompt-lifecycle.mjs";
import { dispatchCard } from "../src/dispatch.mjs";

const PHASES = ["inspect", "patch", "verify", "review", "revise", "submit"];
const STEP_TOOLS = {
  inspect: ["read", "ls", "grep", "find"],
  patch: ["write", "edit"],
  verify: ["bash", "read"],
  review: ["review_work"],
  revise: ["write", "edit"],
  submit: ["finish_task"],
};
const ALL_TOOLS = ["read", "bash", "edit", "write", "grep", "find", "ls", "dispatch_card"];

function reply(text, details = {}, isError = false, extra = {}) {
  return { content: [{ type: "text", text }], details, isError, ...extra };
}

export function createProductControl(design, seedIds) {
  const errors = methodContractErrors(design, seedIds);
  if (!PHASES.every((phase) => !design.steps.includes(phase) || STEP_TOOLS[phase])) errors.push("unknown design phase");
  if (design.steps[0] !== "inspect" || design.steps.at(-1) !== "submit") errors.push("inspect must be first and submit last");
  if (!design.steps.includes("verify")) errors.push("verify is required");
  if (!design.steps.includes("patch") && !design.steps.includes("revise")) errors.push("a write phase is required");
  if (design.steps.includes("review") !== (design.reviewer_model !== "none")) errors.push("review and reviewer_model must agree");
  if (!["instant", "vertical", "horizontal", "hybrid"].includes(design.task_type)) errors.push("invalid task_type");
  if (!design.risk || !design.stop_rule || !Array.isArray(design.acceptance) || !design.acceptance.length || !Array.isArray(design.tool_plan)) errors.push("risk/stop_rule/acceptance/tool_plan are required");
  if (!Array.isArray(design.tool_plan) || design.tool_plan.some((tool) => !ALL_TOOLS.includes(tool))) errors.push("tool_plan contains an unavailable tool");
  if (errors.length) throw new Error(`Invalid design: ${errors.join("; ")}`);
  const state = { cursor: 0, phase: "running", evidence: [], blocked: [], design, pendingCursor: null, reviewPassed: false };
  const currentPhase = () => design.steps[state.cursor] || null;
  const phaseIndexForTool = (toolName, start = state.cursor) => design.steps.findIndex((step, index) => index >= start && STEP_TOOLS[step]?.includes(toolName));
  return {
    state,
    missingPhases: () => design.steps.filter((step) => step !== "submit" && !state.evidence.some((item) => item.phase === step)),
    handleToolCall(event) {
      if (state.phase !== "running") return { block: true, reason: "Task already submitted" };
      // Dispatch is an S-card control-plane action. It records a receipt but
      // does not advance the worker's inspect/patch/verify gate.
      if (event.toolName === "dispatch_card") return undefined;
      if (state.pendingCursor !== null) return { block: true, reason: "Wait for the current tool result before starting another tool" };
      const current = currentPhase();
      const allowed = STEP_TOOLS[current] || [];
      if (allowed.includes(event.toolName)) return undefined;
      const next = phaseIndexForTool(event.toolName, state.cursor + 1);
      const hasEvidence = state.evidence.some((item) => item.phase === current);
      if (hasEvidence && next === state.cursor + 1) {
        state.pendingCursor = next;
        return undefined;
      }
      const reason = `Design expects ${current} (${allowed.join("/")}), not ${event.toolName}`;
      state.blocked.push({ tool: event.toolName, reason });
      return { block: true, reason };
    },
    handleToolResult(event) {
      if (event.toolName === "dispatch_card") {
        state.evidence.push({ phase: currentPhase(), tool: event.toolName, at: new Date().toISOString(), receipt: event.details || null });
        return undefined;
      }
      const failed = event.isError || (event.toolName === "review_work" && event.details?.reviewed !== true) || (event.toolName === "finish_task" && event.details?.finished !== true);
      if (failed) { state.pendingCursor = null; state.reviewPassed = event.toolName === "review_work" ? false : state.reviewPassed; return undefined; }
      const phase = state.pendingCursor !== null ? design.steps[state.pendingCursor] : currentPhase();
      state.evidence.push({ phase, tool: event.toolName, at: new Date().toISOString() });
      if (event.toolName === "review_work") state.reviewPassed = event.details?.reviewed === true;
      if (event.toolName === "finish_task") state.phase = "submitted";
      else if (state.pendingCursor !== null) { state.cursor = state.pendingCursor; state.pendingCursor = null; }
      return undefined;
    },
  };
}

export default function productExtension(pi) {
  const phase = process.env.SMART_AGENT_PHASE;
  const designFile = process.env.SMART_AGENT_DESIGN_FILE;
  if (phase === "design") {
    const model = process.env.SMART_AGENT_MODEL;
    pi.registerTool({
      name: "submit_design",
      label: "Submit Workflow/Loop design",
      description: "Submit a machine-readable design before any worker execution.",
      promptSnippet: "Design the worker before implementing.",
      parameters: Type.Object({
        steps: Type.Array(Type.Union(PHASES.map((step) => Type.Literal(step))), { minItems: 3, maxItems: RUNTIME_LIMITS.maxDesignItems }),
        worker_model: Type.String({ minLength: 1, maxLength: 512 }),
        reviewer_model: Type.String({ minLength: 1, maxLength: 512 }),
        worker_effort: Type.Optional(Type.Union(["off", "minimal", "low", "medium", "high", "xhigh"].map((level) => Type.Literal(level)))),
        reviewer_effort: Type.Optional(Type.Union(["off", "minimal", "low", "medium", "high", "xhigh"].map((level) => Type.Literal(level)))),
        task_type: Type.Union([Type.Literal("instant"), Type.Literal("vertical"), Type.Literal("horizontal"), Type.Literal("hybrid")]),
        strategy_id: Type.Optional(Type.String({ minLength: 1, maxLength: 160 })),
        loop_policy: Type.Optional(Type.Object({
          max_iterations: Type.Optional(Type.Integer({ minimum: 1, maximum: RUNTIME_LIMITS.maxDesignItems })),
          on_failure: Type.Optional(Type.Union([Type.Literal("recover"), Type.Literal("rollback"), Type.Literal("stop")])),
          stop_when: Type.Optional(Type.String({ minLength: 1, maxLength: RUNTIME_LIMITS.maxDesignTextChars })),
        })),
        graph: Type.Optional(Type.Object({
          nodes: Type.Array(Type.Object({
            id: Type.String({ minLength: 1, maxLength: 160 }),
            kind: Type.Optional(Type.String({ minLength: 1, maxLength: 80 })),
            step: Type.Optional(Type.String({ minLength: 1, maxLength: 80 })),
            goal: Type.Optional(Type.String({ minLength: 1, maxLength: RUNTIME_LIMITS.maxDesignTextChars })),
            depends_on: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { maxItems: RUNTIME_LIMITS.maxDesignItems })),
            dependsOn: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { maxItems: RUNTIME_LIMITS.maxDesignItems })),
            inputs: Type.Optional(Type.Array(Type.String(), { maxItems: RUNTIME_LIMITS.maxDesignItems })),
            acceptance: Type.Optional(Type.Array(Type.String(), { maxItems: RUNTIME_LIMITS.maxDesignItems })),
          }), { maxItems: RUNTIME_LIMITS.maxDesignItems }),
        })),
        risk: Type.String({ minLength: 1, maxLength: RUNTIME_LIMITS.maxDesignTextChars }),
        stop_rule: Type.String({ minLength: 1, maxLength: RUNTIME_LIMITS.maxDesignTextChars }),
        acceptance: Type.Array(Type.String({ minLength: 1, maxLength: RUNTIME_LIMITS.maxDesignTextChars }), { minItems: 1, maxItems: RUNTIME_LIMITS.maxDesignItems }),
        tool_plan: Type.Array(Type.Union(ALL_TOOLS.map((tool) => Type.Literal(tool))), { minItems: 1, maxItems: RUNTIME_LIMITS.maxDesignItems }),
        method_refs: Type.Array(Type.Object({
          seed_id: Type.String(), source: Type.String(), source_version_or_commit: Type.String(),
          decision: Type.Union([Type.Literal("use"), Type.Literal("combine"), Type.Literal("fork"), Type.Literal("skip")]),
          signals: Type.Array(Type.String(), { minItems: 1, maxItems: RUNTIME_LIMITS.maxDesignItems }), reason: Type.String({ minLength: 10 }), change_summary: Type.String(),
        }), { maxItems: RUNTIME_LIMITS.maxDesignItems }),
        method_composition: Type.Optional(Type.Array(Type.Object({
          seed_id: Type.String(), order: Type.Integer({ minimum: 1 }), role: Type.String(),
          depends_on: Type.Optional(Type.Array(Type.String(), { maxItems: RUNTIME_LIMITS.maxDesignItems })),
        }), { maxItems: RUNTIME_LIMITS.maxDesignItems })),
        integration_requests: Type.Array(Type.Object({ kind: Type.Literal("method"), seed_id: Type.String(), reason: Type.String({ minLength: 10 }) }), { maxItems: RUNTIME_LIMITS.maxDesignItems }),
        subagent_request: Type.Optional(Type.Object({
          agent: Type.Union([Type.Literal("codex"), Type.Literal("pi"), Type.Literal("opencode")]),
          goal: Type.String({ minLength: 1 }),
          rationale: Type.String({ minLength: 10 }),
        })),
        rationale: Type.String({ minLength: 20, maxLength: RUNTIME_LIMITS.maxDesignTextChars }),
      }),
      executionMode: "sequential",
      async execute(_id, params) {
        const design = { ...params, submitted_at: new Date().toISOString() };
        const errors = methodContractErrors(design, JSON.parse(process.env.SMART_AGENT_SEED_IDS || "[]"));
        if (errors.length) return reply(`Rejected: ${errors.join("; ")}`, { accepted: false, errors }, true);
        fs.writeFileSync(designFile, JSON.stringify(design, null, 2), "utf8");
        return reply(`Design accepted: ${JSON.stringify(design)}`, { accepted: true, design }, false, { terminate: true });
      },
    });
    return;
  }
  if (phase !== "worker") throw new Error(`Unknown SMART_AGENT_PHASE: ${phase}`);
  const design = JSON.parse(fs.readFileSync(designFile, "utf8"));
  const control = createProductControl(design, JSON.parse(process.env.SMART_AGENT_SEED_IDS || "[]"));
  pi.on("tool_call", async (event) => control.handleToolCall(event));
  pi.on("tool_result", async (event) => control.handleToolResult(event));
  if (process.env.SMART_AGENT_CONTROL_PLANE?.startsWith("s-card")) pi.registerTool({
    name: "dispatch_card",
    label: "Dispatch card",
    description: "S-card control-plane action: launch one profile-validated external card and persist a structured receipt.",
    promptSnippet: "Dispatch a card only when the S-card plan requires it; keep the receipt.",
    parameters: Type.Object({
      card_id: Type.String({ minLength: 1, maxLength: 128 }),
      profile_id: Type.Union(["MINIMAX-U", "MINIMAX-L", "GK-U", "GK-L", "CX-U-OFFICIAL"].map((value) => Type.Literal(value))),
      taskbook_path: Type.String({ minLength: 1 }),
      workdir: Type.String({ minLength: 1 }),
      model: Type.Optional(Type.String({ minLength: 1 })),
      effort: Type.Optional(Type.String({ minLength: 1 })),
      write_scope: Type.Optional(Type.Union([Type.Literal("read-only"), Type.Literal("workspace-write")])),
      soft_time_limit_minutes: Type.Optional(Type.Integer({ minimum: 1, maximum: 1440 })),
    }),
    executionMode: "sequential",
    async execute(_id, params) {
      try {
        const receipt = dispatchCard(params);
        return reply(receipt.ok ? "Card dispatch accepted" : "Card dispatch returned a failed receipt", { ...receipt }, !receipt.ok);
      } catch (error) {
        return reply(`Card dispatch failed: ${error instanceof Error ? error.message : String(error)}`, { ok: false, failureClass: "dispatch" }, true);
      }
    },
  });
  pi.registerTool({
    name: "review_work",
    label: "Independent work review",
    description: "Request an independent reviewer for the current goal and workspace evidence.",
    promptSnippet: "Review the work in an independent model context.",
    parameters: Type.Object({ evidence: Type.String({ minLength: 1 }) }),
    executionMode: "sequential",
    async execute(_id, params) {
      let reviewer;
      try {
        const baseProvider = JSON.parse(process.env.SMART_AGENT_PROVIDER_JSON || "{}");
        const provider = providerForModelSelection(baseProvider, design.reviewer_model, design.reviewer_effort);
        const reviewDir = path.join(path.dirname(designFile), "reviewer");
        const events = [];
        reviewer = await createBaseSession({
          cwd: process.env.SMART_AGENT_WORKSPACE || process.cwd(),
          agentDir: reviewDir,
          provider,
          tools: [],
          systemPrompt: "You are an independent reviewer. Do not implement changes. Return concrete correctness and acceptance risks, or APPROVED when evidence is sufficient.",
        });
        reviewer.subscribe((event) => {
          if (event.type === "message_end" && event.message?.role === "assistant") events.push(event);
        });
        await promptWithTimeout(
          reviewer,
          `Goal: ${process.env.SMART_AGENT_GOAL}\nAcceptance: ${JSON.stringify(design.acceptance)}\nWorker evidence:\n${params.evidence}`,
          Number(process.env.SMART_AGENT_REVIEWER_TIMEOUT_MS || RUNTIME_LIMITS.reviewerTimeoutMs),
          "native pi reviewer",
          RUNTIME_LIMITS.abortTimeoutMs,
        );
        const modelError = latestAssistantError(events);
        if (modelError) throw new Error(modelError);
        const content = events.flatMap((event) => Array.isArray(event.message?.content) ? event.message.content : [])
          .filter((item) => item.type === "text")
          .map((item) => item.text)
          .join("\n")
          .trim();
        return reply(content || "Reviewer returned no text", { reviewed: Boolean(content), model: design.reviewer_model, runtime: "pi-native" }, !content);
      } catch (error) {
        return reply(`Reviewer failed: ${error instanceof Error ? error.message : String(error)}`, { reviewed: false, runtime: "pi-native" }, true);
      } finally {
        if (reviewer) await reviewer.dispose();
      }
    },
  });
  pi.registerTool({
    name: "finish_task",
    label: "Finish task with evidence",
    description: "Submit only after all designed phases have real tool receipts.",
    promptSnippet: "Finish with verified evidence.",
    parameters: Type.Object({ summary: Type.String({ minLength: 1 }) }),
    executionMode: "sequential",
    async execute(_id, params) {
      const missing = control.missingPhases();
      if (missing.length) return reply(`Missing phases: ${missing.join(", ")}`, { finished: false, missing }, true);
      if (design.reviewer_model !== "none" && !control.state.reviewPassed) return reply("Review did not produce an approval receipt", { finished: false, reviewPassed: false }, true);
      return reply("Task finished", { finished: true, summary: params.summary, evidence: control.state.evidence });
    },
  });
}
