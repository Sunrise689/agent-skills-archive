import path from "node:path";
import { pathToFileURL } from "node:url";
import { resolvePiRoot } from "./paths.mjs";
import { RUNTIME_LIMITS } from "./runtime-policy.mjs";

export const BASE_TOOLS = Object.freeze(["read", "bash", "edit", "write", "grep", "find", "ls"]);

let cached;
export async function loadPi() {
  if (!cached) {
    const root = resolvePiRoot();
    const [pi, fileProcessor] = await Promise.all([
      import(pathToFileURL(path.join(root, "dist", "index.js")).href),
      import(pathToFileURL(path.join(root, "dist", "cli", "file-processor.js")).href),
    ]);
    cached = { root, pi, fileProcessor };
  }
  return cached;
}

export function toolRegistry(cwd) {
  return BASE_TOOLS.map((name) => ({
    name,
    capability: name === "bash" ? "command" : ["edit", "write"].includes(name) ? "file-write" : "file-read",
    workspace: cwd,
    requiresDesign: false,
    evidence: ["tool", "input", "result", "isError", "attempt"],
    source: "pi-native",
  }));
}

function positiveInteger(value, fallback) {
  return Number.isSafeInteger(value) && value > 0 ? value : fallback;
}

export function outputTokenBudget(provider = {}) {
  const requested = positiveInteger(provider.maxTokens, RUNTIME_LIMITS.maxOutputTokens);
  const contextWindow = positiveInteger(provider.contextWindow, 128000);
  return Math.min(requested, contextWindow);
}

export function createBudgetedStream(streamSimple) {
  return (model, context, options = {}) => streamSimple(model, context, {
    ...options,
    maxTokens: options.maxTokens ?? model.maxTokens,
  });
}

export function modelFromProvider(provider) {
  return {
    id: provider.model,
    name: provider.model,
    api: provider.api || "openai-completions",
    provider: provider.provider || "smart-agent",
    baseUrl: String(provider.baseUrl || "").replace(/\/$/, ""),
    reasoning: provider.reasoning === true,
    input: provider.input || ["text"],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: positiveInteger(provider.contextWindow, 128000),
    maxTokens: outputTokenBudget(provider),
  };
}

function nativeReference(provider = {}) {
  const configuredProvider = provider.piProvider || provider.providerName || (provider.type && provider.type !== "openai-compatible" ? provider.type : "");
  const rawModel = String(provider.model || "").trim();
  if (configuredProvider && rawModel.includes("/") && rawModel.startsWith(`${configuredProvider}/`)) {
    return { provider: configuredProvider, model: rawModel.slice(configuredProvider.length + 1) };
  }
  if (configuredProvider) return { provider: configuredProvider, model: rawModel };
  const slash = rawModel.indexOf("/");
  if (slash > 0) return { provider: rawModel.slice(0, slash), model: rawModel.slice(slash + 1) };
  return { provider: "", model: rawModel };
}

export function resolveNativeModel(modelRegistry, provider = {}) {
  const reference = nativeReference(provider);
  if (!reference.model) return null;
  if (reference.provider) return modelRegistry.find(reference.provider, reference.model) || null;
  const matches = modelRegistry.getAll().filter((model) => model.id === reference.model);
  return matches.length === 1 ? matches[0] : null;
}

export function isNativeProviderConfig(provider = {}) {
  return Boolean(provider.native === true || provider.piProvider || provider.providerName || (provider.type && provider.type !== "openai-compatible"));
}

export function providerForModelSelection(baseProvider, selection, effort = undefined) {
  const model = String(selection || baseProvider.model || "").trim();
  if (!isNativeProviderConfig(baseProvider)) return { ...baseProvider, model };
  const slash = model.indexOf("/");
  return {
    ...baseProvider,
    native: true,
    piProvider: slash > 0 ? model.slice(0, slash) : (baseProvider.piProvider || (String(baseProvider.model || "").includes("/") ? String(baseProvider.model).split("/")[0] : "")),
    model,
    thinkingLevel: effort || baseProvider.thinkingLevel || "off",
  };
}

export async function piCapabilityCatalog(provider = {}) {
  if (!isNativeProviderConfig(provider)) return { native: false, models: [{ ref: provider.model, provider: provider.provider || "smart-agent", id: provider.model, reasoning: provider.reasoning === true, input: provider.input || ["text"] }] };
  const { pi } = await loadPi();
  const authStorage = pi.AuthStorage.create(path.join(pi.getAgentDir(), "auth.json"));
  const registry = pi.ModelRegistry.create(authStorage);
  const current = resolveNativeModel(registry, provider);
  return {
    native: true,
    defaultProvider: current?.provider || provider.piProvider || "",
    models: registry.getAvailable().map((model) => ({
      ref: `${model.provider}/${model.id}`,
      provider: model.provider,
      id: model.id,
      reasoning: model.reasoning === true,
      input: model.input || ["text"],
      contextWindow: model.contextWindow,
    })),
  };
}

export function latestAssistantError(events, role) {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.type !== "message_end" || (role && event.role !== role)) continue;
    const message = event.message;
    if (message?.role === "assistant") return message.stopReason === "error" ? (message.errorMessage || "Model execution failed") : null;
  }
  return null;
}

export async function createBaseSession({ cwd, agentDir, provider, systemPrompt, additionalExtensionPaths = [], tools = BASE_TOOLS }) {
  const { pi } = await loadPi();
  const native = isNativeProviderConfig(provider);
  const authPath = native ? path.join(pi.getAgentDir(), "auth.json") : path.join(agentDir, "auth.json");
  const authStorage = pi.AuthStorage.create(authPath);
  if (!native && provider.apiKeyEnv) authStorage.setRuntimeApiKey("smart-agent", process.env[provider.apiKeyEnv]);
  const modelRegistry = native ? pi.ModelRegistry.create(authStorage) : pi.ModelRegistry.inMemory(authStorage);
  const model = native ? resolveNativeModel(modelRegistry, provider) : modelFromProvider(provider);
  if (!model) {
    const reference = nativeReference(provider);
    throw new Error(`pi 原生模型未找到: ${reference.provider ? `${reference.provider}/` : ""}${reference.model}; 请按 pi 原生方式配置 models.json/auth.json 或选择可用模型`);
  }
  const settingsManager = pi.SettingsManager.inMemory({
    compaction: { enabled: true },
    retry: { enabled: true, maxRetries: RUNTIME_LIMITS.providerRetries },
  });
  const resourceLoader = new pi.DefaultResourceLoader({
    cwd,
    agentDir,
    settingsManager,
    additionalExtensionPaths,
    noSkills: native ? provider.noSkills === true : true,
    noPromptTemplates: native ? provider.noPromptTemplates === true : true,
    noThemes: native ? provider.noThemes === true : true,
    noContextFiles: native ? provider.noContextFiles === true : true,
    systemPrompt,
  });
  await resourceLoader.reload();
  const result = await pi.createAgentSession({
    cwd,
    agentDir,
    model,
    thinkingLevel: provider.thinkingLevel || provider.effort || "off",
    authStorage,
    modelRegistry,
    resourceLoader,
    settingsManager,
    sessionManager: pi.SessionManager.inMemory(cwd),
    tools,
  });
  if (result.extensionsResult.errors.length) throw new Error(JSON.stringify(result.extensionsResult.errors));
  const sdkStream = result.session.agent.streamFn;
  result.session.agent.streamFn = createBudgetedStream(sdkStream);
  return result.session;
}
