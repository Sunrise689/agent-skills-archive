import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

export function resolvePiRoot() {
  const entrypoint = fileURLToPath(import.meta.resolve("@mariozechner/pi-coding-agent"));
  return path.resolve(path.dirname(entrypoint), "..");
}

export function resolvePython() {
  return process.env.SMART_AGENT_PYTHON || (process.platform === "win32" ? "python" : "python3");
}

export function defaultConfigDir() {
  if (process.env.SMART_AGENT_HOME) return path.resolve(process.env.SMART_AGENT_HOME);
  const preferred = process.env.APPDATA ? path.join(process.env.APPDATA, "smart-agent") : path.join(os.homedir(), ".smart-agent");
  const legacy = path.join(os.homedir(), ".smart-agent");
  // Preserve pre-APPDATA installations without maintaining two active homes.
  if (path.resolve(preferred) !== path.resolve(legacy) && !fs.existsSync(path.join(preferred, "config.json")) && fs.existsSync(path.join(legacy, "config.json"))) return legacy;
  return path.resolve(preferred);
}

export function defaultRunRoot() {
  return path.join(defaultConfigDir(), "runs");
}

export function defaultSpiralRoot() {
  return path.join(defaultConfigDir(), "spiral");
}

export function defaultExplorationRoot() {
  return path.join(defaultConfigDir(), "explorations");
}

export function ensureDirectory(directory) {
  fs.mkdirSync(directory, { recursive: true });
  return directory;
}

export function userFacingPath(file) {
  return path.resolve(file);
}
