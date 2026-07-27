import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import {
  compactProductUiProbeReceipt,
  PRODUCT_UI_PROBE_RECEIPT_MAX_BYTES,
  PRODUCT_UI_PROBE_RECEIPT_SCHEMA_VERSION,
  serializeProductUiProbeReceipt,
} from "../scripts/product_ui_probe_receipt_v1.mjs";

function fixtureReceipt() {
  const hugeDomSnapshot = "UNBOUNDED-DOM-SNAPSHOT".repeat(150_000);
  const analysis = (mode, phaseVersion, sampleDate) => ({
    analysisMode: mode,
    analysisExpectedPhase: {
      sampleDate,
      phaseVer: phaseVersion,
      phaseName: "终局主题",
      mechanicName: "终局机制",
      startDate: "2026-07-01",
      endDate: "2026-07-31",
      status: "current",
    },
    characterCardNames: Array.from({ length: 2_000 }, () => hugeDomSnapshot),
  });
  return {
    schema_version: PRODUCT_UI_PROBE_RECEIPT_SCHEMA_VERSION,
    outerCompactLayout: {
      innerWidth: 860,
      documentScrollWidth: 860,
      panel: { left: 24, right: 836, width: 812 },
      items: [
        { left: 24, right: 422, width: 398, sample: "终局最新采样 2026-06-25" },
        { left: 438, right: 836, width: 398, sample: "终局最新采样 2026-07-19" },
      ],
    },
    sequence: [{
      game: "zzz",
      outer: {
        frameGame: "zzz",
        framePage: "box",
        frameDataRevision: "a".repeat(64),
        frameProbeId: "persistent-zzz-0",
        frameProbeLoadCount: 1,
        bodyText: hugeDomSnapshot,
      },
      product: {
        statePage: "box",
        ownedStateCount: 27,
        rosterCount: 42,
        latestEndgameSampleDate: "2026-07-19",
        tierUpdatedAt: "19/July/2026",
        visibleText: hugeDomSnapshot,
      },
      boxRoster: { orderingVerified: true, leadingCards: hugeDomSnapshot },
      boxBatchPreview: { stateUnchanged: true, prompt: hugeDomSnapshot },
      persistenceBefore: {
        boxSha256: "b".repeat(64),
        localStorageSha256: "c".repeat(64),
        ownedCount: 27,
        localStorageKeys: Array.from({ length: 10_000 }, () => hugeDomSnapshot),
      },
      analyses: [analysis("sd", "7", "2026-07-19"), analysis("da", "8", "2026-07-19")],
      banner: {
        bannerRefreshStatus: "fresh",
        bannerRefreshFetchedAt: "2026-07-27T00:00:00Z",
        bannerRefreshSourceLabel: "官方卡池",
        bannerCurrentRowCount: 2,
        bannerCardNames: ["爱丽丝", "仪玄"],
        visibleText: hugeDomSnapshot,
      },
      recommender: { renderedDom: hugeDomSnapshot },
    }],
    publicDataUpdates: {
      updates: [{
        game: "zzz",
        status: "succeeded",
        revisionBefore: "d".repeat(64),
        revisionAfter: "e".repeat(64),
        terminalRevision: "e".repeat(64),
        frameLoadCountBefore: 1,
        frameLoadCountAfter: 2,
        pageBefore: "banner",
        pageAfter: "banner",
        bannerRefresh: {
          status: "fresh",
          fetchedAt: "2026-07-27T00:00:00Z",
          sourceLabel: "官方卡池",
        },
        bannerCurrentNames: ["爱丽丝", "仪玄"],
        analyses: [
          { sampleDate: "2026-07-19", phaseVer: "7", phaseName: "终局主题", mechanicName: "终局机制", startDate: "2026-07-01", endDate: "2026-07-31", status: "current" },
          { sampleDate: "2026-07-19", phaseVer: "8", phaseName: "终局主题", mechanicName: "终局机制", startDate: "2026-07-01", endDate: "2026-07-31", status: "current" },
        ],
        updateHealth: {
          state: "healthy",
          attemptId: "attempt-1",
          completedAtUtc: "2026-07-27T00:01:00Z",
          latestSampleDate: "2026-07-19",
          modes: { sd: { status: "current", sampleDate: "2026-07-19" } },
          otherGameAttemptId: "attempt-0",
          otherGameLatestSampleDate: "2026-06-25",
          outer: hugeDomSnapshot,
        },
      }],
      finalVerification: {
        zzz: {
          bannerRefresh: { status: "fresh", fetchedAt: "2026-07-27T00:00:00Z", sourceLabel: "官方卡池" },
          bannerCurrentNames: ["爱丽丝", "仪玄"],
          analyses: [
            { sampleDate: "2026-07-19", phaseVer: "7", phaseName: "终局主题", mechanicName: "终局机制", startDate: "2026-07-01", endDate: "2026-07-31", status: "current" },
            { sampleDate: "2026-07-19", phaseVer: "8", phaseName: "终局主题", mechanicName: "终局机制", startDate: "2026-07-01", endDate: "2026-07-31", status: "current" },
          ],
        },
      },
      boxProtection: {
        zzz: {
          liveSha256: "f".repeat(64),
          diskSha256: "0".repeat(64),
          owned: 27,
          liveUnchanged: true,
          diskUnchanged: true,
          live: hugeDomSnapshot,
          disk: hugeDomSnapshot,
        },
      },
    },
    boxFlush: [{ game: "hsr", ok: true }, { game: "zzz", ok: true }],
  };
}

test("product UI probe compacts full assertion snapshots into necessary evidence", () => {
  const raw = fixtureReceipt();
  const receipt = compactProductUiProbeReceipt(raw);
  const serialized = serializeProductUiProbeReceipt(raw);

  assert.equal(receipt.schema_version, PRODUCT_UI_PROBE_RECEIPT_SCHEMA_VERSION);
  assert.equal(receipt.outerCompactLayout.viewportWidth, 860);
  assert.equal(receipt.sequence[0].revision, "a".repeat(64));
  assert.equal(receipt.sequence[0].analysis.modes.sd.sampleDate, "2026-07-19");
  assert.equal(receipt.sequence[0].analysis.modes.da.theme, "终局主题");
  assert.equal(receipt.sequence[0].analysis.modes.da.mechanic, "终局机制");
  assert.deepEqual(receipt.sequence[0].banner.currentNames, ["爱丽丝", "仪玄"]);

  const gapRaw = fixtureReceipt();
  Object.assign(gapRaw.sequence[0].banner, {
    bannerPhase: "next",
    bannerCurrentRowCount: 0,
    bannerDataCurrentNames: [],
    bannerCardNames: ["蕾米埃尔·丹"],
  });
  const gapBanner = compactProductUiProbeReceipt(gapRaw).sequence[0].banner;
  assert.equal(gapBanner.selectedPhase, "next");
  assert.equal(gapBanner.currentCount, 0);
  assert.deepEqual(gapBanner.currentNames, []);
  assert.deepEqual(gapBanner.visibleNames, ["蕾米埃尔·丹"]);

  assert.equal(receipt.publicDataUpdates.updates[0].revision.after, "e".repeat(64));
  assert.equal(receipt.publicDataUpdates.updates[0].game, "zzz");
  assert.equal(receipt.publicDataUpdates.boxProtection.zzz.diskUnchanged, true);
  assert.equal(receipt.boxFlush.length, 2);
  assert.ok(Buffer.byteLength(serialized, "ascii") + 1 < PRODUCT_UI_PROBE_RECEIPT_MAX_BYTES);
  assert.doesNotMatch(serialized, /UNBOUNDED-DOM-SNAPSHOT/u);
  assert.doesNotMatch(serialized, /[^\x00-\x7e]/u);
  assert.deepEqual(JSON.parse(serialized), receipt);
});

test("ASCII receipt survives Windows PowerShell 5.1 ConvertFrom-Json", {
  skip: process.platform !== "win32",
}, () => {
  const serialized = serializeProductUiProbeReceipt(fixtureReceipt());
  const command = [
    "$receipt = [Console]::In.ReadToEnd() | ConvertFrom-Json -ErrorAction Stop",
    "$theme = [string]$receipt.sequence[0].analysis.modes.sd.theme",
    "if ($receipt.schema_version -cne 'miho-product-ui-probe-v1' -or $theme.Length -ne 4 -or [int][char]$theme[0] -ne 32456) { exit 41 }",
    "[Console]::Out.Write(([string]$PSVersionTable.PSVersion.Major + '|PASS'))",
  ].join("; ");
  const result = spawnSync("powershell.exe", [
    "-NoLogo",
    "-NoProfile",
    "-NonInteractive",
    "-ExecutionPolicy", "Bypass",
    "-Command", command,
  ], {
    input: serialized,
    encoding: "utf8",
    windowsHide: true,
  });
  assert.equal(result.status, 0, result.stderr || result.stdout);
  assert.equal(result.stdout, "5|PASS");
});
