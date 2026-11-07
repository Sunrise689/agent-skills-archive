import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { addExplorationRound, createExploration, readExploration, updateExplorationStatus } from "../src/exploration.mjs";
import { S_CARD_SYSTEM_PROMPT } from "../src/s-card-system-prompt.mjs";

test("S card prompt names dispatch, cruise, exploration and evidence boundaries", () => {
  assert.match(S_CARD_SYSTEM_PROMPT, /S 卡/);
  assert.match(S_CARD_SYSTEM_PROMPT, /GK-U\/GK-L/);
  assert.match(S_CARD_SYSTEM_PROMPT, /巡航模式/);
  assert.match(S_CARD_SYSTEM_PROMPT, /探索模式/);
  assert.match(S_CARD_SYSTEM_PROMPT, /退出码/);
});

test("exploration state persists two rounds and controlled status changes", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "smart-agent-explore-"));
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "smart-agent-explore-ws-"));
  const initial = createExploration({ question: "compare candidates", workspace, maxRounds: 3, root });
  addExplorationRound(initial.id, { facts: ["a"], hypothesis: "h1", experiment: "e1", result: "r1", nextAction: "e2", evidence: ["a.txt"] }, root);
  addExplorationRound(initial.id, { facts: ["b"], hypothesis: "h2", experiment: "e2", result: "r2", nextAction: "stop", evidence: ["b.txt"] }, root);
  const paused = updateExplorationStatus(initial.id, "paused", "manual pause", root);
  assert.equal(paused.round, 2);
  assert.equal(paused.status, "paused");
  const state = readExploration(initial.id, root);
  assert.equal(state.rounds.length, 2);
  assert.deepEqual(state.facts, ["a", "b"]);
  assert.equal(updateExplorationStatus(initial.id, "active", "resume", root).status, "active");
});

test("exploration rounds reject incomplete six-element evidence", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "smart-agent-explore-gate-"));
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), "smart-agent-explore-gate-ws-"));
  const initial = createExploration({ question: "gated", workspace, root });
  assert.throws(() => addExplorationRound(initial.id, { facts: ["fact"], hypothesis: "h", experiment: "e", result: "r", nextAction: "n", evidence: [] }, root), /六要素/);
  assert.equal(readExploration(initial.id, root).round, 0);
});
