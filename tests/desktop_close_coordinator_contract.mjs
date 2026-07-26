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

test('close waits for workspace, task start, background read, reset, and Box flush before destroying once', async () => {
  const workspace = deferred();
  const taskStart = deferred();
  const backgroundRead = deferred();
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
    setStage(stage) {
      events.push(`stage:${stage}`);
    },
    getWorkspaceTransition() {
      events.push('get-workspace-transition');
      return workspace.promise;
    },
    getTaskStart() {
      events.push('get-task-start');
      return taskStart.promise;
    },
    getBackgroundRead() {
      events.push('get-background-read');
      return backgroundRead.promise;
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
  assert.deepEqual(events, [
    'begin-close',
    'stage:waiting-workspace-transition',
    'get-workspace-transition',
  ]);

  taskStart.resolve();
  await nextTurn();
  assert.deepEqual(
    events,
    ['begin-close', 'stage:waiting-workspace-transition', 'get-workspace-transition'],
    'an already-finished task start must not bypass the workspace transition',
  );
  assert.equal(destroyCount, 0);

  workspaceReconcilePending = true;
  workspace.resolve();
  await nextTurn();
  assert.deepEqual(events, [
    'begin-close',
    'stage:waiting-workspace-transition',
    'get-workspace-transition',
    'stage:waiting-task-start',
    'get-task-start',
    'stage:waiting-background-read',
    'get-background-read',
  ]);
  assert.equal(destroyCount, 0, 'a pending background read must block Box flushing');

  backgroundRead.resolve();
  await nextTurn();
  assert.deepEqual(events, [
    'begin-close',
    'stage:waiting-workspace-transition',
    'get-workspace-transition',
    'stage:waiting-task-start',
    'get-task-start',
    'stage:waiting-background-read',
    'get-background-read',
    'stage:checking-active-task',
    'check-active-task',
    'check-workspace-reset',
    'reset-workspace',
    'stage:flushing-boxes',
    'flush-boxes',
  ]);
  assert.equal(destroyCount, 0, 'a pending Box flush must block window destruction');

  boxFlush.resolve(true);
  assert.equal(await closing, true);
  assert.equal(destroyCount, 1, 'the window must be destroyed exactly once');
  assert.equal(closeGate, false);
  assert.deepEqual(events.slice(-5), [
    'persist',
    'stage:destroying',
    'destroy',
    'stage:destroy-resolved',
    'finish-close:true',
  ]);
  assert.ok(events.indexOf('reset-workspace') < events.indexOf('flush-boxes'));
  assert.ok(events.indexOf('flush-boxes') < events.indexOf('destroy'));
});

test('a failed Box flush cancels close without persisting or destroying', async () => {
  const events = [];
  const closed = await coordinateDesktopClose({
    beginClose() {
      events.push('begin-close');
    },
    setStage(stage) {
      events.push(`stage:${stage}`);
    },
    getWorkspaceTransition() {
      return null;
    },
    getTaskStart() {
      return null;
    },
    getBackgroundRead() {
      return null;
    },
    hasActiveTask() {
      return false;
    },
    confirmActiveTaskClose() {
      assert.fail('inactive tasks must not prompt');
    },
    shouldResetWorkspace() {
      return false;
    },
    resetWorkspace() {
      assert.fail('a stable workspace must not reset');
    },
    flushBoxes() {
      events.push('flush-boxes');
      return false;
    },
    persist() {
      assert.fail('a failed flush must not persist the final close state');
    },
    destroy() {
      assert.fail('a failed flush must not destroy the window');
    },
    finishClose(wasClosed) {
      events.push(`finish-close:${wasClosed}`);
    },
  });

  assert.equal(closed, false);
  assert.deepEqual(events.slice(-4), [
    'stage:flushing-boxes',
    'flush-boxes',
    'stage:box-flush-cancelled',
    'finish-close:false',
  ]);
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
    setStage(stage) {
      events.push(`stage:${stage}`);
    },
    getWorkspaceTransition() {
      return null;
    },
    getTaskStart() {
      return null;
    },
    getBackgroundRead() {
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
  assert.deepEqual(events, [
    'begin-close',
    'stage:waiting-workspace-transition',
    'stage:waiting-task-start',
    'stage:waiting-background-read',
    'stage:checking-active-task',
    'cancel-close',
    'stage:active-task-cancelled',
    'start-reconcile',
  ]);

  reconcile.resolve();
  assert.equal(await closing, false);
  assert.equal(settled, true);
  assert.equal(closeGate, false);
  assert.deepEqual(events, [
    'begin-close',
    'stage:waiting-workspace-transition',
    'stage:waiting-task-start',
    'stage:waiting-background-read',
    'stage:checking-active-task',
    'cancel-close',
    'stage:active-task-cancelled',
    'start-reconcile',
    'finish-reconcile',
  ]);
});
