import { Type } from "typebox";
import fs from "node:fs";
import path from "node:path";
import { createEvolutionExtension, evolutionActions } from "./evolution-core.ts";

const EXPERIMENT_MODEL = "glm-5.3-flash";
const availableModels = [EXPERIMENT_MODEL];

function result(text, details = {}, isError = false, extra = {}) {
  return { content: [{ type: "text", text }], details, isError, ...extra };
}

export default function piEvolutionExtension(pi) {
  const phase = process.env.SMART_AGENT_PHASE;
  const workspace = process.env.SMART_AGENT_WORKSPACE;
  const designFile = process.env.SMART_AGENT_DESIGN_FILE;
  const reviewerUrl = process.env.SMART_AGENT_REVIEWER_URL;
  const reviewerModel = process.env.SMART_AGENT_REVIEWER_MODEL;
  const reviewerKey = process.env.SMART_AGENT_API_KEY || "";
  if (phase === "design") {
    pi.registerTool({
      name: "submit_design",
      label: "Submit agent design",
      description: "Submit the worker loop before implementation; the experiment model is fixed to glm-5.3-flash.",
      promptSnippet: "Design the worker before coding.",
      parameters: Type.Object({
        steps: Type.Array(Type.Union([
          Type.Literal("inspect"),
          Type.Literal("patch"),
          Type.Literal("public_check"),
          Type.Literal("review"),
          Type.Literal("revise"),
          Type.Literal("submit"),
        ]), { minItems: 2, maxItems: 10 }),
        worker_model: Type.Literal(EXPERIMENT_MODEL),
        reviewer_model: Type.Union([Type.Literal("none"), Type.Literal(EXPERIMENT_MODEL)]),
        task_type: Type.Optional(Type.Union([
          Type.Literal("instant"),
          Type.Literal("vertical"),
          Type.Literal("horizontal"),
          Type.Literal("hybrid"),
        ])),
        risk: Type.Optional(Type.String({ minLength: 1, maxLength: 1200 })),
        stop_rule: Type.Optional(Type.String({ minLength: 1, maxLength: 1200 })),
        acceptance: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { maxItems: 12 })),
        tool_plan: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { maxItems: 20 })),
        method_composition: Type.Optional(Type.Array(Type.Object({
          seed_id: Type.String({ minLength: 1 }),
          order: Type.Integer({ minimum: 1 }),
          role: Type.String({ minLength: 1, maxLength: 240 }),
          depends_on: Type.Optional(Type.Array(Type.String({ minLength: 1 }), { maxItems: 20 })),
        }), { maxItems: 20 })),
        rationale: Type.String({ minLength: 20, maxLength: 1800 }),
        method_refs: Type.Array(Type.Object({
          seed_id: Type.String({ minLength: 1 }),
          source: Type.String({ minLength: 1 }),
          source_version_or_commit: Type.String({ minLength: 1 }),
          decision: Type.Union([Type.Literal("use"), Type.Literal("combine"), Type.Literal("fork"), Type.Literal("skip")]),
          signals: Type.Array(Type.String({ minLength: 1 }), { minItems: 1, maxItems: 12 }),
          reason: Type.String({ minLength: 10, maxLength: 800 }),
          change_summary: Type.String({ minLength: 1, maxLength: 800 }),
        }), { maxItems: 20 }),
        integration_requests: Type.Array(Type.Object({
          kind: Type.Literal("method"),
          seed_id: Type.String({ minLength: 1 }),
          reason: Type.String({ minLength: 10, maxLength: 800 }),
        }), { maxItems: 20 }),
      }),
      executionMode: "sequential",
      async execute(_id, params) {
        const validSteps = new Set(["inspect", "patch", "public_check", "review", "revise", "submit"]);
        if (!Array.isArray(params.steps) || params.steps.length < 2 || params.steps.some((s) => !validSteps.has(s))) {
          return result("Rejected: invalid steps", { accepted: false }, true);
        }
        if (params.steps[0] !== "inspect" || params.steps.at(-1) !== "submit") {
          return result("Rejected: inspect must be first and submit last", { accepted: false }, true);
        }
        if (!params.steps.includes("patch") && !params.steps.includes("revise")) {
          return result("Rejected: a write step is required", { accepted: false }, true);
        }
        if (!params.steps.includes("public_check")) {
          return result("Rejected: public_check is required", { accepted: false }, true);
        }
        if (!availableModels.includes(params.worker_model) || ![...availableModels, "none"].includes(params.reviewer_model)) {
          return result("Rejected: unavailable model route", { accepted: false }, true);
        }
        if (params.steps.includes("review") !== (params.reviewer_model !== "none")) {
          return result("Rejected: review step and reviewer_model must agree", { accepted: false }, true);
        }
        if (!Array.isArray(params.method_refs) || !Array.isArray(params.integration_requests)) {
          return result("Rejected: method_refs and integration_requests must be arrays", { accepted: false }, true);
        }
        const design = {
          steps: params.steps,
          worker_model: params.worker_model,
          reviewer_model: params.reviewer_model,
          task_type: params.task_type || null,
          risk: params.risk || null,
          stop_rule: params.stop_rule || null,
          acceptance: params.acceptance || [],
          tool_plan: params.tool_plan || [],
          method_composition: params.method_composition || [],
          rationale: String(params.rationale || ""),
          method_refs: params.method_refs,
          integration_requests: params.integration_requests,
          submitted_at: new Date().toISOString(),
        };
        fs.writeFileSync(designFile, JSON.stringify(design, null, 2), "utf8");
        return result(`Design accepted: ${JSON.stringify(design)}`, { accepted: true, design }, false, { terminate: true });
      },
    });
    return;
  }

  if (phase !== "worker") throw new Error(`Unknown SMART_AGENT_PHASE: ${phase}`);
  const design = JSON.parse(fs.readFileSync(designFile, "utf8"));
  const extension = createEvolutionExtension(design);
  const events = [];
  const host = { cwd: workspace };
  const actions = evolutionActions(host, events, extension.state);
  actions.reviewCode = async () => {
    if (design.reviewer_model === "none") return result("No reviewer configured", {}, true);
    try {
      const source = fs.readFileSync(path.join(workspace, "solution.py"), "utf8");
      const response = await fetch(`${reviewerUrl}/chat/completions`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${reviewerKey}` },
        body: JSON.stringify({
          model: reviewerModel,
          messages: [
            { role: "system", content: "You are an independent code reviewer. Identify concrete correctness risks concisely." },
            { role: "user", content: `Review this solution.py. Do not invent hidden tests.\n\n${source}` },
          ],
          max_tokens: 2400,
          reasoning_effort: "low",
          stream: false,
        }),
        signal: AbortSignal.timeout(120000),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(JSON.stringify(payload));
      const content = payload.choices?.[0]?.message?.content || "";
      return result(content || "Reviewer returned no text", { reviewer_model: design.reviewer_model, upstream_model: payload.model || reviewerModel, usage: payload.usage || null }, !content);
    } catch (error) {
      return result(`Reviewer failed: ${error}`, { reviewer_model: design.reviewer_model, failed: true }, true);
    }
  };
  pi.on("tool_call", async (event) => extension.handleToolCall(event));
  pi.on("tool_result", async (event) => extension.handleToolResult(event));
  const tools = {
    workspace_read: {
      description: "Read solution.py or public_test.py",
      parameters: Type.Object({ path: Type.String() }),
      execute: async (_id, params) => actions.readFile(params),
    },
    workspace_write: {
      description: "Replace solution.py",
      parameters: Type.Object({ path: Type.String(), content: Type.String() }),
      execute: async (_id, params) => actions.writeFile(params),
    },
    run_public_test: {
      description: "Run the fixed public test",
      parameters: Type.Object({}),
      execute: async () => actions.runPublicTest(),
    },
    review_code: {
      description: "Call the reviewer model selected by the manager",
      parameters: Type.Object({}),
      execute: async () => actions.reviewCode(),
    },
    revise_solution: {
      description: "Write a revised solution.py",
      parameters: Type.Object({ content: Type.String() }),
      execute: async (_id, params) => actions.reviseSolution(params),
    },
    finish_task: {
      description: "Finish after all designed steps",
      parameters: Type.Object({ summary: Type.String() }),
      execute: async (_id, params) => actions.finishTask(params),
    },
  };
  for (const [name, tool] of Object.entries(tools)) {
    pi.registerTool({ name, label: name, promptSnippet: tool.description, executionMode: "sequential", ...tool });
  }
}
