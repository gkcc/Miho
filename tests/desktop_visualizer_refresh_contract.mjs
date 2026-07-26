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
  assert.match(source, /if \(!busy && !visualizerRefreshDrainRunning\) schedulePendingVisualizerRefresh\(\)/);
  assert.match(drain, /ensureVisualizerBoxesSaved\(\[targetGame\], "载入最新数据"\)/);
  assert.match(drain, /await loadVisualizer\(false, targetGame\)/);
  assert.match(
    drain,
    /visualizerState\.pendingRevision\s*\|\| visualizerState\.pendingUrl\s*\|\| hasPendingVisualizerRefresh\(visualizerState\)/,
  );
  assert.match(load, /const refreshGeneration = captureVisualizerRefresh\(visualizerState\)/);
  assert.match(source, /finishPendingVisualizerRefresh\(visualizerState\)/);
  assert.match(load, /pageUrl\.hash = visualizerState\.page/);
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
