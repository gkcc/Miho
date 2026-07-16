#!/usr/bin/env node

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
const timeoutMs = Number(args.get("timeout-ms") ?? "30000");

if (!webSocketUrl) throw new Error("--ws is required");
for (const game of ["hsr", "zzz"]) {
  if (!Number.isSafeInteger(expectedOwned[game]) || expectedOwned[game] < 0) {
    throw new Error(`--expected-${game}-owned must be a non-negative integer`);
  }
  if (!Number.isSafeInteger(expectedTotal[game]) || expectedTotal[game] <= 0) {
    throw new Error(`--expected-${game}-total must be a positive integer`);
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
    frameVisible: visible(frame) && !frame.hidden,
    frameHeight: frame?.getBoundingClientRect().height ?? 0,
    utilitiesOpen: utilities?.open ?? null,
    utilitiesSummary: utilities?.querySelector(':scope > summary')?.textContent?.trim() ?? '',
    visibleTaskIds: [...document.querySelectorAll('.task-id')].filter(visible).length,
    activeGame: activeGame?.textContent?.trim() ?? '',
  };
})()`;

const productExpression = `(async () => {
  const cards = [...document.querySelectorAll('#boxGrid .box-card')];
  const images = cards.map((card) => card.querySelector('img')).filter(Boolean);
  for (const image of images) image.loading = 'eager';
  await Promise.all(images.map(async (image) => {
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
  const basename = (value) => {
    try {
      const name = decodeURIComponent(new URL(value, location.href).pathname.split('/').pop() ?? '');
      return name.replace(/\.[^.]+$/, '');
    } catch { return ''; }
  };
  const rosterRows = typeof DATA === 'object' && Array.isArray(DATA?.rosterRows) ? DATA.rosterRows : [];
  const statePage = typeof state === 'object' ? state?.page ?? '' : '';
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

async function evaluate(contextId, expression, sessionId = undefined) {
  const result = await session.send("Runtime.evaluate", {
    ...(contextId === undefined || contextId === null ? {} : { contextId }),
    expression,
    returnByValue: true,
    awaitPromise: true,
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
    const frame = flattenFrames(tree.frameTree).find((candidate) => {
      try {
        const url = new URL(candidate.url);
        return url.hostname === "miho-visualizer.localhost"
          && url.pathname.endsWith(expectedPath)
          && url.hash === "#box";
      } catch {
        return false;
      }
    });
    if (frame) {
      const context = [...contexts.values()].find((candidate) => candidate.auxData?.isDefault === true
        && candidate.auxData?.frameId === frame.id);
      if (context) return context;
    }

    const targets = await session.send("Target.getTargets");
    const target = (targets.targetInfos ?? []).find((candidate) => {
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
  assert(snapshot.utilitiesOpen === false, "advanced utilities are expanded by default", snapshot);
  assert(snapshot.utilitiesSummary === "更新数据、生成报告与设置", "advanced utilities do not use the customer-facing label", snapshot);
  assert(snapshot.visibleTaskIds === 0, "technical task identifiers are visible on the main page", snapshot);
  assert(snapshot.activeGame === gameLabel, "game switch did not update the active game", snapshot);
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
  receipt.sequence.push({ game: "zzz", outer: initialOuter, product: zzzInitial });

  await switchGame(top.id, "hsr");
  const hsrOuter = await waitFor("HSR desktop shell", async () => {
    const value = await evaluate(top.id, outerExpression);
    return value.frameSrc.includes("/hsr/index.html") && value.frameSrc.endsWith("#box") ? value : null;
  });
  verifyOuter(hsrOuter, "hsr");
  const hsrProduct = await productSnapshot("hsr");
  verifyProduct(hsrProduct, "hsr");
  receipt.sequence.push({ game: "hsr", outer: hsrOuter, product: hsrProduct });

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
