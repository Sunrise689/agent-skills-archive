import test from "node:test";
import assert from "node:assert/strict";
import productExtension, { createProductControl } from "../core/product-control.ts";
import { RUNTIME_LIMITS } from "../src/runtime-policy.mjs";

const design = {
  steps: ["inspect", "patch", "verify", "submit"],
  worker_model: "model-x",
  reviewer_model: "none",
  task_type: "vertical",
  risk: "file correctness",
  stop_rule: "verification passes",
  acceptance: ["file exists and content is correct"],
  tool_plan: ["read", "write", "bash"],
  method_refs: [],
  method_composition: [],
  integration_requests: [],
};

test("product control blocks out-of-order tools and advances only on success", async () => {
  const control = createProductControl(design, []);
  assert.equal((await control.handleToolCall({ toolName: "write" })).block, true);
  assert.equal(await control.handleToolCall({ toolName: "read" }), undefined);
  await control.handleToolResult({ toolName: "read", isError: false });
  assert.equal(control.state.cursor, 0);
  assert.equal(await control.handleToolCall({ toolName: "write" }), undefined);
  await control.handleToolResult({ toolName: "write", isError: true });
  assert.equal(control.state.cursor, 0);
  assert.equal(await control.handleToolCall({ toolName: "write" }), undefined);
  await control.handleToolResult({ toolName: "write", isError: false });
  assert.equal(control.state.cursor, 1);
});

test("product control supports independent review and final submission", async () => {
  const control = createProductControl({ ...design, steps: ["inspect", "patch", "review", "revise", "verify", "submit"], reviewer_model: "model-x" }, []);
  for (const tool of ["read", "write", "review_work", "edit", "bash", "finish_task"]) {
    assert.equal(await control.handleToolCall({ toolName: tool }), undefined, tool);
    await control.handleToolResult({ toolName: tool, isError: false, details: tool === "review_work" ? { reviewed: true } : tool === "finish_task" ? { finished: true } : undefined });
  }
  assert.equal(control.state.phase, "submitted");
  assert.equal((await control.handleToolCall({ toolName: "read" })).block, true);
});

test("product control allows multiple inspect and verify receipts", async () => {
  const control = createProductControl(design, []);
  for (const tool of ["read", "ls", "write", "bash", "read", "finish_task"]) {
    assert.equal(await control.handleToolCall({ toolName: tool }), undefined, tool);
    if (tool === "finish_task") assert.deepEqual(control.missingPhases(), []);
    await control.handleToolResult({ toolName: tool, isError: false, details: tool === "finish_task" ? { finished: true } : undefined });
  }
  assert.equal(control.state.phase, "submitted");
});

test("empty review does not advance or authorize submission", async () => {
  const control = createProductControl({ ...design, steps: ["inspect", "patch", "review", "revise", "verify", "submit"], reviewer_model: "model-x" }, []);
  for (const tool of ["read", "write", "review_work"]) {
    assert.equal(await control.handleToolCall({ toolName: tool }), undefined, tool);
    await control.handleToolResult({ toolName: tool, isError: false, details: tool === "review_work" ? { reviewed: false } : undefined });
  }
  assert.equal(control.state.cursor, 1);
  assert.equal(control.state.reviewPassed, false);
  assert.equal(await control.handleToolCall({ toolName: "review_work" }), undefined);
});

test("Manager design schema uses high safety ceilings instead of small field limits", () => {
  const keys = ["SMART_AGENT_PHASE", "SMART_AGENT_MODEL", "SMART_AGENT_DESIGN_FILE", "SMART_AGENT_SEED_IDS"];
  const previous = Object.fromEntries(keys.map((key) => [key, process.env[key]]));
  Object.assign(process.env, { SMART_AGENT_PHASE: "design", SMART_AGENT_MODEL: "model-x", SMART_AGENT_DESIGN_FILE: "unused.json", SMART_AGENT_SEED_IDS: "[]" });
  try {
    let tool;
    productExtension({ registerTool(value) { tool = value; } });
    const schema = tool.parameters;
    assert.equal(schema.properties.rationale.maxLength, RUNTIME_LIMITS.maxDesignTextChars);
    assert.equal(schema.properties.risk.maxLength, RUNTIME_LIMITS.maxDesignTextChars);
    assert.equal(schema.properties.acceptance.maxItems, RUNTIME_LIMITS.maxDesignItems);
    assert.equal(schema.properties.steps.maxItems, RUNTIME_LIMITS.maxDesignItems);
    assert.ok(schema.properties.rationale.maxLength > 2400);
    assert.ok(schema.properties.acceptance.maxItems > 12);
  } finally {
    for (const key of keys) {
      if (previous[key] === undefined) delete process.env[key];
      else process.env[key] = previous[key];
    }
  }
});
