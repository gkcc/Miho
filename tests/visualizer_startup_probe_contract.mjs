import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
  VISUALIZER_STARTUP_FAILURE_CODES,
  VisualizerStartupFailureError,
  throwIfVisualizerStartupFailed,
  visualizerStartupFailure,
  visualizerStartupStageReady,
  waitForVisualizerStartupStage,
} from '../scripts/visualizer_startup_probe_v1.mjs';

const productProbeSource = readFileSync(
  new URL('../scripts/probe_product_ui_v1.mjs', import.meta.url),
  'utf8',
);

function snapshot(game, state = 'ready', code = '') {
  return {
    visualizerStartupState: state,
    visualizerStartupFailureCode: code,
    visualizerStartupGame: game,
  };
}

function deterministicClock() {
  let milliseconds = 0;
  let sleeps = 0;
  return {
    now: () => milliseconds,
    sleep: async (duration) => {
      sleeps += 1;
      milliseconds += duration;
    },
    sleeps: () => sleeps,
  };
}

test('only fixed startup codes become terminal code/game failures', () => {
  for (const code of VISUALIZER_STARTUP_FAILURE_CODES) {
    for (const game of ['zzz', 'hsr']) {
      const value = snapshot(game, 'failed', code);
      assert.deepEqual(visualizerStartupFailure(value), { code, game });
      assert.throws(
        () => throwIfVisualizerStartupFailed(value),
        (error) => error instanceof VisualizerStartupFailureError
          && error.message === `visualizer_startup_failed code=${code} game=${game}`,
      );
    }
  }

  assert.equal(visualizerStartupFailure(snapshot('zzz', 'failed', 'future_failure')), null);
  assert.equal(visualizerStartupFailure(snapshot('other', 'failed', 'ready_timeout'))?.game, 'unknown');
});

test('stage readiness is bound to the expected game and an empty failure code', () => {
  assert.equal(visualizerStartupStageReady(snapshot('zzz'), 'zzz'), true);
  assert.equal(visualizerStartupStageReady(snapshot('hsr'), 'zzz'), false);
  assert.equal(visualizerStartupStageReady(snapshot('zzz', 'pending'), 'zzz'), false);
  assert.equal(visualizerStartupStageReady(snapshot('zzz', 'ready', 'future_failure'), 'zzz'), false);
});

test('stage polling waits through pending state but never swallows a fixed failure', async () => {
  const successClock = deterministicClock();
  const queue = [snapshot('zzz', 'pending'), snapshot('zzz')];
  const ready = await waitForVisualizerStartupStage({
    description: 'synthetic ZZZ stage',
    game: 'zzz',
    timeoutMs: 45_000,
    intervalMs: 100,
    now: successClock.now,
    sleep: successClock.sleep,
    probe: async () => queue.shift(),
  });
  assert.equal(ready.visualizerStartupState, 'ready');
  assert.equal(successClock.sleeps(), 1);

  for (const [index, game] of ['zzz', 'hsr', 'zzz'].entries()) {
    const failureClock = deterministicClock();
    const code = VISUALIZER_STARTUP_FAILURE_CODES[index];
    await assert.rejects(
      waitForVisualizerStartupStage({
        description: `synthetic stage ${index}`,
        game,
        timeoutMs: 45_000,
        intervalMs: 100,
        now: failureClock.now,
        sleep: failureClock.sleep,
        probe: async () => snapshot(game, 'failed', code),
      }),
      (error) => error instanceof VisualizerStartupFailureError
        && error.message === `visualizer_startup_failed code=${code} game=${game}`,
    );
    assert.equal(failureClock.sleeps(), 0, `stage ${index} did not fail immediately`);
  }
});

test('the product probe gates the real ZZZ to HSR to ZZZ sequence and emits exact stderr', () => {
  const stageGames = [...productProbeSource.matchAll(
    /waitForDesktopVisualizerStage\(top\.id, "(zzz|hsr)"/gu,
  )].map((match) => match[1]);
  assert.deepEqual(stageGames, ['zzz', 'hsr', 'zzz']);
  assert.match(productProbeSource, /if \(isVisualizerStartupFailureError\(error\)\) \{/u);
  assert.match(productProbeSource, /process\.stderr\.write\(`\$\{error\.message\}\\n`\)/u);
  assert.match(productProbeSource, /updateHealthState: "healthy"|snapshot\?\.updateHealthState === "healthy"/u);
  assert.match(productProbeSource, /updateHealthSummary\.includes\("本机产物校验通过"\)/u);
  assert.match(productProbeSource, /updateHealthDetail\.includes\("终局采样取决于上游发布"\)/u);
  assert.match(productProbeSource, /历史样本不等于本机刷新失败/u);
  assert.match(productProbeSource, /miho-desktop-update-health-v2/u);
  assert.match(productProbeSource, /终局最新采样\\s\+\\d\{4\}-\\d\{2\}-\\d\{2\}/u);
  assert.match(productProbeSource, /value\.includes\("HSR 最近成功"\)/u);
  assert.match(productProbeSource, /value\.includes\("ZZZ 最近成功"\)/u);
  assert.match(productProbeSource, /updateHealthSampleCards = updateHealthGameItems\.map/u);
  assert.match(productProbeSource, /\.update-health-game-summary \.update-health-sample/u);
  assert.match(productProbeSource, /visible: visible\(sample\)/u);
  assert.match(productProbeSource, /stale: item\.classList\.contains\('has-stale-sample'\)/u);
  assert.match(productProbeSource, /sampleAgeDays\(match\[1\], localDateKey\(\)\)/u);
  assert.match(productProbeSource, /card\.sample\.includes\(`已 \$\{age\} 天未更新`\) && card\.stale/u);
  assert.match(productProbeSource, /snapshot\.updateHealthState === "warning"/u);
  assert.match(productProbeSource, /internals\.invoke\('get_update_health'\)/u);
  assert.match(productProbeSource, /afterTarget\.attempt_id === beforeTarget\.attempt_id/u);
  assert.match(productProbeSource, /afterOther\.attempt_id === beforeOther\.attempt_id/u);
  assert.match(productProbeSource, /afterOther\.completed_at_utc === beforeOther\.completed_at_utc/u);
  assert.match(productProbeSource, /updateHealthGameCompletedAtUtc: updateHealthGameItems\.map/u);
  assert.match(productProbeSource, /item\.dataset\.completedAtUtc/u);
  assert.match(productProbeSource, /const label = game === "hsr" \? "HSR 最近成功" : "ZZZ 最近成功"/u);
  assert.match(productProbeSource, /updateHealthGames\?\.findIndex\(\(value\) => value\.includes\(label\)\)/u);
  assert.match(productProbeSource, /updateHealthGameCompletedAtUtc\?\.\[index\]/u);
  assert.match(productProbeSource, /visibleTargetCompletedAt\.includes\(afterTarget\.completed_at_utc\)/u);
  assert.match(productProbeSource, /visibleOtherCompletedAt\.includes\(afterOther\.completed_at_utc\)/u);
  assert.match(productProbeSource, /updateHealthLatestSampleDate\(health, game\)/u);
  assert.match(productProbeSource, /\^\\d\{4\}-\\d\{2\}-\\d\{2\}\$\/u\.test\(targetSampleDate\)/u);
  assert.match(productProbeSource, /value\.includes\(`终局最新采样 \$\{targetSampleDate\}`\)/u);
  assert.match(productProbeSource, /targetSampleDate === visualizerLatestSampleDate/u);
  assert.match(productProbeSource, /analysisExpectedPhase\?\.sampleDate/u);
  assert.match(productProbeSource, /task\.text\.includes\("本机更新与校验成功"\)/u);
  assert.match(productProbeSource, /task\.text\.includes\("查看本次更新结果"\)/u);
  assert.match(productProbeSource, /终局分析保留上游最新可用的历史样本/u);
  assert.match(productProbeSource, /else if \(hasQualityWarning\)/u);
  assert.match(productProbeSource, /Box、卡池和终局分析已刷新/u);
  assert.match(productProbeSource, /latestSampleDate: targetSampleDate/u);
  assert.match(productProbeSource, /otherGameLatestSampleDate: otherSampleDate/u);
  assert.match(productProbeSource, /modes: Object\.fromEntries/u);
  assert.match(productProbeSource, /Emulation\.setDeviceMetricsOverride/u);
  assert.match(productProbeSource, /width: 860/u);
  assert.match(productProbeSource, /documentScrollWidth <= snapshot\.innerWidth/u);
  assert.match(productProbeSource, /update-health cards overflow or hide sample dates at the supported minimum width/u);
  assert.match(productProbeSource, /Emulation\.clearDeviceMetricsOverride/u);
  assert.match(productProbeSource, /authoritative and visible update health after public-data update/u);
});
