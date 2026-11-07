import crypto from "node:crypto";

export const TASK_SHAPES = Object.freeze(["instant", "vertical", "horizontal", "hybrid"]);

export function normalizeGraph(design) {
  const steps = Array.isArray(design.steps) ? design.steps : [];
  const nodes = Array.isArray(design.graph?.nodes)
    ? design.graph.nodes
    : steps.map((step, index) => ({
        id: `step-${index + 1}`,
        kind: "step",
        step,
        dependsOn: index > 0 ? [`step-${index}`] : [],
      }));
  return nodes.map((node, index) => ({
    id: String(node.id || `node-${index + 1}`),
    kind: node.kind || "step",
    step: node.step || node.kind,
    goal: node.goal,
    dependsOn: [...(node.dependsOn || node.depends_on || [])].map(String),
    inputs: node.inputs || [],
    acceptance: node.acceptance || design.acceptance || [],
  }));
}

export function graphErrors(design) {
  const shape = design.task_type || design.taskShape;
  if (!TASK_SHAPES.includes(shape)) return [`unsupported task shape: ${shape}`];
  // Instant uses the direct pi executor; its legacy control fields are metadata,
  // not a mandatory multi-node graph.
  if (shape === "instant") return [];
  const nodes = normalizeGraph(design);
  const ids = new Set(nodes.map((node) => node.id));
  const errors = [];
  if (ids.size !== nodes.length) errors.push("graph node IDs must be unique");
  const byId = new Map(nodes.map((node) => [node.id, node]));
  for (const node of nodes) {
    for (const dependency of node.dependsOn) {
      if (!ids.has(dependency)) errors.push(`${node.id} depends on missing node ${dependency}`);
      if (dependency === node.id) errors.push(`${node.id} cannot depend on itself`);
    }
  }
  const visiting = new Set();
  const visited = new Set();
  const visit = (id) => {
    if (visiting.has(id)) return true;
    if (visited.has(id)) return false;
    visiting.add(id);
    const cycle = byId.get(id)?.dependsOn.some(visit) || false;
    visiting.delete(id);
    visited.add(id);
    return cycle;
  };
  if (nodes.some((node) => visit(node.id))) errors.push("graph contains a cycle");
  if (shape === "instant" && nodes.length > 2) errors.push("instant must remain a lightweight one-step/two-step execution");
  if (shape === "vertical" && nodes.some((node) => node.dependsOn.length > 1)) errors.push("vertical graph cannot have fan-in parallel dependencies");
  if (shape === "horizontal" && nodes.filter((node) => node.dependsOn.length === 0).length < 2 && nodes.length > 1) errors.push("horizontal graph requires independent roots");
  return errors;
}

export function readyNodes(design, completed = new Set(), failed = new Set()) {
  if (graphErrors(design).length) return [];
  return normalizeGraph(design).filter((node) => !completed.has(node.id) && !failed.has(node.id) && node.dependsOn.every((dependency) => completed.has(dependency)));
}

export class GraphOrchestrator {
  constructor(design, { maxParallel = 8 } = {}) {
    const errors = graphErrors(design);
    if (errors.length) throw new Error(`Invalid orchestration design: ${errors.join("; ")}`);
    this.design = design;
    this.shape = design.task_type || design.taskShape;
    this.maxParallel = Number.isSafeInteger(maxParallel) && maxParallel > 0 ? maxParallel : 8;
    this.completed = new Set();
    this.failed = new Map();
    this.receipts = new Map();
    this.attempts = new Map();
    this.startedAt = new Date().toISOString();
  }

  async run(executor, { signal, onEvent } = {}) {
    const emit = (event) => onEvent?.({ at: new Date().toISOString(), ...event });
    const nodes = normalizeGraph(this.design);
    while (this.completed.size + this.failed.size < nodes.length) {
      if (signal?.aborted) throw new Error("Orchestration aborted");
      const runnable = readyNodes(this.design, this.completed, new Set(this.failed.keys()));
      if (!runnable.length) {
        const remaining = nodes.filter((node) => !this.completed.has(node.id) && !this.failed.has(node.id));
        if (remaining.every((node) => node.dependsOn.some((dependency) => this.failed.has(dependency)))) {
          for (const node of remaining) this.failed.set(node.id, { blockedByDependency: true });
          break;
        }
        throw new Error("Graph stalled without a ready node");
      }
      const batch = this.shape === "horizontal" || this.shape === "hybrid" ? runnable.slice(0, this.maxParallel) : runnable.slice(0, 1);
      emit({ type: "batch_started", nodeIds: batch.map((node) => node.id) });
      const results = await Promise.all(batch.map(async (node) => {
        const attempt = (this.attempts.get(node.id) || 0) + 1;
        this.attempts.set(node.id, attempt);
        emit({ type: "node_started", nodeId: node.id, attempt });
        try {
          const receipt = await executor(node, { attempt, signal, completed: [...this.completed], receipts: Object.fromEntries(this.receipts) });
          if (!receipt || receipt.ok !== true) throw new Error(receipt?.error || "Node executor did not return ok=true");
          return { node, receipt, attempt };
        } catch (error) {
          return { node, error: error instanceof Error ? error.message : String(error), attempt };
        }
      }));
      for (const result of results) {
        if (result.error) {
          this.failed.set(result.node.id, { error: result.error, attempt: result.attempt });
          emit({ type: "node_failed", nodeId: result.node.id, error: result.error, attempt: result.attempt });
        } else {
          this.completed.add(result.node.id);
          this.receipts.set(result.node.id, result.receipt);
          emit({ type: "node_completed", nodeId: result.node.id, attempt: result.attempt, receipt: result.receipt, checkpoint: this.checkpoint() });
        }
      }
    }
    const consistency = this.checkConsistency();
    return {
      schema: "smart-agent-orchestration-v1",
      runId: crypto.randomUUID(),
      shape: this.shape,
      status: this.failed.size === 0 && consistency.ok ? "completed" : "failed",
      completed: [...this.completed],
      failed: Object.fromEntries(this.failed),
      receipts: Object.fromEntries(this.receipts),
      attempts: Object.fromEntries(this.attempts),
      consistency,
      startedAt: this.startedAt,
      endedAt: new Date().toISOString(),
    };
  }

  checkConsistency() {
    const expected = normalizeGraph(this.design).filter((node) => node.kind === "join" || node.kind === "merge");
    for (const node of expected) {
      const receipt = this.receipts.get(node.id);
      if (!receipt || receipt.consistent !== true) return { ok: false, nodeId: node.id, reason: "join did not provide consistent=true" };
    }
    return { ok: this.failed.size === 0, checkedJoins: expected.map((node) => node.id) };
  }

  checkpoint() {
    return {
      schema: "smart-agent-orchestration-checkpoint-v1",
      shape: this.shape,
      design: this.design,
      completed: [...this.completed],
      failed: Object.fromEntries(this.failed),
      receipts: Object.fromEntries(this.receipts),
      attempts: Object.fromEntries(this.attempts),
      startedAt: this.startedAt,
    };
  }

  static restore(checkpoint, { retryFailed = true } = {}) {
    const orchestrator = new GraphOrchestrator(checkpoint.design);
    orchestrator.completed = new Set(checkpoint.completed || []);
    orchestrator.failed = retryFailed ? new Map() : new Map(Object.entries(checkpoint.failed || {}));
    orchestrator.receipts = new Map(Object.entries(checkpoint.receipts || {}));
    orchestrator.attempts = new Map(Object.entries(checkpoint.attempts || {}));
    orchestrator.startedAt = checkpoint.startedAt || orchestrator.startedAt;
    return orchestrator;
  }
}
