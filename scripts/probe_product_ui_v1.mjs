#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import {
  isVisualizerStartupFailureError,
  throwIfVisualizerStartupFailed,
  visualizerStartupStageReady,
  waitForVisualizerStartupStage,
} from "./visualizer_startup_probe_v1.mjs";
import { serializeProductUiProbeReceipt } from "./product_ui_probe_receipt_v1.mjs";
import {
  ENDGAME_SAMPLE_STALE_AFTER_DAYS,
  localDateKey,
  sampleAgeDays,
} from "../crates/miho-desktop/src/freshness-age.js";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index];
  const value = process.argv[index + 1];
  if (!key?.startsWith("--") || value === undefined) {
    throw new Error(`invalid argument near ${key ?? "<end>"}`);
  }
  args.set(key.slice(2), value);
}
const expectedNames = (value) => String(value ?? "")
  .split("|")
  .map((name) => name.trim())
  .filter(Boolean);

function selectUniquePhaseMetadata(rows, sample) {
  const identityFields = [
    "mode",
    "collect_date",
    "phase_ver",
    "snapshot_id",
    "phase_name",
    "start_date",
    "end_date",
  ];
  const identityValue = (row, field) => String(field === "mode"
    ? (row?.tier_mode ?? row?.mode ?? "")
    : (row?.[field] ?? "")).trim();
  const providedIdentity = identityFields
    .map((field) => [field, identityValue(sample, field)])
    .filter(([, value]) => value);
  if (providedIdentity.length === 0) return null;
  const candidates = (rows ?? []).filter((row) => providedIdentity.every(
    ([field, value]) => identityValue(row, field) === value,
  ));
  return candidates.length === 1 ? candidates[0] : null;
}

function completeZzzPhasePresentation(phase) {
  const phaseName = String(phase?.phaseName ?? "").trim();
  const mechanicName = String(phase?.mechanicName ?? "").trim();
  return Boolean(phaseName
    && phaseName !== "期名未提供"
    && mechanicName
    && mechanicName !== "机制未提供");
}

const webSocketUrl = args.get("ws");
const expectedOwned = {
  hsr: Number(args.get("expected-hsr-owned")),
  zzz: Number(args.get("expected-zzz-owned")),
};
const expectedTotal = {
  hsr: Number(args.get("expected-hsr-total")),
  zzz: Number(args.get("expected-zzz-total")),
};
const expectedBannerCount = {
  hsr: args.has("expected-hsr-banner-count")
    ? Number(args.get("expected-hsr-banner-count"))
    : null,
  zzz: args.has("expected-zzz-banner-count")
    ? Number(args.get("expected-zzz-banner-count"))
    : null,
};
const expectedBannerNames = {
  hsr: expectedNames(args.get("expected-hsr-banner-names")),
  zzz: expectedNames(args.get("expected-zzz-banner-names")),
};
const expectedNextBannerCount = {
  hsr: args.has("expected-hsr-next-banner-count")
    ? Number(args.get("expected-hsr-next-banner-count"))
    : null,
  zzz: args.has("expected-zzz-next-banner-count")
    ? Number(args.get("expected-zzz-next-banner-count"))
    : null,
};
const expectedNextBannerNames = {
  hsr: expectedNames(args.get("expected-hsr-next-banner-names")),
  zzz: expectedNames(args.get("expected-zzz-next-banner-names")),
};
const expectedAnalysisModes = {
  hsr: ["moc", "pf", "as", "aa"],
  zzz: ["sd", "da"],
};
const timeoutMs = Number(args.get("timeout-ms") ?? "45000");
const runUpdatesValue = args.get("run-updates") ?? "false";
const runUpdates = runUpdatesValue === "true";
const updateTimeoutMs = Number(args.get("update-timeout-ms") ?? "600000");
const boxExportDir = args.get("box-export-dir") ?? null;
const sourceHsrBox = args.get("source-hsr-box") ?? null;
const sourceDateMonths = {
  january: "01", february: "02", march: "03", april: "04",
  may: "05", june: "06", july: "07", august: "08",
  september: "09", october: "10", november: "11", december: "12",
};

function normalizeSourceDate(value) {
  const text = String(value ?? "").trim();
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s]|$)/u);
  if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`;
  const named = text.match(/^(\d{1,2})\/([A-Za-z]+)\/(\d{4})$/u);
  const month = named ? sourceDateMonths[named[2].toLowerCase()] : "";
  return named && month
    ? `${named[3]}-${month}-${named[1].padStart(2, "0")}`
    : "";
}

function verifyVisibleUpdateHealthSampleAges(snapshot) {
  const cards = snapshot.updateHealthSampleCards ?? [];
  assert(cards.length === 2
    && new Set(cards.map((card) => card.game)).size === 2
    && cards.some((card) => card.game === "hsr")
    && cards.some((card) => card.game === "zzz"),
  "update-health sample cards are not uniquely bound to both games", cards);
  let hasStaleSample = false;
  for (const card of cards) {
    assert(card.visible, "update-health latest sample is not visibly rendered", card);
    const match = card.sample.match(/终局最新采样\s+(\d{4}-\d{2}-\d{2})/u);
    assert(match, "update-health card is missing its latest sample date", card);
    const age = sampleAgeDays(match[1], localDateKey());
    assert(age !== null, "update-health card exposes an invalid latest sample date", card);
    if (age >= ENDGAME_SAMPLE_STALE_AFTER_DAYS) {
      hasStaleSample = true;
      assert(card.sample.includes(`已 ${age} 天未更新`) && card.stale,
        "update-health card hides the exact stale sample age or warning state", { card, age });
    } else {
      assert(!/已\s+\d+\s+天未更新/u.test(card.sample),
        "update-health card incorrectly marks a recent sample as stale", { card, age });
    }
  }
  if (hasStaleSample) {
    assert(snapshot.updateHealthState === "warning",
      "stale endgame samples do not put update health into warning state", snapshot);
  }
}

if (!webSocketUrl) throw new Error("--ws is required");
if ((boxExportDir === null) !== (sourceHsrBox === null)) {
  throw new Error("--box-export-dir and --source-hsr-box must be provided together");
}
if (boxExportDir !== null && (!path.isAbsolute(boxExportDir) || !path.isAbsolute(sourceHsrBox))) {
  throw new Error("Box export verification paths must be absolute");
}
for (const game of ["hsr", "zzz"]) {
  if (!Number.isSafeInteger(expectedOwned[game]) || expectedOwned[game] < 0) {
    throw new Error(`--expected-${game}-owned must be a non-negative integer`);
  }
  if (!Number.isSafeInteger(expectedTotal[game]) || expectedTotal[game] <= 0) {
    throw new Error(`--expected-${game}-total must be a positive integer`);
  }
  if (expectedBannerCount[game] !== null
    && (!Number.isSafeInteger(expectedBannerCount[game]) || expectedBannerCount[game] <= 0)) {
    throw new Error(`--expected-${game}-banner-count must be a positive integer`);
  }
  if (expectedBannerNames[game].length > 0
    && expectedBannerNames[game].length !== expectedBannerCount[game]) {
    throw new Error(`--expected-${game}-banner-names must match the expected banner count`);
  }
  if (expectedNextBannerCount[game] !== null
    && (!Number.isSafeInteger(expectedNextBannerCount[game]) || expectedNextBannerCount[game] <= 0)) {
    throw new Error(`--expected-${game}-next-banner-count must be a positive integer`);
  }
  if (expectedNextBannerNames[game].length > 0
    && expectedNextBannerNames[game].length !== expectedNextBannerCount[game]) {
    throw new Error(`--expected-${game}-next-banner-names must match the expected next banner count`);
  }
}
if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 45000 || timeoutMs > 120000) {
  throw new Error("--timeout-ms must be an integer between 45000 and 120000");
}
if (runUpdatesValue !== "true" && runUpdatesValue !== "false") {
  throw new Error("--run-updates must be true or false");
}
if (!Number.isSafeInteger(updateTimeoutMs) || updateTimeoutMs < 30000 || updateTimeoutMs > 900000) {
  throw new Error("--update-timeout-ms must be an integer between 30000 and 900000");
}

class CdpSession {
  constructor(url) {
    const endpoint = new URL(url);
    if (endpoint.hostname === "localhost") endpoint.hostname = "127.0.0.1";
    this.url = endpoint.href;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    this.socket = new WebSocket(this.url);
    this.socket.addEventListener("message", (event) => this.#onMessage(event));
    await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("CDP WebSocket connection timed out")), 10000);
      this.socket.addEventListener("open", () => {
        clearTimeout(timer);
        resolve();
      }, { once: true });
      this.socket.addEventListener("error", (event) => {
        clearTimeout(timer);
        const detail = event?.message || event?.error?.message || "unknown network error";
        reject(new Error(`CDP WebSocket connection failed: ${detail}; endpoint=${this.url}`));
      }, { once: true });
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) ?? new Set();
    listeners.add(listener);
    this.listeners.set(method, listeners);
  }

  send(method, params = {}, sessionId = undefined) {
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const commandTimeoutMs = method === "Runtime.evaluate"
        ? Math.max(15000, timeoutMs + 5000)
        : 15000;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP command timed out: ${method}`));
      }, commandTimeoutMs);
      this.pending.set(id, { resolve, reject, timer, method });
      this.socket.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
    });
  }

  close() {
    for (const { reject, timer, method } of this.pending.values()) {
      clearTimeout(timer);
      reject(new Error(`CDP session closed before ${method} returned`));
    }
    this.pending.clear();
    this.socket?.close();
  }

  #onMessage(event) {
    let message;
    try {
      message = JSON.parse(String(event.data));
    } catch {
      return;
    }
    if (message.id !== undefined) {
      const pending = this.pending.get(message.id);
      if (!pending) return;
      clearTimeout(pending.timer);
      this.pending.delete(message.id);
      if (message.error) pending.reject(new Error(`${pending.method}: ${message.error.message}`));
      else pending.resolve(message.result ?? {});
      return;
    }
    for (const listener of this.listeners.get(message.method) ?? []) {
      listener(message.params ?? {}, message.sessionId);
    }
  }
}

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function waitFor(description, probe, waitTimeoutMs = timeoutMs) {
  const deadline = Date.now() + waitTimeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await probe();
      if (value) return value;
    } catch (error) {
      if (isVisualizerStartupFailureError(error)) throw error;
      lastError = error;
    }
    await delay(150);
  }
  const suffix = lastError ? `; last error: ${lastError.message}` : "";
  throw new Error(`timed out waiting for ${description}${suffix}`);
}

function flattenFrames(node, rows = []) {
  if (!node?.frame) return rows;
  rows.push(node.frame);
  for (const child of node.childFrames ?? []) flattenFrames(child, rows);
  return rows;
}

function assert(condition, message, details) {
  if (condition) return;
  const suffix = details === undefined ? "" : `: ${JSON.stringify(details)}`;
  throw new Error(`${message}${suffix}`);
}

const outerExpression = `(() => {
  const visible = (element) => !!element && element.getClientRects().length > 0;
  const frames = [...document.querySelectorAll('iframe.visualizer-frame')];
  const activeFrames = frames.filter((candidate) => !candidate.hidden);
  const frame = activeFrames[0];
  const utilities = document.querySelector('details.utilities');
  const updateHealthPanel = document.querySelector('.update-health');
  const updateHealthGameItems = [...(updateHealthPanel?.querySelectorAll('.update-health-game') ?? [])];
  const updateHealthSampleCards = updateHealthGameItems.map((item) => {
    const sample = item.querySelector('.update-health-game-summary .update-health-sample');
    return {
      game: item.dataset.game ?? '',
      sample: sample?.textContent?.trim() ?? '',
      visible: visible(sample),
      stale: item.classList.contains('has-stale-sample'),
    };
  });
  const updateHealthState = ['loading', 'healthy', 'warning', 'busy', 'error']
    .find((value) => updateHealthPanel?.classList.contains(value)) ?? '';
  const activeGame = [...document.querySelectorAll('.game-button')]
    .find((button) => button.getAttribute('aria-pressed') === 'true');
  return {
    href: location.href,
    readyState: document.readyState,
    ready: document.documentElement.dataset.mihoAppReady ?? '',
    visualizerStartupState: document.documentElement.dataset.visualizerStartupState ?? '',
    visualizerStartupFailureCode: document.documentElement.dataset.visualizerStartupFailureCode ?? '',
    visualizerStartupGame: document.documentElement.dataset.visualizerStartupGame ?? '',
    brand: document.querySelector('.brand .eyebrow')?.textContent?.trim() ?? '',
    updateHealthVisible: visible(updateHealthPanel),
    updateHealthState,
    updateHealthBadge: updateHealthPanel?.querySelector('.update-health-badge')?.textContent?.trim() ?? '',
    updateHealthSummary: updateHealthPanel?.querySelector('.update-health-summary')?.textContent?.trim() ?? '',
    updateHealthDetail: updateHealthPanel?.querySelector('.update-health-detail')?.textContent?.trim() ?? '',
    updateHealthGames: updateHealthGameItems.map((item) => item.textContent?.trim() ?? ''),
    updateHealthSampleCards,
    updateHealthGameCompletedAtUtc: updateHealthGameItems.map((item) => item.dataset.completedAtUtc ?? ''),
    firstPanel: document.querySelector('main.dashboard')?.firstElementChild?.className ?? '',
    visualizerTitle: document.querySelector('.visualizer-panel h2')?.textContent?.trim() ?? '',
    frameCount: frames.length,
    activeFrameCount: activeFrames.length,
    frameGame: frame?.dataset.game ?? '',
    framePage: frame?.dataset.page ?? '',
    frameProbeId: frame?.dataset.probeId ?? '',
    frameProbeLoadCount: Number.parseInt(frame?.dataset.probeLoadCount ?? '-1', 10),
    frameLoaded: frame?.dataset.loaded === 'true',
    frameDataRevision: frame?.dataset.loadedRevision ?? '',
    frameSrc: frame?.getAttribute('src') ?? '',
    frameSandbox: frame?.getAttribute('sandbox') ?? '',
    frameVisible: visible(frame) && !frame.hidden,
    frameHeight: frame?.getBoundingClientRect().height ?? 0,
    utilitiesOpen: utilities?.open ?? null,
    utilitiesSummary: utilities?.querySelector(':scope > summary')?.textContent?.trim() ?? '',
    visibleTaskIds: [...document.querySelectorAll('.task-id')].filter(visible).length,
    activeGame: activeGame?.textContent?.trim() ?? '',
  };
})()`;

const productExpression = `(async () => {
  const selectUniquePhaseMetadata = ${selectUniquePhaseMetadata.toString()};
  const visualState = (element) => {
    if (!element) return { visible: false, display: '', visibility: '', opacity: null, rectCount: 0 };
    const own = getComputedStyle(element);
    let visible = element.getClientRects().length > 0;
    for (let current = element; current; current = current.parentElement) {
      const style = getComputedStyle(current);
      const opacity = Number.parseFloat(style.opacity);
      if (style.display === 'none'
        || style.visibility === 'hidden'
        || style.visibility === 'collapse'
        || (Number.isFinite(opacity) && opacity <= 0)) {
        visible = false;
        break;
      }
    }
    const opacity = Number.parseFloat(own.opacity);
    return {
      visible,
      display: own.display,
      visibility: own.visibility,
      opacity: Number.isFinite(opacity) ? opacity : null,
      rectCount: element.getClientRects().length,
    };
  };
  const visible = (element) => visualState(element).visible;
  const settleImages = async (items) => {
    for (const image of items) image.loading = 'eager';
    await Promise.all(items.map(async (image) => {
      if (!image.complete) {
        await Promise.race([
          new Promise((resolve) => {
            image.addEventListener('load', resolve, { once: true });
            image.addEventListener('error', resolve, { once: true });
          }),
          new Promise((resolve) => setTimeout(resolve, 10000)),
        ]);
      }
      try { await image.decode(); } catch {}
    }));
  };
  const cards = [...document.querySelectorAll('#boxGrid .box-card')];
  const images = cards.map((card) => card.querySelector('img')).filter(Boolean);
  await settleImages(images);
  const basename = (value) => {
    try {
      const name = decodeURIComponent(new URL(value, location.href).pathname.split('/').pop() ?? '');
      return name.replace(/\.[^.]+$/, '');
    } catch { return ''; }
  };
  const rosterRows = typeof DATA === 'object' && Array.isArray(DATA?.rosterRows) ? DATA.rosterRows : [];
  const usageRows = typeof DATA === 'object' && Array.isArray(DATA?.usageRows) ? DATA.usageRows : [];
  const latestEndgameSampleDate = usageRows
    .map((row) => String(row?.collect_date ?? '').trim())
    .filter((value) => /^\\d{4}-\\d{2}-\\d{2}$/.test(value))
    .sort()
    .at(-1) ?? '';
  const tierUpdatedAt = String(DATA?.meta?.tierUpdatedDate ?? DATA?.meta?.tierUpdatedAt ?? '').trim();
  const freshnessByMode = DATA?.freshness ?? DATA?.data_quality?.modes ?? DATA?.dataQuality?.modes ?? {};
  const staleModeCodes = Object.entries(freshnessByMode)
    .filter(([, value]) => (value?.freshness?.status ?? value?.status) === 'stale')
    .map(([mode]) => mode)
    .sort();
  const statePage = typeof state === 'object' ? state?.page ?? '' : '';
  const analysisMode = typeof state === 'object' ? state?.mode ?? '' : '';
  const analysisModeUsageRows = usageRows.filter((row) => (row?.tier_mode ?? row?.mode) === analysisMode);
  const datedAnalysisRows = analysisModeUsageRows
    .filter((row) => row?.collect_date)
    .slice()
    .sort((left, right) => (
      String(left?.collect_date ?? '') + '|' + String(left?.phase_ver ?? '') + '|'
        + String(left?.snapshot_id ?? '') + '|' + String(left?.phase_name ?? '')
    ).localeCompare(
      String(right?.collect_date ?? '') + '|' + String(right?.phase_ver ?? '') + '|'
        + String(right?.snapshot_id ?? '') + '|' + String(right?.phase_name ?? ''),
    ));
  const latestAnalysisRow = datedAnalysisRows[datedAnalysisRows.length - 1] ?? {};
  const analysisSampleDate = String(latestAnalysisRow?.collect_date ?? '').trim();
  const analysisSamplePhase = String(latestAnalysisRow?.phase_ver ?? '').trim();
  const analysisSampleSnapshot = String(latestAnalysisRow?.snapshot_id ?? '').trim();
  const analysisSamplePhaseName = String(latestAnalysisRow?.phase_name ?? '').trim();
  const phaseRows = typeof DATA === 'object' && Array.isArray(DATA?.phaseInfoRows)
    ? DATA.phaseInfoRows.filter((row) => row?.mode === analysisMode)
    : [];
  const exactPhase = analysisSampleDate
    ? selectUniquePhaseMetadata(phaseRows, latestAnalysisRow)
    : null;
  const latestPhase = !analysisSampleDate
    ? phaseRows.slice().sort((left, right) => (
      String(left?.collect_date ?? '') + '|' + String(left?.phase_ver ?? '') + '|' + String(left?.snapshot_id ?? '')
    ).localeCompare(
      String(right?.collect_date ?? '') + '|' + String(right?.phase_ver ?? '') + '|' + String(right?.snapshot_id ?? ''),
    ))[phaseRows.length - 1]
    : null;
  const matchedPhase = exactPhase || latestPhase || null;
  const analysisPhaseInfo = matchedPhase || latestAnalysisRow;
  const phaseNameCn = String(analysisPhaseInfo?.phase_name_cn ?? '').trim();
  const phaseNameRaw = String(analysisPhaseInfo?.phase_name ?? '').trim();
  const compactPhaseLabel = (value) => String(value || '').replace(/[\\s·:_-]+/gu, '').toLowerCase();
  const zzzPhaseNamePlaceholders = new Set([
    analysisSamplePhase,
    analysisSamplePhase + ' ' + analysisMode,
    analysisMode + ' ' + analysisSamplePhase,
    (analysisMode === 'sd' ? '式舆防卫 ' : '危局强袭 ') + analysisSamplePhase,
    (analysisMode === 'sd' ? '式舆防卫战 ' : '危局强袭战 ') + analysisSamplePhase,
  ].map(compactPhaseLabel).filter(Boolean));
  const expectedPhaseName = [phaseNameCn, phaseNameRaw].find((name) => name
    && name !== '中文期名待维护'
    && (!(analysisMode === 'sd' || analysisMode === 'da')
      || !zzzPhaseNamePlaceholders.has(compactPhaseLabel(name)))) ?? '';
  const mechanicNameRaw = String(analysisPhaseInfo?.mechanic_name ?? '').trim();
  const expectedMechanicName = mechanicNameRaw
    && !['当期数据', '机制效果待维护'].includes(mechanicNameRaw)
    ? mechanicNameRaw
    : '';
  const analysisExpectedPhase = {
    matched: Boolean(matchedPhase),
    sampleDate: analysisSampleDate || String(analysisPhaseInfo?.collect_date ?? '').trim(),
    phaseVer: String(analysisPhaseInfo?.phase_ver ?? analysisSamplePhase).trim(),
    snapshotId: String(analysisPhaseInfo?.snapshot_id ?? analysisSampleSnapshot).trim(),
    phaseName: expectedPhaseName,
    mechanicName: expectedMechanicName,
    startDate: String(analysisPhaseInfo?.start_date ?? latestAnalysisRow?.start_date ?? '').trim(),
    endDate: String(analysisPhaseInfo?.end_date ?? latestAnalysisRow?.end_date ?? '').trim(),
    status: String(analysisPhaseInfo?.phase_status ?? latestAnalysisRow?.phase_status ?? '').trim(),
  };
  const ownedStateCount = typeof box === 'object' && box?.owned instanceof Set ? box.owned.size : -1;
  const slugByDisplayName = new Map(rosterRows.map((row) => [
    String(row?.character_name_cn || row?.character_name_en || row?.character_slug || '').trim(),
    row?.character_slug ?? '',
  ]));
  const mappingErrors = cards.flatMap((card) => {
    const displayName = card.querySelector('.box-name, .name')?.textContent?.trim() ?? '';
    const slug = card.dataset.slug || slugByDisplayName.get(displayName) || '';
    const image = card.querySelector('img');
    const actual = basename(image?.getAttribute('src') ?? '');
    return slug && actual === slug ? [] : [{ slug, actual }];
  });
  const dataMappingErrors = rosterRows.flatMap((row) => {
    const actual = basename(row?.icon_url ?? '');
    return row?.character_slug && actual === row.character_slug
      ? []
      : [{ slug: row?.character_slug ?? '', actual }];
  });
  const brokenImages = images.flatMap((image) => image.complete && image.naturalWidth > 0
    ? []
    : [{ src: image.getAttribute('src') ?? '', complete: image.complete, naturalWidth: image.naturalWidth }]);
  const emptyImages = document.querySelectorAll('img[src=""]').length;
  const tabs = [...document.querySelectorAll('#appTabs button, #tabs button')].map((button) => ({
    text: button.textContent?.trim() ?? '',
    active: button.classList.contains('active'),
  }));
  const visibleText = [];
  const textWalker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = textWalker.nextNode(); node; node = textWalker.nextNode()) {
    const value = node.nodeValue?.trim() ?? '';
    if (value && visible(node.parentElement)) visibleText.push(value);
  }
  const bannerCards = [...document.querySelectorAll('#bannerGrid .banner-card')].filter(visible);
  const bannerSectionTexts = [...document.querySelectorAll('#bannerGrid .banner-section-head p')]
    .filter(visible)
    .map((element) => element.textContent?.trim() ?? '');
  const currentBannerRows = typeof DATA === 'object' && Array.isArray(DATA?.bannerRows)
    ? DATA.bannerRows.filter((row) => row?.phase_status === 'current')
    : [];
  const nextBannerRows = typeof DATA === 'object' && Array.isArray(DATA?.bannerRows)
    ? DATA.bannerRows.filter((row) => row?.phase_status === 'next')
    : [];
  const dateDrivenBannerStatuses = new Set(['current', 'next', 'previous', 'expired', 'past']);
  const strictBannerBoundary = (value) => {
    const text = String(value ?? '').trim();
    if (!text) return null;
    if (!/^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}\\+08:00$/.test(text)) return Number.NaN;
    const parsed = Date.parse(text);
    return Number.isFinite(parsed) ? parsed : Number.NaN;
  };
  const bannerBoundaryFieldErrors = [];
  const bannerClockStatusErrors = [];
  const bannerClockNow = Date.now();
  for (const [index, row] of (typeof DATA === 'object' && Array.isArray(DATA?.bannerRows) ? DATA.bannerRows : []).entries()) {
    for (const field of ['phase_starts_at', 'phase_ends_at_exclusive']) {
      if (!Object.hasOwn(row ?? {}, field) || typeof row?.[field] !== 'string') {
        bannerBoundaryFieldErrors.push({ index, phaseId: String(row?.phase_id ?? ''), field, value: row?.[field] });
      }
    }
    const start = strictBannerBoundary(row?.phase_starts_at);
    const endExclusive = strictBannerBoundary(row?.phase_ends_at_exclusive);
    if (Number.isNaN(start)) bannerBoundaryFieldErrors.push({ index, phaseId: String(row?.phase_id ?? ''), field: 'phase_starts_at', value: row?.phase_starts_at });
    if (Number.isNaN(endExclusive)) bannerBoundaryFieldErrors.push({ index, phaseId: String(row?.phase_id ?? ''), field: 'phase_ends_at_exclusive', value: row?.phase_ends_at_exclusive });
    const declared = String(row?.declared_phase_status || row?.phase_status || '').trim().toLowerCase();
    if (!dateDrivenBannerStatuses.has(declared) || (start === null && endExclusive === null)
      || Number.isNaN(start) || Number.isNaN(endExclusive)) continue;
    const expectedStatus = start !== null && bannerClockNow < start
      ? 'next'
      : endExclusive !== null && bannerClockNow >= endExclusive
        ? 'previous'
        : 'current';
    if (row?.phase_status !== expectedStatus) {
      bannerClockStatusErrors.push({
        index,
        phaseId: String(row?.phase_id ?? ''),
        actual: String(row?.phase_status ?? ''),
        expected: expectedStatus,
      });
    }
  }
  const bannerPhaseValue = typeof banner === 'object' ? banner?.phase ?? '' : '';
  const renderedBannerRows = bannerPhaseValue === 'current'
    ? currentBannerRows
    : bannerPhaseValue === 'next'
      ? nextBannerRows
      : typeof DATA === 'object' && Array.isArray(DATA?.bannerRows)
        ? DATA.bannerRows
        : [];
  const bannerRefresh = typeof DATA === 'object' && DATA?.bannerRefresh && typeof DATA.bannerRefresh === 'object'
    ? DATA.bannerRefresh
    : {};
  const bannerRefreshFetchedAt = String(bannerRefresh?.fetched_at ?? '').trim();
  const bannerRefreshDate = new Date(bannerRefreshFetchedAt);
  const padDatePart = (value) => String(value).padStart(2, '0');
  const bannerRefreshExpectedMinutes = [];
  const rawRefreshMinute = bannerRefreshFetchedAt.match(/^(\\d{4}-\\d{2}-\\d{2})T(\\d{2}:\\d{2})/);
  if (rawRefreshMinute) bannerRefreshExpectedMinutes.push(rawRefreshMinute[1] + ' ' + rawRefreshMinute[2]);
  if (Number.isFinite(bannerRefreshDate.getTime())) {
    bannerRefreshExpectedMinutes.push(
      String(bannerRefreshDate.getFullYear()) + '-'
        + padDatePart(bannerRefreshDate.getMonth() + 1) + '-'
        + padDatePart(bannerRefreshDate.getDate()) + ' '
        + padDatePart(bannerRefreshDate.getHours()) + ':'
        + padDatePart(bannerRefreshDate.getMinutes()),
    );
    const chinaRefreshDate = new Date(bannerRefreshDate.getTime() + 8 * 60 * 60 * 1000);
    bannerRefreshExpectedMinutes.push(
      String(chinaRefreshDate.getUTCFullYear()) + '-'
        + padDatePart(chinaRefreshDate.getUTCMonth() + 1) + '-'
        + padDatePart(chinaRefreshDate.getUTCDate()) + ' '
        + padDatePart(chinaRefreshDate.getUTCHours()) + ':'
        + padDatePart(chinaRefreshDate.getUTCMinutes()),
    );
  }
  const bannerImages = bannerCards.map((card) => card.querySelector('img')).filter(Boolean);
  await settleImages(bannerImages);
  const bannerBrokenImages = bannerImages.flatMap((image) => image.complete && image.naturalWidth > 0
    ? []
    : [{ src: image.getAttribute('src') ?? '', complete: image.complete, naturalWidth: image.naturalWidth }]);
  const bannerSlugByName = new Map(renderedBannerRows.map((row) => [
    String(row?.character_name_cn || row?.character_name_en || row?.character_slug || '').trim(),
    row?.character_slug ?? '',
  ]));
  const bannerMappingErrors = bannerCards.flatMap((card) => {
    const displayName = card.querySelector('h3')?.textContent?.trim() ?? '';
    const slug = bannerSlugByName.get(displayName) ?? '';
    const actual = basename(card.querySelector('img')?.getAttribute('src') ?? '');
    return slug && actual === slug ? [] : [{ displayName, slug, actual }];
  });
  const analysisElement = document.querySelector('#analysisView');
  const chart = document.querySelector('#chart');
  const characterList = document.querySelector('#characterList');
  const characterCards = [...document.querySelectorAll('#characterList .character-card')].filter(visible);
  const characterImages = characterCards.map((card) => card.querySelector('img')).filter(Boolean);
  await settleImages(characterImages);
  const characterBrokenImages = characterImages.flatMap((image) => image.complete && image.naturalWidth > 0
    ? []
    : [{ src: image.getAttribute('src') ?? '', complete: image.complete, naturalWidth: image.naturalWidth }]);
  const chartMarks = [...(chart?.querySelectorAll('path, line, rect, circle, image, text') ?? [])];
  const dataRequests = performance.getEntriesByType('resource')
    .map((entry) => ({name: String(entry.name || ''), initiatorType: String(entry.initiatorType || '')}))
    .filter((entry) => /\\/data(?:\\.v2)?\\.json(?:[?#]|$)/.test(entry.name));
  return {
    href: location.href,
    readyState: document.readyState,
    statePage,
    sourceMetaLine: document.querySelector('#metaLine')?.textContent?.trim() ?? '',
    latestEndgameSampleDate,
    tierUpdatedAt,
    staleModeCodes,
    boxVisible: !document.querySelector('#boxView')?.classList.contains('hidden'),
    subtitle: document.querySelector('#boxSubtitle')?.textContent?.trim() ?? '',
    tabs,
    cardCount: cards.length,
    rosterCount: rosterRows.length,
    ownedCardCount: cards.filter((card) => card.classList.contains('owned')).length,
    ownedStateCount,
    imageCount: images.length,
    decodedImageCount: images.length - brokenImages.length,
    brokenImages,
    emptyImages,
    mappingErrors,
    dataMappingErrors,
    dataRequests,
    usageRowCount: usageRows.length,
    analysisMode,
    analysisModeUsageRowCount: analysisModeUsageRows.length,
    analysisExpectedPhase,
    analysisVisualState: visualState(analysisElement),
    analysisVisible: visible(analysisElement),
    analysisTitle: document.querySelector('#chartTitle')?.textContent?.trim() ?? '',
    analysisSubtitle: document.querySelector('#chartSubtitle')?.textContent?.trim() ?? '',
    chartVisualState: visualState(chart),
    chartChildCount: chart?.querySelectorAll('*').length ?? 0,
    chartMarkCount: chartMarks.length,
    chartVisibleMarkCount: chartMarks.filter(visible).length,
    characterListVisualState: visualState(characterList),
    characterCardCount: characterCards.length,
    characterCardNames: characterCards.map((card) => card.querySelector('.name')?.textContent?.trim() ?? ''),
    characterImageCount: characterImages.length,
    characterBrokenImages,
    bannerVisible: visible(document.querySelector('#bannerView')),
    bannerTitle: document.querySelector('#bannerTitle')?.textContent?.trim() ?? '',
    bannerSubtitle: document.querySelector('#bannerSubtitle')?.textContent?.trim() ?? '',
    bannerBadges: document.querySelector('#bannerBadges')?.textContent?.trim() ?? '',
    bannerRefreshStatus: String(bannerRefresh?.status ?? '').trim(),
    bannerRefreshFetchedAt,
    bannerRefreshSourceLabel: String(bannerRefresh?.source_label ?? '').trim(),
    bannerRefreshExpectedMinutes: [...new Set(bannerRefreshExpectedMinutes)],
    bannerPhase: bannerPhaseValue,
    bannerAllRowCount: typeof DATA === 'object' && Array.isArray(DATA?.bannerRows) ? DATA.bannerRows.length : 0,
    bannerCurrentRowCount: currentBannerRows.length,
    bannerNextRowCount: nextBannerRows.length,
    bannerCardCount: bannerCards.length,
    bannerCardNames: bannerCards.map((card) => card.querySelector('h3')?.textContent?.trim() ?? ''),
    bannerCardRoles: bannerCards.map((card) => card.querySelector('.banner-kicker')?.textContent?.trim() ?? ''),
    bannerDataCurrentNames: currentBannerRows.map((row) => (
      String(row?.character_name_cn || row?.character_name_en || row?.character_slug || '').trim()
    )),
    bannerDataCurrentRoles: currentBannerRows.map((row) => String(row?.banner_role ?? '').trim()),
    bannerDataNextNames: nextBannerRows.map((row) => (
      String(row?.character_name_cn || row?.character_name_en || row?.character_slug || '').trim()
    )),
    bannerDataNextRoles: nextBannerRows.map((row) => String(row?.banner_role ?? '').trim()),
    bannerDataNextDateRanges: [...new Set(nextBannerRows
      .map((row) => String(row?.date_range ?? '').trim())
      .filter(Boolean))],
    bannerBoundaryFieldErrors,
    bannerClockStatusErrors,
    bannerSectionTexts,
    bannerImageCount: bannerImages.length,
    bannerBrokenImages,
    bannerMappingErrors,
    visibleMissingMessages: visibleText.filter((text) => /卡池数据未生成|该模式数据未生成|缺数据/.test(text)),
  };
})()`;

for (const [label, expression] of [["outer", outerExpression], ["product", productExpression]]) {
  try {
    Function(`return ${expression}`);
  } catch (error) {
    throw new Error(`${label} CDP expression is invalid: ${error instanceof Error ? error.message : error}`);
  }
}

const session = new CdpSession(webSocketUrl);
const contexts = new Map();
const attachedTargets = new Map();
session.on("Runtime.executionContextCreated", ({ context }) => {
  if (context?.id !== undefined) contexts.set(context.id, context);
});
session.on("Runtime.executionContextDestroyed", ({ executionContextId }) => {
  contexts.delete(executionContextId);
});
session.on("Runtime.executionContextsCleared", () => contexts.clear());
session.on("Target.detachedFromTarget", ({ sessionId, targetId }) => {
  if (targetId) attachedTargets.delete(targetId);
  for (const [attachedTargetId, attachedSessionId] of attachedTargets) {
    if (attachedSessionId === sessionId) attachedTargets.delete(attachedTargetId);
  }
});

async function evaluate(contextId, expression, sessionId = undefined, options = {}) {
  const result = await session.send("Runtime.evaluate", {
    ...(contextId === undefined || contextId === null ? {} : { contextId }),
    expression,
    returnByValue: true,
    awaitPromise: true,
    userGesture: options.userGesture === true,
  }, sessionId);
  if (result.exceptionDetails) {
    throw new Error(result.exceptionDetails.exception?.description ?? result.exceptionDetails.text ?? "evaluation failed");
  }
  return result.result?.value;
}

async function outerSnapshot(topId) {
  const snapshot = await evaluate(topId, outerExpression);
  throwIfVisualizerStartupFailed(snapshot);
  return snapshot;
}

function waitForDesktopVisualizerStage(topId, game, description, accept) {
  return waitForVisualizerStartupStage({
    description,
    game,
    timeoutMs,
    probe: () => evaluate(topId, outerExpression),
    accept,
  });
}

async function activeFrameContext(game) {
  const expectedPath = `/${game}/index.html`;
  return waitFor(`${game} Visualizer frame`, async () => {
    const tree = await session.send("Page.getFrameTree");
    const frames = flattenFrames(tree.frameTree).filter((candidate) => {
      try {
        const url = new URL(candidate.url);
        return url.hostname === "miho-visualizer.localhost"
          && url.pathname.endsWith(expectedPath);
      } catch {
        return false;
      }
    });
    assert(frames.length <= 1, `${game} has multiple matching Visualizer frames`, frames);
    const frame = frames[0];
    if (frame) {
      const context = [...contexts.values()].find((candidate) => candidate.auxData?.isDefault === true
        && candidate.auxData?.frameId === frame.id);
      if (context) return context;
    }

    const targets = await session.send("Target.getTargets");
    const matchingTargets = (targets.targetInfos ?? []).filter((candidate) => {
      try {
        const url = new URL(candidate.url);
        return candidate.type === "iframe"
          && url.hostname === "miho-visualizer.localhost"
          && url.pathname.endsWith(expectedPath);
      } catch {
        return false;
      }
    });
    assert(matchingTargets.length <= 1, `${game} has multiple matching Visualizer targets`, matchingTargets);
    const target = matchingTargets[0];
    if (!target) return null;
    let childSessionId = attachedTargets.get(target.targetId);
    if (!childSessionId) {
      const attached = await session.send("Target.attachToTarget", {
        targetId: target.targetId,
        flatten: true,
      });
      childSessionId = attached.sessionId;
      attachedTargets.set(target.targetId, childSessionId);
      await session.send("Runtime.enable", {}, childSessionId);
    }
    return { id: undefined, sessionId: childSessionId, targetId: target.targetId };
  });
}

async function topContext() {
  return waitFor("desktop top frame", async () => {
    const tree = await session.send("Page.getFrameTree");
    const frameId = tree.frameTree?.frame?.id;
    if (!frameId) return null;
    return [...contexts.values()].find((context) => context.auxData?.isDefault === true
      && context.auxData?.frameId === frameId) ?? null;
  });
}

async function productSnapshot(game, expectedPage = "box") {
  return waitFor(`${game} product DOM`, async () => {
    const context = await activeFrameContext(game);
    try {
      const snapshot = await evaluate(context.id, productExpression, context.sessionId);
      return snapshot?.readyState === "complete"
        && snapshot?.statePage === expectedPage
        && snapshot?.tabs?.length > 0
        && (expectedPage !== "box"
          || (snapshot?.rosterCount > 0 && snapshot?.cardCount === snapshot?.rosterCount))
        ? snapshot
        : null;
    } catch (error) {
      if (context.targetId) attachedTargets.delete(context.targetId);
      if (/Session with given id not found|Cannot find context|Inspected target navigated or closed/i.test(error.message)) {
        return null;
      }
      throw error;
    }
  });
}

function verifyOuter(snapshot, game, expectedPage = "box") {
  const gameLabel = game === "hsr" ? "崩坏：星穹铁道" : "绝区零";
  assert(snapshot.href === "https://tauri.localhost/#miho-app-ready-v1", "desktop URL is not the production ready URL", snapshot);
  assert(snapshot.readyState === "complete" && snapshot.ready === "v1", "desktop ready sentinel is absent", snapshot);
  assert(visualizerStartupStageReady(snapshot, game), "desktop Visualizer startup diagnostic is not ready for the selected game", snapshot);
  assert(snapshot.brand === "MIHO ENDGAME", "desktop brand is absent", snapshot);
  assert(automaticUpdateHealthReady(snapshot), "automatic update health did not reach a verified state", snapshot);
  assert(snapshot.updateHealthVisible, "automatic update health is not visible above the Visualizer", snapshot);
  assert(snapshot.updateHealthSummary.includes("本机产物校验通过"), "automatic update health lost artifact-integrity evidence", snapshot);
  assert(snapshot.updateHealthDetail.includes("终局采样取决于上游发布")
    && snapshot.updateHealthDetail.includes("历史样本不等于本机刷新失败"),
  "automatic update health does not distinguish upstream staleness from a local failure", snapshot);
  assert(snapshot.updateHealthGames.length === 2
    && snapshot.updateHealthGames.some((value) => value.includes("HSR 最近成功"))
    && snapshot.updateHealthGames.some((value) => value.includes("ZZZ 最近成功"))
    && snapshot.updateHealthGames.every((value) => /终局最新采样\s+\d{4}-\d{2}-\d{2}/u.test(value)),
  "automatic update health does not show both per-game success times and sample dates", snapshot);
  verifyVisibleUpdateHealthSampleAges(snapshot);
  assert(snapshot.firstPanel.includes("visualizer-panel"), "Visualizer is not the first product panel", snapshot);
  assert(snapshot.visualizerTitle.includes(gameLabel) && snapshot.visualizerTitle.includes("我的 Box"), "Visualizer title does not describe the selected Box", snapshot);
  assert(snapshot.frameCount === 2 && snapshot.activeFrameCount === 1, "desktop does not retain exactly two Visualizer frames with one active", snapshot);
  assert(snapshot.frameGame === game, "active Visualizer frame does not match the selected game", snapshot);
  assert(snapshot.framePage === expectedPage, `Visualizer page bridge did not report ${expectedPage}`, snapshot);
  assert(snapshot.frameLoaded && /^[a-f0-9]{64}$/.test(snapshot.frameDataRevision), "active Visualizer frame does not expose a validated data revision", snapshot);
  assert(snapshot.frameVisible && snapshot.frameHeight >= 500, "Visualizer frame is not visibly usable", snapshot);
  assert(snapshot.frameSrc.includes(`/${game}/index.html`) && snapshot.frameSrc.endsWith("#box"), "Visualizer frame did not open the Box page", snapshot);
  assert(new Set(snapshot.frameSandbox.split(/\s+/u)).has("allow-downloads"), "Visualizer frame does not permit Box downloads", snapshot);
  assert(snapshot.utilitiesOpen === false, "advanced utilities are expanded by default", snapshot);
  assert(snapshot.utilitiesSummary === "更新数据、生成报告与设置", "advanced utilities do not use the customer-facing label", snapshot);
  assert(snapshot.visibleTaskIds === 0, "technical task identifiers are visible on the main page", snapshot);
  assert(snapshot.activeGame === gameLabel, "game switch did not update the active game", snapshot);
}

async function verifyOuterCompactLayout(topId) {
  await session.send("Emulation.setDeviceMetricsOverride", {
    width: 860,
    height: 720,
    deviceScaleFactor: 1,
    mobile: false,
  });
  try {
    const snapshot = await waitFor("desktop 860px update-health layout", async () => evaluate(topId, `(() => {
      const panel = document.querySelector('.update-health');
      const items = [...(panel?.querySelectorAll('.update-health-game') ?? [])];
      const rect = panel?.getBoundingClientRect();
      return {
        innerWidth,
        documentScrollWidth: document.documentElement.scrollWidth,
        panel: rect ? {left: rect.left, right: rect.right, width: rect.width} : null,
        items: items.map((item) => {
          const itemRect = item.getBoundingClientRect();
          return {
            left: itemRect.left,
            right: itemRect.right,
            width: itemRect.width,
            sample: item.querySelector('.update-health-sample')?.textContent?.trim() ?? '',
          };
        }),
      };
    })()`));
    assert(Math.abs(snapshot.innerWidth - 860) <= 1
      && snapshot.documentScrollWidth <= snapshot.innerWidth
      && snapshot.panel
      && snapshot.panel.left >= 0
      && snapshot.panel.right <= snapshot.innerWidth + 1
      && snapshot.items.length === 2
      && snapshot.items.every((item) => item.left >= snapshot.panel.left - 1
        && item.right <= snapshot.panel.right + 1
        && item.width > 0
        && /终局最新采样\s+\d{4}-\d{2}-\d{2}/u.test(item.sample)),
    "desktop update-health cards overflow or hide sample dates at the supported minimum width", snapshot);
    return snapshot;
  } finally {
    await session.send("Emulation.clearDeviceMetricsOverride");
  }
}

function automaticUpdateHealthReady(snapshot) {
  return snapshot?.updateHealthState === "healthy" || snapshot?.updateHealthState === "warning";
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

async function zzzPersistenceSnapshot(context) {
  const snapshot = await evaluate(context.id, `(() => {
    const normalize = (value) => {
      if (Array.isArray(value)) return value.map(normalize);
      if (value && typeof value === 'object') {
        return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalize(value[key])]));
      }
      return value;
    };
    if (typeof box !== 'object' || !(box?.owned instanceof Set)) return null;
    const storageEntries = [];
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key?.startsWith('zzz_')) storageEntries.push([key, localStorage.getItem(key)]);
    }
    storageEntries.sort(([left], [right]) => left.localeCompare(right));
    const boxState = normalize({
      owned: [...box.owned].sort(),
      buildSlug: box.buildSlug ?? '',
      builds: box.builds ?? {},
    });
    return {
      boxState: JSON.stringify(boxState),
      localStorageState: JSON.stringify(storageEntries),
      ownedCount: box.owned.size,
      localStorageKeys: storageEntries.map(([key]) => key),
    };
  })()`, context.sessionId);
  assert(snapshot?.boxState && typeof snapshot.localStorageState === "string", "ZZZ state could not be snapshotted", snapshot);
  return {
    ...snapshot,
    boxSha256: sha256(snapshot.boxState),
    localStorageSha256: sha256(snapshot.localStorageState),
  };
}

function zzzPersistenceReceipt(snapshot) {
  return {
    boxSha256: snapshot.boxSha256,
    localStorageSha256: snapshot.localStorageSha256,
    ownedCount: snapshot.ownedCount,
    localStorageKeys: snapshot.localStorageKeys,
  };
}

function verifyZzzPersistence(before, after) {
  assert(after.boxState === before.boxState, "ZZZ Box state changed during the product probe", {
    before: before.boxSha256,
    after: after.boxSha256,
  });
  assert(after.localStorageState === before.localStorageState, "ZZZ localStorage changed during the product probe", {
    before: before.localStorageSha256,
    after: after.localStorageSha256,
    beforeKeys: before.localStorageKeys,
    afterKeys: after.localStorageKeys,
  });
  return {
    ...zzzPersistenceReceipt(after),
    boxUnchanged: true,
    localStorageUnchanged: true,
  };
}

async function verifyZzzBoxRoster(context) {
  const snapshot = await evaluate(context.id, `(() => {
    const rosterRows = typeof DATA === 'object' && Array.isArray(DATA?.rosterRows) ? DATA.rosterRows : [];
    const rosterBySlug = new Map(rosterRows.map((row) => [row.character_slug, row]));
    const slugByName = new Map(rosterRows.map((row) => [
      String(row.character_name_cn || row.character_name_en || row.character_slug || '').trim(),
      row.character_slug || '',
    ]));
    const statuses = (row) => String(row?.banner_statuses || '').split(';').filter(Boolean);
    const releaseOrder = (row) => {
      const raw = String(row?.release_order ?? '').trim();
      const value = Number(raw);
      return raw && Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
    };
    const cards = [...document.querySelectorAll('#boxGrid .box-card')].map((card, index) => {
      const displayName = card.querySelector('.box-name, .name')?.textContent?.trim() ?? '';
      const slug = card.dataset.slug || slugByName.get(displayName) || '';
      const rosterRow = rosterBySlug.get(slug);
      return {
        index,
        slug,
        displayName,
        statuses: statuses(rosterRow),
        releaseOrder: releaseOrder(rosterRow),
        metaText: [...card.querySelectorAll('.meta')].map((node) => node.textContent ?? '').join(' · '),
      };
    });
    const expectedSlugs = rosterRows
      .map((row, index) => ({ slug: row.character_slug, index, releaseOrder: releaseOrder(row) }))
      .sort((left, right) => left.releaseOrder - right.releaseOrder || left.index - right.index)
      .map((row) => row.slug);
    const isNorma = (row) => {
      const slug = String(row?.character_slug || '').toLowerCase();
      const nameCn = String(row?.character_name_cn || '');
      const nameEn = String(row?.character_name_en || '').toLowerCase();
      return slug === 'norma' || slug === 'nom' || nameCn.includes('诺姆') || nameEn === 'norma' || nameEn === 'nom';
    };
    const normaRoster = rosterRows.filter(isNorma).map((row) => ({
      slug: row.character_slug || '',
      name: row.character_name_cn || row.character_name_en || '',
    }));
    const normaCards = cards.filter((card) => card.slug === 'norma'
      || card.slug === 'nom'
      || card.displayName.includes('诺姆')
      || card.displayName.toLowerCase() === 'norma'
      || card.displayName.toLowerCase() === 'nom');
    const current = cards.filter((card) => card.statuses.includes('current'));
    const next = cards.filter((card) => card.statuses.includes('next'));
    const satellite = cards.filter((card) => card.statuses.includes('satellite'));
    const missingStatusMarkers = cards.filter((card) => (
      (card.statuses.includes('current') && !card.metaText.includes('当期UP'))
      || (card.statuses.includes('satellite') && !card.metaText.includes('卫星'))
    ));
    const orderingViolations = cards.flatMap((card, index) => (
      index > 0 && cards[index - 1].releaseOrder > card.releaseOrder
        ? [{ index, previous: cards[index - 1], card }]
        : []
    ));
    return {
      cardCount: cards.length,
      normaRoster,
      normaCards,
      currentCount: current.length,
      nextCount: next.length,
      satelliteCount: satellite.length,
      expectedSlugs,
      actualSlugs: cards.map((card) => card.slug),
      missingStatusMarkers,
      orderingViolations,
      leadingCards: cards.slice(0, 12),
    };
  })()`, context.sessionId);
  assert(snapshot.normaRoster.length === 1 && snapshot.normaRoster[0].slug === "norma", "ZZZ roster does not contain exactly one canonical Norma row", snapshot.normaRoster);
  assert(snapshot.normaCards.length === 1 && snapshot.normaCards[0].slug === "norma", "ZZZ Box does not render exactly one canonical Norma card", snapshot.normaCards);
  assert(snapshot.currentCount > 0 && snapshot.satelliteCount > 0, "ZZZ Box is missing current or satellite roster cards", snapshot);
  assert(JSON.stringify(snapshot.actualSlugs) === JSON.stringify(snapshot.expectedSlugs), "ZZZ Box card identities do not exactly follow stable release_order", {
    expected: snapshot.expectedSlugs,
    actual: snapshot.actualSlugs,
  });
  assert(snapshot.orderingViolations.length === 0, "ZZZ Box does not follow actual release_order", {
    violations: snapshot.orderingViolations,
    leadingCards: snapshot.leadingCards,
  });
  assert(snapshot.missingStatusMarkers.length === 0, "ZZZ Box lost current/satellite labels while removing their sort priority", snapshot.missingStatusMarkers);
  return {
    normaSlug: snapshot.normaCards[0].slug,
    normaCardCount: snapshot.normaCards.length,
    currentCount: snapshot.currentCount,
    nextCount: snapshot.nextCount,
    satelliteCount: snapshot.satelliteCount,
    leadingCards: snapshot.leadingCards,
    orderingVerified: true,
  };
}

function comparableBox(value) {
  const normalize = (item) => {
    if (Array.isArray(item)) return item.map(normalize);
    if (item && typeof item === "object") {
      return Object.fromEntries(Object.keys(item).sort().map((key) => [key, normalize(item[key])]));
    }
    return item;
  };
  return normalize({
    version: value?.version,
    owned: value?.owned,
    buildSlug: value?.buildSlug ?? "",
    builds: value?.builds ?? {},
  });
}

async function verifyHsrBoxExport(context) {
  if (boxExportDir === null) return null;
  const exportNamePattern = /^hsr_box_state(?: \(\d+\))?\.json$/u;
  const exportsBefore = new Set(readdirSync(boxExportDir).filter((name) => exportNamePattern.test(name)));
  const sourceBefore = readFileSync(sourceHsrBox);
  const sourceState = JSON.parse(sourceBefore.toString("utf8"));
  const clicked = await evaluate(context.id, `(() => {
    const button = document.querySelector('#boxExportBtn');
    if (!button || button.disabled) return false;
    button.click();
    return true;
  })()`, context.sessionId, { userGesture: true });
  assert(clicked === true, "HSR Box export button could not be clicked");
  const exportResult = await waitFor("HSR Box export file and visible completion state", async () => {
    const newNames = readdirSync(boxExportDir)
      .filter((name) => exportNamePattern.test(name) && !exportsBefore.has(name));
    if (newNames.length !== 1) return null;
    const destination = path.join(boxExportDir, newNames[0]);
    if (!existsSync(destination) || statSync(destination).size === 0) return null;
    const buttonState = await evaluate(context.id, `(() => {
      const button = document.querySelector('#boxExportBtn');
      return button ? {
        disabled: button.disabled,
        text: button.textContent?.trim() ?? '',
        title: button.getAttribute('title') ?? '',
      } : null;
    })()`, context.sessionId);
    if (!buttonState || buttonState.disabled || !buttonState.text.includes('已导出到下载文件夹')) return null;
    if (buttonState.title !== path.basename(destination)) return null;
    try {
      return {
        destination,
        buttonText: buttonState.text,
        buttonTitle: buttonState.title,
        state: JSON.parse(readFileSync(destination, "utf8")),
      };
    } catch {
      return null;
    }
  });
  const { destination, buttonText, buttonTitle, state: exportedState } = exportResult;
  const sourceAfter = readFileSync(sourceHsrBox);
  assert(sha256(sourceAfter) === sha256(sourceBefore), "HSR Box export changed the saved Box state");
  assert(exportedState?.version === 2, "HSR Box export has an unexpected schema version", exportedState);
  assert(Array.isArray(exportedState?.owned) && exportedState.owned.length === expectedOwned.hsr, "HSR Box export has an unexpected owned count", exportedState);
  assert(JSON.stringify(comparableBox(exportedState)) === JSON.stringify(comparableBox(sourceState)), "HSR Box export differs from the saved Box state");
  return {
    fileName: path.basename(destination),
    bytes: statSync(destination).size,
    sha256: sha256(readFileSync(destination)),
    owned: exportedState.owned.length,
    sourceUnchanged: true,
    visibleCompletion: buttonText,
    visibleFileName: buttonTitle,
  };
}

function verifyProduct(snapshot, game) {
  const productUrl = new URL(snapshot.href);
  assert(snapshot.readyState === "complete", `${game} Visualizer did not finish loading`, snapshot);
  assert(productUrl.hostname === "miho-visualizer.localhost"
    && productUrl.pathname.endsWith(`/${game}/index.html`)
    && productUrl.hash === "#box", `${game} Visualizer URL is not #box`, snapshot);
  assert(snapshot.statePage === "box" && snapshot.boxVisible, `${game} Visualizer did not render My Box`, snapshot);
  assert(snapshot.tabs.some((tab) => tab.text === "我的 Box" && tab.active), `${game} My Box tab is not active`, snapshot);
  assert(snapshot.cardCount === expectedTotal[game] && snapshot.rosterCount === expectedTotal[game], `${game} roster is incomplete`, snapshot);
  assert(snapshot.ownedCardCount === expectedOwned[game] && snapshot.ownedStateCount === expectedOwned[game], `${game} owned Box count does not match disk state`, snapshot);
  assert(snapshot.imageCount === expectedTotal[game] && snapshot.decodedImageCount === expectedTotal[game], `${game} has broken character images`, snapshot);
  assert(snapshot.emptyImages === 0, `${game} contains empty character image sources`, snapshot);
  assert(snapshot.mappingErrors.length === 0 && snapshot.dataMappingErrors.length === 0, `${game} character images do not match character slugs`, snapshot);
  assert(snapshot.dataRequests.some((entry) => /\/data\.v2\.json(?:[?#]|$)/.test(entry.name)), `${game} did not request the v2 Visualizer payload`, snapshot.dataRequests);
  assert(!snapshot.dataRequests.some((entry) => /\/data\.json(?:[?#]|$)/.test(entry.name)), `${game} unexpectedly fell back to the legacy Visualizer payload`, snapshot.dataRequests);
}

async function verifyBoxBatchPreview(context, game) {
  const snapshot = await evaluate(context.id, `(() => {
    const normalize = (value) => {
      if (Array.isArray(value)) return value.map(normalize);
      if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalize(value[key])]));
      return value;
    };
    const state = () => JSON.stringify(normalize({
      owned: [...box.owned].sort(), builds: box.builds || {}, buildSlug: box.buildSlug || '',
      undoDepth: Array.isArray(boxUndoStack) ? boxUndoStack.length : -1,
      saveRevision: typeof boxSaveRevision === 'number' ? boxSaveRevision : -1,
    }));
    const before = state();
    const prompts = [];
    const originalConfirm = globalThis.confirm;
    try {
      globalThis.confirm = (message) => { prompts.push(String(message)); return false; };
      const button = document.querySelector('#boxMarkVisibleBtn');
      if (!button || button.disabled) throw new Error('missing enabled Box batch button');
      button.click();
    } finally {
      globalThis.confirm = originalConfirm;
    }
    return {before, after: state(), prompts};
  })()`, context.sessionId);
  assert(snapshot.before === snapshot.after, `${game} cancelled Box batch preview changed state`, snapshot);
  assert(snapshot.prompts.length === 1
    && snapshot.prompts[0].includes("批量修改预览")
    && snapshot.prompts[0].includes("拥有：新增")
    && snapshot.prompts[0].includes("移除")
    && snapshot.prompts[0].includes("确认修改")
    && snapshot.prompts[0].includes("可以撤销"), `${game} Box batch preview is incomplete`, snapshot.prompts);
  return {cancelled: true, stateUnchanged: true, prompt: snapshot.prompts[0]};
}

async function switchProductPage(context, game, page) {
  const labels = {
    box: "我的 Box",
    analysis: "终局分析",
    banner: "卡池",
  };
  const label = labels[page];
  assert(label, `unsupported ${game} product page`, { game, page });
  const clicked = await evaluate(context.id, `(() => {
    const button = [...document.querySelectorAll('#appTabs button, #tabs button')]
      .find((candidate) => candidate.textContent?.trim() === ${JSON.stringify(label)});
    if (!button || button.disabled) return false;
    button.click();
    return true;
  })()`, context.sessionId);
  assert(clicked === true, `could not switch ${game} Visualizer to ${page}`);
  return waitFor(`${game} ${page} product DOM`, async () => {
    const snapshot = await evaluate(context.id, productExpression, context.sessionId);
    const pageVisible = page === "analysis"
      ? snapshot?.analysisVisible
      : page === "banner"
        ? snapshot?.bannerVisible
        : snapshot?.boxVisible;
    return snapshot?.readyState === "complete" && snapshot?.statePage === page && pageVisible
      ? snapshot
      : null;
  });
}

async function verifyZzzRecommender(context) {
  const storageKey = "zzz_endgame_rec_v1";
  const saved = await evaluate(context.id, `(() => ({
    storageRaw: localStorage.getItem(${JSON.stringify(storageKey)}),
    recState: typeof rec === 'object' ? JSON.parse(JSON.stringify(rec)) : null,
  }))()`, context.sessionId);
  assert(saved?.recState && typeof saved.recState === "object", "ZZZ recommender state could not be snapshotted", saved);

  let result;
  try {
    result = await evaluate(context.id, `(async () => {
      const visible = (element) => !!element && element.getClientRects().length > 0;
      const need = (value, message) => {
        if (!value) throw new Error(message);
        return value;
      };
      const clickControl = (rootSelector, value) => {
        const button = need(document.querySelector(rootSelector + ' button[data-value="' + value + '"]'),
          'missing control ' + rootSelector + '=' + value);
        button.click();
        return button;
      };
      const primarySlate = () => document.querySelector('#recSlateList .rec-solution');
      const primarySlateCards = () => [...(primarySlate()?.querySelectorAll('.rec-slate-card') ?? [])];
      const waitForSlate = async (expected) => {
        const deadline = Date.now() + 30000;
        while (Date.now() < deadline) {
          const count = primarySlateCards().length;
          const subtitle = document.querySelector('#recSlateSubtitle')?.textContent?.trim() ?? '';
          const meta = document.querySelector('#recSlateMeta')?.textContent ?? '';
          if (primarySlate() && count === expected && subtitle && !meta.includes('正在')) return;
          await new Promise((resolve) => setTimeout(resolve, 50));
        }
        throw new Error('timed out waiting for ZZZ joint slate');
      };
      const tab = need([...document.querySelectorAll('#tabs button')]
        .find((button) => button.textContent?.trim().startsWith('组队推荐')), 'missing ZZZ recommender tab');
      tab.click();
      rec.targetScopes = {};
      rec.elements = {};
      rec.constraints = {};
      rec.gap = '3';
      rec.riskMode = 'warn';
      rec.sortMode = 'balanced';
      rec.search = '';
      rec.locks = {};
      if (typeof saveRec === 'function') saveRec();
      if (typeof renderRec === 'function') renderRec();
      clickControl('#recModeControl', 'da');
      await Promise.resolve();

      const defaults = {
        page: typeof state === 'object' ? state.page : '',
        viewVisible: visible(document.querySelector('#recommenderView')),
        controlVisible: visible(document.querySelector('#recTargetScopeControl')),
        targetValues: [...document.querySelectorAll('#recTargetScopeControl button')].map((button) => button.dataset.value),
        selectedTargets: [...document.querySelectorAll('#recTargetScopeControl button.active')].map((button) => button.dataset.value),
      };

      clickControl('#recTargetScopeControl', '1-2');
      await waitForSlate(2);
      const pair = {
        selectedTargets: [...document.querySelectorAll('#recTargetScopeControl button.active')].map((button) => button.dataset.value),
        storedTargets: JSON.parse(localStorage.getItem(${JSON.stringify(storageKey)}) || '{}').targetScopes?.da ?? [],
        planScopes: typeof recPlanScopes === 'function' ? recPlanScopes().map((scope) => scope.key) : [],
        slateCount: primarySlateCards().length,
        slateTitles: primarySlateCards().map((card) => card.querySelector('h3')?.textContent?.trim() ?? ''),
        slateSubtitle: document.querySelector('#recSlateSubtitle')?.textContent?.trim() ?? '',
        targetHint: document.querySelector('#recommenderView .rec-target-controls > p')?.textContent?.trim() ?? '',
        badgeText: document.querySelector('#recBadges')?.textContent?.trim() ?? '',
      };

      clickControl('#recModeControl', 'sd');
      await Promise.resolve();
      const modeIsolation = {
        mode: rec.mode,
        targetValues: [...document.querySelectorAll('#recTargetScopeControl button')].map((button) => button.dataset.value),
        selectedTargets: [...document.querySelectorAll('#recTargetScopeControl button.active')].map((button) => button.dataset.value),
        daStoredTargets: JSON.parse(localStorage.getItem(${JSON.stringify(storageKey)}) || '{}').targetScopes?.da ?? [],
      };
      clickControl('#recModeControl', 'da');
      await waitForSlate(2);
      const returnedPair = [...document.querySelectorAll('#recTargetScopeControl button.active')].map((button) => button.dataset.value);

      clickControl('#recTargetScopeControl', '1-1');
      await waitForSlate(1);
      const singleBeforeLastClick = {
        selectedTargets: [...document.querySelectorAll('#recTargetScopeControl button.active')].map((button) => button.dataset.value),
        planScopes: typeof recPlanScopes === 'function' ? recPlanScopes().map((scope) => scope.key) : [],
        slateCount: primarySlateCards().length,
      };
      clickControl('#recTargetScopeControl', '1-3');
      await Promise.resolve();
      const single = {
        ...singleBeforeLastClick,
        selectedAfterLastClick: [...document.querySelectorAll('#recTargetScopeControl button.active')].map((button) => button.dataset.value),
        storedTargets: JSON.parse(localStorage.getItem(${JSON.stringify(storageKey)}) || '{}').targetScopes?.da ?? [],
      };
      return {defaults, pair, modeIsolation, returnedPair, single};
    })()`, context.sessionId);

    assert(result.defaults.page === "recommender"
      && result.defaults.viewVisible
      && result.defaults.controlVisible
      && JSON.stringify(result.defaults.targetValues) === JSON.stringify(["1-1", "1-2", "1-3"])
      && JSON.stringify(result.defaults.selectedTargets) === JSON.stringify(["1-1", "1-2", "1-3"]), "ZZZ Dangerous Assault targets do not default to all real stages", result.defaults);
    assert(JSON.stringify(result.pair.selectedTargets) === JSON.stringify(["1-1", "1-3"])
      && JSON.stringify(result.pair.storedTargets) === JSON.stringify(["1-1", "1-3"])
      && JSON.stringify(result.pair.planScopes) === JSON.stringify(["1-1", "1-3"])
      && result.pair.slateCount === 2
      && result.pair.slateTitles.some((title) => title.includes("1 / 1"))
      && result.pair.slateTitles.some((title) => title.includes("1 / 3"))
      && result.pair.slateTitles.every((title) => !title.includes("1 / 2"))
      && result.pair.slateSubtitle.includes("2/2 队")
      && result.pair.targetHint.includes("只在已选关卡之间联合分配 Box")
      && result.pair.targetHint.includes("未选关卡不会占用或预留代理人")
      && result.pair.badgeText.includes("2 队模型"), "ZZZ Dangerous Assault did not honor a non-contiguous target pair", result.pair);
    assert(result.modeIsolation.mode === "sd"
      && JSON.stringify(result.modeIsolation.targetValues) === JSON.stringify(["5-1", "5-2", "5-3"])
      && JSON.stringify(result.modeIsolation.selectedTargets) === JSON.stringify(["5-1", "5-2", "5-3"])
      && JSON.stringify(result.modeIsolation.daStoredTargets) === JSON.stringify(["1-1", "1-3"])
      && JSON.stringify(result.returnedPair) === JSON.stringify(["1-1", "1-3"]), "ZZZ target stages leaked between modes", result.modeIsolation);
    assert(JSON.stringify(result.single.selectedTargets) === JSON.stringify(["1-3"])
      && JSON.stringify(result.single.planScopes) === JSON.stringify(["1-3"])
      && result.single.slateCount === 1
      && JSON.stringify(result.single.selectedAfterLastClick) === JSON.stringify(["1-3"])
      && JSON.stringify(result.single.storedTargets) === JSON.stringify(["1-3"]), "ZZZ Dangerous Assault did not preserve a valid single-stage target", result.single);
    return result;
  } finally {
    const restored = await evaluate(context.id, `(() => {
      const storageRaw = ${JSON.stringify(saved.storageRaw)};
      if (storageRaw === null) localStorage.removeItem(${JSON.stringify(storageKey)});
      else localStorage.setItem(${JSON.stringify(storageKey)}, storageRaw);
      const recState = ${JSON.stringify(saved.recState)};
      if (typeof rec === 'object' && rec && recState && typeof recState === 'object') {
        for (const key of Object.keys(rec)) delete rec[key];
        Object.assign(rec, recState);
        if (typeof ensureScope === 'function') ensureScope();
        if (typeof renderRec === 'function' && typeof state === 'object' && state.page === 'recommender') renderRec();
      }
      return localStorage.getItem(${JSON.stringify(storageKey)}) === storageRaw;
    })()`, context.sessionId);
    assert(restored === true, "ZZZ recommender localStorage snapshot was not restored");
    if (result) result.storageRestored = restored;
  }
}

async function verifyRecommenderSearchAndLock(context, game) {
  const storageKey = game === "hsr" ? "hsr_endgame_recommender_v1" : "zzz_endgame_rec_v1";
  const saved = await evaluate(context.id, `(() => ({
    storageRaw: localStorage.getItem(${JSON.stringify(storageKey)}),
    recState: JSON.parse(JSON.stringify(rec)),
  }))()`, context.sessionId);
  const signatureExpression = `JSON.stringify([...document.querySelectorAll('#recSlateList .rec-solution, #recSlateList .rec-slate-solution')].map((section) => ({text:(section.textContent||'').replace(/\\s+/g,' ').trim(),images:[...section.querySelectorAll('img')].map((image)=>image.title||image.getAttribute('src')||'')})))`;
  let receipt;
  try {
    await evaluate(context.id, `(() => {
      const tab = [...document.querySelectorAll('#appTabs button, #tabs button')].find((button) => button.textContent?.trim().startsWith('组队推荐'));
      if (!tab) throw new Error('missing recommender tab');
      tab.click();
      rec.search = '';
      rec.locks = {};
      ${game === "hsr"
        ? "rec.mode='as';rec.strategy='final';rec.scope='4-1';rec.targetScopes={as:['4-1','4-2']};rec.elements={};rec.constraints={};rec.gap='4';rec.riskMode='warn';rec.sortMode='balanced';ensureRecScope();saveRecSettings();renderRecommender();"
        : "rec.mode='da';rec.scope='1-1';rec.targetScopes={da:['1-1','1-2']};rec.elements={};rec.constraints={};rec.gap='3';rec.riskMode='warn';rec.sortMode='balanced';ensureScope();saveRec();renderRec();"}
      return true;
    })()`, context.sessionId);
    const ready = await waitFor(`${game} searchable lockable slate`, async () => evaluate(context.id, `(() => {
      const progress = [...document.querySelectorAll('#recSlateMeta, #recSlateStatus')].map((element) => element.textContent || '').join(' ');
      const candidateCount = document.querySelectorAll('#recList .rec-card').length;
      const primary = document.querySelector('#recSlateList .rec-solution, #recSlateList .rec-slate-solution');
      const lockCount = primary?.querySelectorAll('.rec-lock-button').length ?? 0;
      return candidateCount > 0 && lockCount === 2 && !progress.includes('正在')
        ? {candidateCount, lockCount, signature:${signatureExpression}}
        : null;
    })()`, context.sessionId));
    await evaluate(context.id, `(() => {
      const input=document.querySelector('#recSearchInput');
      if(!input)throw new Error('missing recommendation search');
      input.value='__miho_probe_no_match__';
      input.dispatchEvent(new Event('input',{bubbles:true}));
      return true;
    })()`, context.sessionId);
    const searched = await waitFor(`${game} debounced candidate search`, async () => evaluate(context.id, `(() => {
      if(rec.search!=='__miho_probe_no_match__'||document.querySelectorAll('#recList .rec-card').length!==0)return null;
      return {signature:${signatureExpression},message:[...document.querySelectorAll('#recSlateStatus, #recSlateMessage, #recSlateSubtitle')].map((element)=>element.textContent||'').join(' ')};
    })()`, context.sessionId));
    assert(searched.signature === ready.signature, `${game} recommendation search changed the joint slate`, {ready, searched});
    assert(searched.message.includes("搜索"), `${game} recommendation search did not explain joint-slate isolation`, searched);
    await evaluate(context.id, `(() => {const input=document.querySelector('#recSearchInput');input.value='';input.dispatchEvent(new Event('input',{bubbles:true}));return true;})()`, context.sessionId);
    await waitFor(`${game} cleared candidate search`, async () => evaluate(context.id, `(() => document.querySelectorAll('#recList .rec-card').length>0&&${signatureExpression}===${JSON.stringify(ready.signature)})()`, context.sessionId));
    await evaluate(context.id, `(() => {const button=document.querySelector('#recSlateList .rec-lock-button');if(!button)throw new Error('missing lock button');button.click();return true;})()`, context.sessionId);
    const locked = await waitFor(`${game} locked slate recomputation`, async () => evaluate(context.id, `(() => {
      const stored=JSON.parse(localStorage.getItem(${JSON.stringify(storageKey)})||'{}');
      const message=[...document.querySelectorAll('#recSlateStatus, #recSlateMessage, #recSlateSubtitle')].map((element)=>element.textContent||'').join(' ');
      const primary=document.querySelector('#recSlateList .rec-solution, #recSlateList .rec-slate-solution');
      return primary?.querySelectorAll('.rec-slate-card').length===2&&!message.includes('正在')&&primary.querySelector('.rec-lock-button[aria-pressed="true"]')&&Object.keys(stored.locks||{}).length===1&&message.includes('其余关卡已重新优化')?{message,lockKeys:Object.keys(stored.locks||{})}:null;
    })()`, context.sessionId));
    await evaluate(context.id, `(() => {const button=document.querySelector('#recSlateList .rec-lock-button[aria-pressed="true"]');if(!button)throw new Error('missing active lock');button.click();return true;})()`, context.sessionId);
    const unlocked = await waitFor(`${game} unlocked slate`, async () => evaluate(context.id, `(() => {
      const stored=JSON.parse(localStorage.getItem(${JSON.stringify(storageKey)})||'{}');
      const message=[...document.querySelectorAll('#recSlateStatus, #recSlateMessage, #recSlateSubtitle')].map((element)=>element.textContent||'').join(' ');
      const primary=document.querySelector('#recSlateList .rec-solution, #recSlateList .rec-slate-solution');
      return primary?.querySelectorAll('.rec-slate-card').length===2&&!message.includes('正在')&&!primary.querySelector('.rec-lock-button[aria-pressed="true"]')&&Object.keys(stored.locks||{}).length===0&&message.includes('已解锁')?{message}:null;
    })()`, context.sessionId));
    receipt = {searchLeftBefore: ready.candidateCount, searchLeftAfter: 0, jointSlateUnchanged: true, locked, unlocked};
    return receipt;
  } finally {
    const restored = await evaluate(context.id, `(() => {
      const raw=${JSON.stringify(saved.storageRaw)};if(raw===null)localStorage.removeItem(${JSON.stringify(storageKey)});else localStorage.setItem(${JSON.stringify(storageKey)},raw);
      for(const key of Object.keys(rec))delete rec[key];Object.assign(rec,${JSON.stringify(saved.recState)});
      ${game === "hsr" ? "ensureRecScope();renderRecommender();" : "ensureScope();renderRec();"}
      return localStorage.getItem(${JSON.stringify(storageKey)})===raw;
    })()`, context.sessionId);
    assert(restored, `${game} search/lock probe did not restore recommender state`);
    if (receipt) receipt.storageRestored = true;
  }
}

async function verifyHsrRecommender(context) {
  const storageKey = "hsr_endgame_recommender_v1";
  const saved = await evaluate(context.id, `(() => ({
    storageRaw: localStorage.getItem(${JSON.stringify(storageKey)}),
    recState: typeof rec === 'object' ? JSON.parse(JSON.stringify(rec)) : null,
  }))()`, context.sessionId);
  assert(saved?.recState && typeof saved.recState === "object", "HSR recommender state could not be snapshotted", saved);

  let result;
  try {
    result = await evaluate(context.id, `(async () => {
      const visible = (element) => !!element && element.getClientRects().length > 0;
      const need = (value, message) => {
        if (!value) throw new Error(message);
        return value;
      };
      const clickControl = (rootSelector, value) => {
        const button = need(document.querySelector(rootSelector + ' button[data-value="' + value + '"]'),
          'missing control ' + rootSelector + '=' + value);
        button.click();
        return button;
      };
      const primarySlate = () => document.querySelector('#recSlateList .rec-slate-solution');
      const primarySlateCards = () => [...(primarySlate()?.querySelectorAll('.rec-slate-card') ?? [])];
      const waitForSlate = async (expected, expectedModeLabel = '') => {
        const deadline = Date.now() + 30000;
        while (Date.now() < deadline) {
          const subtitle = document.querySelector('#recSlateSubtitle')?.textContent?.trim() ?? '';
          const status = document.querySelector('#recSlateStatus')?.textContent ?? '';
          if (primarySlate()
            && primarySlateCards().length === expected
            && subtitle
            && (!expectedModeLabel || subtitle.includes('目标：' + expectedModeLabel))
            && !status.includes('正在')) return;
          await new Promise((resolve) => setTimeout(resolve, 50));
        }
        throw new Error('timed out waiting for HSR joint slate');
      };
      const waitForCandidateCards = async () => {
        const deadline = Date.now() + 30000;
        while (Date.now() < deadline) {
          const cards = [...document.querySelectorAll('#recList .rec-card')];
          if (cards.length) return cards;
          await new Promise((resolve) => setTimeout(resolve, 50));
        }
        throw new Error('timed out waiting for HSR recommendation cards');
      };
      const tab = need([...document.querySelectorAll('#appTabs button, #tabs button')]
        .find((button) => button.textContent?.trim().startsWith('组队推荐')), 'missing recommender tab');
      tab.click();
      await Promise.resolve();
      const entry = {
        page: typeof state === 'object' ? state.page : '',
        hash: location.hash,
        tabActive: tab.classList.contains('active'),
        viewVisible: visible(document.querySelector('#recommenderView')),
      };

      need(document.querySelector('#resetBtn'), 'missing current-page reset button').click();
      rec.targetScopes = {};
      rec.elements = {};
      rec.constraints = {};
      rec.locks = {};
      rec.gap = '4';
      rec.riskMode = 'warn';
      rec.sortMode = 'balanced';
      rec.search = '';
      for (const slot of ['custom-1', 'custom-2', 'custom-3']) {
        delete rec.constraints?.['as|' + slot];
        delete rec.elements?.['as|' + slot];
      }
      if (typeof saveRecSettings === 'function') saveRecSettings();
      clickControl('#recModeControl', 'as');
      clickControl('#recStrategyControl', 'custom');
      await waitForCandidateCards();

      const initialTeamSelect = need(document.querySelector('#recTeamCountSelect'), 'missing team-count select');
      const initialScopeSelect = need(document.querySelector('#recScopeSelect'), 'missing recommender scope select');
      const customPool = typeof customPoolTemplates === 'function' ? customPoolTemplates(rec.mode) : [];
      const poolSources = [...new Set(customPool.flatMap((template) =>
        Array.isArray(template.evidenceScopes) && template.evidenceScopes.length
          ? template.evidenceScopes
          : [template.scope_key]
      ).filter(Boolean))].sort();
      const custom = {
        mode: rec.mode,
        strategy: rec.strategy,
        teamCount: initialTeamSelect.value,
        teamCountVisible: visible(document.querySelector('#recTeamCountControl')),
        targetControlVisible: visible(document.querySelector('#recTargetScopeControl')),
        scopeValues: [...initialScopeSelect.options].map((option) => option.value),
        hint: document.querySelector('#recStrategyHint')?.textContent?.trim() ?? '',
        subtitle: document.querySelector('#recSubtitle')?.textContent?.trim() ?? '',
        poolTemplateCount: customPool.length,
        poolSources,
        candidateSources: [...document.querySelectorAll('#recList .rec-meta')]
          .map((element) => element.textContent?.trim() ?? ''),
      };

      initialTeamSelect.value = '3';
      initialTeamSelect.dispatchEvent(new Event('change', { bubbles: true }));
      await Promise.resolve();
      const threeTeamScope = need(document.querySelector('#recScopeSelect'), 'scope select disappeared');
      const storedAfterThree = JSON.parse(localStorage.getItem(${JSON.stringify(storageKey)}) || '{}');
      const threeTeams = {
        teamCount: document.querySelector('#recTeamCountSelect')?.value ?? '',
        scopeValues: [...threeTeamScope.options].map((option) => option.value),
        storedTeamCount: storedAfterThree.teamCounts?.as ?? '',
      };

      const controls = {
        select: document.querySelector('#recCharacterSelect'),
        required: document.querySelector('#recRequireBtn'),
        excluded: document.querySelector('#recExcludeBtn'),
        clear: document.querySelector('#recConstraintClearBtn'),
        requiredList: document.querySelector('#recRequiredList'),
        excludedList: document.querySelector('#recExcludedList'),
      };
      Object.entries(controls).forEach(([name, element]) => need(element, 'missing constraint control ' + name));
      const choices = [...controls.select.options].map((option) => option.value).filter(Boolean);
      need(choices.length >= 2, 'not enough roster options to probe constraints');
      controls.select.value = choices[0];
      controls.required.click();
      controls.select.value = choices[1];
      controls.excluded.click();
      await Promise.resolve();

      const slotOneKey = rec.mode + '|' + rec.scope;
      const storedSlotOne = JSON.parse(localStorage.getItem(${JSON.stringify(storageKey)}) || '{}')
        .constraints?.[slotOneKey] ?? {};
      const slotOne = {
        key: slotOneKey,
        requiredSaved: Array.isArray(storedSlotOne.required) && storedSlotOne.required.includes(choices[0]),
        excludedSaved: Array.isArray(storedSlotOne.excluded) && storedSlotOne.excluded.includes(choices[1]),
        requiredChipCount: document.querySelector('#recRequiredList')?.children.length ?? -1,
        excludedChipCount: document.querySelector('#recExcludedList')?.children.length ?? -1,
      };

      const scopeSelect = need(document.querySelector('#recScopeSelect'), 'scope select disappeared after constraints');
      scopeSelect.value = 'custom-2';
      scopeSelect.dispatchEvent(new Event('change', { bubbles: true }));
      await Promise.resolve();
      const slotTwo = {
        key: rec.mode + '|' + rec.scope,
        requiredChipCount: document.querySelector('#recRequiredList')?.children.length ?? -1,
        excludedChipCount: document.querySelector('#recExcludedList')?.children.length ?? -1,
      };
      const returnScopeSelect = need(document.querySelector('#recScopeSelect'), 'scope select disappeared on slot two');
      returnScopeSelect.value = 'custom-1';
      returnScopeSelect.dispatchEvent(new Event('change', { bubbles: true }));
      await Promise.resolve();
      const returnedSlotOne = {
        requiredChipCount: document.querySelector('#recRequiredList')?.children.length ?? -1,
        excludedChipCount: document.querySelector('#recExcludedList')?.children.length ?? -1,
      };

      clickControl('#recStrategyControl', 'final');
      await Promise.resolve();
      delete rec.constraints?.['as|4-2'];
      delete rec.elements?.['as|4-2'];
      if (typeof saveRecSettings === 'function') saveRecSettings();
      const finalScopeSelect = need(document.querySelector('#recScopeSelect'), 'missing final scope select');
      finalScopeSelect.value = '4-2';
      finalScopeSelect.dispatchEvent(new Event('change', { bubbles: true }));
      await Promise.resolve();
      rec.targetScopes = {as: ['4-1', '4-2']};
      saveRecSettings();
      syncRecControls();
      renderRecommender();

      const sortSelect = need(document.querySelector('#recSortSelect'), 'missing recommendation sort select');
      const captureSort = async (mode) => {
        sortSelect.value = mode;
        sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
        const expectedModeLabel = mode === 'history' ? '历史表现' : mode === 'box' ? 'Box 即战力' : '综合推荐';
        await waitForSlate(recPlanScopes().length, expectedModeLabel);
        const cards = await waitForCandidateCards();
        const ranked = typeof rankedRecommendations === 'function' ? rankedRecommendations() : [];
        const keys = ranked.map((item) => typeof templatePoolKey === 'function'
          ? templatePoolKey(item.template)
          : [...(item.template?.chars ?? [])].sort().join('|'));
        const stored = JSON.parse(localStorage.getItem(${JSON.stringify(storageKey)}) || '{}');
        const expectedScoreLabel = mode === 'history' ? '历史参考分' : mode === 'box' ? 'Box 分' : '综合分';
        return {
          mode: rec.sortMode,
          storedMode: stored.sortMode ?? '',
          topKeys: keys.slice(0, 8),
          scoreMatches: ranked.every((item) => item.scoreMode === mode && item.score === item.scores?.[mode]),
          partsComplete: ranked.every((item) => ['balanced', 'history', 'box'].every((key) =>
            Array.isArray(item.scoreParts?.[key]) && Number.isFinite(item.scores?.[key]))),
          referenceCounts: cards.map((card) => card.querySelectorAll('.rec-score-refs > span').length),
          breakdowns: cards.map((card) => card.querySelector('.rec-score-breakdown')?.textContent?.trim() ?? ''),
          slateTitles: primarySlateCards().map((card) => card.querySelector('h3')?.textContent?.trim() ?? ''),
          slateSubtitle: document.querySelector('#recSlateSubtitle')?.textContent?.trim() ?? '',
          expectedScoreLabel,
          expectedModeLabel,
        };
      };
      const sortProbe = {
        options: [...sortSelect.options].map((option) => ({value: option.value, text: option.textContent?.trim() ?? ''})),
        balanced: await captureSort('balanced'),
        history: await captureSort('history'),
        box: await captureSort('box'),
      };
      rec.sortMode = 'balanced';
      rec.targetScopes = {};
      saveRecSettings();
      syncRecControls();
      renderRecommender();
      await Promise.resolve();

      const finalTargetRoot = need(document.querySelector('#recTargetScopeButtons'), 'missing final target-scope control');
      const finalDefaults = {
        targetControlVisible: visible(document.querySelector('#recTargetScopeControl')),
        teamCountVisible: visible(document.querySelector('#recTeamCountControl')),
        targetValues: [...finalTargetRoot.querySelectorAll('button')].map((button) => button.dataset.value),
        selectedTargets: [...finalTargetRoot.querySelectorAll('button.active')].map((button) => button.dataset.value),
      };

      clickControl('#recTargetScopeButtons', '4-2');
      await waitForSlate(2, '综合推荐');
      const storedAfterPair = JSON.parse(localStorage.getItem(${JSON.stringify(storageKey)}) || '{}');
      const pair = {
        selectedTargets: [...document.querySelectorAll('#recTargetScopeButtons button.active')].map((button) => button.dataset.value),
        storedTargets: storedAfterPair.targetScopes?.as ?? [],
        planScopes: typeof recPlanScopes === 'function' ? recPlanScopes().map((scope) => scope.key) : [],
        slateCount: primarySlateCards().length,
        slateTitles: primarySlateCards().map((card) => card.querySelector('h3')?.textContent?.trim() ?? ''),
        slateSubtitle: document.querySelector('#recSlateSubtitle')?.textContent?.trim() ?? '',
      };

      clickControl('#recTargetScopeButtons', '4-1');
      await waitForSlate(1, '综合推荐');
      const singleBeforeLastClick = {
        selectedTargets: [...document.querySelectorAll('#recTargetScopeButtons button.active')].map((button) => button.dataset.value),
        planScopes: typeof recPlanScopes === 'function' ? recPlanScopes().map((scope) => scope.key) : [],
        slateCount: primarySlateCards().length,
      };
      clickControl('#recTargetScopeButtons', '4-3');
      await Promise.resolve();
      const single = {
        ...singleBeforeLastClick,
        selectedAfterLastClick: [...document.querySelectorAll('#recTargetScopeButtons button.active')].map((button) => button.dataset.value),
        storedTargets: JSON.parse(localStorage.getItem(${JSON.stringify(storageKey)}) || '{}').targetScopes?.as ?? [],
      };
      const final = {
        strategy: rec.strategy,
        elementLabel: document.querySelector('#recElementLabel')?.textContent?.trim() ?? '',
        hint: document.querySelector('#recStrategyHint')?.textContent?.trim() ?? '',
        subtitle: document.querySelector('#recSubtitle')?.textContent?.trim() ?? '',
        defaults: finalDefaults,
        pair,
        single,
      };

      return {
        entry,
        custom,
        threeTeams,
        constraints: {
          controlsVisible: Object.values(controls).every(visible),
          slotOne,
          slotTwo,
          returnedSlotOne,
        },
        sortProbe,
        final,
      };
    })()`, context.sessionId);

    assert(result.entry.page === "recommender"
      && result.entry.hash === "#recommender"
      && result.entry.tabActive
      && result.entry.viewVisible, "HSR recommender could not be opened through its product tab", result.entry);
    assert(result.custom.mode === "as" && result.custom.strategy === "custom", "HSR weakness-driven scenario could not be selected", result.custom);
    assert(result.custom.teamCount === "2"
      && result.custom.teamCountVisible
      && !result.custom.targetControlVisible
      && JSON.stringify(result.custom.scopeValues) === JSON.stringify(["custom-1", "custom-2"]), "HSR weakness-driven scenario does not default to two teams", result.custom);
    assert(result.custom.poolTemplateCount > 0
      && result.custom.poolSources.length >= 2
      && result.custom.poolSources.some((scope) => scope !== "4-1")
      && result.custom.hint.includes("当前模式完整实战阵容池")
      && result.custom.subtitle.includes("跨全部具体战斗侧去重"), "HSR custom recommendations are not visibly backed by the full mode pool", result.custom);
    assert(result.threeTeams.teamCount === "3"
      && result.threeTeams.storedTeamCount === "3"
      && JSON.stringify(result.threeTeams.scopeValues) === JSON.stringify(["custom-1", "custom-2", "custom-3"]), "HSR weakness-driven scenario could not switch to three teams", result.threeTeams);
    assert(result.constraints.controlsVisible
      && result.constraints.slotOne.key === "as|custom-1"
      && result.constraints.slotOne.requiredSaved
      && result.constraints.slotOne.excludedSaved
      && result.constraints.slotOne.requiredChipCount === 1
      && result.constraints.slotOne.excludedChipCount === 1, "HSR required/excluded constraints were not saved for the current slot", result.constraints);
    assert(result.constraints.slotTwo.key === "as|custom-2"
      && result.constraints.slotTwo.requiredChipCount === 0
      && result.constraints.slotTwo.excludedChipCount === 0
      && result.constraints.returnedSlotOne.requiredChipCount === 1
      && result.constraints.returnedSlotOne.excludedChipCount === 1, "HSR role constraints leaked between custom team slots", result.constraints);
    assert(JSON.stringify(result.sortProbe.options.map((option) => option.value)) === JSON.stringify(["balanced", "history", "box"])
      && result.sortProbe.options.map((option) => option.text).join("|") === "综合推荐|历史表现|Box 即战力", "HSR recommendation sort choices are incomplete", result.sortProbe.options);
    for (const [mode, snapshot] of Object.entries({
      balanced: result.sortProbe.balanced,
      history: result.sortProbe.history,
      box: result.sortProbe.box,
    })) {
      assert(snapshot.mode === mode
        && snapshot.storedMode === mode
        && snapshot.scoreMatches
        && snapshot.partsComplete
        && snapshot.topKeys.length > 0
        && new Set(snapshot.topKeys).size === snapshot.topKeys.length
        && snapshot.referenceCounts.length > 0
        && snapshot.referenceCounts.every((count) => count === 3)
        && snapshot.breakdowns.every((text) => text.length > 0)
        && snapshot.slateTitles.length > 0
        && snapshot.slateTitles.some((title) => title.includes(snapshot.expectedScoreLabel))
        && snapshot.slateTitles.filter((title) => title.includes(" · ")).every((title) => title.includes(snapshot.expectedScoreLabel))
        && snapshot.slateSubtitle.includes(`目标：${snapshot.expectedModeLabel}`), `HSR ${mode} sort is not wired through cards, persistence, and the joint slate`, snapshot);
    }
    assert(result.final.strategy === "final"
      && result.final.elementLabel.includes("仅标注")
      && result.final.hint.includes("弱点默认不改榜")
      && result.final.hint.includes("未选关卡不会预留角色")
      && result.final.subtitle.includes("弱点默认仅标注，不参与加减分")
      && result.final.subtitle.includes("过滤风险"), "HSR final-floor scenario does not explain the weakness-risk behavior", result.final);
    assert(result.final.defaults.targetControlVisible
      && !result.final.defaults.teamCountVisible
      && JSON.stringify(result.final.defaults.targetValues) === JSON.stringify(["4-1", "4-2", "4-3"])
      && JSON.stringify(result.final.defaults.selectedTargets) === JSON.stringify(["4-1", "4-2", "4-3"]), "HSR final-stage targets do not default to all real nodes", result.final.defaults);
    assert(JSON.stringify(result.final.pair.selectedTargets) === JSON.stringify(["4-1", "4-3"])
      && JSON.stringify(result.final.pair.storedTargets) === JSON.stringify(["4-1", "4-3"])
      && JSON.stringify(result.final.pair.planScopes) === JSON.stringify(["4-1", "4-3"])
      && result.final.pair.slateCount === 2
      && result.final.pair.slateTitles.some((title) => title.includes("4-1"))
      && result.final.pair.slateTitles.some((title) => title.includes("4-3"))
      && result.final.pair.slateTitles.every((title) => !title.includes("4-2"))
      && result.final.pair.slateSubtitle.includes("未选关卡不预留角色"), "HSR final-stage planner did not honor a non-contiguous target pair", result.final.pair);
    assert(JSON.stringify(result.final.single.selectedTargets) === JSON.stringify(["4-3"])
      && JSON.stringify(result.final.single.planScopes) === JSON.stringify(["4-3"])
      && result.final.single.slateCount === 1
      && JSON.stringify(result.final.single.selectedAfterLastClick) === JSON.stringify(["4-3"])
      && JSON.stringify(result.final.single.storedTargets) === JSON.stringify(["4-3"]), "HSR final-stage planner did not preserve a valid single-node target", result.final.single);
    return result;
  } finally {
    const restored = await evaluate(context.id, `(() => {
      const storageRaw = ${JSON.stringify(saved.storageRaw)};
      if (storageRaw === null) localStorage.removeItem(${JSON.stringify(storageKey)});
      else localStorage.setItem(${JSON.stringify(storageKey)}, storageRaw);
      const recState = ${JSON.stringify(saved.recState)};
      if (typeof rec === 'object' && rec && recState && typeof recState === 'object') {
        for (const key of Object.keys(rec)) delete rec[key];
        Object.assign(rec, recState);
        if (typeof ensureRecScope === 'function') ensureRecScope();
        if (typeof renderRecommender === 'function' && typeof state === 'object' && state.page === 'recommender') {
          renderRecommender();
        }
      }
      return localStorage.getItem(${JSON.stringify(storageKey)}) === storageRaw;
    })()`, context.sessionId);
    assert(restored === true, "HSR recommender localStorage snapshot was not restored");
    if (result) result.storageRestored = restored;
  }
}

async function verifyHsrRecommenderLayout(topId, context) {
  const storageKey = "hsr_endgame_recommender_v1";
  const savedStyle = await evaluate(topId, `(() => {
    const frame = document.querySelector('iframe.visualizer-frame[data-game="hsr"]');
    if (!frame) throw new Error('missing Visualizer frame');
    return frame.getAttribute('style');
  })()`);
  const savedRec = await evaluate(context.id, `(() => ({
    storageRaw: localStorage.getItem(${JSON.stringify(storageKey)}),
    recState: JSON.parse(JSON.stringify(rec)),
  }))()`, context.sessionId);
  const snapshots = [];
  try {
    await evaluate(context.id, `(() => {
      const tab = [...document.querySelectorAll('#appTabs button, #tabs button')]
        .find((button) => button.textContent?.trim().startsWith('组队推荐'));
      if (!tab) throw new Error('missing recommender tab');
      tab.click();
      rec.mode='as';rec.strategy='final';rec.scope='4-1';rec.sortMode='balanced';
      rec.targetScopes={as:['4-1','4-2']};rec.elements={};rec.constraints={};rec.locks={};
      rec.gap='4';rec.riskMode='warn';rec.search='';
      ensureRecScope();saveRecSettings();syncRecControls();renderRecommender();
      return true;
    })()`, context.sessionId);
    await waitFor("HSR deterministic layout candidates", async () => evaluate(context.id, `(() => {
      const status=document.querySelector('#recSlateStatus')?.textContent||'';
      const primary=document.querySelector('#recSlateList .rec-slate-solution');
      return document.querySelectorAll('#recList .rec-card').length>0
        && primary?.querySelectorAll('.rec-slate-card').length===2
        && !status.includes('正在');
    })()`, context.sessionId));
    for (const [width, height] of [[1180, 720], [720, 720], [320, 568]]) {
      await evaluate(topId, `(() => {
        const frame = document.querySelector('iframe.visualizer-frame[data-game="hsr"]');
        if (!frame) throw new Error('missing Visualizer frame');
        frame.style.width = ${JSON.stringify(`${width}px`)};
        frame.style.height = ${JSON.stringify(`${height}px`)};
        frame.style.flex = 'none';
        return true;
      })()`);
      const snapshot = await waitFor(`HSR recommender ${width}x${height} layout`, async () => {
        const value = await evaluate(context.id, `(async () => {
          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
          const tab = [...document.querySelectorAll('#appTabs button, #tabs button')]
            .find((button) => button.textContent?.trim().startsWith('组队推荐'));
          if (!tab) throw new Error('missing recommender tab');
          if (typeof state === 'object' && state.page !== 'recommender') {
            tab.click();
            await new Promise((resolve) => requestAnimationFrame(resolve));
          }
          const card = document.querySelector('#recList .rec-card');
          const tooltip = document.querySelector('#recTooltip');
          if (!card || !tooltip) return null;
          const clientX = innerWidth - 24;
          const clientY = innerHeight - 24;
          card.dispatchEvent(new MouseEvent('mouseenter', {clientX, clientY}));
          card.dispatchEvent(new MouseEvent('mousemove', {clientX, clientY}));
          tooltip.scrollTop = tooltip.scrollHeight;
          await new Promise((resolve) => requestAnimationFrame(resolve));
          card.dispatchEvent(new MouseEvent('mousemove', {clientX, clientY}));
          await new Promise((resolve) => requestAnimationFrame(resolve));
          const rect = tooltip.getBoundingClientRect();
          const lastValue = tooltip.querySelector('.tooltip-grid > div:last-child');
          const lastRect = lastValue?.getBoundingClientRect() ?? null;
          const result = {
            innerWidth,
            innerHeight,
            documentScrollWidth: document.documentElement.scrollWidth,
            tooltipHidden: tooltip.hidden,
            tooltipRect: {left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height},
            tooltipClientWidth: tooltip.clientWidth,
            tooltipScrollWidth: tooltip.scrollWidth,
            tooltipClientHeight: tooltip.clientHeight,
            tooltipScrollHeight: tooltip.scrollHeight,
            lastValueRight: lastRect?.right ?? null,
            lastValueBottom: lastRect?.bottom ?? null,
          };
          tooltip.hidden = true;
          return result;
        })()`, context.sessionId);
        return value && Math.abs(value.innerWidth - width) <= 1 && Math.abs(value.innerHeight - height) <= 1
          ? value
          : null;
      });
      const rect = snapshot.tooltipRect;
      assert(!snapshot.tooltipHidden
        && rect.left >= 13
        && rect.top >= 13
        && rect.right <= snapshot.innerWidth - 13
        && rect.bottom <= snapshot.innerHeight - 13,
      `HSR recommendation tooltip escaped ${width}x${height}`, snapshot);
      assert(snapshot.documentScrollWidth <= snapshot.innerWidth
        && snapshot.tooltipScrollWidth <= snapshot.tooltipClientWidth + 1,
      `HSR recommendation content overflows ${width}x${height}`, snapshot);
      assert(snapshot.lastValueRight !== null
        && snapshot.lastValueBottom !== null
        && snapshot.lastValueRight <= rect.right + 1
        && snapshot.lastValueBottom <= rect.bottom + 1,
      `HSR recommendation tooltip clips its final field at ${width}x${height}`, snapshot);
      snapshots.push({width, height, ...snapshot});
    }
    return snapshots;
  } finally {
    try {
      const restored = await evaluate(context.id, `(() => {
        const raw=${JSON.stringify(savedRec.storageRaw)};
        if(raw===null)localStorage.removeItem(${JSON.stringify(storageKey)});else localStorage.setItem(${JSON.stringify(storageKey)},raw);
        for(const key of Object.keys(rec))delete rec[key];Object.assign(rec,${JSON.stringify(savedRec.recState)});
        ensureRecScope();syncRecControls();renderRecommender();
        return localStorage.getItem(${JSON.stringify(storageKey)})===raw;
      })()`, context.sessionId);
      assert(restored === true, "HSR layout probe did not restore recommender state");
    } finally {
      await evaluate(topId, `(() => {
        const frame = document.querySelector('iframe.visualizer-frame[data-game="hsr"]');
        if (!frame) return false;
        const style = ${JSON.stringify(savedStyle)};
        if (style === null) frame.removeAttribute('style');
        else frame.setAttribute('style', style);
        return true;
      })()`);
    }
  }
}

async function verifyZzzCompactTooltipLayout(topId, context) {
  const savedStyle = await evaluate(topId, `(() => document.querySelector('iframe.visualizer-frame[data-game="zzz"]')?.getAttribute('style') ?? null)()`);
  try {
    await evaluate(topId, `(() => {const frame=document.querySelector('iframe.visualizer-frame[data-game="zzz"]');if(!frame)throw new Error('missing ZZZ frame');frame.style.width='320px';frame.style.height='568px';frame.style.flex='none';return true;})()`);
    const snapshot = await waitFor("ZZZ 320x568 tooltip layout", async () => evaluate(context.id, `(async () => {
      await new Promise((resolve)=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      const target=document.querySelector('#chart [role="button"][tabindex="0"]');
      const tooltip=document.querySelector('#tooltip');
      if(!target||!tooltip)return null;
      const clientX=innerWidth-12,clientY=innerHeight-12;
      target.dispatchEvent(new MouseEvent('mouseenter',{clientX,clientY}));
      target.dispatchEvent(new MouseEvent('mousemove',{clientX,clientY}));
      tooltip.scrollTop=tooltip.scrollHeight;
      await new Promise((resolve)=>requestAnimationFrame(resolve));
      const rect=tooltip.getBoundingClientRect(),last=tooltip.querySelector('.tooltip-grid > :last-child')?.getBoundingClientRect()||null;
      const result={innerWidth,innerHeight,documentScrollWidth:document.documentElement.scrollWidth,hidden:tooltip.hidden,rect:{left:rect.left,top:rect.top,right:rect.right,bottom:rect.bottom},clientWidth:tooltip.clientWidth,scrollWidth:tooltip.scrollWidth,lastRight:last?.right??null,lastBottom:last?.bottom??null};
      tooltip.hidden=true;return result;
    })()`, context.sessionId));
    assert(Math.abs(snapshot.innerWidth - 320) <= 1 && Math.abs(snapshot.innerHeight - 568) <= 1
      && !snapshot.hidden && snapshot.rect.left >= 11 && snapshot.rect.top >= 11
      && snapshot.rect.right <= snapshot.innerWidth - 11 && snapshot.rect.bottom <= snapshot.innerHeight - 11,
    "ZZZ tooltip escaped 320x568", snapshot);
    assert(snapshot.documentScrollWidth <= snapshot.innerWidth && snapshot.scrollWidth <= snapshot.clientWidth + 1
      && snapshot.lastRight <= snapshot.rect.right + 1 && snapshot.lastBottom <= snapshot.rect.bottom + 1,
    "ZZZ tooltip content is clipped at 320x568", snapshot);
    return snapshot;
  } finally {
    await evaluate(topId, `(() => {const frame=document.querySelector('iframe.visualizer-frame[data-game="zzz"]');if(!frame)return false;const style=${JSON.stringify(savedStyle)};if(style===null)frame.removeAttribute('style');else frame.setAttribute('style',style);return true;})()`);
  }
}

function verifyAnalysis(
  snapshot,
  game,
  mode,
  { requirePhaseMatch = true, requirePhasePresentation = true } = {},
) {
  const tierUpdatedDate = normalizeSourceDate(snapshot.tierUpdatedAt);
  assert(snapshot.sourceMetaLine.includes("终局统计最新采样：")
    && snapshot.latestEndgameSampleDate
    && snapshot.sourceMetaLine.includes(`终局统计最新采样：${snapshot.latestEndgameSampleDate}`),
  `${game} top metadata does not identify the authoritative endgame sample date`, snapshot);
  assert(tierUpdatedDate
    && snapshot.sourceMetaLine.includes("Prydwen 榜单更新：")
    && snapshot.sourceMetaLine.includes(`Prydwen 榜单更新：${tierUpdatedDate}`),
  `${game} top metadata does not separately identify the Prydwen list date`, snapshot);
  if (snapshot.staleModeCodes.length > 0) {
    assert(/部分模式已过期|全部模式已过期/u.test(snapshot.sourceMetaLine),
      `${game} top metadata hides stale endgame modes`, snapshot);
  }
  assert(snapshot.statePage === "analysis" && snapshot.analysisVisible, `${game} endgame analysis is not visible`, snapshot);
  assert(snapshot.analysisMode === mode, `${game} endgame analysis did not switch to ${mode}`, snapshot);
  assert(snapshot.usageRowCount > 0, `${game} endgame usage data is absent`, snapshot);
  assert(snapshot.analysisModeUsageRowCount > 0, `${game} ${mode} endgame data is absent`, snapshot);
  const phase = snapshot.analysisExpectedPhase;
  if (requirePhaseMatch) {
    assert(phase?.matched === true, `${game} ${mode} latest sample did not resolve to phaseInfoRows`, phase);
  }
  if (requirePhasePresentation) {
    assert(phase.phaseVer, `${game} ${mode} latest phase identity is incomplete`, phase);
    assert(/^\d{4}-\d{2}-\d{2}$/u.test(phase.startDate)
      && /^\d{4}-\d{2}-\d{2}$/u.test(phase.endDate), `${game} ${mode} latest phase date range is incomplete`, phase);
  }
  assert(snapshot.analysisVisualState.display !== "none"
    && snapshot.analysisVisualState.visibility === "visible"
    && snapshot.analysisVisualState.opacity > 0, `${game} ${mode} endgame container is visually suppressed`, snapshot);
  assert(snapshot.analysisTitle.length > 0, `${game} ${mode} endgame title is absent`, snapshot);
  if (requirePhasePresentation) {
    assert(snapshot.analysisSubtitle.includes(`期次：${phase.phaseVer}`), `${game} ${mode} endgame phase version is not displayed`, {
      expected: phase.phaseVer,
      subtitle: snapshot.analysisSubtitle,
    });
    if (game === "zzz") {
      assert(completeZzzPhasePresentation(phase), `${game} ${mode} latest phase name or mechanic is absent`, phase);
      const phaseName = phase.phaseName;
      const mechanicName = phase.mechanicName;
      assert(snapshot.analysisSubtitle.includes(`期名：${phaseName}`), `${game} ${mode} endgame phase name is not displayed independently`, {
        expected: phaseName,
        subtitle: snapshot.analysisSubtitle,
      });
      assert(snapshot.analysisSubtitle.includes(`机制：${mechanicName}`), `${game} ${mode} endgame mechanic is not displayed independently`, {
        expected: mechanicName,
        subtitle: snapshot.analysisSubtitle,
      });
      assert(!["期名未提供", "机制未提供", "中文期名待维护", "当期数据", "机制效果待维护"].some((placeholder) => (
        snapshot.analysisSubtitle.includes(placeholder)
      )), `${game} ${mode} endgame subtitle exposes a metadata placeholder`, snapshot);
    } else {
      assert(phase.phaseName
        && snapshot.analysisSubtitle.includes(`主题：${phase.phaseName}`), `${game} ${mode} endgame phase theme is not displayed`, {
        expected: phase.phaseName,
        subtitle: snapshot.analysisSubtitle,
      });
    }
    assert(snapshot.analysisSubtitle.includes(`${phase.startDate} 至 ${phase.endDate}`),
    `${game} ${mode} endgame phase date range is not displayed`, {
      expected: `${phase.startDate} 至 ${phase.endDate}`,
      subtitle: snapshot.analysisSubtitle,
    });
  }
  assert(snapshot.analysisSubtitle.includes("最新采样："), `${game} endgame sample date is not displayed`, snapshot);
  assert(!snapshot.analysisSubtitle.includes("最新采样：未知"), `${game} endgame sample date is unknown`, snapshot);
  assert(phase.sampleDate && snapshot.analysisSubtitle.includes(`最新采样：${phase.sampleDate}`),
    `${game} ${mode} endgame sample date does not match the latest phase`, {
      expected: phase.sampleDate,
      subtitle: snapshot.analysisSubtitle,
    });
  const now = new Date();
  const today = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  const sampleDay = /^\d{4}-\d{2}-\d{2}$/u.test(phase.sampleDate)
    ? Date.parse(`${phase.sampleDate}T00:00:00Z`) / 86_400_000
    : null;
  const todayDay = Date.parse(`${today}T00:00:00Z`) / 86_400_000;
  const sampleAgeDays = sampleDay === null ? null : todayDay - sampleDay;
  if (sampleAgeDays !== null && sampleAgeDays >= 15) {
    const ageLabel = `已 ${sampleAgeDays} 天未更新`;
    assert(snapshot.analysisSubtitle.includes(ageLabel), `${game} ${mode} stale sample age is not visibly disclosed`, {
      expected: ageLabel,
      subtitle: snapshot.analysisSubtitle,
    });
  }
  const latestSampleDay = /^\d{4}-\d{2}-\d{2}$/u.test(snapshot.latestEndgameSampleDate)
    ? Date.parse(`${snapshot.latestEndgameSampleDate}T00:00:00Z`) / 86_400_000
    : null;
  const latestSampleAgeDays = latestSampleDay === null ? null : todayDay - latestSampleDay;
  if (latestSampleAgeDays !== null && latestSampleAgeDays >= 15) {
    const topAgeLabel = `已 ${latestSampleAgeDays} 天未更新`;
    assert(snapshot.sourceMetaLine.includes(topAgeLabel), `${game} top metadata hides the latest sample age`, {
      expected: topAgeLabel,
      sourceMetaLine: snapshot.sourceMetaLine,
    });
  }
  const effectivePhaseStatus = /^\d{4}-\d{2}-\d{2}$/u.test(phase.startDate) && phase.startDate > today
    ? "future"
    : /^\d{4}-\d{2}-\d{2}$/u.test(phase.endDate) && phase.endDate < today
      ? "expired"
      : phase.status;
  const expectedStatus = {
    current: "当前周期",
    expired: "历史样本",
    future: "未来周期",
    unknown: "周期未知",
  }[effectivePhaseStatus];
  if (requirePhaseMatch && requirePhasePresentation) {
    const expectedStatusText = game === "zzz" ? `状态：${expectedStatus}` : expectedStatus;
    assert(expectedStatus && snapshot.analysisSubtitle.includes(expectedStatusText),
      `${game} ${mode} endgame freshness label does not match phase status`, {
        expectedStatus: expectedStatusText,
        phase,
        subtitle: snapshot.analysisSubtitle,
      });
  } else {
    assert(/当前周期|历史样本|未来周期|周期未知/.test(snapshot.analysisSubtitle),
      `${game} endgame freshness label is absent`, snapshot);
  }
  assert(!/该模式数据未生成|缺数据/.test(snapshot.analysisSubtitle), `${game} endgame analysis falsely reports missing data`, snapshot);
  assert(snapshot.chartVisualState.visible
    && snapshot.chartVisualState.visibility === "visible"
    && snapshot.chartVisualState.opacity > 0
    && snapshot.chartChildCount > 0
    && snapshot.chartMarkCount > 0
    && snapshot.chartVisibleMarkCount > 0, `${game} ${mode} endgame chart is not visibly rendered`, snapshot);
  assert(snapshot.characterListVisualState.visible
    && snapshot.characterListVisualState.visibility === "visible"
    && snapshot.characterListVisualState.opacity > 0
    && snapshot.characterCardCount > 0
    && snapshot.characterCardNames.every(Boolean), `${game} ${mode} endgame character list is not visibly rendered`, snapshot);
  assert(snapshot.characterImageCount === snapshot.characterCardCount
    && snapshot.characterBrokenImages.length === 0, `${game} ${mode} endgame character images are broken`, snapshot);
  assert(snapshot.visibleMissingMessages.length === 0, `${game} endgame page exposes a missing-data warning`, snapshot);
}

async function verifyAnalysisModes(context, game, initialSnapshot, options = {}) {
  const snapshots = [];
  for (const mode of expectedAnalysisModes[game]) {
    let snapshot = initialSnapshot?.analysisMode === mode ? initialSnapshot : null;
    if (!snapshot) {
      const clicked = await evaluate(context.id, `(() => {
        const button = [...document.querySelectorAll('#modeControl button')]
          .find((candidate) => candidate.dataset.value === ${JSON.stringify(mode)});
        if (!button || button.disabled) return false;
        button.click();
        return true;
      })()`, context.sessionId);
      assert(clicked === true, `could not switch ${game} endgame analysis to ${mode}`);
      snapshot = await waitFor(`${game} ${mode} endgame DOM`, async () => {
        const value = await evaluate(context.id, productExpression, context.sessionId);
        return value?.readyState === "complete"
          && value?.statePage === "analysis"
          && value?.analysisMode === mode
          && value?.analysisVisible
          ? value
          : null;
      });
    }
    verifyAnalysis(snapshot, game, mode, options);
    snapshots.push(snapshot);
  }
  return snapshots;
}

function verifyBanner(snapshot, game, {
  requireFresh = true,
  requireExpected = true,
  requireCurrent = true,
} = {}) {
  assert(snapshot.statePage === "banner" && snapshot.bannerVisible, `${game} banner page is not visible`, snapshot);
  assert(snapshot.bannerTitle === "卡池情报", `${game} banner title is absent`, snapshot);
  assert(snapshot.bannerBadges.includes(`Box ${expectedOwned[game]}`), `${game} banner page lost the current Box`, snapshot);
  assert(Array.isArray(snapshot.bannerBoundaryFieldErrors) && snapshot.bannerBoundaryFieldErrors.length === 0,
    `${game} banner rows do not expose valid structured China-time boundaries`, snapshot.bannerBoundaryFieldErrors);
  assert(Array.isArray(snapshot.bannerClockStatusErrors) && snapshot.bannerClockStatusErrors.length === 0,
    `${game} banner status disagrees with the structured boundary clock`, snapshot.bannerClockStatusErrors);
  if (requireCurrent) {
    assert(snapshot.bannerAllRowCount > 0, `${game} banner data is absent`, snapshot);
    assert(snapshot.visibleMissingMessages.length === 0, `${game} banner page exposes a missing-data warning`, snapshot);
    assert(snapshot.bannerCurrentRowCount > 0, `${game} current banner data is absent`, snapshot);
    assert(snapshot.bannerPhase === "current", `${game} banner page did not select the current populated phase`, snapshot);
    assert(snapshot.bannerCardCount > 0 && snapshot.bannerCardNames.every(Boolean), `${game} current banner cards are absent`, snapshot);
    assert(snapshot.bannerCardCount === snapshot.bannerCurrentRowCount, `${game} banner DOM does not render every current snapshot row`, snapshot);
    assert(JSON.stringify([...snapshot.bannerCardNames].sort()) === JSON.stringify([...snapshot.bannerDataCurrentNames].sort()),
      `${game} banner DOM does not match the refreshed snapshot`, {
        rendered: snapshot.bannerCardNames,
        snapshot: snapshot.bannerDataCurrentNames,
      });
    assert(snapshot.bannerCardRoles.every(Boolean)
      && JSON.stringify([...snapshot.bannerCardRoles].sort())
        === JSON.stringify([...snapshot.bannerDataCurrentRoles].sort()),
    `${game} visible banner roles do not match the refreshed snapshot`, {
      rendered: snapshot.bannerCardRoles,
      snapshot: snapshot.bannerDataCurrentRoles,
    });
    assert(snapshot.bannerImageCount === snapshot.bannerCardCount
      && snapshot.bannerBrokenImages.length === 0
      && snapshot.bannerMappingErrors.length === 0, `${game} current banner images are broken or mismatched`, snapshot);
  }
  if (requireFresh) {
    assert(snapshot.bannerRefreshStatus === "fresh", `${game} banner snapshot is not marked fresh`, snapshot);
    assert(Number.isFinite(Date.parse(snapshot.bannerRefreshFetchedAt)), `${game} banner refresh timestamp is invalid`, snapshot);
    assert(snapshot.bannerSubtitle.includes("官方卡池资料上次刷新："), `${game} banner refresh timestamp is not visibly labelled`, snapshot);
    assert(Array.isArray(snapshot.bannerRefreshExpectedMinutes)
      && snapshot.bannerRefreshExpectedMinutes.length > 0
      && snapshot.bannerRefreshExpectedMinutes.some((minute) => snapshot.bannerSubtitle.includes(minute)),
    `${game} visible banner refresh minute does not match DATA.bannerRefresh`, {
      fetchedAt: snapshot.bannerRefreshFetchedAt,
      expectedMinutes: snapshot.bannerRefreshExpectedMinutes,
      subtitle: snapshot.bannerSubtitle,
    });
  }
  if (requireExpected && expectedBannerCount[game] !== null) {
    assert(snapshot.bannerCurrentRowCount === expectedBannerCount[game], `${game} current banner data count changed`, snapshot);
    assert(snapshot.bannerCardCount === expectedBannerCount[game], `${game} rendered current banner count changed`, snapshot);
  }
  if (requireExpected && expectedBannerNames[game].length > 0) {
    const actual = [...snapshot.bannerCardNames].sort();
    const expected = [...expectedBannerNames[game]].sort();
    assert(JSON.stringify(actual) === JSON.stringify(expected), `${game} rendered current banner names changed`, { actual, expected });
  }
  if (requireExpected && expectedNextBannerCount[game] !== null) {
    assert(snapshot.bannerNextRowCount === expectedNextBannerCount[game], `${game} next banner data count changed`, snapshot);
  }
  if (requireExpected && expectedNextBannerNames[game].length > 0) {
    const actual = [...snapshot.bannerDataNextNames].sort();
    const expected = [...expectedNextBannerNames[game]].sort();
    assert(JSON.stringify(actual) === JSON.stringify(expected), `${game} next banner names changed`, { actual, expected });
  }
}

async function verifyExpectedNextBanner(context, game) {
  if (expectedNextBannerCount[game] === null) return null;
  const clicked = await evaluate(context.id, `(() => {
    const button = [...document.querySelectorAll('#bannerPhaseControl button')]
      .find((candidate) => candidate.dataset.value === 'next');
    if (!button || button.disabled) return false;
    button.click();
    return true;
  })()`, context.sessionId);
  assert(clicked === true, `could not switch ${game} banner page to the next phase`);
  const snapshot = await waitFor(`${game} next banner DOM`, async () => {
    const value = await evaluate(context.id, productExpression, context.sessionId);
    return value?.readyState === "complete"
      && value?.statePage === "banner"
      && value?.bannerVisible
      && value?.bannerPhase === "next"
      ? value
      : null;
  });
  assert(snapshot.bannerNextRowCount === expectedNextBannerCount[game],
    `${game} next banner data count changed`, snapshot);
  assert(snapshot.bannerCardCount === snapshot.bannerNextRowCount,
    `${game} next banner DOM does not render every next snapshot row`, snapshot);
  assert(snapshot.bannerCardRoles.every(Boolean)
    && JSON.stringify([...snapshot.bannerCardRoles].sort())
      === JSON.stringify([...snapshot.bannerDataNextRoles].sort()),
  `${game} visible next-banner roles do not match the refreshed snapshot`, {
    rendered: snapshot.bannerCardRoles,
    snapshot: snapshot.bannerDataNextRoles,
  });
  assert(JSON.stringify([...snapshot.bannerCardNames].sort())
      === JSON.stringify([...snapshot.bannerDataNextNames].sort()),
  `${game} next banner DOM does not match the refreshed snapshot`, {
    rendered: snapshot.bannerCardNames,
    snapshot: snapshot.bannerDataNextNames,
  });
  if (expectedNextBannerNames[game].length > 0) {
    const actual = [...snapshot.bannerCardNames].sort();
    const expected = [...expectedNextBannerNames[game]].sort();
    assert(JSON.stringify(actual) === JSON.stringify(expected),
      `${game} rendered next banner names changed`, { actual, expected });
  }
  assert(snapshot.bannerImageCount === snapshot.bannerCardCount
    && snapshot.bannerBrokenImages.length === 0
    && snapshot.bannerMappingErrors.length === 0,
  `${game} next banner images are broken or mismatched`, snapshot);
  assert(snapshot.visibleMissingMessages.length === 0,
    `${game} next banner page exposes a missing-data warning`, snapshot);
  assert(snapshot.bannerDataNextDateRanges.length > 0
    && snapshot.bannerDataNextDateRanges.every((dateRange) => (
      snapshot.bannerSectionTexts.some((text) => text.includes(dateRange))
    )), `${game} next banner dates are not visibly rendered`, snapshot);

  const restored = await evaluate(context.id, `(() => {
    const button = [...document.querySelectorAll('#bannerPhaseControl button')]
      .find((candidate) => candidate.dataset.value === 'current');
    if (!button || button.disabled) return false;
    button.click();
    return true;
  })()`, context.sessionId);
  assert(restored === true, `could not restore ${game} banner page to the current phase`);
  const current = await waitFor(`${game} restored current banner DOM`, async () => {
    const value = await evaluate(context.id, productExpression, context.sessionId);
    return value?.readyState === "complete"
      && value?.statePage === "banner"
      && value?.bannerVisible
      && value?.bannerPhase === "current"
      ? value
      : null;
  });
  verifyBanner(current, game);
  return {
    count: snapshot.bannerCardCount,
    names: snapshot.bannerCardNames,
  };
}

async function switchGame(topId, game) {
  const label = game === "hsr" ? "崩坏：星穹铁道" : "绝区零";
  const clicked = await evaluate(topId, `(() => {
    const button = [...document.querySelectorAll('.game-button')]
      .find((candidate) => candidate.textContent?.trim() === ${JSON.stringify(label)});
    if (!button || button.disabled) return false;
    button.click();
    return true;
  })()`);
  assert(clicked === true, `could not switch the desktop to ${game}`);
}

async function boxProtectionSnapshot(context, game) {
  const snapshot = await evaluate(context.id, `(async () => {
    const normalize = (value) => {
      if (Array.isArray(value)) return value.map(normalize);
      if (value && typeof value === 'object') {
        return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalize(value[key])]));
      }
      return value;
    };
    const comparable = (value) => normalize({
      owned: Array.isArray(value?.owned) ? [...value.owned].sort() : [],
      buildSlug: value?.buildSlug ?? '',
      builds: value?.builds ?? {},
    });
    if (typeof box !== 'object' || !(box?.owned instanceof Set)) {
      return {error: 'Visualizer Box state is unavailable'};
    }
    const response = await fetch(${JSON.stringify(`/api/${game}/box`)}, {cache: 'no-store'});
    if (!response.ok) return {error: 'Box API returned ' + response.status};
    const diskRaw = await response.json();
    const disk = normalize({
      ...diskRaw,
      owned: Array.isArray(diskRaw?.owned) ? [...diskRaw.owned].sort() : [],
    });
    const live = comparable({
      owned: [...box.owned],
      buildSlug: box.buildSlug ?? '',
      builds: box.builds ?? {},
    });
    return {
      live: JSON.stringify(live),
      disk: JSON.stringify(disk),
      liveOwned: live.owned.length,
      diskOwned: Array.isArray(disk.owned) ? disk.owned.length : -1,
    };
  })()`, context.sessionId);
  assert(!snapshot?.error && snapshot?.live && snapshot?.disk, `${game} Box protection snapshot failed`, snapshot);
  assert(snapshot.liveOwned === expectedOwned[game] && snapshot.diskOwned === expectedOwned[game],
    `${game} Box protection snapshot has an unexpected owned count`, snapshot);
  return {
    ...snapshot,
    liveSha256: sha256(snapshot.live),
    diskSha256: sha256(snapshot.disk),
  };
}

function boxProtectionReceipt(snapshot) {
  return {
    liveSha256: snapshot.liveSha256,
    diskSha256: snapshot.diskSha256,
    owned: snapshot.liveOwned,
  };
}

function verifyBoxProtection(before, after, game) {
  assert(after.live === before.live && after.disk === before.disk,
    `${game} Box changed while refreshing public data`, {
      before: boxProtectionReceipt(before),
      after: boxProtectionReceipt(after),
    });
  return {
    ...boxProtectionReceipt(after),
    liveUnchanged: true,
    diskUnchanged: true,
  };
}

async function ensureActiveGame(topId, game) {
  const label = game === "hsr" ? "崩坏：星穹铁道" : "绝区零";
  const current = await outerSnapshot(topId);
  if (current?.activeGame !== label) await switchGame(topId, game);
  return waitFor(`${game} active desktop frame before update`, async () => {
    const snapshot = await outerSnapshot(topId);
    return snapshot?.frameGame === game && snapshot?.frameLoaded ? snapshot : null;
  });
}

async function clickPublicDataUpdate(topId, game) {
  const operationTitle = game === "hsr" ? "更新星穹铁道数据" : "更新绝区零数据";
  const started = await evaluate(topId, `(() => {
    const taskId = (card) => {
      const text = card.querySelector('.task-id')?.textContent?.trim() ?? '';
      return text.replace(/^运行编号：\\s*/u, '');
    };
    const existingTaskIds = [...document.querySelectorAll('.task-card')]
      .map(taskId)
      .filter(Boolean);
    const activeTasks = [...document.querySelectorAll('.task-card')]
      .filter((card) => !['status-succeeded', 'status-failed', 'status-cancelled']
        .some((className) => card.classList.contains(className)));
    if (activeTasks.length) return {clicked: false, reason: 'another task is active', existingTaskIds};
    const utilities = document.querySelector('details.utilities');
    if (utilities) utilities.open = true;
    const card = [...document.querySelectorAll('.export-card')]
      .find((candidate) => candidate.querySelector('h3')?.textContent?.trim() === ${JSON.stringify(operationTitle)});
    const button = card?.querySelector('button');
    if (!button) return {clicked: false, reason: 'update button is absent', existingTaskIds};
    if (button.disabled) return {clicked: false, reason: 'update button is disabled', existingTaskIds};
    const startedAt = Date.now();
    button.click();
    return {clicked: true, existingTaskIds, startedAt};
  })()`, undefined, { userGesture: true });
  assert(started?.clicked === true, `${game} public-data update button could not be clicked`, started);

  const terminal = await waitFor(`${game} public-data update task terminal state`, async () => {
    const cards = await evaluate(topId, `(() => [...document.querySelectorAll('.task-card')].map((card) => {
      const idText = card.querySelector('.task-id')?.textContent?.trim() ?? '';
      const statusClass = [...card.classList].find((value) => value.startsWith('status-')) ?? '';
      return {
        taskId: idText.replace(/^运行编号：\\s*/u, ''),
        title: card.querySelector('.task-title-row h3')?.textContent?.trim() ?? '',
        status: statusClass.slice('status-'.length),
        text: card.textContent?.trim() ?? '',
      };
    }))()`);
    const existingTaskIds = new Set(started.existingTaskIds);
    const candidate = cards.find((card) => card.title === operationTitle
      && card.taskId
      && !existingTaskIds.has(card.taskId));
    return candidate && ['succeeded', 'failed', 'cancelled'].includes(candidate.status) ? candidate : null;
  }, updateTimeoutMs);
  assert(terminal.status === "succeeded", `${game} public-data update did not succeed`, terminal);
  return {
    taskId: terminal.taskId,
    status: terminal.status,
    startedAt: started.startedAt,
    text: terminal.text,
  };
}

async function authoritativeVisualizerDescriptor(topId, game) {
  const descriptor = await evaluate(topId, `(async () => {
    const internals = globalThis.__TAURI_INTERNALS__;
    if (!internals || typeof internals.invoke !== 'function') return null;
    return internals.invoke('get_visualizer_url', {game: ${JSON.stringify(game)}});
  })()`);
  assert(descriptor?.schema_version === "miho-visualizer-descriptor-v1"
    && typeof descriptor?.url === "string"
    && /^[a-f0-9]{64}$/u.test(descriptor?.data_revision ?? ""),
  `${game} authoritative Visualizer descriptor is invalid`, descriptor);
  return descriptor;
}

async function authoritativeUpdateHealth(topId) {
  const health = await evaluate(topId, `(async () => {
    const internals = globalThis.__TAURI_INTERNALS__;
    if (!internals || typeof internals.invoke !== 'function') return null;
    return internals.invoke('get_update_health');
  })()`);
  assert(health?.schema_version === "miho-desktop-update-health-v2"
    && typeof health?.workspace_id === "string"
    && typeof health?.healthy === "boolean"
    && Array.isArray(health?.checked_games)
    && Array.isArray(health?.games)
    && health.games.every((entry) => entry?.freshness
      && typeof entry.freshness.status === "string"
      && entry.freshness.modes
      && typeof entry.freshness.modes === "object"),
  "authoritative update health is invalid", health);
  return health;
}

function updateHealthGame(health, game) {
  return health?.games?.find((entry) => entry?.game === game) ?? null;
}

function updateHealthLatestSampleDate(health, game) {
  const dates = Object.values(updateHealthGame(health, game)?.freshness?.modes ?? {})
    .map((mode) => mode?.sample_date ?? "")
    .filter((value) => /^\d{4}-\d{2}-\d{2}$/u.test(value))
    .sort();
  return dates.at(-1) ?? "";
}

function visibleUpdateHealthCompletedAt(snapshot, game) {
  const label = game === "hsr" ? "HSR 最近成功" : "ZZZ 最近成功";
  const index = snapshot?.updateHealthGames?.findIndex((value) => value.includes(label)) ?? -1;
  return index >= 0 ? snapshot?.updateHealthGameCompletedAtUtc?.[index] ?? "" : "";
}

async function verifyPublicDataUpdate(topId, game) {
  await ensureActiveGame(topId, game);
  const beforeHealth = await waitFor(`${game} healthy update state before public-data update`, async () => {
    const health = await authoritativeUpdateHealth(topId);
    return health.healthy && updateHealthGame(health, "hsr") && updateHealthGame(health, "zzz")
      ? health
      : null;
  });
  const beforeContext = await activeFrameContext(game);
  const beforeBanner = await switchProductPage(beforeContext, game, "banner");
  assert(beforeBanner.statePage === "banner", `${game} could not open the banner page before updating`, beforeBanner);
  const beforeOuter = await waitFor(`${game} banner page bridge before public-data update`, async () => {
    const snapshot = await outerSnapshot(topId);
    return snapshot?.frameGame === game && snapshot?.framePage === "banner" ? snapshot : null;
  });
  assert(/^[a-f0-9]{64}$/u.test(beforeOuter.frameDataRevision), `${game} pre-update revision is invalid`, beforeOuter);
  const task = await clickPublicDataUpdate(topId, game);
  const terminalDescriptor = await authoritativeVisualizerDescriptor(topId, game);
  assert(terminalDescriptor.data_revision !== beforeOuter.frameDataRevision,
    `${game} public-data update did not publish a new terminal revision`, {
      before: beforeOuter.frameDataRevision,
      terminal: terminalDescriptor.data_revision,
    });
  const afterOuter = await waitFor(`${game} authoritative Visualizer revision after public-data update`, async () => {
    const snapshot = await outerSnapshot(topId);
    return snapshot?.frameGame === game
      && snapshot?.frameLoaded
      && snapshot?.frameSrc.includes(`/${game}/index.html`)
      && snapshot?.frameSrc.endsWith("#banner")
      && snapshot?.framePage === "banner"
      && /^[a-f0-9]{64}$/u.test(snapshot?.frameDataRevision ?? "")
      && snapshot.frameDataRevision === terminalDescriptor.data_revision
      ? snapshot
      : null;
  }, updateTimeoutMs);
  assert(afterOuter.frameProbeId === beforeOuter.frameProbeId,
    `${game} Visualizer iframe node was replaced by the data update`, { beforeOuter, afterOuter });
  assert(afterOuter.frameProbeLoadCount > beforeOuter.frameProbeLoadCount,
    `${game} Visualizer did not navigate after its revision changed`, { beforeOuter, afterOuter });
  assert(new URL(afterOuter.frameSrc).searchParams.get("revision") === terminalDescriptor.data_revision,
    `${game} iframe URL is not bound to the terminal data revision`, {
      frameSrc: afterOuter.frameSrc,
      terminalRevision: terminalDescriptor.data_revision,
    });
  const stableDescriptor = await authoritativeVisualizerDescriptor(topId, game);
  assert(stableDescriptor.data_revision === terminalDescriptor.data_revision,
    `${game} Visualizer revision changed after the update reached terminal state`, {
      terminal: terminalDescriptor,
      afterLoad: stableDescriptor,
    });

  const context = await activeFrameContext(game);
  const bannerSnapshot = await productSnapshot(game, "banner");
  verifyBanner(bannerSnapshot, game);
  const nextBanner = await verifyExpectedNextBanner(context, game);
  const fetchedAtMs = Date.parse(bannerSnapshot.bannerRefreshFetchedAt);
  assert(fetchedAtMs >= task.startedAt - 300000 && fetchedAtMs <= Date.now() + 300000,
    `${game} refreshed banner timestamp does not belong to this update run`, {
      taskStartedAt: new Date(task.startedAt).toISOString(),
      bannerRefreshFetchedAt: bannerSnapshot.bannerRefreshFetchedAt,
    });
  const analysisSnapshot = await switchProductPage(context, game, "analysis");
  const analyses = await verifyAnalysisModes(context, game, analysisSnapshot);
  const otherGame = game === "hsr" ? "zzz" : "hsr";
  const healthReceipt = await waitFor(`${game} authoritative and visible update health after public-data update`, async () => {
    const health = await authoritativeUpdateHealth(topId);
    if (!health.healthy) return null;
    const beforeTarget = updateHealthGame(beforeHealth, game);
    const afterTarget = updateHealthGame(health, game);
    const beforeOther = updateHealthGame(beforeHealth, otherGame);
    const afterOther = updateHealthGame(health, otherGame);
    if (!beforeTarget || !afterTarget || !beforeOther || !afterOther
      || afterTarget.attempt_id === beforeTarget.attempt_id) return null;
    assert(Date.parse(afterTarget.completed_at_utc) >= task.startedAt - 300000,
      `${game} update-health completion time predates this button run`, { task, beforeTarget, afterTarget });
    assert(afterOther.attempt_id === beforeOther.attempt_id
      && afterOther.completed_at_utc === beforeOther.completed_at_utc,
    `${game} single-game update changed ${otherGame} health provenance`, { beforeOther, afterOther });
    const outer = await outerSnapshot(topId);
    const visibleTargetCompletedAt = visibleUpdateHealthCompletedAt(outer, game);
    const visibleOtherCompletedAt = visibleUpdateHealthCompletedAt(outer, otherGame);
    const targetSampleDate = updateHealthLatestSampleDate(health, game);
    const otherSampleDate = updateHealthLatestSampleDate(health, otherGame);
    return automaticUpdateHealthReady(outer)
      && /^\d{4}-\d{2}-\d{2}$/u.test(targetSampleDate)
      && /^\d{4}-\d{2}-\d{2}$/u.test(otherSampleDate)
      && outer.updateHealthGames.some((value) => value.includes("HSR 最近成功"))
      && outer.updateHealthGames.some((value) => value.includes("ZZZ 最近成功"))
      && outer.updateHealthGames.some((value) => value.includes(`${game === "hsr" ? "HSR" : "ZZZ"} 最近成功`)
        && value.includes(`终局最新采样 ${targetSampleDate}`))
      && outer.updateHealthGames.some((value) => value.includes(`${otherGame === "hsr" ? "HSR" : "ZZZ"} 最近成功`)
        && value.includes(`终局最新采样 ${otherSampleDate}`))
      && visibleTargetCompletedAt.includes(afterTarget.completed_at_utc)
      && visibleOtherCompletedAt.includes(afterOther.completed_at_utc)
      ? { health, outer, visibleTargetCompletedAt, visibleOtherCompletedAt }
      : null;
  }, updateTimeoutMs);
  const updatedGameHealth = updateHealthGame(healthReceipt.health, game);
  const targetSampleDate = updateHealthLatestSampleDate(healthReceipt.health, game);
  const otherSampleDate = updateHealthLatestSampleDate(healthReceipt.health, otherGame);
  const analysisSampleDates = analyses
    .map((snapshot) => snapshot?.analysisExpectedPhase?.sampleDate ?? "")
    .filter((value) => /^\d{4}-\d{2}-\d{2}$/u.test(value))
    .sort();
  const visualizerLatestSampleDate = analysisSampleDates.at(-1) ?? "";
  assert(/^\d{4}-\d{2}-\d{2}$/u.test(targetSampleDate)
    && /^\d{4}-\d{2}-\d{2}$/u.test(otherSampleDate),
  `${game} update health does not expose strict sample dates for both games`, healthReceipt.health);
  assert(targetSampleDate === visualizerLatestSampleDate,
    `${game} update health sample date disagrees with the verified analysis modes`, {
      targetSampleDate,
      analysisSampleDates,
    });
  const hasHistoricalSamples = Object.values(updatedGameHealth?.freshness?.modes ?? {})
    .some((mode) => mode?.status === "stale");
  const hasQualityWarning = updatedGameHealth?.freshness?.status === "warning";
  assert(task.text.includes("本机更新与校验成功")
    && task.text.includes("查看本次更新结果")
    && !task.text.includes("查看最新 Box 和分析"),
  `${game} completed task card still overstates update freshness`, task);
  if (hasHistoricalSamples) {
    assert(task.text.includes("终局分析保留上游最新可用的历史样本"),
      `${game} completed task card does not disclose historical upstream samples`, task);
  } else if (hasQualityWarning) {
    assert(task.text.includes("终局数据质量有告警") && !task.text.includes("历史样本"),
      `${game} completed task card misstates a non-historical quality warning`, task);
  } else {
    assert(task.text.includes("Box、卡池和终局分析已刷新") && !task.text.includes("历史样本"),
      `${game} completed task card incorrectly claims historical upstream samples`, task);
  }
  return {
    game,
    taskId: task.taskId,
    status: task.status,
    revisionBefore: beforeOuter.frameDataRevision,
    revisionAfter: afterOuter.frameDataRevision,
    terminalRevision: terminalDescriptor.data_revision,
    frameLoadCountBefore: beforeOuter.frameProbeLoadCount,
    frameLoadCountAfter: afterOuter.frameProbeLoadCount,
    pageBefore: beforeOuter.framePage,
    pageAfter: afterOuter.framePage,
    bannerRefresh: {
      status: bannerSnapshot.bannerRefreshStatus,
      fetchedAt: bannerSnapshot.bannerRefreshFetchedAt,
      sourceLabel: bannerSnapshot.bannerRefreshSourceLabel,
    },
    bannerCurrentNames: bannerSnapshot.bannerCardNames,
    bannerNext: nextBanner,
    analyses: analyses.map((snapshot) => snapshot.analysisExpectedPhase),
    updateHealth: {
      state: healthReceipt.outer.updateHealthState,
      attemptId: updateHealthGame(healthReceipt.health, game).attempt_id,
      completedAtUtc: updateHealthGame(healthReceipt.health, game).completed_at_utc,
      latestSampleDate: targetSampleDate,
      modes: Object.fromEntries(Object.entries(updatedGameHealth.freshness.modes)
        .map(([mode, freshness]) => [mode, {
          status: freshness.status,
          sampleDate: freshness.sample_date,
          startDate: freshness.start_date,
          endDate: freshness.end_date,
        }])),
      otherGameAttemptId: updateHealthGame(healthReceipt.health, otherGame).attempt_id,
      otherGameLatestSampleDate: otherSampleDate,
      visibleCompletedAtUtc: healthReceipt.visibleTargetCompletedAt,
      otherGameVisibleCompletedAtUtc: healthReceipt.visibleOtherCompletedAt,
    },
  };
}

async function verifyPublicDataUpdates(topId) {
  const boxesBefore = {};
  for (const game of ["hsr", "zzz"]) {
    boxesBefore[game] = await boxProtectionSnapshot(await activeFrameContext(game), game);
  }
  const updates = [];
  for (const game of ["zzz", "hsr"]) updates.push(await verifyPublicDataUpdate(topId, game));
  const finalVerification = {};
  for (const game of ["hsr", "zzz"]) {
    await ensureActiveGame(topId, game);
    const context = await activeFrameContext(game);
    const banner = await switchProductPage(context, game, "banner");
    verifyBanner(banner, game);
    const analysis = await switchProductPage(context, game, "analysis");
    const analyses = await verifyAnalysisModes(context, game, analysis);
    finalVerification[game] = {
      bannerRefresh: {
        status: banner.bannerRefreshStatus,
        fetchedAt: banner.bannerRefreshFetchedAt,
        sourceLabel: banner.bannerRefreshSourceLabel,
      },
      bannerCurrentNames: banner.bannerCardNames,
      analyses: analyses.map((snapshot) => snapshot.analysisExpectedPhase),
    };
  }
  const boxesAfter = {};
  const boxProtection = {};
  for (const game of ["hsr", "zzz"]) {
    boxesAfter[game] = await boxProtectionSnapshot(await activeFrameContext(game), game);
    boxProtection[game] = verifyBoxProtection(boxesBefore[game], boxesAfter[game], game);
  }
  return { updates, finalVerification, boxProtection };
}

async function verifyBoxFlushBridges(topId) {
  const receipt = await evaluate(topId, `(async () => {
    const frames=[...document.querySelectorAll('iframe.visualizer-frame')]
      .filter((frame)=>frame.dataset.loaded==='true'&&frame.contentWindow);
    if(frames.length!==2)throw new Error('both Visualizer frames must be loaded before the Box flush probe');
    const expected=new Map(frames.map((frame,index)=>['product-probe-flush-'+index,{game:frame.dataset.game,source:frame.contentWindow}]));
    const results=[];
    await new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>{window.removeEventListener('message',onMessage);reject(new Error('Box flush bridge timed out'));},10000);
      const onMessage=(event)=>{
        const message=event.data,entry=message&&expected.get(message.request_id);
        if(!entry||event.source!==entry.source||message.schema_version!=='miho-visualizer-box-flush-result-v1')return;
        expected.delete(message.request_id);
        results.push({game:entry.game,ok:message.ok===true});
        if(expected.size===0){clearTimeout(timeout);window.removeEventListener('message',onMessage);resolve();}
      };
      window.addEventListener('message',onMessage);
      for(const [request_id,entry] of expected)entry.source.postMessage({schema_version:'miho-visualizer-box-flush-request-v1',request_id},'*');
    });
    return results.sort((left,right)=>left.game.localeCompare(right.game));
  })()`);
  assert(Array.isArray(receipt)
    && receipt.length === 2
    && receipt.every((entry) => (entry.game === "hsr" || entry.game === "zzz") && entry.ok === true),
  "Visualizer Box flush bridge did not acknowledge both loaded games", receipt);
  return receipt;
}

const receipt = {
  schema_version: "miho-product-ui-probe-v1",
  sequence: [],
};

try {
  await session.connect();
  await session.send("Target.setDiscoverTargets", { discover: true });
  await session.send("Runtime.enable");
  await session.send("Page.enable");
  const top = await topContext();
  await waitFor("persistent Visualizer frame probes", async () => evaluate(top.id, `(() => {
    const frames = [...document.querySelectorAll('iframe.visualizer-frame')];
    if (frames.length !== 2) return false;
    frames.forEach((frame, index) => {
      if (frame.dataset.probeId) return;
      frame.dataset.probeId = 'persistent-' + (frame.dataset.game || index) + '-' + index;
      frame.dataset.probeLoadCount = '0';
      frame.addEventListener('load', () => {
        frame.dataset.probeLoadCount = String(Number.parseInt(frame.dataset.probeLoadCount || '0', 10) + 1);
      });
    });
    return true;
  })()`));

  const initialOuter = await waitForDesktopVisualizerStage(top.id, "zzz", "initial ZZZ desktop shell", (value) => (
    value.frameLoaded && value.frameSrc.includes("/zzz/index.html") && value.frameSrc.endsWith("#box")
      && automaticUpdateHealthReady(value)
  ));
  verifyOuter(initialOuter, "zzz");
  receipt.outerCompactLayout = await verifyOuterCompactLayout(top.id);
  const zzzInitial = await productSnapshot("zzz");
  verifyProduct(zzzInitial, "zzz");
  const zzzContext = await activeFrameContext("zzz");
  const zzzStateBefore = await zzzPersistenceSnapshot(zzzContext);
  const zzzBoxRoster = await verifyZzzBoxRoster(zzzContext);
  const zzzBoxBatchPreview = await verifyBoxBatchPreview(zzzContext, "zzz");
  const zzzRecommender = await verifyZzzRecommender(zzzContext);
  const zzzSearchAndLock = await verifyRecommenderSearchAndLock(zzzContext, "zzz");
  const zzzAnalysis = await switchProductPage(zzzContext, "zzz", "analysis");
  const zzzAnalyses = await verifyAnalysisModes(
    zzzContext,
    "zzz",
    zzzAnalysis,
    {
      requirePhaseMatch: !runUpdates,
      requirePhasePresentation: !runUpdates,
    },
  );
  const zzzCompactTooltip = await verifyZzzCompactTooltipLayout(top.id, zzzContext);
  const zzzBanner = await switchProductPage(zzzContext, "zzz", "banner");
  verifyBanner(zzzBanner, "zzz", {
    requireFresh: !runUpdates,
    requireExpected: !runUpdates,
    requireCurrent: !runUpdates,
  });
  receipt.sequence.push({
    game: "zzz",
    outer: initialOuter,
    product: zzzInitial,
    boxRoster: zzzBoxRoster,
    boxBatchPreview: zzzBoxBatchPreview,
    recommender: zzzRecommender,
    searchAndLock: zzzSearchAndLock,
    persistenceBefore: zzzPersistenceReceipt(zzzStateBefore),
    analyses: zzzAnalyses,
    compactTooltip: zzzCompactTooltip,
    banner: zzzBanner,
  });

  await switchGame(top.id, "hsr");
  const hsrOuter = await waitForDesktopVisualizerStage(top.id, "hsr", "HSR desktop shell", (value) => (
    value.frameLoaded && value.frameSrc.includes("/hsr/index.html") && value.frameSrc.endsWith("#box")
      && automaticUpdateHealthReady(value)
  ));
  verifyOuter(hsrOuter, "hsr");
  const hsrProduct = await productSnapshot("hsr");
  verifyProduct(hsrProduct, "hsr");
  const hsrContext = await activeFrameContext("hsr");
  const hsrBoxBatchPreview = await verifyBoxBatchPreview(hsrContext, "hsr");
  const hsrBoxExport = await verifyHsrBoxExport(hsrContext);
  const hsrRecommender = await verifyHsrRecommender(hsrContext);
  const hsrSearchAndLock = await verifyRecommenderSearchAndLock(hsrContext, "hsr");
  const hsrRecommenderLayout = await verifyHsrRecommenderLayout(top.id, hsrContext);
  const hsrAnalysis = await switchProductPage(hsrContext, "hsr", "analysis");
  const hsrAnalyses = await verifyAnalysisModes(
    hsrContext,
    "hsr",
    hsrAnalysis,
    {
      requirePhaseMatch: !runUpdates,
      requirePhasePresentation: !runUpdates,
    },
  );
  const hsrBanner = await switchProductPage(hsrContext, "hsr", "banner");
  verifyBanner(hsrBanner, "hsr", {
    requireFresh: !runUpdates,
    requireExpected: !runUpdates,
    requireCurrent: !runUpdates,
  });
  receipt.sequence.push({ game: "hsr", outer: hsrOuter, product: hsrProduct, boxBatchPreview: hsrBoxBatchPreview, boxExport: hsrBoxExport, recommender: hsrRecommender, searchAndLock: hsrSearchAndLock, recommenderLayout: hsrRecommenderLayout, analyses: hsrAnalyses, banner: hsrBanner });

  await switchGame(top.id, "zzz");
  const zzzReturnOuter = await waitForDesktopVisualizerStage(top.id, "zzz", "returned ZZZ desktop shell", (value) => (
    value.frameLoaded && value.frameSrc.includes("/zzz/index.html") && value.frameSrc.endsWith("#box")
      && automaticUpdateHealthReady(value)
  ));
  verifyOuter(zzzReturnOuter, "zzz", "banner");
  assert(zzzReturnOuter.frameProbeId === initialOuter.frameProbeId,
    "ZZZ Visualizer iframe node was replaced across game switches", { initialOuter, zzzReturnOuter });
  assert(zzzReturnOuter.frameSrc === initialOuter.frameSrc,
    "ZZZ Visualizer URL changed across a revision-stable game switch", { initialOuter, zzzReturnOuter });
  assert(zzzReturnOuter.frameDataRevision === initialOuter.frameDataRevision,
    "ZZZ Visualizer data revision changed across a read-only game switch", { initialOuter, zzzReturnOuter });
  assert(zzzReturnOuter.frameProbeLoadCount === initialOuter.frameProbeLoadCount,
    "ZZZ Visualizer navigated while its data revision was unchanged", { initialOuter, zzzReturnOuter });
  const zzzReturnContext = await activeFrameContext("zzz");
  const zzzPreserved = await waitFor("returned ZZZ preserved product page", async () => {
    const value = await evaluate(zzzReturnContext.id, productExpression, zzzReturnContext.sessionId);
    return value?.readyState === "complete" && value?.statePage === "banner" && value?.bannerVisible
      ? value
      : null;
  });
  verifyBanner(zzzPreserved, "zzz", {
    requireFresh: !runUpdates,
    requireExpected: !runUpdates,
    requireCurrent: !runUpdates,
  });
  assert(new URL(zzzPreserved.href).hash === "#banner"
    && JSON.stringify(zzzPreserved.bannerCardNames) === JSON.stringify(zzzBanner.bannerCardNames),
  "ZZZ iframe did not preserve its product page across game switches", {before: zzzBanner, after: zzzPreserved});
  const zzzReturn = await switchProductPage(zzzReturnContext, "zzz", "box");
  verifyProduct(zzzReturn, "zzz");
  const zzzReturnBoxRoster = await verifyZzzBoxRoster(zzzReturnContext);
  const zzzStateAfter = await zzzPersistenceSnapshot(zzzReturnContext);
  const zzzPersistence = verifyZzzPersistence(zzzStateBefore, zzzStateAfter);
  receipt.sequence.push({
    game: "zzz",
    outer: zzzReturnOuter,
    preservedPage: zzzPreserved,
    product: zzzReturn,
    boxRoster: zzzReturnBoxRoster,
    persistence: zzzPersistence,
  });

  receipt.publicDataUpdates = runUpdates
    ? await verifyPublicDataUpdates(top.id)
    : { skipped: true, reason: "--run-updates was not enabled" };
  receipt.boxFlush = await verifyBoxFlushBridges(top.id);

  process.stdout.write(`${serializeProductUiProbeReceipt(receipt)}\n`);
} catch (error) {
  if (isVisualizerStartupFailureError(error)) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  } else {
    throw error;
  }
} finally {
  session.close();
}
