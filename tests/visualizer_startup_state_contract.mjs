import assert from 'node:assert/strict';
import test from 'node:test';
import {
  beginVisualizerStartup,
  createVisualizerStartupState,
  resetVisualizerStartup,
  transitionVisualizerStartup,
  VISUALIZER_STARTUP_CODE,
  VISUALIZER_STARTUP_STATUS,
} from '../crates/miho-desktop/src/visualizer-startup-state.js';

const REVISION_A = 'a'.repeat(64);
const REVISION_B = 'b'.repeat(64);
const SRC_A = `https://miho-visualizer.localhost/hsr/index.html?revision=${REVISION_A}&navigation_id=hsr-1`;
const SRC_B = `https://miho-visualizer.localhost/hsr/index.html?revision=${REVISION_B}&navigation_id=hsr-2`;

function start(state, overrides = {}) {
  const identity = {
    navigation_id: 'hsr-1',
    data_revision: REVISION_A,
    src: SRC_A,
    ...overrides,
  };
  const started = beginVisualizerStartup(state, identity);
  return {
    generation: started.generation,
    ...identity,
  };
}

function send(state, ticket, type, overrides = {}) {
  return transitionVisualizerStartup(state, {
    type,
    ...ticket,
    ...overrides,
  });
}

function assertPending(result) {
  assert.equal(result.status, VISUALIZER_STARTUP_STATUS.PENDING);
  assert.equal(result.code, null);
}

test('navigation start binds generation, navigation id, revision, and exact src', () => {
  const state = createVisualizerStartupState();
  assert.deepEqual(state, {
    generation: 0,
    navigation_id: null,
    data_revision: null,
    src: null,
    status: VISUALIZER_STARTUP_STATUS.IDLE,
    code: null,
    frame_loaded: false,
    initializing_seen: false,
  });

  const ticket = start(state);
  assert.deepEqual(ticket, {
    generation: 1,
    navigation_id: 'hsr-1',
    data_revision: REVISION_A,
    src: SRC_A,
  });
  assertPending(state);
});

test('initializing then matching ready completes the current navigation', () => {
  const state = createVisualizerStartupState();
  const ticket = start(state);

  const initializing = send(state, ticket, 'initializing');
  assert.equal(initializing.outcome, 'accepted');
  assert.equal(initializing.initializing_seen, true);
  assertPending(initializing);

  const ready = send(state, ticket, 'ready');
  assert.equal(ready.outcome, 'accepted');
  assert.equal(ready.status, VISUALIZER_STARTUP_STATUS.READY);
  assert.equal(ready.code, null);
});

test('a valid ready-only legacy handshake succeeds without initializing', () => {
  const state = createVisualizerStartupState();
  const ticket = start(state);

  const frameLoad = send(state, ticket, 'frame_load');
  assert.equal(frameLoad.outcome, 'accepted');
  assert.equal(frameLoad.frame_loaded, true);
  assertPending(frameLoad);

  const ready = send(state, ticket, 'ready');
  assert.equal(ready.status, VISUALIZER_STARTUP_STATUS.READY);
  assert.equal(ready.initializing_seen, false);
});

test('frame load is diagnostic only and identifies a missing startup protocol at timeout', () => {
  const state = createVisualizerStartupState();
  const ticket = start(state);

  const loaded = send(state, ticket, 'frame_load');
  assertPending(loaded);
  assert.notEqual(loaded.status, VISUALIZER_STARTUP_STATUS.READY);

  const timedOut = send(state, ticket, 'timeout');
  assert.equal(timedOut.status, VISUALIZER_STARTUP_STATUS.FAILED);
  assert.equal(timedOut.code, VISUALIZER_STARTUP_CODE.LEGACY_PROTOCOL_MISSING);
});

test('an initializing page and a page that never loads produce ready_timeout', () => {
  const initializingState = createVisualizerStartupState();
  const initializingTicket = start(initializingState);
  send(initializingState, initializingTicket, 'frame_load');
  send(initializingState, initializingTicket, 'initializing');
  const initializingTimeout = send(initializingState, initializingTicket, 'timeout');
  assert.equal(initializingTimeout.code, VISUALIZER_STARTUP_CODE.READY_TIMEOUT);

  const unloadedState = createVisualizerStartupState();
  const unloadedTicket = start(unloadedState);
  const unloadedTimeout = send(unloadedState, unloadedTicket, 'timeout');
  assert.equal(unloadedTimeout.code, VISUALIZER_STARTUP_CODE.READY_TIMEOUT);
});

test('a current-navigation ready with the wrong revision or src is rejected', () => {
  for (const mismatch of [
    { data_revision: REVISION_B },
    { src: `${SRC_A}&unexpected=1` },
  ]) {
    const state = createVisualizerStartupState();
    const ticket = start(state);
    const rejected = send(state, ticket, 'ready', mismatch);
    assert.equal(rejected.outcome, 'accepted');
    assert.equal(rejected.status, VISUALIZER_STARTUP_STATUS.FAILED);
    assert.equal(rejected.code, VISUALIZER_STARTUP_CODE.READY_HANDSHAKE_REJECTED);
  }
});

test('late events from an older navigation are ignored before document validation', () => {
  const state = createVisualizerStartupState();
  const oldTicket = start(state);
  const currentTicket = start(state, {
    navigation_id: 'hsr-2',
    data_revision: REVISION_B,
    src: SRC_B,
  });
  // postMessage handlers learn the frame's current generation locally. Keep
  // that generation here so this test isolates the navigation_id guard.
  const lateMessageTicket = {
    ...oldTicket,
    generation: currentTicket.generation,
  };

  for (const [type, extra] of [
    ['initializing', {}],
    ['failed', { code: VISUALIZER_STARTUP_CODE.DATA_LOAD_FAILED }],
    ['ready', { data_revision: 'c'.repeat(64), src: 'https://late.invalid/' }],
    ['frame_load', {}],
    ['timeout', {}],
  ]) {
    const ignored = send(state, lateMessageTicket, type, extra);
    assert.equal(ignored.outcome, 'ignored', `${type} was not ignored`);
    assertPending(ignored);
    assert.equal(ignored.navigation_id, currentTicket.navigation_id);
    assert.equal(ignored.data_revision, currentTicket.data_revision);
    assert.equal(ignored.src, currentTicket.src);
  }
});

test('only the fixed data_load_failed code can fail a matching failed event', () => {
  const state = createVisualizerStartupState();
  const ticket = start(state);

  const unknown = send(state, ticket, 'failed', { code: 'parse_exploded' });
  assert.equal(unknown.outcome, 'ignored');
  assertPending(unknown);

  const failed = send(state, ticket, 'failed', {
    code: VISUALIZER_STARTUP_CODE.DATA_LOAD_FAILED,
  });
  assert.equal(failed.outcome, 'accepted');
  assert.equal(failed.status, VISUALIZER_STARTUP_STATUS.FAILED);
  assert.equal(failed.code, VISUALIZER_STARTUP_CODE.DATA_LOAD_FAILED);
});

test('reset invalidates old timers and messages and returns the machine to idle', () => {
  const state = createVisualizerStartupState();
  const oldTicket = start(state);
  send(state, oldTicket, 'frame_load');

  const reset = resetVisualizerStartup(state);
  assert.equal(reset.outcome, 'accepted');
  assert.equal(reset.generation, oldTicket.generation + 1);
  assert.equal(reset.status, VISUALIZER_STARTUP_STATUS.IDLE);
  assert.equal(reset.code, null);
  assert.equal(reset.navigation_id, null);

  for (const type of ['timeout', 'ready', 'initializing', 'frame_load']) {
    const ignored = send(state, oldTicket, type);
    assert.equal(ignored.outcome, 'ignored', `${type} survived reset`);
    assert.equal(ignored.status, VISUALIZER_STARTUP_STATUS.IDLE);
  }

  // Reuse the exact document identity to prove generation, by itself, keeps
  // a timer captured before reset from affecting the replacement navigation.
  const currentTicket = start(state);
  assert.ok(currentTicket.generation > reset.generation);
  assert.equal(send(state, oldTicket, 'timeout').outcome, 'ignored');
  assertPending(state);
});

test('terminal navigation results are stable against duplicate asynchronous events', () => {
  const state = createVisualizerStartupState();
  const ticket = start(state);
  send(state, ticket, 'ready');

  for (const type of ['ready', 'timeout', 'frame_load', 'initializing']) {
    const ignored = send(state, ticket, type);
    assert.equal(ignored.outcome, 'ignored');
    assert.equal(ignored.status, VISUALIZER_STARTUP_STATUS.READY);
    assert.equal(ignored.code, null);
  }
});
