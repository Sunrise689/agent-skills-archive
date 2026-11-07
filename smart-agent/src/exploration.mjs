import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { defaultExplorationRoot, ensureDirectory } from "./paths.mjs";

const idFor = () => `explore-${new Date().toISOString().replaceAll(":", "-")}-${crypto.randomUUID().slice(0, 8)}`;
const fileFor = (id, root = defaultExplorationRoot()) => path.join(root, id, "state.json");

function writeState(file, state) {
  ensureDirectory(path.dirname(file));
  const temporary = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(state, null, 2)}\n`, "utf8");
  fs.renameSync(temporary, file);
}

export function createExploration({ question, workspace, maxRounds = 8, id = idFor(), root = defaultExplorationRoot() }) {
  const now = new Date().toISOString();
  const state = { schema: "smart-agent-exploration-v1", id, question, workspace: path.resolve(workspace), status: "active", round: 0, maxRounds: Math.max(1, Number(maxRounds) || 8), facts: [], hypotheses: [], experiments: [], rounds: [], nextAction: "collect facts", createdAt: now, updatedAt: now };
  writeState(fileFor(id, root), state);
  return state;
}

export function readExploration(id, root = defaultExplorationRoot()) {
  const file = fileFor(id, root);
  if (!fs.existsSync(file)) throw new Error(`Exploration 不存在: ${id}`);
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

export function addExplorationRound(id, input, root = defaultExplorationRoot()) {
  const file = fileFor(id, root);
  const state = readExploration(id, root);
  if (state.status !== "active") throw new Error(`Exploration 当前状态不能添加轮次: ${state.status}`);
  if (state.round >= state.maxRounds) throw new Error(`Exploration 已达到 maxRounds=${state.maxRounds}`);
  const facts = Array.isArray(input.facts) ? input.facts.filter(Boolean) : [];
  const evidence = Array.isArray(input.evidence) ? input.evidence.filter(Boolean) : [];
  const required = {
    facts: facts.length > 0,
    hypothesis: Boolean(String(input.hypothesis || "").trim()),
    experiment: Boolean(String(input.experiment || "").trim()),
    result: Boolean(String(input.result || "").trim()),
    nextAction: Boolean(String(input.nextAction || "").trim()),
    evidence: evidence.length > 0,
  };
  const missing = Object.entries(required).filter(([, present]) => !present).map(([name]) => name);
  if (missing.length) throw new Error(`探索轮次缺少六要素: ${missing.join(", ")}`);
  const round = { number: state.round + 1, facts, hypothesis: String(input.hypothesis).trim(), experiment: String(input.experiment).trim(), result: String(input.result).trim(), nextAction: String(input.nextAction).trim(), evidence, at: new Date().toISOString() };
  state.round = round.number;
  state.rounds.push(round);
  state.facts.push(...round.facts);
  if (round.hypothesis) state.hypotheses.push(round.hypothesis);
  if (round.experiment) state.experiments.push(round.experiment);
  state.nextAction = round.nextAction || "evaluate stopping conditions";
  state.updatedAt = new Date().toISOString();
  writeState(file, state);
  return state;
}

export function explorationSummary(stateOrId, root = defaultExplorationRoot()) {
  const state = typeof stateOrId === "string" ? readExploration(stateOrId, root) : stateOrId;
  if (!state || state.schema !== "smart-agent-exploration-v1") return null;
  return {
    id: state.id,
    question: state.question,
    status: state.status,
    round: state.round,
    maxRounds: state.maxRounds,
    nextAction: state.nextAction,
    facts: state.facts.slice(-24),
    hypotheses: state.hypotheses.slice(-12),
    experiments: state.experiments.slice(-12),
    rounds: state.rounds.slice(-8),
    statusReason: state.statusReason || null,
    updatedAt: state.updatedAt,
  };
}

export function updateExplorationStatus(id, status, reason = "", root = defaultExplorationRoot()) {
  const allowed = new Set(["active", "paused", "stopped", "completed", "blocked"]);
  if (!allowed.has(status)) throw new Error(`未知 exploration 状态: ${status}`);
  const file = fileFor(id, root);
  const state = readExploration(id, root);
  state.status = status;
  if (reason) state.statusReason = reason;
  state.updatedAt = new Date().toISOString();
  writeState(file, state);
  return state;
}
