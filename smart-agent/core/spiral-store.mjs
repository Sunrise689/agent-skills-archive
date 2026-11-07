import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const REDACTED_KEYS = new Set(["apikey", "authorization", "headers", "token", "secret", "password", "credential"]);
const now = () => new Date().toISOString();
const hash = (value) => crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex").slice(0, 16);

function sanitize(value) {
  return JSON.parse(JSON.stringify(value, (key, item) => REDACTED_KEYS.has(key.toLowerCase()) ? "[REDACTED]" : item));
}

function atomicWrite(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temporary = `${file}.${process.pid}.${Date.now()}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
  let lastError;
  for (let attempt = 0; attempt < 20; attempt += 1) {
    try {
      fs.renameSync(temporary, file);
      return;
    } catch (error) {
      lastError = error;
      if (!['EPERM', 'EBUSY', 'EACCES'].includes(error?.code)) throw error;
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 25);
    }
  }
  throw lastError;
}

function readJson(file, fallback) {
  if (!fs.existsSync(file)) return structuredClone(fallback);
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return structuredClone(fallback); }
}

export const EMPTY_SPIRAL_STATE = Object.freeze({
  schema: "smart-agent-spiral-state-v1",
  sequence: 0,
  currentStrategies: {},
  strategies: {},
  runs: {},
  feedback: [],
  promotions: [],
  checkpoints: {},
});

export class SpiralStore {
  constructor(root) {
    this.root = path.resolve(root);
    this.eventsFile = path.join(this.root, "events.jsonl");
    this.stateFile = path.join(this.root, "state.json");
    this.lockFile = path.join(this.root, ".lock");
    fs.mkdirSync(this.root, { recursive: true });
    this.state = readJson(this.stateFile, EMPTY_SPIRAL_STATE);
    if (!this.state.schema) this.state = structuredClone(EMPTY_SPIRAL_STATE);
    this.rebuildIfNeeded();
  }

  rebuildIfNeeded() {
    if (this.state.sequence > 0 || !fs.existsSync(this.eventsFile)) return;
    for (const line of fs.readFileSync(this.eventsFile, "utf8").split(/\r?\n/).filter(Boolean)) {
      try { this.apply(JSON.parse(line), false); } catch { /* preserve the log; an invalid event is reported by inspect */ }
    }
    if (this.state.sequence > 0) atomicWrite(this.stateFile, this.state);
  }

  withLock(action) {
    let fd;
    for (let attempt = 0; fd === undefined; attempt += 1) {
      try {
        fd = fs.openSync(this.lockFile, "wx");
      } catch (error) {
        if (error?.code !== "EEXIST") throw error;
        try {
          if (Date.now() - fs.statSync(this.lockFile).mtimeMs > 60_000) fs.rmSync(this.lockFile, { force: true });
        } catch { /* another process may have released it */ }
        if (attempt >= 3000) throw new Error(`Spiral state lock did not become available: ${this.lockFile}`);
        Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 10);
      }
    }
    try {
      return action();
    } finally {
      fs.closeSync(fd);
      fs.rmSync(this.lockFile, { force: true });
    }
  }

  reloadFromDisk() {
    this.state = readJson(this.stateFile, EMPTY_SPIRAL_STATE);
    this.rebuildIfNeeded();
  }

  apply(event, persist = true) {
    const safe = sanitize({ ...event, schema: event.schema || "smart-agent-spiral-event-v1" });
    if (!safe.type) throw new Error("Spiral event type is required");
    if (!safe.eventId) safe.eventId = `${safe.type}-${Date.now()}-${crypto.randomUUID().slice(0, 8)}`;
    if (!safe.at) safe.at = now();
    if (!safe.sequence) safe.sequence = Number(this.state.sequence || 0) + 1;
    this.state.sequence = Math.max(Number(this.state.sequence || 0), safe.sequence);

    switch (safe.type) {
      case "run_started":
        this.state.runs[safe.runId] = { ...safe, status: "running" };
        break;
      case "run_finished":
        this.state.runs[safe.runId] = { ...(this.state.runs[safe.runId] || {}), ...safe, status: safe.status || "completed" };
        break;
      case "feedback_recorded":
        this.state.feedback.push(safe);
        break;
      case "strategy_candidate": {
        const item = safe.strategy;
        if (!item?.strategyId || !item.version || !item.hash) throw new Error("strategy_candidate requires strategyId/version/hash");
        const bucket = this.state.strategies[item.strategyId] || { strategyId: item.strategyId, versions: {}, current: null };
        bucket.versions[item.hash] = { ...item, status: "candidate" };
        this.state.strategies[item.strategyId] = bucket;
        break;
      }
      case "strategy_promoted": {
        const item = this.state.strategies[safe.strategyId] || { strategyId: safe.strategyId, versions: {}, current: null };
        const version = item.versions[safe.versionHash];
        if (version) version.status = "promoted";
        item.current = safe.versionHash;
        this.state.strategies[safe.strategyId] = item;
        this.state.currentStrategies[safe.strategyId] = safe.versionHash;
        this.state.promotions.push(safe);
        break;
      }
      case "strategy_rolled_back": {
        const item = this.state.strategies[safe.strategyId];
        if (!item?.versions?.[safe.versionHash]) throw new Error(`Unknown rollback target: ${safe.strategyId}/${safe.versionHash}`);
        item.current = safe.versionHash;
        this.state.currentStrategies[safe.strategyId] = safe.versionHash;
        this.state.promotions.push(safe);
        break;
      }
      case "checkpoint_saved":
        this.state.checkpoints[safe.jobId] = safe.checkpoint;
        break;
      case "checkpoint_cleared":
        delete this.state.checkpoints[safe.jobId];
        break;
      default:
        break;
    }

    if (persist) {
      fs.mkdirSync(this.root, { recursive: true });
      fs.appendFileSync(this.eventsFile, `${JSON.stringify(safe)}\n`, "utf8");
      atomicWrite(this.stateFile, this.state);
    }
    return safe;
  }

  append(type, payload = {}) {
    return this.withLock(() => {
      this.reloadFromDisk();
      return this.apply({ type, ...payload });
    });
  }

  startRun(runId, meta = {}) {
    return this.append("run_started", { runId, ...meta });
  }

  finishRun(runId, status, meta = {}) {
    return this.append("run_finished", { runId, status, ...meta });
  }

  recordFeedback(runId, feedback) {
    return this.append("feedback_recorded", { runId, feedback: sanitize(feedback) });
  }

  candidate(strategy, runId) {
    const clean = sanitize(strategy);
    const strategyId = clean.strategyId || "default-loop";
    const version = Number(clean.version || 1);
    const parentHash = clean.parentHash || null;
    const versionBody = { ...clean, strategyId, version, parentHash, createdAt: clean.createdAt || now() };
    const versionHash = clean.hash || hash(versionBody);
    const record = { ...versionBody, strategyId, version, hash: versionHash, runId };
    return this.append("strategy_candidate", { strategy: record });
  }

  promote(strategyId, versionHash, runId, evidence = {}) {
    return this.append("strategy_promoted", { strategyId, versionHash, runId, evidence: sanitize(evidence) });
  }

  rollback(strategyId, versionHash, runId, reason) {
    return this.append("strategy_rolled_back", { strategyId, versionHash, runId, reason });
  }

  saveCheckpoint(jobId, checkpoint) {
    return this.append("checkpoint_saved", { jobId, checkpoint: sanitize({ ...checkpoint, updatedAt: now() }) });
  }

  clearCheckpoint(jobId) {
    return this.append("checkpoint_cleared", { jobId });
  }

  getStrategy(strategyId = "default-loop") {
    const item = this.state.strategies[strategyId];
    if (!item) return null;
    return item.current ? item.versions[item.current] || null : null;
  }

  listStrategies() {
    return Object.values(this.state.strategies).map((item) => ({ strategyId: item.strategyId, current: item.current, versions: Object.values(item.versions) }));
  }

  listRuns() {
    return Object.values(this.state.runs).sort((a, b) => String(b.startedAt || b.at).localeCompare(String(a.startedAt || a.at)));
  }

  getCheckpoint(jobId) {
    return this.state.checkpoints[jobId] || null;
  }

  snapshot() {
    return structuredClone(this.state);
  }
}

export function defaultSpiralStore(root) {
  return new SpiralStore(root);
}

export { hash as spiralHash, sanitize as sanitizeSpiralValue };
