const SCHEMA_VERSION = "miho-product-ui-probe-v1";
const MAX_RECEIPT_BYTES = 64 * 1024;
const expectedModes = {
  hsr: ["moc", "pf", "as", "aa"],
  zzz: ["sd", "da"],
};

function definedObject(value) {
  return value && typeof value === "object" ? value : {};
}

function phaseReceipt(phaseLike) {
  const phase = definedObject(phaseLike?.analysisExpectedPhase ?? phaseLike);
  return {
    sampleDate: phase.sampleDate ?? "",
    phaseVersion: phase.phaseVer ?? phase.phaseVersion ?? "",
    theme: phase.phaseName ?? phase.theme ?? "",
    mechanic: phase.mechanicName ?? phase.mechanic ?? "",
    startDate: phase.startDate ?? "",
    endDate: phase.endDate ?? "",
    status: phase.status ?? "",
  };
}

function analysesReceipt(snapshots, game) {
  const modes = expectedModes[game] ?? [];
  return Object.fromEntries((Array.isArray(snapshots) ? snapshots : []).flatMap((snapshot, index) => {
    const mode = snapshot?.analysisMode ?? snapshot?.mode ?? modes[index] ?? "";
    return mode ? [[mode, phaseReceipt(snapshot)]] : [];
  }));
}

function bannerReceipt(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return null;
  const refresh = definedObject(snapshot.bannerRefresh);
  const selectedPhase = snapshot.bannerSelectedPhase ?? snapshot.bannerPhase ?? "";
  const currentNames = snapshot.bannerDataCurrentNames
    ?? snapshot.bannerCurrentNames
    ?? (selectedPhase === "" || selectedPhase === "current" ? snapshot.bannerCardNames : [])
    ?? [];
  const visibleNames = snapshot.bannerVisibleNames ?? snapshot.bannerCardNames ?? [];
  return {
    status: snapshot.bannerRefreshStatus ?? refresh.status ?? "",
    fetchedAt: snapshot.bannerRefreshFetchedAt ?? refresh.fetchedAt ?? "",
    sourceLabel: snapshot.bannerRefreshSourceLabel ?? refresh.sourceLabel ?? "",
    selectedPhase,
    currentCount: snapshot.bannerCurrentRowCount
      ?? (Array.isArray(currentNames) ? currentNames.length : 0),
    currentNames: Array.isArray(currentNames) ? currentNames : [],
    visibleNames: Array.isArray(visibleNames) ? visibleNames : [],
  };
}

function persistenceReceipt(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return null;
  return {
    boxSha256: snapshot.boxSha256 ?? "",
    localStorageSha256: snapshot.localStorageSha256 ?? "",
    owned: snapshot.ownedCount ?? snapshot.owned ?? null,
    boxUnchanged: snapshot.boxUnchanged ?? null,
    localStorageUnchanged: snapshot.localStorageUnchanged ?? null,
  };
}

function boxExportReceipt(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return null;
  return {
    sha256: snapshot.sha256 ?? "",
    bytes: snapshot.bytes ?? null,
    owned: snapshot.owned ?? null,
    sourceUnchanged: snapshot.sourceUnchanged ?? null,
  };
}

function sequenceEntryReceipt(entry, index) {
  const outer = definedObject(entry?.outer);
  const product = definedObject(entry?.product);
  const roster = definedObject(entry?.boxRoster);
  const analysisModes = analysesReceipt(entry?.analyses, entry?.game);
  const banner = bannerReceipt(entry?.banner ?? entry?.preservedPage);
  const persistence = persistenceReceipt(entry?.persistence ?? entry?.persistenceBefore);
  const boxExport = boxExportReceipt(entry?.boxExport);
  const stage = entry?.persistence ? "return" : index === 0 ? "initial" : "switch";
  return {
    game: entry?.game ?? outer.frameGame ?? "",
    stage,
    revision: outer.frameDataRevision ?? "",
    page: outer.framePage ?? product.statePage ?? "",
    frame: {
      probeId: outer.frameProbeId ?? "",
      loadCount: outer.frameProbeLoadCount ?? null,
    },
    box: {
      owned: product.ownedStateCount ?? product.ownedCardCount ?? persistence?.owned ?? null,
      total: product.rosterCount ?? product.cardCount ?? null,
      orderingVerified: roster.orderingVerified ?? null,
      batchPreviewStateUnchanged: entry?.boxBatchPreview?.stateUnchanged ?? null,
      persistence,
      export: boxExport,
    },
    analysis: {
      latestSampleDate: product.latestEndgameSampleDate ?? "",
      tierUpdatedAt: product.tierUpdatedAt ?? "",
      modes: analysisModes,
    },
    banner,
  };
}

function layoutReceipt(snapshot) {
  const value = definedObject(snapshot);
  const panel = definedObject(value.panel);
  return {
    verified: true,
    viewportWidth: value.innerWidth ?? null,
    documentScrollWidth: value.documentScrollWidth ?? null,
    panel: {
      left: panel.left ?? null,
      right: panel.right ?? null,
      width: panel.width ?? null,
    },
    cards: (Array.isArray(value.items) ? value.items : []).map((item) => ({
      left: item?.left ?? null,
      right: item?.right ?? null,
      width: item?.width ?? null,
      sample: item?.sample ?? "",
    })),
  };
}

function updateHealthReceipt(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return null;
  return {
    state: snapshot.state ?? "",
    attemptId: snapshot.attemptId ?? "",
    completedAtUtc: snapshot.completedAtUtc ?? "",
    latestSampleDate: snapshot.latestSampleDate ?? "",
    modes: definedObject(snapshot.modes),
    otherGameAttemptId: snapshot.otherGameAttemptId ?? "",
    otherGameLatestSampleDate: snapshot.otherGameLatestSampleDate ?? "",
  };
}

function updateReceipt(snapshot, game) {
  const value = definedObject(snapshot);
  return {
    game,
    status: value.status ?? "",
    revision: {
      before: value.revisionBefore ?? "",
      after: value.revisionAfter ?? "",
      terminal: value.terminalRevision ?? "",
    },
    frameLoadCount: {
      before: value.frameLoadCountBefore ?? null,
      after: value.frameLoadCountAfter ?? null,
    },
    page: {
      before: value.pageBefore ?? "",
      after: value.pageAfter ?? "",
    },
    banner: bannerReceipt(value),
    analysis: {
      modes: analysesReceipt(value.analyses, game),
    },
    updateHealth: updateHealthReceipt(value.updateHealth),
  };
}

function boxProtectionReceipt(snapshot) {
  if (!snapshot || typeof snapshot !== "object") return null;
  return {
    liveSha256: snapshot.liveSha256 ?? "",
    diskSha256: snapshot.diskSha256 ?? "",
    owned: snapshot.owned ?? null,
    liveUnchanged: snapshot.liveUnchanged ?? null,
    diskUnchanged: snapshot.diskUnchanged ?? null,
  };
}

function publicDataUpdatesReceipt(snapshot) {
  const value = definedObject(snapshot);
  if (value.skipped === true) {
    return { skipped: true, reason: value.reason ?? "" };
  }
  const updateGames = ["zzz", "hsr"];
  const updates = Array.isArray(value.updates) ? value.updates : [];
  const finalVerification = Object.fromEntries(Object.entries(definedObject(value.finalVerification))
    .map(([game, verification]) => [game, {
      banner: bannerReceipt(verification),
      analysis: { modes: analysesReceipt(verification?.analyses, game) },
    }]));
  const boxProtection = Object.fromEntries(Object.entries(definedObject(value.boxProtection))
    .map(([game, protection]) => [game, boxProtectionReceipt(protection)]));
  return {
    skipped: false,
    updates: updates.map((update, index) => updateReceipt(
      update,
      update?.game ?? updateGames[index] ?? "",
    )),
    finalVerification,
    boxProtection,
  };
}

export function compactProductUiProbeReceipt(rawReceipt) {
  const raw = definedObject(rawReceipt);
  return {
    schema_version: SCHEMA_VERSION,
    sequence: (Array.isArray(raw.sequence) ? raw.sequence : [])
      .map((entry, index) => sequenceEntryReceipt(entry, index)),
    outerCompactLayout: layoutReceipt(raw.outerCompactLayout),
    publicDataUpdates: publicDataUpdatesReceipt(raw.publicDataUpdates),
    boxFlush: (Array.isArray(raw.boxFlush) ? raw.boxFlush : []).map((entry) => ({
      game: entry?.game ?? "",
      ok: entry?.ok === true,
    })),
  };
}

function asciiJson(value) {
  return JSON.stringify(value).replace(/[\u007f-\uffff]/g, (character) => (
    `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`
  ));
}

export function serializeProductUiProbeReceipt(rawReceipt) {
  const serialized = asciiJson(compactProductUiProbeReceipt(rawReceipt));
  const byteLength = Buffer.byteLength(serialized, "ascii") + 1;
  if (byteLength > MAX_RECEIPT_BYTES) {
    throw new Error(`compact product UI probe receipt exceeds ${MAX_RECEIPT_BYTES} bytes: ${byteLength}`);
  }
  return serialized;
}

export const PRODUCT_UI_PROBE_RECEIPT_SCHEMA_VERSION = SCHEMA_VERSION;
export const PRODUCT_UI_PROBE_RECEIPT_MAX_BYTES = MAX_RECEIPT_BYTES;
