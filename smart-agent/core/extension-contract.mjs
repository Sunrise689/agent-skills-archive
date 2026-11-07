import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

function fail(message) {
  throw new Error(`Invalid extension manifest: ${message}`);
}

function requiredString(value, name) {
  if (typeof value !== "string" || !value.trim()) fail(`${name} must be a non-empty string`);
  return value.trim();
}

function stringArray(value, name) {
  if (!Array.isArray(value) || value.length === 0 || value.some((item) => typeof item !== "string" || !item.trim())) {
    fail(`${name} must be a non-empty string array`);
  }
  return value.map((item) => item.trim());
}

export function digest(value) {
  return crypto.createHash("sha256").update(typeof value === "string" ? value : JSON.stringify(value)).digest("hex").slice(0, 16);
}

export function loadExtensionManifest(root, manifestFile) {
  const absoluteManifest = path.resolve(manifestFile);
  const raw = fs.readFileSync(absoluteManifest, "utf8");
  let manifest;
  try {
    manifest = JSON.parse(raw);
  } catch (error) {
    fail(`manifest JSON cannot be parsed: ${error}`);
  }
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) fail("root must be an object");
  const id = requiredString(manifest.id, "id");
  const version = requiredString(manifest.version, "version");
  const coreCompatibility = requiredString(manifest.core_compatibility, "core_compatibility");
  const entrypoint = requiredString(manifest.entrypoint, "entrypoint");
  const source = requiredString(manifest.source, "source");
  const license = requiredString(manifest.license, "license");
  const capabilities = stringArray(manifest.capabilities, "capabilities");
  const applicableSignals = stringArray(manifest.applicable_signals, "applicable_signals");
  const rollback = requiredString(manifest.rollback, "rollback");
  const rootPath = path.resolve(root);
  const resolvedEntrypoint = path.resolve(rootPath, entrypoint);
  if (resolvedEntrypoint !== rootPath && !resolvedEntrypoint.startsWith(`${rootPath}${path.sep}`)) {
    fail("entrypoint must stay inside the project root");
  }
  if (!fs.existsSync(resolvedEntrypoint) || !fs.statSync(resolvedEntrypoint).isFile()) {
    fail(`entrypoint does not exist: ${entrypoint}`);
  }
  return {
    id,
    version,
    core_compatibility: coreCompatibility,
    entrypoint: resolvedEntrypoint,
    entrypoint_relative: path.relative(rootPath, resolvedEntrypoint),
    source,
    license,
    capabilities,
    applicable_signals: applicableSignals,
    rollback,
    manifest_path: absoluteManifest,
    manifest_hash: digest(raw),
  };
}
