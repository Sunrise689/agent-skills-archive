import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { SpiralStore } from "../core/spiral-store.mjs";
import { pauseCruise, stopCruise, resumeCruise } from "../src/cruise.mjs";

test("stopped cruise cannot be woken or resumed", async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "smart-agent-cruise-test-"));
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "smart-agent-cruise-ws-"));
  const jobId = "job-stopped-test";
  const store = new SpiralStore(root);
  store.saveCheckpoint(jobId, { jobId, status: "queued", goal: "test", workspace, provider: { model: "fake-model" } });
  const paused = pauseCruise(jobId, root);
  assert.equal(paused.status, "paused");
  const stopped = stopCruise(jobId, root);
  assert.equal(stopped.status, "stopped");
  await assert.rejects(() => resumeCruise(jobId, { spiralRoot: root, wakeSource: "wake" }), /禁止自动 wake\/resume/);
});
