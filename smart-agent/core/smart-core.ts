import { Type } from "typebox";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawn } from "node:child_process";

const ROOT = process.env.SMART_AGENT_ROOT;
const WORKSPACE = process.env.SMART_AGENT_WORKSPACE;
const STATE_DIR = process.env.SMART_AGENT_STATE_DIR;
const TRACE_FILE = process.env.SMART_AGENT_TRACE_FILE;
const FINISH_FILE = process.env.SMART_AGENT_FINISH_FILE;
const PY = process.env.SMART_AGENT_PY || "py";
const FREEZE = process.env.SMART_AGENT_FREEZE === "1";

if (!ROOT || !WORKSPACE || !STATE_DIR || !TRACE_FILE || !FINISH_FILE) {
	throw new Error("smart-core requires SMART_AGENT_ROOT/WORKSPACE/STATE_DIR/TRACE_FILE/FINISH_FILE");
}

const STRATEGY_FILE = path.join(STATE_DIR, "strategy.json");
const PREVIOUS_FILE = path.join(STATE_DIR, "strategy.previous.json");
const STEP_TOOL = {
	inspect: "workspace_read",
	patch: "workspace_write",
	public_check: "run_public_checks",
	revise: "workspace_write",
	submit: "finish_task",
};
const ALLOWED_STEPS = new Set(Object.keys(STEP_TOOL));

function readJson(file) {
	return JSON.parse(fs.readFileSync(file, "utf8"));
}

function writeJson(file, value) {
	fs.mkdirSync(path.dirname(file), { recursive: true });
	const temp = `${file}.tmp`;
	fs.writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, "utf8");
	fs.renameSync(temp, file);
}

function hashCandidate(parentHash, steps) {
	return crypto.createHash("sha256").update(JSON.stringify({ parentHash, steps })).digest("hex").slice(0, 16);
}

function trace(event) {
	fs.mkdirSync(path.dirname(TRACE_FILE), { recursive: true });
	fs.appendFileSync(TRACE_FILE, `${JSON.stringify({ ts: new Date().toISOString(), ...event })}\n`, "utf8");
}

function textResult(text, details = {}, extra = {}) {
	return { content: [{ type: "text", text }], details, ...extra };
}

function runPublicTest() {
	return new Promise((resolve) => {
		const child = spawn(PY, ["public_test.py"], {
			cwd: WORKSPACE,
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
			resolve({ passed: code === 0, code, output: output.slice(-5000) });
		});
	});
}

export default function smartCore(pi) {
	let active = readJson(STRATEGY_FILE);
	let cursor = 0;
	let hasRead = false;
	let hasWrite = false;
	let lastCheck = null;

	function remainingTools() {
		const tools = new Set();
		const currentStep = active.steps[cursor];
		if (STEP_TOOL[currentStep]) tools.add(STEP_TOOL[currentStep]);
		if (!FREEZE) tools.add("submit_strategy");
		return [...tools];
	}

	function syncTools(source) {
		const tools = remainingTools();
		trace({ event: "tools_sync", source, strategy_hash: active.hash, cursor, next_steps: active.steps.slice(cursor), permitted_tools: tools, enforcement: "tool_call" });
	}

	function toolStepIndex(toolName) {
		return STEP_TOOL[active.steps[cursor]] === toolName ? cursor : -1;
	}

	pi.on("before_agent_start", async (event) => {
		active = readJson(STRATEGY_FILE);
		cursor = 0;
		syncTools("before_agent_start");
		const knowledge = fs.readFileSync(path.join(ROOT, "knowledge.md"), "utf8");
		trace({ event: "agent_start", strategy_hash: active.hash, strategy_version: active.version, steps: active.steps, freeze: FREEZE });
		return {
			systemPrompt: `${event.systemPrompt}\n\n${knowledge}\n\n当前执行策略（由壳强制执行，不只是建议）：${JSON.stringify(active.steps)}\n你只能使用当前步骤对应的工具；完成该步后才进入下一步，不能跳步或倒退。`,
		};
	});

	pi.on("tool_call", async (event) => {
		if (event.toolName === "submit_strategy") {
			trace({ event: "tool_call", tool: event.toolName, allowed: !FREEZE, strategy_hash: active.hash, cursor });
			return FREEZE ? { block: true, reason: "Strategy is frozen for this replay" } : undefined;
		}
		const index = toolStepIndex(event.toolName);
		const allowed = index >= 0;
		trace({
			event: "tool_call",
			tool: event.toolName,
			allowed,
			strategy_hash: active.hash,
			cursor,
			matched_step: allowed ? active.steps[index] : null,
			matched_index: index,
		});
		if (!allowed) {
			return { block: true, reason: `Current strategy ${active.steps.join(" -> ")} does not allow ${event.toolName} after step ${cursor}` };
		}
		if (event.toolName === "finish_task" && (!hasRead || !hasWrite)) {
			trace({ event: "finish_blocked", reason: "read_and_write_required", strategy_hash: active.hash });
			return { block: true, reason: "Read and modify solution.py before finishing" };
		}
		return undefined;
	});

	pi.on("tool_result", async (event) => {
		trace({
			event: "tool_result",
			tool: event.toolName,
			is_error: event.isError,
			strategy_hash: active.hash,
			cursor,
			details: event.details ?? null,
		});
		if (event.toolName === "run_public_checks" && event.details) {
			lastCheck = event.details.passed === true;
		}
		if (event.isError || event.toolName === "submit_strategy" || event.toolName === "finish_task") return;
		if (event.toolName === "workspace_read") hasRead = true;
		if (event.toolName === "workspace_write") hasWrite = true;
		const index = toolStepIndex(event.toolName);
		if (index >= 0) {
			cursor = index + 1;
			syncTools("tool_result");
		}
	});

	pi.registerTool({
		name: "workspace_read",
		label: "Read solution",
		description: "Read the current task's solution.py. No other path is available.",
		promptSnippet: "Read solution.py",
		parameters: Type.Object({}),
		executionMode: "sequential",
		async execute() {
			try {
				const content = fs.readFileSync(path.join(WORKSPACE, "solution.py"), "utf8");
				return textResult(content, { file: "solution.py", bytes: Buffer.byteLength(content) });
			} catch (error) {
				return textResult(`Read failed: ${error}`, { passed: false }, { isError: true });
			}
		},
	});

	pi.registerTool({
		name: "workspace_write",
		label: "Write solution",
		description: "Replace only solution.py with the complete corrected source. Cannot modify tests, strategy, runner, or any other file.",
		promptSnippet: "Replace solution.py with corrected source",
		parameters: Type.Object({ content: Type.String({ description: "Complete new solution.py source" }) }),
		executionMode: "sequential",
		async execute(_id, params) {
			try {
				fs.writeFileSync(path.join(WORKSPACE, "solution.py"), params.content, "utf8");
				const readBack = fs.readFileSync(path.join(WORKSPACE, "solution.py"), "utf8");
				return textResult(`solution.py written (${Buffer.byteLength(readBack)} bytes)`, { file: "solution.py", bytes: Buffer.byteLength(readBack), read_back_changed: readBack === params.content });
			} catch (error) {
				return textResult(`Write failed: ${error}`, { passed: false }, { isError: true });
			}
		},
	});

	pi.registerTool({
		name: "run_public_checks",
		label: "Run public checks",
		description: "Run the fixed public_test.py. A failed test is feedback, not a tool transport error.",
		promptSnippet: "Run the fixed public tests",
		parameters: Type.Object({}),
		executionMode: "sequential",
		async execute() {
			const result = await runPublicTest();
			lastCheck = result.passed;
			return textResult(`PUBLIC_CHECK ${result.passed ? "PASS" : "FAIL"}\n${result.output}`, result);
		},
	});

	pi.registerTool({
		name: "submit_strategy",
		label: "Submit strategy",
		description: "Persist a candidate linear execution strategy for the NEXT fresh session. Use only predefined steps: inspect, patch, public_check, revise, submit. Add missing verification/revision capability when evidence shows the current shell is insufficient.",
		promptSnippet: "Improve the next session's execution strategy",
		parameters: Type.Object({
			steps: Type.Array(Type.String(), { minItems: 2, maxItems: 10 }),
			reason: Type.String({ description: "Evidence-based reason for this structural change" }),
		}),
		executionMode: "sequential",
		async execute(_id, params) {
			if (FREEZE) return textResult("Strategy is frozen", { accepted: false }, { isError: true });
			const valid = params.steps.every((step) => ALLOWED_STEPS.has(step))
				&& params.steps[0] === "inspect"
				&& params.steps.at(-1) === "submit"
				&& params.steps.includes("public_check")
				&& (params.steps.includes("patch") || params.steps.includes("revise"));
			if (!valid) {
				return textResult("Rejected: use inspect first, submit last, include public_check and patch/revise; only predefined steps are allowed", { accepted: false }, { isError: true });
			}
			const current = readJson(STRATEGY_FILE);
			const candidate = {
				version: Number(current.version || 0) + 1,
				parent_hash: current.hash,
				hash: hashCandidate(current.hash, params.steps),
				steps: params.steps,
				reason: params.reason,
				created_at: new Date().toISOString(),
			};
			writeJson(PREVIOUS_FILE, current);
			writeJson(STRATEGY_FILE, candidate);
			writeJson(path.join(STATE_DIR, "candidates", `${candidate.version}-${candidate.hash}.json`), candidate);
			trace({ event: "strategy_submitted", parent_hash: current.hash, candidate_hash: candidate.hash, steps: candidate.steps, reason: candidate.reason });
			return textResult(`Accepted for next fresh session: ${candidate.hash}`, { accepted: true, candidate, activates: "next_session" });
		},
	});

	pi.registerTool({
		name: "finish_task",
		label: "Finish task",
		description: "Finish after reading and modifying solution.py and using the strategy's available verification steps as needed.",
		promptSnippet: "Finish the current coding task",
		parameters: Type.Object({ summary: Type.String() }),
		executionMode: "sequential",
		async execute(_id, params) {
			writeJson(FINISH_FILE, { finished: true, summary: params.summary, strategy_hash: active.hash, last_check_passed: lastCheck });
			trace({ event: "task_finished", strategy_hash: active.hash, last_check_passed: lastCheck });
			return textResult("Task finished", { finished: true }, { terminate: true });
		},
	});
}
