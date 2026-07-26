import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  advanceVisualizerRefresh,
  bindPendingVisualizerRefresh,
  captureVisualizerRefresh,
  finishPendingVisualizerRefresh,
  hasCurrentPendingVisualizerRefresh,
  hasPendingVisualizerRefresh,
} from '../crates/miho-desktop/src/visualizer-refresh-state.js';

const source = readFileSync(new URL('../crates/miho-desktop/src/main.ts', import.meta.url), 'utf8');

function section(start, end) {
  const startIndex = source.indexOf(start);
  const endIndex = source.indexOf(end, startIndex + start.length);
  assert.notEqual(startIndex, -1, `missing section start: ${start}`);
  assert.notEqual(endIndex, -1, `missing section end: ${end}`);
  return source.slice(startIndex, endIndex);
}

test('workspace refresh saves and synchronizes both game visualizers', () => {
  const refresh = section('async function refreshAll()', 'async function installWindowCloseHandler()');

  assert.match(refresh, /ensureVisualizerBoxesSaved\(GAMES, "刷新页面"\)/);
  assert.match(refresh, /for \(const targetGame of GAMES\) markVisualizerDirty\(targetGame, false\)/);
  assert.match(refresh, /GAMES\.map\(\(targetGame\) => loadVisualizer\(false, targetGame\)\)/);
});

test('revision watchers check both games without navigating a stable revision', () => {
  const check = section('async function checkVisualizerRevisions()', 'function handleWindowFocus()');
  const load = section('async function loadVisualizer(', 'async function refreshAll()');

  assert.match(check, /Promise\.all\(GAMES\.map/);
  assert.match(check, /invoke<unknown>\("get_visualizer_url", \{ game: targetGame \}\)/);
  assert.match(check, /if \(displayedRevision === descriptor\.data_revision\) continue/);
  assert.match(source, /window\.addEventListener\("focus", handleWindowFocus\)/);
  assert.match(source, /document\.addEventListener\("visibilitychange", handleVisibilityChange\)/);
  assert.match(source, /const VISUALIZER_REVISION_CHECK_INTERVAL_MS = 60_000/);

  const stableRevision = load.indexOf('visualizerState.loadedRevision === descriptor.data_revision');
  const navigation = load.indexOf('frame.src = navigationUrl');
  assert.ok(stableRevision >= 0 && navigation > stableRevision);
  assert.match(load.slice(stableRevision, navigation), /return;/);
});

test('active refreshes drain after busy transitions and keep the selected tab', () => {
  const taskQuery = section('async function queryTask(', 'async function refreshTasks()');
  const drain = section('async function drainPendingVisualizerRefresh()', 'function requestVisualizerRevisionCheck()');
  const load = section('async function loadVisualizer(', 'async function refreshAll()');

  assert.match(taskQuery, /markVisualizerDirty\(exportedGame, exportedGame === game\)/);
  assert.match(source, /if \(!boxTransitionBusy && !visualizerRefreshDrainRunning\) schedulePendingVisualizerRefresh\(\)/);
  assert.match(drain, /ensureVisualizerBoxesSaved\(\[targetGame\], "载入最新数据"\)/);
  assert.match(drain, /await loadVisualizer\(false, targetGame\)/);
  assert.match(
    drain,
    /visualizerState\.pendingRevision\s*\|\| visualizerState\.pendingUrl\s*\|\| hasPendingVisualizerRefresh\(visualizerState\)/,
  );
  assert.match(load, /const refreshGeneration = captureVisualizerRefresh\(visualizerState\)/);
  assert.match(source, /finishPendingVisualizerRefresh\(sourceState\)/);
  assert.match(load, /pageUrl\.hash = visualizerState\.page/);
});

test('window close owns the transition and late descriptor results cannot navigate a frame', () => {
  const transition = section('function isWindowClosing()', 'const visualizerDirty');
  const load = section('async function loadVisualizer(', 'async function refreshAll()');
  const close = section('async function installWindowCloseHandler()', 'window.addEventListener("beforeunload"');

  assert.match(transition, /boxTransitionDepth = busy \? boxTransitionDepth \+ 1 : Math\.max\(0, boxTransitionDepth - 1\)/);
  assert.match(transition, /boxTransitionBusy = boxTransitionDepth > 0 \|\| isWindowClosing\(\)/);

  const descriptorAwait = load.indexOf('await invoke<unknown>("get_visualizer_url"');
  const closingRecheck = load.indexOf('if (isWindowClosing()', descriptorAwait);
  const flushRejection = load.indexOf('rejectFrameFlushes(frame)', closingRecheck);
  const navigation = load.indexOf('frame.src = navigationUrl', flushRejection);
  assert.ok(descriptorAwait >= 0 && closingRecheck > descriptorAwait);
  assert.ok(flushRejection > closingRecheck && navigation > flushRejection);

  const guardStart = close.indexOf('closeGuardRunning = true');
  const transitionAcquire = close.indexOf('setBoxTransitionBusy(true)', guardStart);
  const workspaceTransitionWait = close.indexOf('if (workspaceTransition) await workspaceTransition', transitionAcquire);
  const taskStartWait = close.indexOf('if (taskStart) await taskStart', workspaceTransitionWait);
  const activeTaskCheck = close.indexOf('if (hasActiveTask()', taskStartWait);
  const workspaceReset = close.indexOf('if (workspaceReconcilePending)', activeTaskCheck);
  const boxFlush = close.indexOf('ensureVisualizerBoxesSaved(["hsr", "zzz"], "关闭程序")');
  const transitionRelease = close.indexOf('setBoxTransitionBusy(false)', boxFlush);
  assert.ok(guardStart >= 0 && transitionAcquire > guardStart && boxFlush > transitionAcquire);
  assert.ok(workspaceTransitionWait > transitionAcquire);
  assert.ok(taskStartWait > workspaceTransitionWait && activeTaskCheck > taskStartWait);
  assert.ok(workspaceReset > activeTaskCheck && boxFlush > workspaceReset);
  assert.ok(transitionRelease > boxFlush);
  assert.match(close, /uninstallVisualizerRevisionWatchers\(\)/);
  assert.match(close, /installVisualizerRevisionWatchers\(\)/);
  assert.match(close, /await reconcileWorkspaceAfterCloseCancellation\(\)/);
});

test('closing gates task launches and reconciles a workspace mutation before controls reopen', () => {
  const reloadWorkspace = section('async function reloadSelectedWorkspaceState()', 'async function reconcileWorkspaceAfterCloseCancellation()');
  const select = section('async function selectWorkspace()', 'async function openLogLocation()');
  const exports = section('async function startExport(', 'function updateTaskForm()');
  const reports = section('async function startTask()', 'function mergeQueriedTask(');
  const close = section('async function installWindowCloseHandler()', 'window.addEventListener("beforeunload"');
  const unload = section('window.addEventListener("beforeunload"', 'updateGameUI()');

  assert.match(exports, /boxTransitionBusy\s*\|\| isWindowClosing\(\)/);
  assert.match(exports, /const finishTaskStart = beginTaskStartTracking\(\)/);
  assert.match(exports, /taskBusy = false;\s*finishTaskStart\(\)/);
  assert.match(reports, /boxTransitionBusy\s*\|\| isWindowClosing\(\)/);
  assert.match(reports, /const finishTaskStart = beginTaskStartTracking\(\)/);
  assert.match(reports, /taskBusy = false;\s*finishTaskStart\(\)/);
  assert.match(unload, /hasActiveTask\(\) \|\| taskBusy \|\| pendingTaskStart !== null/);

  assert.match(reloadWorkspace, /const capabilitiesReady = await refreshCapabilities\(\)/);
  assert.match(reloadWorkspace, /if \(!capabilitiesReady \|\| isWindowClosing\(\)\) return false/);
  assert.match(select, /const finishWorkspaceTransition = beginWorkspaceTransitionTracking\(\)/);
  assert.match(select, /workspaceSelectionUncertain = true;\s*const result = await invoke/);
  assert.match(select, /workspaceReconcilePending = true;\s*if \(isWindowClosing\(\)\) return/);
  assert.match(select, /finishWorkspaceTransition\(\)/);
  assert.match(close, /if \(workspaceReconcilePending\) \{\s*capabilitiesRequestGeneration \+= 1;\s*resetVisualizerFrames\(\)/);
});

test('only a matching Visualizer ready handshake can complete iframe navigation', () => {
  const frameSetup = section('const visualizerDirty', 'window.addEventListener("message"');
  const messages = section('window.addEventListener("message"', 'function updateVisualizerFrameVisibility()');
  const load = section('async function loadVisualizer(', 'async function refreshAll()');

  assert.doesNotMatch(frameSetup, /frame\.addEventListener\("load"/);
  assert.doesNotMatch(frameSetup, /frame\.addEventListener\("error"/);
  assert.match(messages, /event\.data\.schema_version === "miho-visualizer-ready-v1"/);
  assert.match(messages, /sourceState\.pendingNavigationId === event\.data\.navigation_id/);
  assert.match(messages, /sourceState\.pendingRevision === event\.data\.data_revision/);
  assert.match(messages, /sourceState\.frame\.dataset\.loaded = "true"/);
  assert.match(load, /pageUrl\.searchParams\.set\("navigation_id", navigationId\)/);
  assert.match(load, /failVisualizerReady\(targetGame, navigationId\)/);
  assert.match(source, /function failVisualizerReady[\s\S]*?visualizerLoading\.delete\(targetGame\)/);
  assert.match(source, /frame\.dataset\.loaded === "true"\s*&& visualizerState\.pendingNavigationId === null/);
  assert.match(source, /frame\.inert = boxTransitionBusy \|\| !active/);
  assert.match(source, /frame\.removeAttribute\("src"\)/);
});

test('pending iframe navigation serializes A, queued B, A load, then B load', () => {
  const state = {refreshGeneration: 0, pendingRefreshGeneration: null};
  const navigations = [];
  let queuedRevision = null;
  let pendingRevision = null;

  function queueRevision(revision) {
    advanceVisualizerRefresh(state);
    queuedRevision = revision;
  }

  function drain() {
    if (pendingRevision !== null || hasPendingVisualizerRefresh(state) || queuedRevision === null) {
      return false;
    }
    pendingRevision = queuedRevision;
    queuedRevision = null;
    bindPendingVisualizerRefresh(state, captureVisualizerRefresh(state));
    navigations.push(pendingRevision);
    return true;
  }

  function finishLoad() {
    assert.notEqual(pendingRevision, null, 'a load must belong to the serialized pending navigation');
    const loadedRevision = pendingRevision;
    pendingRevision = null;
    return {
      loadedRevision,
      completedCurrentRefresh: finishPendingVisualizerRefresh(state),
    };
  }

  queueRevision('A');
  assert.equal(drain(), true);
  assert.deepEqual(navigations, ['A']);
  assert.equal(hasPendingVisualizerRefresh(state), true);
  assert.equal(hasCurrentPendingVisualizerRefresh(state), true);

  queueRevision('B');
  assert.equal(drain(), false, 'B must not replace the in-flight A navigation');
  assert.deepEqual(navigations, ['A']);
  assert.equal(hasPendingVisualizerRefresh(state), true);
  assert.equal(hasCurrentPendingVisualizerRefresh(state), false);

  assert.deepEqual(finishLoad(), {
    loadedRevision: 'A',
    completedCurrentRefresh: false,
  });
  assert.equal(hasPendingVisualizerRefresh(state), false);

  assert.equal(drain(), true, 'drain must navigate to B after A finishes');
  assert.deepEqual(navigations, ['A', 'B']);
  assert.equal(hasCurrentPendingVisualizerRefresh(state), true);
  assert.deepEqual(finishLoad(), {
    loadedRevision: 'B',
    completedCurrentRefresh: true,
  });
  assert.equal(hasPendingVisualizerRefresh(state), false);
});
