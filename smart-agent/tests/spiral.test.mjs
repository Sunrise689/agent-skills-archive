import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { SpiralStore } from "../core/spiral-store.mjs";
import { GraphOrchestrator, graphErrors, readyNodes } from "../core/orchestration.mjs";
import { runtimeProvider } from "../src/config.mjs";
import { isNativeProviderConfig, loadPi, resolveNativeModel } from "../src/pi-runtime.mjs";

const temp = () => fs.mkdtempSync(path.join(os.tmpdir(), "smart-agent-spiral-test-"));

const baseDesign = (task_type = "vertical") => ({
  task_type,
  steps: ["inspect", "patch", "verify", "submit"],
  graph: { nodes: [
    { id: "inspect", step: "inspect" },
    { id: "patch", step: "patch", dependsOn: ["inspect"] },
    { id: "verify", step: "verify", dependsOn: ["patch"] },
    { id: "submit", step: "submit", dependsOn: ["verify"] },
  ] },
});

test("SpiralStore persists candidates, promotions and rollback across fresh instances", () => {
  const root = temp();
  const first = new SpiralStore(root);
  first.startRun("run-1", { goal: "goal", provider: { model: "m", apiKey: "must-not-persist" } });
  const event = first.candidate({ strategyId: "loop-a", version: 1, steps: ["inspect", "submit"], parentHash: null }, "run-1");
  const hash = event.strategy.hash;
  first.promote("loop-a", hash, "run-1", { designExecutionMatched: true });
  first.finishRun("run-1", "completed");
  const second = new SpiralStore(root);
  assert.equal(second.getStrategy("loop-a").hash, hash);
  assert.equal(second.state.runs["run-1"].status, "completed");
  const secondVersion = second.candidate({ strategyId: "loop-a", version: 2, parentHash: hash, steps: ["inspect", "patch", "submit"] }, "run-2").strategy;
  second.rollback("loop-a", hash, "run-2", "candidate failed");
  const third = new SpiralStore(root);
  assert.equal(third.getStrategy("loop-a").hash, hash);
  assert.notEqual(third.getStrategy("loop-a").hash, secondVersion.hash);
  const raw = fs.readFileSync(path.join(root, "events.jsonl"), "utf8");
  assert.equal(raw.includes("must-not-persist"), false);
});

test("SpiralStore reconstructs state from append-only events when snapshot is absent", () => {
  const root = temp();
  const first = new SpiralStore(root);
  const hash = first.candidate({ strategyId: "loop-a", version: 1, steps: ["inspect", "submit"] }, "run-1").strategy.hash;
  first.promote("loop-a", hash, "run-1");
  fs.rmSync(path.join(root, "state.json"));
  const restored = new SpiralStore(root);
  assert.equal(restored.getStrategy("loop-a").hash, hash);
});

test("GraphOrchestrator validates DAG and exposes independent ready nodes", () => {
  const design = {
    task_type: "horizontal",
    steps: ["inspect", "submit"],
    graph: { nodes: [
      { id: "a", step: "inspect" },
      { id: "b", step: "inspect" },
      { id: "join", kind: "join", dependsOn: ["a", "b"] },
    ] },
  };
  assert.deepEqual(graphErrors(design), []);
  assert.deepEqual(readyNodes(design).map((node) => node.id), ["a", "b"]);
  design.graph.nodes[1].dependsOn = ["join"];
  assert.ok(graphErrors(design).some((error) => error.includes("cycle")));
});

test("GraphOrchestrator executes independent nodes in parallel and verifies join consistency", async () => {
  const design = {
    task_type: "horizontal",
    steps: ["inspect", "submit"],
    graph: { nodes: [
      { id: "a", step: "inspect" },
      { id: "b", step: "inspect" },
      { id: "join", kind: "join", dependsOn: ["a", "b"] },
    ] },
  };
  let active = 0;
  let maxActive = 0;
  const result = await new GraphOrchestrator(design, { maxParallel: 2 }).run(async (node) => {
    active += 1;
    maxActive = Math.max(maxActive, active);
    await new Promise((resolve) => setTimeout(resolve, 15));
    active -= 1;
    return { ok: true, node: node.id, consistent: node.kind === "join" ? true : undefined };
  });
  assert.equal(result.status, "completed");
  assert.equal(maxActive, 2);
  assert.equal(result.consistency.ok, true);
});

test("GraphOrchestrator checkpoint can resume without repeating completed nodes", async () => {
  const design = baseDesign("vertical");
  const first = new GraphOrchestrator(design);
  const calls = [];
  await first.run(async (node) => { calls.push(node.id); return { ok: true }; });
  const restored = GraphOrchestrator.restore(first.checkpoint());
  const result = await restored.run(async (node) => { calls.push(`again:${node.id}`); return { ok: true }; });
  assert.equal(result.status, "completed");
  assert.deepEqual(calls, ["inspect", "patch", "verify", "submit"]);
});

test("pi native ModelRegistry resolves custom provider and environment credential reference", async () => {
  const home = temp();
  const previousDir = process.env.PI_CODING_AGENT_DIR;
  const previousKey = process.env.SMART_AGENT_TEST_KEY;
  process.env.PI_CODING_AGENT_DIR = home;
  process.env.SMART_AGENT_TEST_KEY = "local-test-only";
  try {
    fs.writeFileSync(path.join(home, "models.json"), JSON.stringify({ providers: {
      "custom-openai": {
        baseUrl: "http://127.0.0.1:1/v1",
        apiKey: "SMART_AGENT_TEST_KEY",
        api: "openai-completions",
        models: [{ id: "demo", input: ["text"], contextWindow: 8192, maxTokens: 1024 }],
      },
      "custom-anthropic": {
        baseUrl: "http://127.0.0.1:1",
        apiKey: "SMART_AGENT_TEST_KEY",
        api: "anthropic-messages",
        models: [{ id: "demo-anthropic", input: ["text"], contextWindow: 8192, maxTokens: 1024 }],
      },
    } }), "utf8");
    const { pi } = await loadPi();
    const auth = pi.AuthStorage.create(path.join(home, "auth.json"));
    const registry = pi.ModelRegistry.create(auth);
    const openai = resolveNativeModel(registry, { native: true, model: "custom-openai/demo" });
    const anthropic = resolveNativeModel(registry, { native: true, model: "custom-anthropic/demo-anthropic" });
    assert.equal(openai.api, "openai-completions");
    assert.equal(anthropic.api, "anthropic-messages");
    assert.equal(registry.hasConfiguredAuth(openai), true);
    assert.equal(registry.hasConfiguredAuth(anthropic), true);
  } finally {
    if (previousDir === undefined) delete process.env.PI_CODING_AGENT_DIR;
    else process.env.PI_CODING_AGENT_DIR = previousDir;
    if (previousKey === undefined) delete process.env.SMART_AGENT_TEST_KEY;
    else process.env.SMART_AGENT_TEST_KEY = previousKey;
  }
});

test("native pi runtime selection is the primary path, with legacy provider fallback", () => {
  const config = { version: 3, pi: { provider: "anthropic", model: "claude-sonnet", thinkingLevel: "high" }, provider: { model: "legacy", baseUrl: "https://legacy.invalid/v1" } };
  const native = runtimeProvider(config);
  assert.equal(native.native, true);
  assert.equal(native.piProvider, "anthropic");
  assert.equal(native.model, "claude-sonnet");
  assert.equal(isNativeProviderConfig(runtimeProvider({ pi: {}, provider: config.provider }, { model: "openrouter/example" })), true);
  const legacy = runtimeProvider({ pi: {}, provider: config.provider });
  assert.equal(legacy.native, false);
  assert.equal(legacy.model, "legacy");
});
