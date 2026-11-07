import fs from "node:fs";
import path from "node:path";
import { defaultConfigDir, ensureDirectory } from "./paths.mjs";
import { RUNTIME_LIMITS } from "./runtime-policy.mjs";

const DEFAULT_CONFIG = {
  version: 3,
  // Native pi selection. Credentials and model definitions remain owned by pi.
  pi: {
    provider: "",
    model: "",
    thinkingLevel: "off",
  },
  // Legacy compatibility shim for v1/v2 installations. New configuration should
  // use pi.* or the pi-native models.json/auth.json path instead.
  provider: {
    type: "openai-compatible",
    baseUrl: "",
    model: "",
    apiKeyEnv: "SMART_AGENT_API_KEY",
    input: ["text", "image"],
    contextWindow: 128000,
    maxTokens: RUNTIME_LIMITS.maxOutputTokens,
  },
  plugins: {},
};

function nonEmpty(value) {
  return typeof value === "string" && value.trim().length > 0;
}

export function configPath() {
  return path.join(defaultConfigDir(), "config.json");
}

export function loadConfig({ required = true } = {}) {
  const file = configPath();
  if (!fs.existsSync(file)) {
    if (required) throw new Error(`尚未初始化配置。先运行 smart-agent config init，再按 pi 原生方式配置模型，或使用旧版 provider.* 兼容字段。配置文件：${file}`);
    return structuredClone(DEFAULT_CONFIG);
  }
  const config = JSON.parse(fs.readFileSync(file, "utf8"));
  const provider = { ...DEFAULT_CONFIG.provider, ...(config.provider || {}) };
  const pi = { ...DEFAULT_CONFIG.pi, ...(config.pi || {}) };
  // Version 1 always wrote 4096 as its implicit default and offered no CLI to
  // customize it. Migrate that value without overriding later explicit choices.
  if (Number(config.version || 1) < 2 && provider.maxTokens === 4096) provider.maxTokens = RUNTIME_LIMITS.maxOutputTokens;
  return {
    ...structuredClone(DEFAULT_CONFIG),
    ...config,
    version: Math.max(3, Number(config.version) || 3),
    pi,
    provider,
    plugins: { ...(config.plugins || {}) },
  };
}

export function saveConfig(config) {
  ensureDirectory(defaultConfigDir());
  const file = configPath();
  const temporary = `${file}.${process.pid}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(config, null, 2)}\n`, { encoding: "utf8", mode: 0o600 });
  fs.renameSync(temporary, file);
  return file;
}

export function validateProvider(config, { requireKey = true } = {}) {
  const pi = config.pi || {};
  const provider = config.provider || {};
  const errors = [];
  if (nonEmpty(pi.model)) {
    if (!nonEmpty(pi.provider) && !pi.model.includes("/")) errors.push("pi.provider 未配置；或将 pi.model 写成 provider/model");
    if (pi.thinkingLevel !== undefined && !["off", "minimal", "low", "medium", "high", "xhigh"].includes(pi.thinkingLevel)) errors.push("pi.thinkingLevel 不是 pi 支持的档位");
    return errors;
  }
  // Legacy compatibility path. It remains valid for existing installations and
  // local OpenAI-compatible gateways, but is no longer the product's primary path.
  if (provider.type !== "openai-compatible") errors.push("旧版兼容 provider.type 目前仅接受 openai-compatible；第三方模型请走 pi 原生配置");
  if (!nonEmpty(provider.baseUrl)) errors.push("尚未选择 pi 原生模型，且 provider.baseUrl 未配置");
  if (!nonEmpty(provider.model)) errors.push("尚未选择 pi 原生模型，且 provider.model 未配置");
  if (!nonEmpty(provider.apiKeyEnv)) errors.push("provider.apiKeyEnv 未配置");
  if (requireKey && nonEmpty(provider.apiKeyEnv) && !nonEmpty(process.env[provider.apiKeyEnv])) {
    errors.push(`请通过环境变量 ${provider.apiKeyEnv} 提供模型凭证；不要把密钥写入 config.json`);
  }
  if (!Array.isArray(provider.input) || provider.input.some((item) => !["text", "image"].includes(item))) errors.push("provider.input 只能包含 text/image");
  for (const field of ["contextWindow", "maxTokens"]) {
    if (!Number.isSafeInteger(provider[field]) || provider[field] <= 0) errors.push(`provider.${field} 必须是正整数`);
  }
  return errors;
}

export function effectiveRuntimeConfig(config, overrides = {}) {
  const native = {
    ...(config.pi || {}),
    ...(overrides.pi || {}),
  };
  if (nonEmpty(overrides.model)) native.model = overrides.model;
  if (nonEmpty(overrides.provider)) native.provider = overrides.provider;
  if (nonEmpty(overrides.thinkingLevel)) native.thinkingLevel = overrides.thinkingLevel;
  if (nonEmpty(native.model)) return { ...config, pi: native };
  return { ...config, provider: { ...(config.provider || {}), ...(overrides.providerConfig || {}) } };
}

export function runtimeProvider(config, overrides = {}) {
  const effective = effectiveRuntimeConfig(config, overrides);
  if (nonEmpty(effective.pi?.model)) {
    return {
      piProvider: effective.pi.provider,
      model: effective.pi.model,
      thinkingLevel: effective.pi.thinkingLevel || "off",
      native: true,
      input: effective.provider?.input || ["text", "image"],
    };
  }
  return { ...effective.provider, native: false };
}

export function redactConfig(config) {
  const copy = structuredClone(config);
  if (copy.provider) delete copy.provider.apiKey;
  if (copy.pi) delete copy.pi.apiKey;
  return copy;
}
