#!/usr/bin/env node

import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index];
  const value = process.argv[index + 1];
  if (!key?.startsWith("--") || value === undefined) {
    throw new Error(`invalid argument near ${key ?? "<end>"}`);
  }
  args.set(key.slice(2), value);
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
  hsr: (args.get("expected-hsr-banner-names") ?? "").split("|").filter(Boolean),
  zzz: (args.get("expected-zzz-banner-names") ?? "").split("|").filter(Boolean),
};
const expectedAnalysisModes = {
  hsr: ["moc", "pf", "as", "aa"],
  zzz: ["sd", "da"],
};
const timeoutMs = Number(args.get("timeout-ms") ?? "30000");
const boxExportDir = args.get("box-export-dir") ?? null;
const sourceHsrBox = args.get("source-hsr-box") ?? null;

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
}
if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 5000 || timeoutMs > 120000) {
  throw new Error("--timeout-ms must be an integer between 5000 and 120000");
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
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP command timed out: ${method}`));
      }, 15000);
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

async function waitFor(description, probe) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const value = await probe();
      if (value) return value;
    } catch (error) {
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
  const frame = document.querySelector('iframe.visualizer-frame');
  const utilities = document.querySelector('details.utilities');
  const activeGame = [...document.querySelectorAll('.game-button')]
    .find((button) => button.getAttribute('aria-pressed') === 'true');
  return {
    href: location.href,
    readyState: document.readyState,
    ready: document.documentElement.dataset.mihoAppReady ?? '',
    brand: document.querySelector('.brand .eyebrow')?.textContent?.trim() ?? '',
    firstPanel: document.querySelector('main.dashboard')?.firstElementChild?.className ?? '',
    visualizerTitle: document.querySelector('.visualizer-panel h2')?.textContent?.trim() ?? '',
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
  const statePage = typeof state === 'object' ? state?.page ?? '' : '';
  const analysisMode = typeof state === 'object' ? state?.mode ?? '' : '';
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
  const currentBannerRows = typeof DATA === 'object' && Array.isArray(DATA?.bannerRows)
    ? DATA.bannerRows.filter((row) => row?.phase_status === 'current')
    : [];
  const bannerImages = bannerCards.map((card) => card.querySelector('img')).filter(Boolean);
  await settleImages(bannerImages);
  const bannerBrokenImages = bannerImages.flatMap((image) => image.complete && image.naturalWidth > 0
    ? []
    : [{ src: image.getAttribute('src') ?? '', complete: image.complete, naturalWidth: image.naturalWidth }]);
  const bannerSlugByName = new Map(currentBannerRows.map((row) => [
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
  return {
    href: location.href,
    readyState: document.readyState,
    statePage,
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
    usageRowCount: usageRows.length,
    analysisMode,
    analysisModeUsageRowCount: usageRows.filter((row) => (row?.tier_mode ?? row?.mode) === analysisMode).length,
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
    bannerBadges: document.querySelector('#bannerBadges')?.textContent?.trim() ?? '',
    bannerPhase: typeof banner === 'object' ? banner?.phase ?? '' : '',
    bannerAllRowCount: typeof DATA === 'object' && Array.isArray(DATA?.bannerRows) ? DATA.bannerRows.length : 0,
    bannerCurrentRowCount: currentBannerRows.length,
    bannerCardCount: bannerCards.length,
    bannerCardNames: bannerCards.map((card) => card.querySelector('h3')?.textContent?.trim() ?? ''),
    bannerImageCount: bannerImages.length,
    bannerBrokenImages,
    bannerMappingErrors,
    visibleMissingMessages: visibleText.filter((text) => /卡池数据未生成|该模式数据未生成|缺数据/.test(text)),
  };
})()`;

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

async function activeFrameContext(game) {
  const expectedPath = `/${game}/index.html`;
  return waitFor(`${game} Visualizer frame`, async () => {
    const tree = await session.send("Page.getFrameTree");
    const frames = flattenFrames(tree.frameTree).filter((candidate) => {
      try {
        const url = new URL(candidate.url);
        return url.hostname === "miho-visualizer.localhost"
          && url.pathname.endsWith(expectedPath)
          && url.hash === "#box";
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
          && url.pathname.endsWith(expectedPath)
          && url.hash === "#box";
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

async function productSnapshot(game) {
  return waitFor(`${game} product DOM`, async () => {
    const context = await activeFrameContext(game);
    try {
      const snapshot = await evaluate(context.id, productExpression, context.sessionId);
      return snapshot?.readyState === "complete"
        && snapshot?.statePage === "box"
        && snapshot?.tabs?.length > 0
        && snapshot?.rosterCount > 0
        && snapshot?.cardCount === snapshot?.rosterCount
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

function verifyOuter(snapshot, game) {
  const gameLabel = game === "hsr" ? "崩坏：星穹铁道" : "绝区零";
  assert(snapshot.href === "https://tauri.localhost/#miho-app-ready-v1", "desktop URL is not the production ready URL", snapshot);
  assert(snapshot.readyState === "complete" && snapshot.ready === "v1", "desktop ready sentinel is absent", snapshot);
  assert(snapshot.brand === "MIHO ENDGAME", "desktop brand is absent", snapshot);
  assert(snapshot.firstPanel.includes("visualizer-panel"), "Visualizer is not the first product panel", snapshot);
  assert(snapshot.visualizerTitle.includes(gameLabel) && snapshot.visualizerTitle.includes("我的 Box"), "Visualizer title does not describe the selected Box", snapshot);
  assert(snapshot.frameVisible && snapshot.frameHeight >= 500, "Visualizer frame is not visibly usable", snapshot);
  assert(snapshot.frameSrc.includes(`/${game}/index.html`) && snapshot.frameSrc.endsWith("#box"), "Visualizer frame did not open the Box page", snapshot);
  assert(new Set(snapshot.frameSandbox.split(/\s+/u)).has("allow-downloads"), "Visualizer frame does not permit Box downloads", snapshot);
  assert(snapshot.utilitiesOpen === false, "advanced utilities are expanded by default", snapshot);
  assert(snapshot.utilitiesSummary === "更新数据、生成报告与设置", "advanced utilities do not use the customer-facing label", snapshot);
  assert(snapshot.visibleTaskIds === 0, "technical task identifiers are visible on the main page", snapshot);
  assert(snapshot.activeGame === gameLabel, "game switch did not update the active game", snapshot);
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
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
}

async function switchProductPage(context, game, page) {
  const labels = {
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
    const pageVisible = page === "analysis" ? snapshot?.analysisVisible : snapshot?.bannerVisible;
    return snapshot?.readyState === "complete" && snapshot?.statePage === page && pageVisible
      ? snapshot
      : null;
  });
}

function verifyAnalysis(snapshot, game, mode) {
  assert(snapshot.statePage === "analysis" && snapshot.analysisVisible, `${game} endgame analysis is not visible`, snapshot);
  assert(snapshot.analysisMode === mode, `${game} endgame analysis did not switch to ${mode}`, snapshot);
  assert(snapshot.usageRowCount > 0, `${game} endgame usage data is absent`, snapshot);
  assert(snapshot.analysisModeUsageRowCount > 0, `${game} ${mode} endgame data is absent`, snapshot);
  assert(snapshot.analysisVisualState.display !== "none"
    && snapshot.analysisVisualState.visibility === "visible"
    && snapshot.analysisVisualState.opacity > 0, `${game} ${mode} endgame container is visually suppressed`, snapshot);
  assert(snapshot.analysisTitle.length > 0, `${game} ${mode} endgame title is absent`, snapshot);
  assert(snapshot.analysisSubtitle.includes("最新采样 "), `${game} endgame sample date is not displayed`, snapshot);
  assert(!snapshot.analysisSubtitle.includes("最新采样 未知"), `${game} endgame sample date is unknown`, snapshot);
  assert(/当前周期|历史样本|周期未知/.test(snapshot.analysisSubtitle), `${game} endgame freshness label is absent`, snapshot);
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

async function verifyAnalysisModes(context, game, initialSnapshot) {
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
    verifyAnalysis(snapshot, game, mode);
    snapshots.push(snapshot);
  }
  return snapshots;
}

function verifyBanner(snapshot, game) {
  assert(snapshot.statePage === "banner" && snapshot.bannerVisible, `${game} banner page is not visible`, snapshot);
  assert(snapshot.bannerTitle === "卡池情报", `${game} banner title is absent`, snapshot);
  assert(snapshot.bannerAllRowCount > 0 && snapshot.bannerCurrentRowCount > 0, `${game} current banner data is absent`, snapshot);
  assert(snapshot.bannerPhase === "current", `${game} banner page did not select the current populated phase`, snapshot);
  assert(snapshot.bannerCardCount > 0 && snapshot.bannerCardNames.every(Boolean), `${game} current banner cards are absent`, snapshot);
  assert(snapshot.bannerImageCount === snapshot.bannerCardCount
    && snapshot.bannerBrokenImages.length === 0
    && snapshot.bannerMappingErrors.length === 0, `${game} current banner images are broken or mismatched`, snapshot);
  assert(snapshot.bannerBadges.includes(`Box ${expectedOwned[game]}`), `${game} banner page lost the current Box`, snapshot);
  assert(snapshot.visibleMissingMessages.length === 0, `${game} banner page exposes a missing-data warning`, snapshot);
  if (expectedBannerCount[game] !== null) {
    assert(snapshot.bannerCurrentRowCount === expectedBannerCount[game], `${game} current banner data count changed`, snapshot);
    assert(snapshot.bannerCardCount === expectedBannerCount[game], `${game} rendered current banner count changed`, snapshot);
  }
  if (expectedBannerNames[game].length > 0) {
    const actual = [...snapshot.bannerCardNames].sort();
    const expected = [...expectedBannerNames[game]].sort();
    assert(JSON.stringify(actual) === JSON.stringify(expected), `${game} rendered current banner names changed`, { actual, expected });
  }
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

  const initialOuter = await waitFor("initial ZZZ desktop shell", async () => {
    const value = await evaluate(top.id, outerExpression);
    return value.frameSrc.includes("/zzz/index.html") && value.frameSrc.endsWith("#box") ? value : null;
  });
  verifyOuter(initialOuter, "zzz");
  const zzzInitial = await productSnapshot("zzz");
  verifyProduct(zzzInitial, "zzz");
  const zzzContext = await activeFrameContext("zzz");
  const zzzAnalysis = await switchProductPage(zzzContext, "zzz", "analysis");
  const zzzAnalyses = await verifyAnalysisModes(zzzContext, "zzz", zzzAnalysis);
  const zzzBanner = await switchProductPage(zzzContext, "zzz", "banner");
  verifyBanner(zzzBanner, "zzz");
  receipt.sequence.push({ game: "zzz", outer: initialOuter, product: zzzInitial, analyses: zzzAnalyses, banner: zzzBanner });

  await switchGame(top.id, "hsr");
  const hsrOuter = await waitFor("HSR desktop shell", async () => {
    const value = await evaluate(top.id, outerExpression);
    return value.frameSrc.includes("/hsr/index.html") && value.frameSrc.endsWith("#box") ? value : null;
  });
  verifyOuter(hsrOuter, "hsr");
  const hsrProduct = await productSnapshot("hsr");
  verifyProduct(hsrProduct, "hsr");
  const hsrContext = await activeFrameContext("hsr");
  const hsrBoxExport = await verifyHsrBoxExport(hsrContext);
  const hsrAnalysis = await switchProductPage(hsrContext, "hsr", "analysis");
  const hsrAnalyses = await verifyAnalysisModes(hsrContext, "hsr", hsrAnalysis);
  const hsrBanner = await switchProductPage(hsrContext, "hsr", "banner");
  verifyBanner(hsrBanner, "hsr");
  receipt.sequence.push({ game: "hsr", outer: hsrOuter, product: hsrProduct, boxExport: hsrBoxExport, analyses: hsrAnalyses, banner: hsrBanner });

  await switchGame(top.id, "zzz");
  const zzzReturnOuter = await waitFor("returned ZZZ desktop shell", async () => {
    const value = await evaluate(top.id, outerExpression);
    return value.frameSrc.includes("/zzz/index.html") && value.frameSrc.endsWith("#box") ? value : null;
  });
  verifyOuter(zzzReturnOuter, "zzz");
  const zzzReturn = await productSnapshot("zzz");
  verifyProduct(zzzReturn, "zzz");
  receipt.sequence.push({ game: "zzz", outer: zzzReturnOuter, product: zzzReturn });

  process.stdout.write(`${JSON.stringify(receipt)}\n`);
} finally {
  session.close();
}
