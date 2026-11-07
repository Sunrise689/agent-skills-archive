import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { createBudgetedStream, latestAssistantError, toolRegistry, modelFromProvider } from "../src/pi-runtime.mjs";
import { loadConfig, saveConfig, validateProvider, redactConfig } from "../src/config.mjs";
import { loadAttachments } from "../src/attachments.mjs";
import { extractSeedIds, methodContractErrors } from "../core/method-contract.mjs";
import { promptWithTimeout } from "../core/prompt-lifecycle.mjs";
import { RUNTIME_LIMITS } from "../src/runtime-policy.mjs";

const temp = () => fs.mkdtempSync(path.join(os.tmpdir(), "smart-agent-test-"));

test("base runtime exposes ordinary pi tools without Sub Agents", () => {
  const tools = toolRegistry("C:/workspace").map((tool) => tool.name);
  assert.deepEqual(tools, ["read", "bash", "edit", "write", "grep", "find", "ls"]);
  assert.equal(tools.includes("subagent"), false);
});

test("provider model supports text and image without embedding a key", () => {
  const model = modelFromProvider({ model: "model-x", baseUrl: "https://example.test/v1/", input: ["text", "image"], contextWindow: 1000, maxTokens: 100 });
  assert.equal(model.baseUrl, "https://example.test/v1");
  assert.deepEqual(model.input, ["text", "image"]);
  assert.equal(JSON.stringify(model).includes("apiKey"), false);
});

test("config roundtrip contains no credential value", () => {
  const home = temp();
  process.env.SMART_AGENT_HOME = home;
  const config = loadConfig({ required: false });
  config.provider.baseUrl = "https://example.test/v1";
  config.provider.model = "model-x";
  saveConfig(config);
  const raw = fs.readFileSync(path.join(home, "config.json"), "utf8");
  assert.equal(raw.includes("actual-secret"), false);
  assert.deepEqual(validateProvider(config, { requireKey: false }), []);
  assert.equal(redactConfig(config).provider.apiKey, undefined);
});

test("attachments preserve text and native image content", async () => {
  const workspace = temp();
  fs.writeFileSync(path.join(workspace, "note.txt"), "hello", "utf8");
  fs.writeFileSync(path.join(workspace, "pixel.png"), Buffer.from("iVBORw0KGgo=", "base64"));
  const result = await loadAttachments(["note.txt", "pixel.png"], workspace);
  assert.match(result.text, /hello/);
  assert.equal(result.images.length, 1);
  assert.equal(result.images[0].type, "image");
  assert.equal(result.images[0].mimeType, "image/png");
});

test("Loop Seed composition allows multiple methods and rejects bad references", () => {
  const catalog = fs.readFileSync(new URL("../loop_seeds/seeds.md", import.meta.url), "utf8");
  const ids = extractSeedIds(catalog);
  assert.equal(ids.length, 5);
  const refs = ids.slice(0, 2).map((seed_id) => ({ seed_id, source: "catalog", source_version_or_commit: "0.2.1", decision: "combine", signals: ["test"], reason: "test combination rationale", change_summary: "combine" }));
  const design = { method_refs: refs, integration_requests: [], method_composition: refs.map((ref, index) => ({ seed_id: ref.seed_id, order: index + 1, role: `role-${index}` })) };
  assert.deepEqual(methodContractErrors(design, ids), []);
  design.method_composition[1].seed_id = "NOT-A-SEED";
  assert.ok(methodContractErrors(design, ids).length > 0);
});

test("high runtime defaults avoid legacy output, timeout and recovery ceilings", () => {
  const previousHome = process.env.SMART_AGENT_HOME;
  process.env.SMART_AGENT_HOME = temp();
  try {
    const config = loadConfig({ required: false });
    assert.equal(config.provider.maxTokens, 1_000_000);
    const model = modelFromProvider(config.provider);
    assert.equal(model.maxTokens, 128000);
    let forwarded;
    const stream = createBudgetedStream((_model, _context, options) => { forwarded = options; return "stream"; });
    assert.equal(stream(model, {}), "stream");
    assert.equal(forwarded.maxTokens, 128000, "must bypass pi's implicit 32000-token clamp");
    assert.ok(RUNTIME_LIMITS.promptTimeoutMs > 150000);
    assert.ok(RUNTIME_LIMITS.maxWorkerTurns > 4);
    assert.ok(RUNTIME_LIMITS.maxManagerAttempts > 2);
  } finally {
    if (previousHome === undefined) delete process.env.SMART_AGENT_HOME;
    else process.env.SMART_AGENT_HOME = previousHome;
  }
});

test("version 1 implicit 4096 output budget migrates without changing explicit v2 choices", () => {
  const previousHome = process.env.SMART_AGENT_HOME;
  const home = temp();
  process.env.SMART_AGENT_HOME = home;
  try {
    fs.writeFileSync(path.join(home, "config.json"), JSON.stringify({ version: 1, provider: { baseUrl: "https://example.test/v1", model: "model-x", apiKeyEnv: "KEY", input: ["text"], contextWindow: 128000, maxTokens: 4096 } }), "utf8");
    const migrated = loadConfig();
    assert.equal(migrated.version, 3);
    assert.equal(migrated.provider.maxTokens, 1_000_000);
    migrated.provider.maxTokens = 8192;
    saveConfig(migrated);
    assert.equal(loadConfig().provider.maxTokens, 8192);
  } finally {
    if (previousHome === undefined) delete process.env.SMART_AGENT_HOME;
    else process.env.SMART_AGENT_HOME = previousHome;
  }
});

test("only the latest assistant message determines model failure", () => {
  const error = { type: "message_end", role: "worker", message: { role: "assistant", stopReason: "error", errorMessage: "controlled-error" } };
  const success = { type: "message_end", role: "worker", message: { role: "assistant", stopReason: "stop" } };
  assert.equal(latestAssistantError([error, success], "worker"), null);
  assert.equal(latestAssistantError([success, error], "worker"), "controlled-error");
});

test("an explicitly small timeout still aborts cleanly", async () => {
  let finish;
  let aborted = false;
  const session = {
    prompt: () => new Promise((resolve) => { finish = resolve; }),
    abort: async () => { aborted = true; finish(); },
  };
  const result = await promptWithTimeout(session, "test", 10, "controlled timeout", 100);
  assert.equal(result.timedOut, true);
  assert.equal(result.aborted, true);
  assert.equal(aborted, true);
});
