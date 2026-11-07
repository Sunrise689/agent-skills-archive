const DAY_MS = 24 * 60 * 60 * 1000;

// Product safety ceilings, not per-task targets. Providers may impose their own
// smaller context/output limits; those external limits remain explicit errors.
export const RUNTIME_LIMITS = Object.freeze({
  maxOutputTokens: 1_000_000,
  maxDesignTextChars: 1_000_000,
  maxDesignItems: 10_000,
  maxManagerAttempts: 32,
  maxWorkerTurns: 4096,
  promptTimeoutMs: DAY_MS,
  reviewerTimeoutMs: DAY_MS,
  abortTimeoutMs: 60_000,
  providerRetries: 32,
  maxTraceExcerptChars: 1_000_000,
});
