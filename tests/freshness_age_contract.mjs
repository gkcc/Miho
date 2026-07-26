import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";
import {
  ENDGAME_SAMPLE_STALE_AFTER_DAYS,
  localDateKey,
  nextLocalDateBoundary,
  sampleAgeDays,
  sampleAgeSuffix,
  staleSampleAgeDays,
} from "../crates/miho-desktop/src/freshness-age.js";

test("sample age uses strict calendar days instead of elapsed 24-hour periods", () => {
  assert.equal(sampleAgeDays("2026-06-25", "2026-07-27"), 32);
  assert.equal(sampleAgeDays("2026-07-19", "2026-07-27"), 8);
  assert.equal(staleSampleAgeDays("2026-07-19", "2026-07-27"), null);
  assert.equal(sampleAgeSuffix("2026-07-19", "2026-07-27"), "（8 天前）");
  assert(!sampleAgeSuffix("2026-07-19", "2026-07-27").includes("未更新"));
  assert.equal(sampleAgeDays("2026-03-07", "2026-03-09"), 2);
  assert.equal(sampleAgeDays("2024-02-28", "2024-03-01"), 2);
  assert.equal(sampleAgeDays("2023-02-28", "2023-03-01"), 1);
  assert.equal(sampleAgeDays("2026-07-28", "2026-07-27"), -1);
});

test("sample age rejects impossible or non-canonical dates", () => {
  for (const value of ["", "2026-2-03", "0000-01-01", "2026-02-29", "2026-04-31", "not-a-date"]) {
    assert.equal(sampleAgeDays(value, "2026-07-27"), null, value);
  }
  assert.equal(sampleAgeDays("2026-07-19", "2026-02-29"), null);
});

test("stale disclosure starts at fifteen days and preserves exact age", () => {
  assert.equal(ENDGAME_SAMPLE_STALE_AFTER_DAYS, 15);
  assert.equal(staleSampleAgeDays("2026-07-13", "2026-07-27"), null);
  assert.equal(sampleAgeSuffix("2026-07-27", "2026-07-27"), "（今天采样）");
  assert.equal(sampleAgeSuffix("2026-07-26", "2026-07-27"), "（1 天前）");
  assert.equal(sampleAgeSuffix("2026-07-13", "2026-07-27"), "（14 天前）");
  assert.equal(staleSampleAgeDays("2026-07-12", "2026-07-27"), 15);
  assert.equal(sampleAgeSuffix("2026-07-12", "2026-07-27"), "（已 15 天未更新）");
  assert.equal(sampleAgeSuffix("2026-06-25", "2026-07-27"), "（已 32 天未更新）");
  assert.equal(sampleAgeSuffix("2026-07-28", "2026-07-27"), "（样本日期在 1 天后）");
  assert.equal(sampleAgeSuffix("not-a-date", "2026-07-27"), "");
});

test("local date formatting and the next boundary follow the local calendar", () => {
  const now = new Date(2026, 6, 27, 23, 59, 58, 500);
  assert.equal(localDateKey(now), "2026-07-27");
  const boundary = nextLocalDateBoundary(now);
  assert.notEqual(boundary, null);
  const next = new Date(boundary);
  assert.equal(localDateKey(next), "2026-07-28");
  assert.deepEqual(
    [next.getHours(), next.getMinutes(), next.getSeconds(), next.getMilliseconds()],
    [0, 0, 0, 0],
  );
  assert(boundary > now.getTime() && boundary - now.getTime() <= 26 * 60 * 60 * 1_000);
  assert.equal(localDateKey(new Date(Number.NaN)), "");
  assert.equal(nextLocalDateBoundary(new Date(Number.NaN)), null);
});

function timezoneSnapshot(timezone, source) {
  const moduleUrl = new URL("../crates/miho-desktop/src/freshness-age.js", import.meta.url).href;
  const result = spawnSync(process.execPath, [
    "--input-type=module",
    "--eval",
    `import { localDateKey, nextLocalDateBoundary, sampleAgeDays } from ${JSON.stringify(moduleUrl)};${source}`,
  ], {
    encoding: "utf8",
    env: { ...process.env, TZ: timezone },
  });
  assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}

test("local date and midnight scheduling remain correct across timezone and DST boundaries", () => {
  const shanghai = timezoneSnapshot("Asia/Shanghai", `
    const now = new Date("2026-07-26T16:30:00.000Z");
    process.stdout.write(JSON.stringify({ today: localDateKey(now), age: sampleAgeDays("2026-06-25", localDateKey(now)) }));
  `);
  assert.deepEqual(shanghai, { today: "2026-07-27", age: 32 });

  const newYork = timezoneSnapshot("America/New_York", `
    const spring = new Date(2026, 2, 8, 0, 0, 0, 0);
    const fall = new Date(2026, 10, 1, 0, 0, 0, 0);
    process.stdout.write(JSON.stringify({
      springHours: (nextLocalDateBoundary(spring) - spring.getTime()) / 3600000,
      fallHours: (nextLocalDateBoundary(fall) - fall.getTime()) / 3600000,
    }));
  `);
  assert.deepEqual(newYork, { springHours: 23, fallHours: 25 });
});
