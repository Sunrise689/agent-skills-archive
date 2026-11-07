import { RUNTIME_LIMITS } from "../src/runtime-policy.mjs";

export async function promptWithTimeout(session, prompt, timeoutMs = RUNTIME_LIMITS.promptTimeoutMs, label, abortTimeoutMs = RUNTIME_LIMITS.abortTimeoutMs, promptOptions = undefined) {
  let timer;
  let timedOut = false;
  const operation = session.prompt(prompt, promptOptions);
  try {
    await Promise.race([
      operation,
      new Promise((_, reject) => {
        timer = setTimeout(() => { timedOut = true; reject(new Error(`${label} timeout`)); }, timeoutMs);
      }),
    ]);
    return { error: null, timedOut: false, aborted: false, abortError: null };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (!timedOut) return { error: message, timedOut: false, aborted: false, abortError: null };
    let abortTimer;
    try {
      await Promise.race([
        session.abort(),
        new Promise((_, reject) => { abortTimer = setTimeout(() => reject(new Error(`${label} abort timeout`)), abortTimeoutMs); }),
      ]);
      await operation.catch(() => {});
      return { error: message, timedOut: true, aborted: true, abortError: null };
    } catch (abortError) {
      return { error: message, timedOut: true, aborted: false, abortError: abortError instanceof Error ? abortError.message : String(abortError) };
    } finally {
      if (abortTimer) clearTimeout(abortTimer);
    }
  } finally {
    if (timer) clearTimeout(timer);
  }
}
