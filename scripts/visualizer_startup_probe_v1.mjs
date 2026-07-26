export const VISUALIZER_STARTUP_FAILURE_CODES = Object.freeze([
  "legacy_protocol_missing",
  "data_load_failed",
  "ready_handshake_rejected",
  "ready_timeout",
]);

const FAILURE_CODES = new Set(VISUALIZER_STARTUP_FAILURE_CODES);

export class VisualizerStartupFailureError extends Error {
  constructor(code, game) {
    super(`visualizer_startup_failed code=${code} game=${game}`);
    this.name = "VisualizerStartupFailureError";
    this.code = code;
    this.game = game;
  }
}

export function isVisualizerStartupFailureError(error) {
  return error instanceof VisualizerStartupFailureError;
}

export function visualizerStartupFailure(snapshot) {
  const code = String(snapshot?.visualizerStartupFailureCode ?? "");
  if (!FAILURE_CODES.has(code)) return null;
  const rawGame = String(snapshot?.visualizerStartupGame ?? "");
  return {
    code,
    game: rawGame === "hsr" || rawGame === "zzz" ? rawGame : "unknown",
  };
}

export function throwIfVisualizerStartupFailed(snapshot) {
  const failure = visualizerStartupFailure(snapshot);
  if (failure) throw new VisualizerStartupFailureError(failure.code, failure.game);
}

export function visualizerStartupStageReady(snapshot, expectedGame) {
  throwIfVisualizerStartupFailed(snapshot);
  return snapshot?.visualizerStartupState === "ready"
    && snapshot?.visualizerStartupFailureCode === ""
    && snapshot?.visualizerStartupGame === expectedGame;
}

export async function waitForVisualizerStartupStage({
  description,
  game,
  timeoutMs,
  probe,
  accept = () => true,
  intervalMs = 150,
  now = () => Date.now(),
  sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds)),
}) {
  if (game !== "hsr" && game !== "zzz") throw new TypeError("Visualizer startup game is invalid");
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs <= 0) {
    throw new TypeError("Visualizer startup timeout must be a positive safe integer");
  }
  if (!Number.isSafeInteger(intervalMs) || intervalMs <= 0) {
    throw new TypeError("Visualizer startup polling interval must be a positive safe integer");
  }
  if (typeof probe !== "function" || typeof accept !== "function"
    || typeof now !== "function" || typeof sleep !== "function") {
    throw new TypeError("Visualizer startup polling callbacks are invalid");
  }

  const deadline = now() + timeoutMs;
  let lastError;
  while (now() < deadline) {
    try {
      const snapshot = await probe();
      if (visualizerStartupStageReady(snapshot, game) && await accept(snapshot)) return snapshot;
    } catch (error) {
      if (isVisualizerStartupFailureError(error)) throw error;
      lastError = error;
    }
    await sleep(intervalMs);
  }
  const suffix = lastError instanceof Error ? `; last error: ${lastError.message}` : "";
  throw new Error(`timed out waiting for ${description}${suffix}`);
}
