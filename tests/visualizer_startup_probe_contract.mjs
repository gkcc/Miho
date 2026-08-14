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

function extractNamedFunction(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `${name} is absent`);
  const bodyStart = source.indexOf('{', start);
  let depth = 0;
  for (let index = bodyStart; index < source.length; index += 1) {
    if (source[index] === '{') depth += 1;
    if (source[index] === '}') depth -= 1;
    if (depth === 0) {
      const declaration = source.slice(start, index + 1);
      return Function(`"use strict"; return (${declaration});`)();
    }
  }
  throw new Error(`${name} is incomplete`);
}

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
  assert.match(productProbeSource, /const staleSampleDates = freshnessModes/u);
  assert.match(productProbeSource, /age !== null && age >= ENDGAME_SAMPLE_STALE_AFTER_DAYS/u);
  assert.match(productProbeSource, /hasStaleSamples[\s\S]*task\.text\.includes\("联网与本机校验成功"\)/u);
  assert.match(productProbeSource, /task\.text\.includes\("本机更新与校验成功"\)/u);
  assert.match(productProbeSource, /task\.text\.includes\("查看本次更新结果"\)/u);
  assert.match(productProbeSource, /task\.text\.includes\(`最早停在 \$\{oldestStaleSampleDate\}`\)/u);
  assert.match(productProbeSource, /task\.text\.includes\(`已 \$\{oldestStaleSampleAge\} 天未更新`\)/u);
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
  assert.match(productProbeSource, /verifyExpectedNextBanner\(\s*context,\s*game,\s*restorePhase,\s*preservedBannerSnapshot\.bannerNextRowCount/su);
  assert.match(productProbeSource, /function primaryBannerPhase\(snapshot, game\)/u);
  assert.match(productProbeSource, /snapshot\.bannerCurrentRowCount === 0[\s\S]*snapshot\.bannerNextRowCount > 0/u);
  assert.match(productProbeSource, /has neither a current banner nor a structurally verified next-banner gap/u);
  assert.match(productProbeSource, /requireCurrent: restorePhase === "current"/u);
  assert.match(productProbeSource, /bannerCurrentNames: bannerSnapshot\.bannerDataCurrentNames/u);
  assert.match(productProbeSource, /bannerSelectedPhase: bannerSnapshot\.bannerPhase/u);
  assert.match(productProbeSource, /async function verifyBannerForProbeState\(context, snapshot, game, updating\)/u);
  assert.match(productProbeSource, /requireFresh: false,[\s\S]*requireData: false/u);
  assert.match(productProbeSource, /requireCurrent: selectedPhase === "current"/u);
  assert.match(productProbeSource, /if \(snapshot\.bannerPhase !== selectedPhase\)[\s\S]*button\.click\(\)/u);
  assert.match(productProbeSource, /value\?\.bannerPhase === selectedPhase/u);
  assert.match(productProbeSource, /if \(requireCurrent\) \{/u);
  assert.match(productProbeSource, /requireExpected && expectedNextBannerCount/u);
  assert.match(productProbeSource, /\.map\(\(name\) => name\.trim\(\)\)/u);
  assert.match(productProbeSource, /#bannerPhaseControl button/u);
  assert.match(productProbeSource, /candidate\.dataset\.value === 'next'/u);
  assert.match(productProbeSource, /snapshot\.bannerCardCount === snapshot\.bannerNextRowCount/u);
  assert.match(productProbeSource, /snapshot\.bannerCardNames.*snapshot\.bannerDataNextNames/su);
  assert.match(productProbeSource, /next banner images are broken or mismatched/u);
  assert.match(productProbeSource, /next banner dates are not visibly rendered/u);
});

test('the product probe verifies visible ZZZ recommendations and per-team weakness isolation', () => {
  assert.match(productProbeSource, /const primarySlate = \(\) => \[\.\.\.document\.querySelectorAll\('#recSlateList \.rec-solution'\)\]\.find\(visible\) \?\? null/u);
  assert.match(productProbeSource, /const primarySlateCards = \(\) => \[\.\.\.\(primarySlate\(\)\?\.querySelectorAll\('\.rec-slate-card'\) \?\? \[\]\)\]\.filter\(visible\)/u);
  assert.match(productProbeSource, /const visibleCandidateCards = \(\) => \[\.\.\.document\.querySelectorAll\('#recList \.rec-card'\)\]\.filter\(visible\)/u);
  assert.match(productProbeSource, /weaknessScopeSelect\.value = 'custom-2'/u);
  assert.match(productProbeSource, /result\.weaknessSlotTwoBefore\.active\.length === 0/u);
  assert.match(productProbeSource, /result\.weaknessSlotTwoBefore\.pressed\.length === 0/u);
  assert.match(productProbeSource, /result\.weaknessSlotTwoBefore\.stored\.length === 0/u);
  assert.match(productProbeSource, /result\.weaknessSlotTwo\.expected !== result\.weaknessSlotOne\.expected/u);
  assert.match(productProbeSource, /JSON\.stringify\(result\.returnedWeaknessSlotOne\.active\) === JSON\.stringify\(\[result\.weaknessSlotOne\.expected\]\)/u);
  assert.match(productProbeSource, /ZZZ custom weaknesses leaked between target teams/u);
  assert.match(productProbeSource, /ZZZ compact recommendation cards/u);
  assert.match(productProbeSource, /document\.querySelector\('#recTooltip'\)/u);
  assert.match(productProbeSource, /hasDataRange:text\.includes\('数据范围'\)/u);
  assert.match(productProbeSource, /hasEvidence:text\.includes\('阵容证据'\)/u);
  assert.match(productProbeSource, /hasBangboo:text\.includes\('邦布证据'\)/u);
  assert.match(productProbeSource, /ZZZ recommendation tooltip omits auditable evidence fields/u);
});

test('the product probe verifies cross-game recommendation parity through real controls', () => {
  assert.match(productProbeSource, /not enough visible HSR weakness controls to probe team isolation/u);
  assert.match(productProbeSource, /HSR custom weaknesses leaked between target teams/u);
  assert.match(productProbeSource, /result\.threeTeams\.slateCount === 3/u);
  assert.match(productProbeSource, /result\.constraints\.slotOne\.scopeHint\.includes\("队伍"\)/u);
  assert.match(productProbeSource, /result\.constraints\.slotOne\.clearText === "清空本队"/u);
  assert.match(productProbeSource, /ZZZ recommendation sort choices are incomplete/u);
  assert.match(productProbeSource, /ZZZ \$\{mode\} sort is not wired through cards, persistence, and the joint slate/u);
  assert.match(productProbeSource, /hasOriginalBox: text\.includes\('原模板 Box'\) && text\.includes\('原实证模板准入'\)/u);
  assert.match(productProbeSource, /HSR recommendation tooltip lacks keyboard focus on the joint path/u);
  assert.match(productProbeSource, /HSR recommendation tooltip omits auditable evidence fields/u);
});

test('the product probe rejects partial or ambiguous phase metadata identities', () => {
  const selectUniquePhaseMetadata = extractNamedFunction(productProbeSource, 'selectUniquePhaseMetadata');
  const sample = {
    mode: 'sd',
    collect_date: '2026-07-19',
    phase_ver: '3.0.2',
    snapshot_id: 'snapshot-current',
    phase_name: 'Usage identity',
    start_date: '2026-07-10',
    end_date: '2026-07-24',
  };
  const exact = {...sample, id: 'exact'};

  assert.equal(selectUniquePhaseMetadata([
    {...exact, phase_name: 'Wrong identity', id: 'wrong-name'},
    exact,
  ], sample)?.id, 'exact');
  assert.equal(selectUniquePhaseMetadata([
    {...exact, start_date: '2026-07-09', id: 'wrong-start'},
  ], sample), null);
  assert.equal(selectUniquePhaseMetadata([
    {...exact, id: 'duplicate-a'},
    {...exact, id: 'duplicate-b'},
  ], sample), null);
  assert.equal(selectUniquePhaseMetadata([exact], {
    mode: sample.mode,
    collect_date: sample.collect_date,
    phase_ver: sample.phase_ver,
    phase_name: sample.phase_name,
  })?.id, 'exact', 'identity fields omitted by usage must remain optional');
  assert.match(productProbeSource, /selectUniquePhaseMetadata\(phaseRows, latestAnalysisRow\)/u);
});

test('the product probe fails closed on missing ZZZ phase presentation', () => {
  const complete = extractNamedFunction(productProbeSource, 'completeZzzPhasePresentation');
  assert.equal(complete({phaseName: '官方期名', mechanicName: '官方机制'}), true);
  assert.equal(complete({phaseName: '', mechanicName: '官方机制'}), false);
  assert.equal(complete({phaseName: '期名未提供', mechanicName: '官方机制'}), false);
  assert.equal(complete({phaseName: '官方期名', mechanicName: ''}), false);
  assert.equal(complete({phaseName: '官方期名', mechanicName: '机制未提供'}), false);
  assert.match(productProbeSource, /assert\(completeZzzPhasePresentation\(phase\)/u);
});
