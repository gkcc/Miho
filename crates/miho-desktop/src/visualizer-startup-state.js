export const VISUALIZER_STARTUP_STATUS = Object.freeze({
  IDLE: "idle",
  PENDING: "pending",
  READY: "ready",
  FAILED: "failed",
});

export const VISUALIZER_STARTUP_CODE = Object.freeze({
  LEGACY_PROTOCOL_MISSING: "legacy_protocol_missing",
  DATA_LOAD_FAILED: "data_load_failed",
  READY_HANDSHAKE_REJECTED: "ready_handshake_rejected",
  READY_TIMEOUT: "ready_timeout",
});

const REVISION_PATTERN = /^[a-f0-9]{64}$/;

function nextGeneration(state) {
  if (!Number.isSafeInteger(state.generation) || state.generation < 0) {
    throw new TypeError("Visualizer startup generation must be a non-negative safe integer.");
  }
  if (state.generation === Number.MAX_SAFE_INTEGER) {
    throw new RangeError("Visualizer startup generation is exhausted.");
  }
  return state.generation + 1;
}

function requireIdentity(identity) {
  if (typeof identity.navigation_id !== "string" || identity.navigation_id.length === 0) {
    throw new TypeError("Visualizer startup navigation_id must be a non-empty string.");
  }
  if (typeof identity.data_revision !== "string"
    || !REVISION_PATTERN.test(identity.data_revision)) {
    throw new TypeError("Visualizer startup data_revision must be a lowercase SHA-256 digest.");
  }
  if (typeof identity.src !== "string" || identity.src.length === 0) {
    throw new TypeError("Visualizer startup src must be a non-empty string.");
  }
}

function result(state, outcome) {
  return Object.freeze({
    outcome,
    status: state.status,
    code: state.code,
    generation: state.generation,
    navigation_id: state.navigation_id,
    data_revision: state.data_revision,
    src: state.src,
    frame_loaded: state.frame_loaded,
    initializing_seen: state.initializing_seen,
  });
}

function ignoresEvent(state, event) {
  return state.status !== VISUALIZER_STARTUP_STATUS.PENDING
    || event.generation !== state.generation
    || event.navigation_id !== state.navigation_id;
}

function matchesExpectedDocument(state, event) {
  return event.data_revision === state.data_revision && event.src === state.src;
}

function fail(state, code) {
  state.status = VISUALIZER_STARTUP_STATUS.FAILED;
  state.code = code;
  return result(state, "accepted");
}

/**
 * Create the mutable state owned by one Visualizer frame.
 *
 * The transition helpers are synchronous and side-effect free outside this
 * object, so callers can use the same module from a browser ESM bundle or a
 * Node test without timers, DOM globals, or other dependencies.
 */
export function createVisualizerStartupState() {
  return {
    generation: 0,
    navigation_id: null,
    data_revision: null,
    src: null,
    status: VISUALIZER_STARTUP_STATUS.IDLE,
    code: null,
    frame_loaded: false,
    initializing_seen: false,
  };
}

/** Begin a new navigation and invalidate every event from an older one. */
export function beginVisualizerStartup(state, identity) {
  requireIdentity(identity);
  state.generation = nextGeneration(state);
  state.navigation_id = identity.navigation_id;
  state.data_revision = identity.data_revision;
  state.src = identity.src;
  state.status = VISUALIZER_STARTUP_STATUS.PENDING;
  state.code = null;
  state.frame_loaded = false;
  state.initializing_seen = false;
  return result(state, "accepted");
}

/**
 * Apply one asynchronous event for the current navigation.
 *
 * Every event carries the identity captured by its producer. A stale
 * generation or navigation_id is ignored before document fields are checked.
 * This ordering is important: a late ready from an old page is not evidence
 * that the current page rejected its handshake.
 */
export function transitionVisualizerStartup(state, event) {
  if (event === null || typeof event !== "object") {
    throw new TypeError("Visualizer startup event must be an object.");
  }
  if (ignoresEvent(state, event)) return result(state, "ignored");

  switch (event.type) {
    case "initializing":
      if (!matchesExpectedDocument(state, event)) return result(state, "ignored");
      state.initializing_seen = true;
      return result(state, "accepted");

    case "failed":
      if (event.code !== VISUALIZER_STARTUP_CODE.DATA_LOAD_FAILED) {
        return result(state, "ignored");
      }
      if (!matchesExpectedDocument(state, event)) return result(state, "ignored");
      return fail(state, VISUALIZER_STARTUP_CODE.DATA_LOAD_FAILED);

    case "ready":
      if (!matchesExpectedDocument(state, event)) {
        return fail(state, VISUALIZER_STARTUP_CODE.READY_HANDSHAKE_REJECTED);
      }
      state.status = VISUALIZER_STARTUP_STATUS.READY;
      state.code = null;
      return result(state, "accepted");

    case "frame_load":
      if (!matchesExpectedDocument(state, event)) return result(state, "ignored");
      state.frame_loaded = true;
      return result(state, "accepted");

    case "timeout":
      if (!matchesExpectedDocument(state, event)) return result(state, "ignored");
      return fail(
        state,
        state.frame_loaded && !state.initializing_seen
          ? VISUALIZER_STARTUP_CODE.LEGACY_PROTOCOL_MISSING
          : VISUALIZER_STARTUP_CODE.READY_TIMEOUT,
      );

    default:
      throw new TypeError(`Unsupported Visualizer startup event type: ${String(event.type)}`);
  }
}

/** Reset the frame and invalidate callbacks captured by the prior generation. */
export function resetVisualizerStartup(state) {
  state.generation = nextGeneration(state);
  state.navigation_id = null;
  state.data_revision = null;
  state.src = null;
  state.status = VISUALIZER_STARTUP_STATUS.IDLE;
  state.code = null;
  state.frame_loaded = false;
  state.initializing_seen = false;
  return result(state, "accepted");
}
