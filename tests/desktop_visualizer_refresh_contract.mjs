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
const styles = readFileSync(new URL('../crates/miho-desktop/src/styles.css', import.meta.url), 'utf8');

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
  assert.match(refresh, /invalidateUpdateHealth\("正在刷新当前工作区的自动更新记录…"\)/);
  assert.match(refresh, /refreshUpdateHealth\(\)/);
  assert.match(refresh, /for \(const targetGame of GAMES\) markVisualizerDirty\(targetGame, false\)/);
  assert.match(refresh, /GAMES\.map\(\(targetGame\) => loadVisualizer\(false, targetGame\)\)/);
});

test('completed update cards open the matching game and request its latest revision', () => {
  const showUpdated = section('async function showUpdatedGame(', 'function updateVisualizerFrameVisibility()');
  const startExport = section('async function startExport(', 'function updateTaskForm()');
  const renderTasks = section('function renderTasks()', 'function isRecord(');

  assert.match(showUpdated, /页面正在同步最新数据，请稍后再查看/);
  assert.match(showUpdated, /ensureVisualizerBoxesSaved\(\[game\], "查看更新结果"\)/);
  assert.match(showUpdated, /game = targetGame;\s*updateGameUI\(\)/);
  assert.match(showUpdated, /markVisualizerDirty\(targetGame, false\)/);
  assert.match(showUpdated, /await loadVisualizer\(false, targetGame\)/);
  assert.match(showUpdated, /utilities\.open = false/);
  assert.match(showUpdated, /visualizerSection\.scrollIntoView/);
  assert.match(renderTasks, /task\.operation === "hsr-export" \? "hsr"/);
  assert.match(renderTasks, /makeButton\("查看本次更新结果"[\s\S]*?showUpdatedGame\(exportedGame\)/);
  assert.match(renderTasks, /本机更新与校验成功；Box 与卡池已刷新，终局分析保留上游最新可用的历史样本/);
  assert.match(renderTasks, /本机更新与校验成功；Box 与卡池已刷新，终局数据质量有告警/);
  assert.match(renderTasks, /freshnessLabel\(effectiveFreshnessStatus\(freshness\)\)/);
  assert.doesNotMatch(renderTasks, /查看最新 Box 和分析|即可查看最新 Box、卡池和终局分析/);
  assert.match(renderTasks, /viewUpdate\.disabled = workspaceBusy \|\| boxTransitionBusy \|\| isWindowClosing\(\)/);
  assert.match(startExport, /setBoxTransitionBusy\(true\)/);
  assert.match(startExport, /ensureVisualizerBoxesSaved\(GAMES, "更新数据"\)/);
  assert.match(startExport, /finally \{[\s\S]*?setBoxTransitionBusy\(false\)/);
});

test('automatic update health is always visible above the Visualizer and adapts on narrow screens', () => {
  const setup = section('const visualizerSection =', 'const utilities =');
  const panel = setup.indexOf('const updateHealthPanel = element("aside", "update-health loading")');
  const append = setup.indexOf('visualizerSection.append(');
  const appendedPanel = setup.indexOf('updateHealthPanel,', append);
  const appendedMessage = setup.indexOf('visualizerMessage,', append);
  const appendedFrames = setup.indexOf('...[...visualizerFrames.values()]', append);

  assert.ok(panel >= 0 && append > panel);
  assert.ok(appendedPanel > append && appendedMessage > appendedPanel && appendedFrames > appendedMessage);
  assert.match(setup, /aria-label", "自动更新健康状态"/);
  assert.match(setup, /aria-live", "polite"/);
  assert.match(setup, /正在读取最近自动更新记录…/);
  assert.doesNotMatch(section('const utilities =', 'main.append('), /updateHealthPanel/);

  assert.match(styles, /\.update-health \{[\s\S]*?flex:\s*0 0 auto/);
  assert.match(styles, /\.update-health\.healthy/);
  assert.match(styles, /\.update-health\.warning, \.update-health\.busy/);
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*?\.update-health-copy, \.update-health-games/);
});

test('update health validates native responses and binds late results to request and workspace generations', () => {
  const request = section('async function refreshUpdateHealth(', 'function updateWorkspaceControls()');
  const gameParser = section('function isDesktopUpdateHealthGame(', 'function backendUpdateHealth(');
  const parser = section('function backendUpdateHealth(', 'function isTaskStatus(');
  const freshnessParser = section('function isTaskFreshnessDate(', 'function isPublicTaskSnapshot(');
  const close = section('async function installWindowCloseHandler()', 'window.addEventListener("beforeunload"');

  assert.match(request, /const workspaceId = capabilities\?\.workspace\.workspace_id \?\? ""/);
  assert.match(request, /const request = \+\+updateHealthRequestGeneration/);
  assert.match(request, /await invokeTrackedUpdateHealth\(\)/);
  assert.match(source, /const pendingUpdateHealthReads = new Set<Promise<unknown>>\(\)/);
  assert.match(source, /function invokeTrackedUpdateHealth\(\)[\s\S]*?pendingUpdateHealthReads\.add\(read\)/);
  assert.match(source, /function pendingUpdateHealthRead\(\)[\s\S]*?Promise\.allSettled\(reads\)/);
  assert.equal((request.match(/request !== updateHealthRequestGeneration/g) ?? []).length, 2);
  assert.equal((request.match(/workspaceId !== \(capabilities\?\.workspace\.workspace_id \?\? ""\)/g) ?? []).length, 2);
  assert.equal((request.match(/isWindowClosing\(\)/g) ?? []).length >= 3, true);
  assert.match(request, /health\.workspace_id !== workspaceId/);

  assert.match(parser, /miho-desktop-update-health-v2/);
  assert.match(parser, /"schema_version", "workspace_id", "healthy", "checked_games", "games", "retryable"/);
  assert.match(parser, /hasExactKeys\(value, expectedKeys\)/);
  assert.match(gameParser, /hasExactKeys\(value, \["game", "attempt_id", "completed_at_utc", "freshness"\]\)/);
  assert.match(gameParser, /isTaskFreshness\(value\.freshness\)/);
  assert.match(freshnessParser, /if \(value === ""\) return true/);
  assert.match(freshnessParser, /setUTCFullYear\(year, month - 1, day\)/);
  assert.match(freshnessParser, /parsed\.getUTCFullYear\(\) === year/);
  assert.match(freshnessParser, /const boundaryShapeMatches = freshness\.status === "future"/);
  assert.match(freshnessParser, /freshness\.status === "active"[\s\S]*?freshness\.start_date !== "" \|\| freshness\.end_date !== ""/);
  assert.match(parser, /GAMES\.every\(\(targetGame\) => games\.some/);
  assert.match(close, /beginClose\(\) \{[\s\S]*?updateHealthRequestGeneration \+= 1/);
  assert.match(close, /resetWorkspace\(\) \{[\s\S]*?updateHealthRequestGeneration \+= 1;[\s\S]*?resetVisualizerFrames\(\)/);
  assert.match(close, /finishClose\(closed\)[\s\S]*?if \(!isWindowClosing\(\)\) \{[\s\S]*?await refreshUpdateHealth\(\)/);
});

test('update health explains artifact integrity, per-game success times, staleness, busy workspaces and retry action', () => {
  const rendering = section('function setUpdateHealthView(', 'async function refreshUpdateHealth(');

  assert.match(source, /const UPDATE_HEALTH_STALE_AFTER_MS = 36 \* 60 \* 60 \* 1_000/);
  assert.match(source, /ENDGAME_SAMPLE_STALE_AFTER_DAYS/);
  assert.match(rendering, />= UPDATE_HEALTH_STALE_AFTER_MS/);
  assert.match(rendering, /const staleSampleGames = GAMES\.filter/);
  assert.match(rendering, /summary\.staleSamples/);
  assert.match(rendering, /"样本陈旧"/);
  assert.match(rendering, /存在已超过 \$\{ENDGAME_SAMPLE_STALE_AFTER_DAYS - 1\} 天未更新的终局样本/);
  assert.match(rendering, /本机产物校验通过/);
  assert.match(rendering, /\$\{gameShortLabel\(targetGame\)\} 最近成功/);
  assert.match(rendering, /终局最新采样/);
  assert.match(rendering, /freshnessLabel\(effectiveFreshnessStatus\(modeFreshness\)\)/);
  assert.match(rendering, /最近更新记录正常/);
  assert.match(rendering, /上游仍有历史终局样本/);
  assert.match(rendering, /上游数据质量有告警/);
  assert.match(rendering, /上游数据质量需留意/);
  assert.match(rendering, /return targetGame === "hsr" \? "HSR" : "ZZZ"/);
  assert.match(rendering, /计划任务可能未运行/);
  assert.match(rendering, /历史样本不等于本机刷新失败/);
  assert.match(rendering, /workspace\.busy/);
  assert.match(rendering, /workspace\.write_busy/);
  assert.match(rendering, /busy\|locked\|in_progress\|already_running/);
  assert.match(rendering, /数据正在更新，完成后会自动重新检查/);
  assert.match(rendering, /可以重试：建议稍后点击刷新/);
  assert.match(rendering, /需要修正后再重试/);
  assert.match(rendering, /desktop\.update_health_failed/);
  assert.match(rendering, /\$\{publicCode\}/);
  assert.match(source, /desktop\.update_health_invalid_response/);
  assert.match(source, /desktop\.update_health_workspace_mismatch/);
});

test('per-mode update health is keyboard and touch expandable without relying on hover titles', () => {
  const rendering = section('function setUpdateHealthView(', 'async function refreshUpdateHealth(');

  assert.match(source, /function freshnessPeriodLabel\(freshness: TaskModeFreshness\)/);
  assert.match(rendering, /const item = element\("details", "update-health-game"\)/);
  assert.match(rendering, /item\.dataset\.game = targetGame/);
  assert.match(rendering, /item\.dataset\.completedAtUtc = entry\.completed_at_utc/);
  assert.match(rendering, /const itemSummary = element\("summary", "update-health-game-summary"\)/);
  assert.match(rendering, /itemSummary\.setAttribute\([\s\S]*?"aria-label"[\s\S]*?各模式状态、采样日、样本年龄与周期边界/);
  assert.match(rendering, /element\("span", "update-health-toggle", "各模式详情"\)/);
  assert.match(rendering, /modeList\.setAttribute\("aria-label", `\$\{gameShortLabel\(targetGame\)\} 各模式终局数据时效`\)/);
  assert.match(rendering, /freshnessLabel\(effectiveFreshnessStatus\(modeFreshness\)\)/);
  assert.match(rendering, /sampleAgeSuffix\(summary\.latestSampleDate, today\)/);
  assert.match(rendering, /sampleAgeSuffix\(modeFreshness\.sample_date, today\)/);
  assert.match(rendering, /item\.classList\.add\("has-stale-sample"\)/);
  assert.match(rendering, /modeItem\.classList\.add\("has-stale-sample"\)/);
  assert.match(rendering, /采样日未知/);
  assert.match(rendering, /freshnessPeriodLabel\(modeFreshness\)/);
  assert.doesNotMatch(rendering, /item\.title\s*=/);

  assert.match(styles, /\.update-health-game-summary:focus-visible\s*\{[^}]*outline:/);
  assert.match(styles, /\.update-health-game\[open\] > \.update-health-game-summary::after/);
  assert.match(styles, /\.update-health-game\.has-stale-sample \.update-health-sample,[\s\S]*?\.update-health-mode\.has-stale-sample \.update-health-mode-dates/);
  assert.match(styles, /\.update-health-mode-dates\s*\{[^}]*overflow-wrap:\s*anywhere/);
  assert.match(styles, /@media \(max-width: 640px\)[\s\S]*?\.update-health-game\s*\{[^}]*min-width:\s*0;[^}]*flex-basis:\s*100%/);
});

test('update health retries busy workspaces with bounded backoff and rechecks at the next stale deadline', () => {
  const scheduling = section('function clearUpdateHealthTimers(', 'function invalidateUpdateHealth(');
  const request = section('async function refreshUpdateHealth(', 'function updateWorkspaceControls()');
  const close = section('async function installWindowCloseHandler()', 'window.addEventListener("beforeunload"');
  const unload = section('window.addEventListener("beforeunload"', 'updateGameUI();');

  assert.match(source, /const UPDATE_HEALTH_BUSY_RETRY_DELAYS_MS = \[1_000, 2_500, 5_000, 10_000, 30_000\]/);
  assert.match(scheduling, /Math\.min\(updateHealthBusyRetryAttempt, UPDATE_HEALTH_BUSY_RETRY_DELAYS_MS\.length - 1\)/);
  assert.match(scheduling, /void refreshUpdateHealth\(true\)/);
  assert.match(scheduling, /Date\.parse\(entry\.completed_at_utc\) \+ UPDATE_HEALTH_STALE_AFTER_MS/);
  assert.match(scheduling, /\[\[mode\.start_date, 0\], \[mode\.end_date, 1\]\]/);
  assert.match(scheduling, /new Date\(year, month - 1, day \+ dayOffset\)\.getTime\(\)/);
  assert.match(scheduling, /nextLocalDateBoundary\(new Date\(now\)\)/);
  assert.match(scheduling, /nextDateBoundary === null \? \[\] : \[nextDateBoundary\]/);
  assert.match(scheduling, /Math\.min\(Math\.max\(1, Math\.min\(\.\.\.futureDeadlines\) - now\), MAX_BROWSER_TIMER_DELAY_MS\)/);
  assert.match(scheduling, /workspaceId !== capabilities\?\.workspace\.workspace_id/);
  assert.match(request, /clearUpdateHealthTimers\(!fromBusyRetry\)/);
  assert.match(close, /beginClose\(\) \{[\s\S]*?clearUpdateHealthTimers\(\)/);
  assert.match(unload, /clearUpdateHealthTimers\(\)/);
});

test('update health refreshes on meaningful lifecycle events without hashing every stable focus check', () => {
  const reloadButton = section('const reloadVisualizerButton', 'visualizerHeading.append(');
  const revisions = section('async function checkVisualizerRevisions()', 'function handleWindowFocus()');
  const focusWatchers = section('function handleWindowFocus()', 'function setNotice(');
  const reloadWorkspace = section('async function reloadSelectedWorkspaceState()', 'async function reconcileWorkspaceAfterCloseCancellation()');
  const taskQuery = section('async function queryTask(', 'async function refreshTasks()');
  const taskRefresh = section('async function refreshTasks()', 'async function cancelTask(');

  assert.match(reloadButton, /Promise\.all\(\[loadVisualizer\(true\), refreshUpdateHealth\(\)\]\)/);
  assert.match(reloadWorkspace, /invalidateUpdateHealth\("正在读取当前工作区的自动更新记录…"\)/);
  assert.match(reloadWorkspace, /refreshTasks\(\), loadVisualizer\(false\), refreshUpdateHealth\(\)/);
  assert.match(revisions, /const previousObservedRevision = observedVisualizerRevisions\.get\(targetGame\)/);
  assert.match(revisions, /previousObservedRevision !== descriptor\.data_revision/);
  assert.match(revisions, /if \(observedRevisionChanged\) await refreshUpdateHealth\(\)/);
  assert.equal((revisions.match(/refreshUpdateHealth\(\)/g) ?? []).length, 1);
  assert.doesNotMatch(focusWatchers, /refreshUpdateHealth\(\)/);
  assert.match(taskQuery, /TERMINAL_STATUSES\.has\(snapshot\.status\)/);
  assert.match(taskQuery, /updateHealthRefreshedTaskIds\.add\(snapshot\.task_id\);\s*await refreshUpdateHealth\(\)/);
  assert.match(taskRefresh, /!TERMINAL_STATUSES\.has\(previous\.status\)[\s\S]*?TERMINAL_STATUSES\.has\(snapshot\.status\)/);
  assert.match(taskRefresh, /if \(updateHealthAfterTerminalExport\) await refreshUpdateHealth\(\)/);
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

  assert.match(close, /coordinateDesktopClose\(\{/);
  assert.match(close, /if \(allowWindowClose \|\| closeRequestRunning\) return;\s*closeRequestRunning = true/);
  assert.match(close, /beginClose\(\) \{[\s\S]*?closeGuardRunning = true;[\s\S]*?setBoxTransitionBusy\(true\)/);
  assert.match(close, /getWorkspaceTransition\(\) \{\s*return pendingWorkspaceTransition/);
  assert.match(close, /getTaskStart\(\) \{\s*return pendingTaskStart/);
  assert.match(close, /getBackgroundRead\(\) \{\s*return pendingUpdateHealthRead\(\)/);
  assert.match(close, /hasActiveTask,/);
  assert.match(close, /shouldResetWorkspace\(\) \{\s*return workspaceReconcilePending/);
  assert.match(close, /resetWorkspace\(\) \{\s*capabilitiesRequestGeneration \+= 1;\s*updateHealthRequestGeneration \+= 1;\s*resetVisualizerFrames\(\)/);
  assert.match(close, /setStage: setDesktopCloseStage/);
  assert.match(close, /flushBoxes\(\) \{\s*return ensureVisualizerBoxesSaved\(\["hsr", "zzz"\], "关闭程序", \{/);
  assert.match(close, /failureMode: "cancel"/);
  assert.match(close, /"flushing-hsr-box" : "flushing-zzz-box"/);
  assert.match(close, /persist: persistTaskHistory/);
  assert.match(close, /allowWindowClose = true;[\s\S]*?await appWindow\.destroy\(\)/);
  assert.match(close, /finishClose\(closed\)[\s\S]*?if \(closed\) return;[\s\S]*?setBoxTransitionBusy\(false\)/);
  assert.match(close, /uninstallVisualizerRevisionWatchers\(\)/);
  assert.match(close, /installVisualizerRevisionWatchers\(\)/);
  assert.match(close, /await reconcileWorkspaceAfterCloseCancellation\(\)/);
  assert.match(close, /finally \{\s*closeRequestRunning = false/);
});

test('Box saves are serialized and close failures do not enter a confirmation loop', () => {
  const flush = section('async function ensureVisualizerBoxesSaved(', 'function markVisualizerDirty(');

  assert.match(flush, /for \(const targetGame of loadedGames\) \{[\s\S]*?await flushVisualizerBox\(targetGame\)/);
  assert.doesNotMatch(flush, /Promise\.all\(loadedGames\.map\(flushVisualizerBox\)\)/);
  assert.match(flush, /if \(options\.failureMode === "cancel"\) return false;[\s\S]*?window\.confirm/);
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
  assert.match(reloadWorkspace, /if \(!capabilitiesReady \|\| isWindowClosing\(\)\) \{[\s\S]*?return false;\s*\}/);
  assert.match(select, /const finishWorkspaceTransition = beginWorkspaceTransitionTracking\(\)/);
  assert.match(select, /workspaceSelectionUncertain = true;\s*const result = await invoke/);
  assert.match(select, /workspaceReconcilePending = true;\s*if \(isWindowClosing\(\)\) return/);
  assert.match(select, /finishWorkspaceTransition\(\)/);
  assert.match(close, /shouldResetWorkspace\(\) \{\s*return workspaceReconcilePending/);
  assert.match(close, /resetWorkspace\(\) \{\s*capabilitiesRequestGeneration \+= 1;\s*updateHealthRequestGeneration \+= 1;\s*resetVisualizerFrames\(\)/);
});

test('external links are ignored while closing or another Box transition owns the UI', () => {
  const messages = section('window.addEventListener("message"', 'visualizerSection.append(');
  const externalLink = messages.indexOf('event.data.schema_version === "miho-visualizer-external-link-v1"');
  const closeGate = messages.indexOf('if (isWindowClosing() || boxTransitionBusy) return;', externalLink);
  const open = messages.indexOf('invoke("open_external_https"', closeGate);

  assert.ok(externalLink >= 0 && closeGate > externalLink && open > closeGate);
  assert.ok(
    messages.indexOf('miho-visualizer-box-flush-result-v1') < closeGate,
    'Box flush responses must remain available while closing',
  );
  assert.ok(
    messages.indexOf('miho-visualizer-ready-v1') < closeGate,
    'ready handshakes must remain available while closing',
  );
});

test('frame load is diagnostic only and a matching startup handshake alone completes iframe navigation', () => {
  const frameSetup = section('const visualizerDirty', 'window.addEventListener("message"');
  const messages = section('window.addEventListener("message"', 'function updateVisualizerFrameVisibility()');
  const load = section('async function loadVisualizer(', 'async function refreshAll()');
  const frameLoad = section('frame.addEventListener("load"', 'window.addEventListener("message"');

  assert.match(frameSetup, /frame\.addEventListener\("load"/);
  assert.match(frameLoad, /transitionVisualizerStartup\(visualizerState\.startup, \{\s*type: "frame_load"/);
  assert.doesNotMatch(frameLoad, /dataset\.loaded\s*=\s*"true"/);
  assert.doesNotMatch(frameSetup, /frame\.addEventListener\("error"/);
  assert.match(messages, /event\.data\.schema_version === "miho-visualizer-initializing-v1"|lifecycleSchema === "miho-visualizer-initializing-v1"/);
  assert.match(messages, /lifecycleSchema === "miho-visualizer-failed-v1"/);
  assert.match(messages, /lifecycleSchema === "miho-visualizer-ready-v1"/);
  assert.match(messages, /transitionVisualizerStartup\(sourceState\.startup/);
  assert.match(messages, /transition\.status !== VISUALIZER_STARTUP_STATUS\.READY/);
  assert.match(messages, /sourceState\.frame\.dataset\.loaded = "true"/);
  assert.match(load, /pageUrl\.searchParams\.set\("navigation_id", navigationId\)/);
  assert.match(load, /beginVisualizerStartup\(visualizerState\.startup/);
  assert.match(load, /failVisualizerStartupOnTimeout\(targetGame, startupTicket\)/);
  assert.match(source, /function finishVisualizerStartupFailure[\s\S]*?visualizerLoading\.delete\(targetGame\)/);
  const startupFailure = section('function finishVisualizerStartupFailure(', 'function failVisualizerStartupOnTimeout(');
  assert.match(startupFailure, /const failedCurrentRefresh = finishPendingVisualizerRefresh\(visualizerState\)/);
  assert.match(startupFailure, /if \(failedCurrentRefresh\) pendingVisualizerRefreshes\.delete\(targetGame\)/);
  assert.match(startupFailure, /if \(!failedCurrentRefresh && pendingVisualizerRefreshes\.has\(targetGame\)\)/);
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

test('failed iframe navigation stops the same revision but preserves a newer queued revision', () => {
  function createModel() {
    return {
      refresh: { refreshGeneration: 0, pendingRefreshGeneration: null },
      pending: false,
      scheduled: 0,
    };
  }

  function queue(model) {
    advanceVisualizerRefresh(model.refresh);
    model.pending = true;
  }

  function begin(model) {
    bindPendingVisualizerRefresh(model.refresh, captureVisualizerRefresh(model.refresh));
  }

  function fail(model) {
    const failedCurrentRefresh = finishPendingVisualizerRefresh(model.refresh);
    if (failedCurrentRefresh) model.pending = false;
    if (!failedCurrentRefresh && model.pending) model.scheduled += 1;
    return failedCurrentRefresh;
  }

  const sameRevision = createModel();
  queue(sameRevision);
  begin(sameRevision);
  assert.equal(fail(sameRevision), true);
  assert.equal(sameRevision.pending, false);
  assert.equal(sameRevision.scheduled, 0);

  const newerRevision = createModel();
  queue(newerRevision);
  begin(newerRevision);
  queue(newerRevision);
  assert.equal(fail(newerRevision), false);
  assert.equal(newerRevision.pending, true);
  assert.equal(newerRevision.scheduled, 1);

  begin(newerRevision);
  assert.equal(fail(newerRevision), true);
  assert.equal(newerRevision.pending, false);
  assert.equal(newerRevision.scheduled, 1);
});
