import assert from 'node:assert/strict';
import test from 'node:test';
import { coordinateDesktopClose } from '../crates/miho-desktop/src/desktop-close-coordinator.js';

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function nextTurn() {
  return new Promise((resolve) => setImmediate(resolve));
}

test('close waits for workspace, task start, reset, and Box flush before destroying once', async () => {
  const workspace = deferred();
  const taskStart = deferred();
  const boxFlush = deferred();
  const events = [];
  let closeGate = false;
  let destroyCount = 0;
  let workspaceReconcilePending = false;

  const closing = coordinateDesktopClose({
    beginClose() {
      closeGate = true;
      events.push('begin-close');
    },
    getWorkspaceTransition() {
      events.push('get-workspace-transition');
      return workspace.promise;
    },
    getTaskStart() {
      events.push('get-task-start');
      return taskStart.promise;
    },
    hasActiveTask() {
      events.push('check-active-task');
      return false;
    },
    confirmActiveTaskClose() {
      assert.fail('inactive tasks must not prompt');
    },
    shouldResetWorkspace() {
      events.push('check-workspace-reset');
      return workspaceReconcilePending;
    },
    resetWorkspace() {
      events.push('reset-workspace');
    },
    flushBoxes() {
      events.push('flush-boxes');
      return boxFlush.promise;
    },
    persist() {
      events.push('persist');
    },
    async destroy() {
      destroyCount += 1;
      events.push('destroy');
    },
    async finishClose(closed) {
      events.push(`finish-close:${closed}`);
      closeGate = false;
    },
  });

  assert.equal(closeGate, true, 'beginClose must acquire the close gate synchronously');
  assert.deepEqual(events, ['begin-close', 'get-workspace-transition']);

  taskStart.resolve();
  await nextTurn();
  assert.deepEqual(
    events,
    ['begin-close', 'get-workspace-transition'],
    'an already-finished task start must not bypass the workspace transition',
  );
  assert.equal(destroyCount, 0);

  workspaceReconcilePending = true;
  workspace.resolve();
  await nextTurn();
  assert.deepEqual(events, [
    'begin-close',
    'get-workspace-transition',
    'get-task-start',
    'check-active-task',
    'check-workspace-reset',
    'reset-workspace',
    'flush-boxes',
  ]);
  assert.equal(destroyCount, 0, 'a pending Box flush must block window destruction');

  boxFlush.resolve(true);
  assert.equal(await closing, true);
  assert.equal(destroyCount, 1, 'the window must be destroyed exactly once');
  assert.equal(closeGate, false);
  assert.deepEqual(events.slice(-3), ['persist', 'destroy', 'finish-close:true']);
  assert.ok(events.indexOf('reset-workspace') < events.indexOf('flush-boxes'));
  assert.ok(events.indexOf('flush-boxes') < events.indexOf('destroy'));
});

test('a cancelled close keeps its gate until asynchronous reconciliation finishes', async () => {
  const reconcile = deferred();
  const events = [];
  let closeGate = false;
  let settled = false;

  const closing = coordinateDesktopClose({
    beginClose() {
      closeGate = true;
      events.push('begin-close');
    },
    getWorkspaceTransition() {
      return null;
    },
    getTaskStart() {
      return null;
    },
    hasActiveTask() {
      return true;
    },
    confirmActiveTaskClose() {
      events.push('cancel-close');
      return false;
    },
    shouldResetWorkspace() {
      assert.fail('cancellation must stop before reset');
    },
    resetWorkspace() {
      assert.fail('cancellation must not reset here');
    },
    flushBoxes() {
      assert.fail('cancellation must stop before Box flush');
    },
    persist() {
      assert.fail('cancellation must not persist the final close state');
    },
    destroy() {
      assert.fail('cancellation must not destroy the window');
    },
    async finishClose(closed) {
      assert.equal(closed, false);
      events.push('start-reconcile');
      await reconcile.promise;
      events.push('finish-reconcile');
      closeGate = false;
    },
  });
  void closing.finally(() => {
    settled = true;
  });

  await nextTurn();
  assert.equal(closeGate, true, 'the close gate must remain acquired during reconciliation');
  assert.equal(settled, false, 'the coordinator must await reconciliation in finishClose');
  assert.deepEqual(events, ['begin-close', 'cancel-close', 'start-reconcile']);

  reconcile.resolve();
  assert.equal(await closing, false);
  assert.equal(settled, true);
  assert.equal(closeGate, false);
  assert.deepEqual(events, [
    'begin-close',
    'cancel-close',
    'start-reconcile',
    'finish-reconcile',
  ]);
});
