import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

export const INITIAL_EVOLUTION_POLICY = {
  steps: ["inspect", "patch", "public_check", "submit"],
  worker_model: "glm-5.3-flash",
  reviewer_model: "none",
  rationale: "Initial minimal loop; the manager must explicitly design each next episode.",
  method_refs: [],
  integration_requests: [],
};

export function policySignature(design, parentPolicy) {
  return {
    steps: [...design.steps],
    worker_model: design.worker_model,
    reviewer_model: design.reviewer_model,
    rationale: design.rationale,
    method_refs: design.method_refs || [],
    integration_requests: design.integration_requests || [],
    method_composition: design.method_composition || [],
    parent: parentPolicy ? {
      steps: [...parentPolicy.steps],
      worker_model: parentPolicy.worker_model,
      reviewer_model: parentPolicy.reviewer_model,
      method_refs: parentPolicy.method_refs || [],
      integration_requests: parentPolicy.integration_requests || [],
      method_composition: parentPolicy.method_composition || [],
    } : null,
  };
}

const STEP_TOOL = {
  inspect: "workspace_read",
  patch: "workspace_write",
  public_check: "run_public_test",
  review: "review_code",
  revise: "revise_solution",
  submit: "finish_task",
};

function textResult(text, details = {}, isError = false) {
  return { content: [{ type: "text", text }], details, isError };
}

export function createEvolutionExtension(design) {
  const state = {
    design,
    cursor: 0,
    phase: "running",
    hasRead: false,
    hasWrite: false,
    hasCheck: false,
    hasReview: false,
    publicPassed: null,
  };
  const currentStep = () => design.steps[state.cursor] || null;
  const currentTool = () => STEP_TOOL[currentStep()] || null;
  return {
    state,
    async handleToolCall(event) {
      if (state.phase !== "running") return { block: true, reason: "Task already submitted" };
      if (event.toolName !== currentTool()) {
        return { block: true, reason: `Design expects ${currentStep()} (${currentTool()}), not ${event.toolName}` };
      }
      if (event.toolName === "finish_task") {
        const missing = [];
        if (!state.hasRead) missing.push("read");
        if (!state.hasWrite) missing.push("write");
        if (!state.hasCheck) missing.push("public_check");
        if (design.steps.includes("review") && !state.hasReview) missing.push("review");
        if (missing.length) return { block: true, reason: `Missing evidence: ${missing.join(", ")}` };
      }
      return undefined;
    },
    async handleToolResult(event) {
      if (event.isError) return undefined;
      if (event.toolName === "workspace_read") state.hasRead = true;
      if (["workspace_write", "revise_solution"].includes(event.toolName)) state.hasWrite = true;
      if (event.toolName === "run_public_test") {
        state.hasCheck = true;
        state.publicPassed = !event.isError && JSON.stringify(event.result || {}).includes("PASS");
      }
      if (event.toolName === "review_code") state.hasReview = true;
      if (event.toolName === currentTool()) state.cursor += 1;
      if (event.toolName === "finish_task") state.phase = "submitted";
      return undefined;
    },
  };
}

function runPublicTest(cwd) {
  return new Promise((resolve) => {
    const child = spawn("C:/Python312/python.exe", ["public_test.py"], {
      cwd,
      env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8" },
      windowsHide: true,
    });
    let output = "";
    const timer = setTimeout(() => child.kill(), 20000);
    child.stdout.on("data", (chunk) => { output += chunk.toString(); });
    child.stderr.on("data", (chunk) => { output += chunk.toString(); });
    child.on("error", (error) => {
      clearTimeout(timer);
      resolve({ passed: false, code: -1, output: String(error) });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({ passed: code === 0, code, output: output.slice(-6000) });
    });
  });
}

export function evolutionActions(host, events, state) {
  const safeFile = (requested) => {
    if (requested !== "solution.py" && requested !== "public_test.py") throw new Error("Only solution.py and public_test.py are accessible");
    return path.join(host.cwd, requested);
  };
  const writeSolution = (content) => {
    if (typeof content !== "string" || !content.trim()) {
      return textResult("solution.py content must be non-empty", {}, true);
    }
    fs.writeFileSync(path.join(host.cwd, "solution.py"), content, "utf8");
    const readBack = fs.readFileSync(path.join(host.cwd, "solution.py"), "utf8");
    return textResult("solution.py written", { read_back_changed: readBack === content, bytes: Buffer.byteLength(readBack) });
  };
  return {
    getState: () => ({ ...state }),
    readFile: async ({ path: requested }) => {
      try {
        const content = fs.readFileSync(safeFile(requested), "utf8");
        return textResult(content, { file: requested, bytes: Buffer.byteLength(content) });
      } catch (error) {
        return textResult(String(error), {}, true);
      }
    },
    writeFile: async ({ path: requested, content }) => {
      try {
        if (requested !== "solution.py") throw new Error("Only solution.py can be written");
        return writeSolution(content);
      } catch (error) {
        return textResult(String(error), {}, true);
      }
    },
    reviseSolution: async ({ content }) => {
      try { return writeSolution(content); } catch (error) { return textResult(String(error), {}, true); }
    },
    runPublicTest: async () => {
      const check = await runPublicTest(host.cwd);
      events.push({ type: "public_check", ...check });
      return textResult(`PUBLIC_CHECK ${check.passed ? "PASS" : "FAIL"}\n${check.output}`, check, !check.passed);
    },
    reviewCode: async () => textResult("Reviewer is not connected", {}, true),
    finishTask: async ({ summary }) => {
      state.phase = "submitted";
      return textResult("Task finished", { finished: true, summary });
    },
  };
}
