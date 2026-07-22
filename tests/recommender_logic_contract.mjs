import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const HSR_APP = path.join(ROOT, 'crates/miho-core/assets/visualizer/hsr/app.js');
const ZZZ_APP = path.join(ROOT, 'crates/miho-core/assets/visualizer/zzz/app.js');
const ZZZ_INDEX = path.join(ROOT, 'crates/miho-core/assets/visualizer/zzz/index.html');
const SLATE_SOLVER = path.join(ROOT, 'crates/miho-core/assets/visualizer/solver.js');

const HSR_HARNESS = String.raw`
;globalThis.__recommenderContract = {
  reset(data, settings = {}, owned = [], builds = {}) {
    DATA = data;
    rec = {
      mode: settings.mode || 'as',
      scope: settings.scope || '4-1',
      strategy: settings.strategy || 'final',
      sortMode: normalizeRecSortMode(settings.sortMode),
      teamCounts: settings.teamCounts || {...DEFAULT_REC_TEAM_COUNTS},
      targetScopes: settings.targetScopes || {},
      elements: settings.elements || {},
      constraints: settings.constraints || {},
      locks: settings.locks || {},
      gap: settings.gap || '4',
      riskMode: settings.riskMode || 'warn',
      limit: settings.limit || '20',
      search: settings.search || '',
    };
    box = {...box, owned: new Set(owned), builds, buildSlug: ''};
    boxUndoStack = [];
  },
  setElements(mode, scope, values) {
    rec.elements[recSettingKey(mode, scope)] = [...values];
  },
  constraints(mode, scope) {
    const sets = recConstraintSets(mode, scope);
    return {required: [...sets.required], excluded: [...sets.excluded]};
  },
  ranked(mode, scope, used = [], options = {}) {
    return rankedRecommendations(mode, scope, new Set(used), options).map(item => ({
      id: item.template.id,
      chars: [...item.template.chars],
      finalChars: [...item.finalChars],
      score: item.score,
      scoreMode: item.scoreMode,
      scores: {...item.scores},
      scoreParts: Object.fromEntries(Object.entries(item.scoreParts).map(([mode, parts]) => [mode, parts.map(part => ({...part}))])),
      performance: {...item.performance},
      elementHits: item.elementHits,
      coreElementHits: item.coreElementHits,
      weaknessMatched: item.weaknessMatched,
      targetScope: item.targetScope,
      ownedCount: item.ownedCount,
      buildRecordedCount: item.buildRecordedCount,
      buildReadyCount: item.buildReadyCount,
      risks: item.risks.map(risk => risk.type || risk.text),
      substitutions: item.substitutions.map(entry => ({
        missing: entry.missing.slug,
        candidates: entry.candidates.map(candidate => candidate.character_slug),
      })),
    }));
  },
  pool(mode) {
    return customPoolTemplates(mode).map(template => ({id: template.id, scope: template.scope_key, evidenceScopes: [...template.evidenceScopes]}));
  },
  scopes() {
    return recScopeOptions(rec.mode).map(scope => scope.key);
  },
  planScopes() {
    return recPlanScopes().map(scope => scope.key);
  },
  plan() {
    const scopes = recPlanScopes();
    return bestRecSlatePlan(scopes).map(item => item?.template.id || null);
  },
  planSnapshot() {
    const scopes = recPlanScopes();
    return bestRecSlatePlan(scopes).map(item => item ? {id: item.template.id, score: item.score, scoreMode: item.scoreMode, scores: {...item.scores}} : null);
  },
  slates() {
    const result = solveRecSlates(recPlanScopes(), {maxSolutions: 3});
    return {
      solver_meta: {...result.solver_meta},
      plans: result.plans.map(plan => ({
        totalScore: plan.totalScore,
        picks: plan.picks.map(item => item ? {
          id: item.template.id,
          variantKey: item.variantKey,
          score: item.score,
          scores: {...item.scores},
          finalChars: [...item.finalChars],
          finalMissingCount: item.finalMissingCount,
          finalBuildRecordedCount: item.finalBuildRecordedCount,
          finalBuildReadyCount: item.finalBuildReadyCount,
          evidenceConfidence: item.evidenceConfidence,
          substitutions: item.substitutionAssignments.map(row => ({missing: row.missing, replacement: row.replacement})),
        } : null),
      })),
    };
  },
  lockCandidate(scopeKey, templateId) {
    const scopes = recPlanScopes();
    const scopeIndex = scopes.findIndex(scope => scope.key === scopeKey);
    const candidate = scopeIndex < 0 ? null : recSlateCandidateLists(scopes)[scopeIndex].find(item => item.template.id === templateId);
    if (!candidate) return null;
    rec.locks[recLockKey(scopeKey)] = candidate.variantKey;
    return candidate.variantKey;
  },
  locks() {
    return {...normalizeRecLocks(rec.locks)};
  },
  setConstraints(mode, scope, required = [], excluded = []) {
    rec.constraints[recSettingKey(mode, scope)] = {required: [...required], excluded: [...excluded]};
  },
  migrateSettings(raw) {
    localStorage.setItem(REC_KEY, JSON.stringify(raw));
    loadRecSettings();
    return {sortMode: rec.sortMode};
  },
  rankFacts(value) {
    return {sortValue: rankSortValue(value), display: rankDisplayText(value)};
  },
  analysis(rows, mode, metric = 'avg_round') {
    state = {...state, mode, metric};
    const policy = analysisMetricPolicy(mode, metric);
    return {
      policy: {label: policy.label, higherBetter: policy.higherBetter, sortable: policy.sortable},
      values: rows.map(row => analysisMetricValue(row, mode, metric)),
      order: groupSeries(rows).map(series => series.slug),
    };
  },
  deploymentGroups(slugs) {
    return slugs.map(deploymentGroup);
  },
  boxPreview(raw) {
    return boxImportPreview(raw);
  },
  boxImportError(raw) {
    try { parseBoxImportDocument(raw); return ''; } catch (error) { return error.message; }
  },
  boxHistoryProbe(count) {
    boxUndoStack = [];
    for (let index = 0; index < count; index += 1) {
      box.owned = new Set(['unit-' + index]);
      box.builds = {};
      box.buildSlug = '';
      rememberBoxUndo();
    }
    return {length: boxUndoStack.length, first: boxUndoStack[0]?.owned[0], last: boxUndoStack.at(-1)?.owned[0]};
  },
  freshness(mode, fallback = {}) {
    return modeFreshness(mode, fallback);
  },
};
`;

const ZZZ_HARNESS = String.raw`
;globalThis.__recommenderContract = {
  reset(data, settings = {}, owned = [], builds = {}) {
    DATA = normalizeVisualizerData(data);
    rec = {
      mode: settings.mode || 'sd',
      scope: settings.scope || 's1',
      targetScopes: settings.targetScopes || {},
      elements: settings.elements || {},
      constraints: settings.constraints || {},
      locks: settings.locks || {},
      gap: settings.gap || '3',
      riskMode: settings.riskMode || 'warn',
      sortMode: normalizeRecSortMode(settings.sortMode),
      limit: settings.limit || '20',
      search: settings.search || '',
    };
    box = {...box, owned: new Set(owned), builds, buildSlug: ''};
    boxUndoStack = [];
  },
  constraints(mode, scope) {
    const sets = constraintSets(mode, scope);
    return {required: [...sets.required], excluded: [...sets.excluded]};
  },
  ranked(mode, scope, used = [], options = {}) {
    return rankedFor(mode, scope, new Set(used), options).map(item => ({
      id: item.template.id,
      chars: [...item.template.chars],
      score: item.score,
      scoreMode: item.scoreMode,
      scores: {...item.scores},
      scoreParts: Object.fromEntries(Object.entries(item.scoreParts).map(([mode, parts]) => [mode, parts.map(part => ({...part}))])),
      performance: {...item.performance},
      ownedCount: item.ownedCount,
      recordedCount: item.recordedCount,
      readyCount: item.readyCount,
      elementHits: item.elementHits,
      coreHits: item.coreHits,
      risks: item.risks.map(risk => risk.text),
    }));
  },
  scopes(mode = rec.mode) {
    return scopes(mode).map(scope => scope.key);
  },
  planScopes(mode = rec.mode) {
    return recPlanScopes(mode).map(scope => scope.key);
  },
  plan() {
    return bestRecSlatePlan(recPlanScopes()).map(item => item?.template.id || null);
  },
  planSnapshot() {
    return bestRecSlatePlan(recPlanScopes()).map(item => item ? {id: item.template.id, score: item.score, scoreMode: item.scoreMode, scores: {...item.scores}} : null);
  },
  tier(slug, mode = rec.mode) {
    return tierMeta(slug, mode);
  },
  rankFacts(value) {
    return {sortValue: rankSortValue(value), positive: positiveMetric(value)};
  },
  identityView(data, settings = {}) {
    DATA = normalizeVisualizerData(data);
    banner = {...banner, phase: settings.bannerPhase || 'all', search: settings.bannerSearch || ''};
    box = {...box, element: settings.element || 'all', style: settings.style || 'all', status: settings.boxStatus || 'all', search: settings.boxSearch || ''};
    return {
      roster: DATA.rosterRows.map(row => ({slug: row.character_slug, name: row.character_name_cn, statuses: row.banner_statuses || ''})),
      boxOrder: filteredRoster().map(row => row.character_slug),
      bannerOrder: bannerRows().map(row => ({slug: row.character_slug, phase: row.phase_id, status: row.phase_status})),
    };
  },
  migrateBox(raw) {
    applyBoxRaw(raw);
    const payload = boxPayload();
    return {owned: [...box.owned].sort(), buildSlug: box.buildSlug, builds: box.builds, payload: {owned: payload.owned, buildSlug: payload.buildSlug, builds: payload.builds}};
  },
  migrateRec(raw) {
    localStorage.setItem(REC_KEY, JSON.stringify(raw));
    loadRec();
    return rec.constraints;
  },
  migrateSort(raw) {
    localStorage.setItem(REC_KEY, JSON.stringify(raw));
    loadRec();
    return rec.sortMode;
  },
  boxPreview(raw) {
    return boxImportPreview(raw);
  },
  boxImportError(raw) {
    try { parseBoxImportDocument(raw); return ''; } catch (error) { return error.message; }
  },
  boxHistoryProbe(count) {
    boxUndoStack = [];
    for (let index = 0; index < count; index += 1) {
      box.owned = new Set(['unit-' + index]);
      box.builds = {};
      box.buildSlug = '';
      rememberBoxUndo();
    }
    return {length: boxUndoStack.length, first: boxUndoStack[0]?.owned[0], last: boxUndoStack.at(-1)?.owned[0]};
  },
  freshness(mode, fallback = {}) {
    return modeFreshness(mode, fallback);
  },
};
`;

function loadContract(appPath, harness) {
  const storage = new Map();
  const document = {
    body: {innerHTML: ''},
    getElementById: () => null,
    createElement: () => ({}),
    createElementNS: () => ({}),
  };
  const context = vm.createContext({
    console,
    document,
    fetch: () => new Promise(() => {}),
    location: {hash: '', href: 'http://localhost/', origin: 'http://localhost'},
    localStorage: {
      getItem: key => storage.get(String(key)) ?? null,
      setItem: (key, value) => storage.set(String(key), String(value)),
      removeItem: key => storage.delete(String(key)),
    },
  });
  context.global = context;
  context.window = context;
  const source = `${readFileSync(SLATE_SOLVER, 'utf8')}\n${readFileSync(appPath, 'utf8')}\n${harness}`;
  new vm.Script(source, {filename: appPath}).runInContext(context, {timeout: 2_000});
  return context.__recommenderContract;
}

function loadBoxFlushContract(appPath, {putOk = true} = {}) {
  const storage = new Map();
  let putCount = 0;
  const context = vm.createContext({
    console,
    __MIHO_DESKTOP__: true,
    document: {body: {innerHTML: ''}, getElementById: () => null, createElement: () => ({})},
    location: {hash: '', href: 'http://localhost/', origin: 'http://localhost'},
    localStorage: {
      getItem: key => storage.get(String(key)) ?? null,
      setItem: (key, value) => storage.set(String(key), String(value)),
      removeItem: key => storage.delete(String(key)),
    },
    setTimeout,
    clearTimeout,
    requestAnimationFrame: () => 0,
    fetch: (url, options = {}) => {
      if (options.method !== 'PUT') return new Promise(() => {});
      putCount += 1;
      const payload = JSON.parse(String(options.body || '{}'));
      return Promise.resolve({ok: putOk, json: () => Promise.resolve(payload)});
    },
  });
  context.global = context;
  context.window = context;
  const harness = String.raw`
;globalThis.__boxFlushContract = {
  async saveOne(slug) {
    DATA = {rosterRows: []};
    state = {...state, page: 'not-rendered'};
    box = {...box, owned: new Set([slug]), builds: {}, buildSlug: ''};
    boxSaveRevision = 0;
    boxPendingSave = null;
    boxSaveChain = Promise.resolve();
    saveBox();
    await flushBoxSave();
    return box.saveStatus;
  },
};
`;
  new vm.Script(`${readFileSync(appPath, 'utf8')}\n${harness}`, {filename: appPath}).runInContext(context, {timeout: 2_000});
  return {api: context.__boxFlushContract, putCount: () => putCount};
}

function solveSlate(input) {
  const context = vm.createContext({console});
  new vm.Script(readFileSync(SLATE_SOLVER, 'utf8'), {filename: SLATE_SOLVER}).runInContext(context, {timeout: 2_000});
  return plain(context.MihoSlateSolver.solve(input));
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

test('shared slate solver keeps the 241st single-stage candidate when it forms the exact global optimum', () => {
  const blocked = Array.from({length: 240}, (_, index) => ({
    key: `left-${String(index).padStart(3, '0')}`,
    score: 100,
    members: [`blocked-${index}`, 'shared'],
  }));
  const result = solveSlate({
    candidateLists: [
      [...blocked, {key: 'left-241', score: 99, members: ['free']}],
      [{key: 'right-best', score: 1000, members: ['shared']}],
    ],
  });
  assert.equal(result.solver_meta.search_type, 'exact');
  assert.deepEqual(result.solutions[0].picks, [240, 0]);
  assert.equal(result.solutions[0].totalScore, 1099);
});

test('shared slate solver returns monotonic unique Top 3 solutions without cross-team reuse', () => {
  const lists = [
    [
      {key: 'a', score: 30, members: ['a']},
      {key: 'b', score: 20, members: ['b']},
      {key: 'c', score: 10, members: ['c']},
    ],
    [
      {key: 'x', score: 30, members: ['a']},
      {key: 'y', score: 25, members: ['y']},
      {key: 'z', score: 15, members: ['z']},
    ],
  ];
  const result = solveSlate({candidateLists: lists, maxSolutions: 3});
  assert.equal(result.solutions.length, 3);
  assert.ok(result.solutions.every(solution => solution.filled === 2));
  assert.ok(result.solutions.every((solution, index, all) => index === 0 || all[index - 1].totalScore >= solution.totalScore));
  assert.equal(new Set(result.solutions.map(solution => solution.picks.join('|'))).size, 3);
  result.solutions.forEach(solution => {
    const members = solution.picks.flatMap((pick, scope) => lists[scope][pick].members);
    assert.equal(new Set(members).size, members.length);
  });
});

test('shared slate solver prefers alternatives that change a whole source team before same-team variants', () => {
  const result = solveSlate({
    candidateLists: [
      [
        {key: 'alpha-real', teamKey: 'alpha', score: 100, members: ['a']},
        {key: 'alpha-sub-1', teamKey: 'alpha', score: 99, members: ['b']},
        {key: 'alpha-sub-2', teamKey: 'alpha', score: 98, members: ['c']},
        {key: 'beta-real', teamKey: 'beta', score: 90, members: ['d']},
        {key: 'gamma-real', teamKey: 'gamma', score: 80, members: ['e']},
      ],
    ],
    maxSolutions: 3,
  });
  assert.deepEqual(result.solutions.map(solution => solution.teamKeys[0]), ['alpha', 'beta', 'gamma']);
  assert.deepEqual(result.solutions.map(solution => solution.totalScore), [100, 90, 80]);
});

test('shared slate solver orders complete solutions by the original score objective, not weakness metadata', () => {
  const result = solveSlate({
    candidateLists: [[
      {key: 'lower-with-hit', score: 10, weaknessMatches: 1, members: ['a']},
      {key: 'higher-without-hit', score: 20, weaknessMatches: 0, members: ['b']},
    ]],
  });
  assert.deepEqual(result.solutions.map(solution => solution.totalScore), [20, 10]);
});

test('shared slate solver returns no public solution when every multi-stage slate is incomplete', () => {
  const result = solveSlate({
    candidateLists: [
      [{key: 'left', score: 20, members: ['shared']}],
      [{key: 'right', score: 30, members: ['shared']}],
    ],
  });
  assert.deepEqual(result.solutions, []);
  assert.equal(result.solver_meta.max_filled, 1);
  assert.equal(result.solver_meta.complete_solution_count, 0);
});

test('shared exact two-stage solver looks past same-team variants for diverse alternatives', () => {
  const result = solveSlate({
    candidateLists: [
      [{key: 'left', teamKey: 'left', score: 100, members: ['left']}],
      [
        {key: 'alpha-1', teamKey: 'alpha', score: 50, members: ['a1']},
        {key: 'alpha-2', teamKey: 'alpha', score: 49, members: ['a2']},
        {key: 'alpha-3', teamKey: 'alpha', score: 48, members: ['a3']},
        {key: 'beta', teamKey: 'beta', score: 40, members: ['b']},
        {key: 'gamma', teamKey: 'gamma', score: 30, members: ['c']},
      ],
    ],
    maxSolutions: 3,
  });
  assert.deepEqual(result.solutions.map(solution => solution.teamKeys[1]), ['alpha', 'beta', 'gamma']);
  assert.deepEqual(result.solutions.map(solution => solution.totalScore), [150, 140, 130]);
});

test('shared slate solver deduplicates different evidence keys that converge to the same final deployment', () => {
  const result = solveSlate({
    candidateLists: [[
      {key: 'source-a', teamKey: 'source-a', score: 30, members: ['same-2', 'same-1']},
      {key: 'source-b', teamKey: 'source-b', score: 29, members: ['same-1', 'same-2']},
      {key: 'different', teamKey: 'different', score: 20, members: ['other-1', 'other-2']},
    ]],
  });
  assert.equal(result.solutions.length, 2);
  assert.deepEqual(result.solutions.map(solution => solution.totalScore), [30, 20]);
});

test('shared slate solver marks three-stage search as bounded beam with auditable limits', () => {
  const result = solveSlate({
    candidateLists: [
      [{key: 'a', score: 3, members: ['a']}],
      [{key: 'b', score: 2, members: ['b']}],
      [{key: 'c', score: 1, members: ['c']}],
    ],
    beamWidth: 17,
    branchLimit: 9,
  });
  assert.equal(result.solver_meta.search_type, 'beam');
  assert.equal(result.solver_meta.exact, false);
  assert.equal(result.solver_meta.beam_width, 17);
  assert.equal(result.solver_meta.branch_limit, 9);
});

function hsrCharacter(slug, element, roles, pathName, releaseOrder) {
  return {
    character_slug: slug,
    alias_slugs: slug,
    character_name_cn: slug,
    character_name_en: slug,
    element_cn: element,
    path_cn: pathName,
    role_groups: roles,
    role_group_cns: roles,
    rarity: 5,
    release_order: releaseOrder,
    icon_url: '',
  };
}

function hsrTemplate(id, scope, chars, rank, appRate, mode = 'as') {
  return {
    id,
    mode,
    mode_cn: mode,
    scope_key: scope,
    scope_label: scope,
    scope_order: 1,
    chars,
    rank,
    app_rate: appRate,
    avg_round: 99,
    collect_date: '2026-07-01',
    phase_ver: 'test-phase',
    snapshot_id: 'test-snapshot',
    phase_status: 'current',
  };
}

function hsrData(rosterRows, teamTemplates) {
  return {
    rosterRows,
    teamTemplates,
    tierRows: [],
    usageRows: [],
    trendRows: [],
  };
}

function hsrFullBuild() {
  return {level: 80, lc: 80, eidolon: 0, signature: 'no', traces: 'max', relics: 'great'};
}

function allBuilds(slugs, factory) {
  return Object.fromEntries(slugs.map(slug => [slug, factory()]));
}

function weaknessFixture() {
  const rosterRows = [
    hsrCharacter('fire-core', '火', 'main_dps', '毁灭', 1),
    hsrCharacter('physical-core', '物理', 'main_dps', '巡猎', 2),
    hsrCharacter('wind-core', '风', 'main_dps', '巡猎', 3),
    hsrCharacter('ice-support', '冰', 'support', '同谐', 4),
    hsrCharacter('quantum-support', '量子', 'support', '虚无', 5),
    hsrCharacter('fire-support', '火', 'support', '同谐', 6),
    hsrCharacter('wind-support', '风', 'support', '虚无', 7),
    hsrCharacter('physical-support', '物理', 'support', '同谐', 8),
    hsrCharacter('imaginary-support', '虚数', 'support', '虚无', 9),
    hsrCharacter('sustain-a', '虚数', 'sustain', '丰饶', 10),
    hsrCharacter('sustain-b', '量子', 'sustain', '存护', 11),
    hsrCharacter('sustain-c', '雷', 'sustain', '丰饶', 12),
  ];
  const teamTemplates = [
    hsrTemplate('team-fire', '4-1', ['fire-core', 'ice-support', 'quantum-support', 'sustain-a'], 1, 30),
    hsrTemplate('team-physical-with-aux-hits', '4-1', ['physical-core', 'fire-support', 'wind-support', 'sustain-b'], 2, 25),
    hsrTemplate('team-wind', '4-1', ['wind-core', 'physical-support', 'imaginary-support', 'sustain-c'], 3, 20),
  ];
  const slugs = rosterRows.map(row => row.character_slug);
  return {data: hsrData(rosterRows, teamTemplates), slugs, builds: allBuilds(slugs, hsrFullBuild)};
}

function endgameRankingFixture() {
  const slugs = ['sparxie', 'trailblazer-elation', 'sparkle', 'yao-guang', 'dan-heng-permansor-terrae'];
  const rosterRows = slugs.map((slug, index) => hsrCharacter(
    slug,
    ['火', '虚数', '量子', '物理', '风'][index],
    index === 0 || index === 4 ? 'main_dps' : 'support',
    index === 4 ? '巡猎' : '同谐',
    index + 1,
  ));
  const first = {
    ...hsrTemplate('elation-trailblazer-team', '4-2', ['sparxie', 'trailblazer-elation', 'sparkle', 'dan-heng-permansor-terrae'], 112, 0.13),
    avg_round: 3467,
  };
  const second = {
    ...hsrTemplate('yao-guang-team', '4-2', ['sparxie', 'sparkle', 'yao-guang', 'dan-heng-permansor-terrae'], 47, 0.32),
    avg_round: 3579,
  };
  const builds = {
    sparxie: {level: 20, lc: 20, eidolon: 2, signature: 'yes', traces: 'low', relics: 'good'},
    'trailblazer-elation': {level: 80, lc: 0, eidolon: 'unset', signature: 'yes', traces: 'low', relics: 'none'},
    'yao-guang': {level: 0, lc: 0, eidolon: 0, signature: 'no', traces: 'unset', relics: 'unset'},
    'dan-heng-permansor-terrae': {level: 80, lc: 80, eidolon: 2, signature: 'no', traces: 'max', relics: 'good'},
  };
  return {data: hsrData(rosterRows, [first, second]), slugs, builds};
}

test('HSR warn mode treats selected weaknesses as annotations, including auxiliary-only hits', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  const {data, slugs, builds} = weaknessFixture();
  api.reset(data, {mode: 'as', scope: '4-1', riskMode: 'warn', gap: '4'}, slugs, builds);

  const withoutWeakness = plain(api.ranked('as', '4-1')).map(({id, score}) => ({id, score}));
  api.setElements('as', '4-1', ['火', '风']);
  const withMultipleWeaknesses = plain(api.ranked('as', '4-1'));
  const multiSnapshot = withMultipleWeaknesses.map(({id, score}) => ({id, score}));
  assert.deepEqual(
    multiSnapshot,
    withoutWeakness,
    'HSR warn mode must not change recommendation order or score after selecting multiple real weaknesses',
  );
  assert.equal(
    withMultipleWeaknesses.find(item => item.id === 'team-physical-with-aux-hits').coreElementHits,
    0,
    'the auxiliary-hit fixture must have no core weakness hit',
  );
  assert.ok(
    withMultipleWeaknesses.find(item => item.id === 'team-physical-with-aux-hits').elementHits > 0,
    'the auxiliary-hit fixture must actually contain a selected support element',
  );

  api.setElements('as', '4-1', ['火']);
  const auxiliarySnapshot = plain(api.ranked('as', '4-1')).map(({id, score}) => ({id, score}));
  assert.deepEqual(
    auxiliarySnapshot,
    withoutWeakness,
    'an auxiliary character matching a weakness must not promote or otherwise rerank its team',
  );
});

test('HSR final multi-team plan is also invariant when weaknesses are annotated', () => {
  const {data, slugs, builds} = weaknessFixture();
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(data, {mode: 'as', scope: '4-1', strategy: 'final', riskMode: 'warn', gap: '4'}, slugs, builds);
  const baseline = plain(api.planSnapshot());
  api.setElements('as', '4-1', ['风']);
  assert.deepEqual(
    plain(api.planSnapshot()),
    baseline,
    'final-stage weakness annotations must not change the multi-team slate or its scores',
  );
});

test('HSR filter mode uses OR across weaknesses and keeps only risk-free core hits', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  const {data, slugs, builds} = weaknessFixture();
  api.reset(
    data,
    {mode: 'as', scope: '4-1', riskMode: 'filter', gap: '4', elements: {'as|4-1': ['火', '风']}},
    slugs,
    builds,
  );

  const ranked = plain(api.ranked('as', '4-1'));
  assert.deepEqual(
    ranked.map(item => item.id),
    ['team-fire', 'team-wind'],
    'filter mode must keep either selected core element and reject an auxiliary-only hit',
  );
  assert.ok(
    ranked.every(item => item.coreElementHits >= 1 && item.risks.length === 0),
    'every filtered result must have a core hit and no build, tier, trend, or attribute risk',
  );
});

test('HSR custom mode searches the deduplicated cross-node pool and ranks core weakness matches first', () => {
  const rosterRows = [
    hsrCharacter('fire-core', '火', 'main_dps', '毁灭', 1),
    hsrCharacter('ice-core', '冰', 'main_dps', '巡猎', 2),
    hsrCharacter('ice-support', '冰', 'support', '同谐', 3),
    hsrCharacter('support-a', '量子', 'support', '虚无', 4),
    hsrCharacter('support-b', '雷', 'support', '同谐', 5),
    hsrCharacter('support-c', '风', 'support', '虚无', 6),
    hsrCharacter('sustain-a', '虚数', 'sustain', '丰饶', 7),
    hsrCharacter('sustain-b', '量子', 'sustain', '存护', 8),
    hsrCharacter('all-only-core', '冰', 'main_dps', '智识', 9),
  ];
  const fireChars = ['fire-core', 'ice-support', 'support-a', 'sustain-a'];
  const templates = [
    hsrTemplate('fire-node-1', '4-1', fireChars, 5, 20),
    hsrTemplate('fire-node-2-better-evidence', '4-2', [...fireChars].reverse(), 2, 28),
    hsrTemplate('ice-node-2', '4-2', ['ice-core', 'support-b', 'support-c', 'sustain-b'], 8, 12),
    hsrTemplate('all-only-must-not-enter-custom-pool', 'all', ['all-only-core', 'support-a', 'support-b', 'sustain-a'], 1, 40),
  ];
  const slugs = rosterRows.map(row => row.character_slug);
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(
    hsrData(rosterRows, templates),
    {mode: 'as', scope: 'custom-1', strategy: 'custom', teamCounts: {as: '2'}, gap: '4', elements: {'as|custom-1': ['冰']}},
    slugs,
    allBuilds(slugs, hsrFullBuild),
  );

  assert.deepEqual(
    plain(api.pool('as')).map(item => item.id).sort(),
    ['fire-node-2-better-evidence', 'ice-node-2'].sort(),
    'custom mode must union concrete nodes, deduplicate unordered teams, and exclude the capped aggregate scope',
  );
  const ranked = plain(api.ranked('as', 'custom-1'));
  assert.equal(ranked[0].id, 'ice-node-2', 'a core weakness match must outrank a stronger off-weakness team in custom mode');
  assert.equal(ranked[0].weaknessMatched, true);
  assert.equal(
    ranked.find(item => item.id === 'fire-node-2-better-evidence').weaknessMatched,
    false,
    'an ice support must not make a fire-core team count as an ice weakness match',
  );
});

test('HSR final mode supports arbitrary real-node targets while custom mode uses the requested team count', () => {
  const rosterRows = [
    hsrCharacter('a', '火', 'main_dps', '毁灭', 1), hsrCharacter('b', '冰', 'support', '同谐', 2),
    hsrCharacter('c', '雷', 'support', '虚无', 3), hsrCharacter('d', '风', 'sustain', '丰饶', 4),
  ];
  const chars = ['a', 'b', 'c', 'd'];
  const templates = ['4-1', '4-2', '4-3'].map((scope, index) => hsrTemplate(`team-${scope}`, scope, chars, index + 1, 20 - index));
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(hsrData(rosterRows, templates), {mode: 'as', scope: '4-1', strategy: 'final', teamCounts: {as: '2'}}, chars, allBuilds(chars, hsrFullBuild));
  assert.deepEqual(plain(api.planScopes()), ['4-1', '4-2', '4-3'], 'legacy settings must default final-stage planning to every real Starward node');
  api.reset(
    hsrData(rosterRows, templates),
    {mode: 'as', scope: '4-1', strategy: 'final', teamCounts: {as: '3'}, targetScopes: {as: ['4-1', '4-3']}},
    chars,
    allBuilds(chars, hsrFullBuild),
  );
  assert.deepEqual(plain(api.planScopes()), ['4-1', '4-3'], 'final-stage planning must support a non-contiguous subset instead of slicing the first N nodes');
  api.reset(
    hsrData(rosterRows, templates),
    {mode: 'as', scope: '4-3', strategy: 'final', targetScopes: {as: ['4-3']}},
    chars,
    allBuilds(chars, hsrFullBuild),
  );
  assert.deepEqual(plain(api.planScopes()), ['4-3'], 'final-stage planning must also support a single real node');
  assert.deepEqual(plain(api.plan()), ['team-4-3']);

  api.reset(hsrData(rosterRows, templates), {mode: 'as', scope: 'custom-1', strategy: 'custom', teamCounts: {as: '2'}}, chars, allBuilds(chars, hsrFullBuild));
  assert.deepEqual(plain(api.scopes()), ['custom-1', 'custom-2']);
  api.reset(hsrData(rosterRows, templates), {mode: 'as', scope: 'custom-1', strategy: 'custom', teamCounts: {as: '3'}}, chars, allBuilds(chars, hsrFullBuild));
  assert.deepEqual(plain(api.scopes()), ['custom-1', 'custom-2', 'custom-3']);
});

test('HSR selected-node planning recomputes the joint optimum instead of truncating a three-node plan', () => {
  const shared = ['shared-core', 'shared-a', 'shared-b', 'shared-sustain'];
  const alternate = ['alternate-core', 'alternate-a', 'alternate-b', 'alternate-sustain'];
  const second = ['second-core', 'second-a', 'second-b', 'second-sustain'];
  const allSlugs = [...shared, ...alternate, ...second];
  const rosterRows = allSlugs.map((slug, index) => hsrCharacter(
    slug,
    index % 3 === 0 ? '火' : '量子',
    slug.endsWith('sustain') ? 'sustain' : slug.endsWith('core') ? 'main_dps' : 'support',
    slug.endsWith('sustain') ? '丰饶' : slug.endsWith('core') ? '毁灭' : '同谐',
    index + 1,
  ));
  const templates = [
    hsrTemplate('node-1-best-shared', '4-1', shared, 1, 35),
    hsrTemplate('node-1-lower-alternate', '4-1', alternate, 30, 1),
    hsrTemplate('node-2-independent', '4-2', second, 1, 35),
    hsrTemplate('node-3-needs-shared', '4-3', shared, 1, 35),
  ];
  const data = hsrData(rosterRows, templates);
  const builds = allBuilds(allSlugs, hsrFullBuild);
  const api = loadContract(HSR_APP, HSR_HARNESS);

  api.reset(data, {mode: 'as', scope: '4-1', strategy: 'final'}, allSlugs, builds);
  assert.deepEqual(
    plain(api.plan()),
    ['node-1-lower-alternate', 'node-2-independent', 'node-3-needs-shared'],
    'the three-node model must reserve the shared team for the third node',
  );

  api.reset(data, {mode: 'as', scope: '4-1', strategy: 'final', targetScopes: {as: ['4-1', '4-2']}}, allSlugs, builds);
  assert.deepEqual(
    plain(api.plan()),
    ['node-1-best-shared', 'node-2-independent'],
    'the two-node model must reclaim characters from the omitted node and optimize only the selected pair',
  );
});

test('HSR multi-team planner jointly assigns teams instead of greedily consuming the weakness match', () => {
  const rosterRows = [
    hsrCharacter('fire-core', '火', 'main_dps', '毁灭', 1),
    hsrCharacter('ice-core', '冰', 'main_dps', '巡猎', 2),
    ...['fa', 'fb', 'fc', 'ia', 'ib', 'ic'].map((slug, index) => hsrCharacter(slug, '量子', index % 3 === 2 ? 'sustain' : 'support', index % 3 === 2 ? '丰饶' : '同谐', index + 3)),
  ];
  const templates = [
    hsrTemplate('strong-fire-team', '4-1', ['fire-core', 'fa', 'fb', 'fc'], 1, 35),
    hsrTemplate('second-ice-team', '4-2', ['ice-core', 'ia', 'ib', 'ic'], 2, 20),
  ];
  const slugs = rosterRows.map(row => row.character_slug);
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(
    hsrData(rosterRows, templates),
    {mode: 'as', scope: 'custom-1', strategy: 'custom', teamCounts: {as: '2'}, gap: '4', elements: {'as|custom-2': ['火']}},
    slugs,
    allBuilds(slugs, hsrFullBuild),
  );
  assert.deepEqual(
    plain(api.plan()),
    ['second-ice-team', 'strong-fire-team'],
    'the joint plan must leave the fire team for the slot whose configured weakness needs it',
  );
});

test('HSR multi-team planner expands beyond the top 50 when only a lower-ranked team completes the slate', () => {
  const rosterRows = [
    hsrCharacter('shared-support', '量子', 'support', '同谐', 1),
    ...Array.from({length: 55}, (_, index) => [
      hsrCharacter(`conflict-core-${index}`, '火', 'main_dps', '毁灭', index * 3 + 2),
      hsrCharacter(`conflict-support-${index}`, '冰', 'support', '虚无', index * 3 + 3),
      hsrCharacter(`conflict-sustain-${index}`, '风', 'sustain', '丰饶', index * 3 + 4),
    ]).flat(),
    hsrCharacter('unique-core', '雷', 'main_dps', '巡猎', 200),
    hsrCharacter('unique-support-a', '物理', 'support', '同谐', 201),
    hsrCharacter('unique-support-b', '虚数', 'support', '虚无', 202),
    hsrCharacter('unique-sustain', '量子', 'sustain', '存护', 203),
  ];
  const conflictTemplates = Array.from({length: 55}, (_, index) => hsrTemplate(
    `high-conflict-${index}`,
    '4-1',
    ['shared-support', `conflict-core-${index}`, `conflict-support-${index}`, `conflict-sustain-${index}`],
    index + 1,
    35,
  ));
  const uniqueTemplate = hsrTemplate(
    'low-unique-team',
    '4-1',
    ['unique-core', 'unique-support-a', 'unique-support-b', 'unique-sustain'],
    999,
    0,
  );
  const slugs = rosterRows.map(row => row.character_slug);
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(
    hsrData(rosterRows, [...conflictTemplates, uniqueTemplate]),
    {mode: 'as', scope: 'custom-1', strategy: 'custom', teamCounts: {as: '2'}, gap: '4'},
    slugs,
    allBuilds(slugs, hsrFullBuild),
  );

  const plan = plain(api.plan());
  assert.equal(plan.filter(Boolean).length, 2, 'the fallback must fill both target teams');
  assert.ok(plan.includes('low-unique-team'), 'the only non-conflicting team below the top 50 must be selected');
  assert.equal(
    plan.filter(id => id?.startsWith('high-conflict-')).length,
    1,
    'only one of the high-ranked teams sharing the same character may be selected',
  );
});

test('HSR two-node final planning searches the complete template pool instead of a Top-N prefix', () => {
  const shared = 'shared-anchor';
  const conflictGroups = Array.from({length: 241}, (_, index) => [
    `conflict-core-${index}`,
    `conflict-support-${index}`,
    `conflict-sustain-${index}`,
  ]);
  const lowerUnique = ['lower-core', 'lower-a', 'lower-b', 'lower-sustain'];
  const secondBestRest = ['second-best-a', 'second-best-b', 'second-best-sustain'];
  const secondFallback = ['second-fallback-core', 'second-fallback-a', 'second-fallback-b', 'second-fallback-sustain'];
  const slugs = [shared, ...conflictGroups.flat(), ...lowerUnique, ...secondBestRest, ...secondFallback];
  const rosterRows = slugs.map((slug, index) => hsrCharacter(
    slug,
    '量子',
    slug.includes('core') ? 'main_dps' : slug.includes('sustain') ? 'sustain' : 'support',
    slug.includes('core') ? '毁灭' : slug.includes('sustain') ? '丰饶' : '同谐',
    index + 1,
  ));
  const firstScopeConflicts = conflictGroups.map((group, index) => hsrTemplate(
    `first-top-${index}`,
    '4-1',
    [shared, ...group],
    index + 1,
    35,
  ));
  const templates = [
    ...firstScopeConflicts,
    hsrTemplate('first-below-top-240-independent', '4-1', lowerUnique, 999, 5),
    hsrTemplate('second-best-shared', '4-2', [shared, ...secondBestRest], 1, 35),
    hsrTemplate('second-low-independent', '4-2', secondFallback, 999, 0),
  ];
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(
    hsrData(rosterRows, templates),
    {mode: 'as', scope: '4-1', strategy: 'final', targetScopes: {as: ['4-1', '4-2']}},
    slugs,
    allBuilds(slugs, hsrFullBuild),
  );

  assert.deepEqual(
    plain(api.plan()),
    ['first-below-top-240-independent', 'second-best-shared'],
    'a fillable prefix search must not hide a higher-scoring two-node combination below rank 240',
  );
});

test('HSR hard constraints filter before ranking and protect required/excluded substitution semantics', () => {
  const rosterRows = [
    hsrCharacter('core', '火', 'main_dps', '毁灭', 1),
    hsrCharacter('required', '冰', 'support', '同谐', 2),
    hsrCharacter('missing-slot', '量子', 'support', '同谐', 3),
    hsrCharacter('sustain', '虚数', 'sustain', '丰饶', 4),
    hsrCharacter('excluded', '火', 'support', '同谐', 5),
    hsrCharacter('allowed-substitute', '雷', 'support', '同谐', 6),
    hsrCharacter('other-required', '风', 'support', '虚无', 7),
  ];
  const teamTemplates = [
    hsrTemplate('valid-constrained-team', '4-1', ['core', 'required', 'missing-slot', 'sustain'], 3, 15),
    hsrTemplate('contains-excluded', '4-1', ['core', 'required', 'excluded', 'sustain'], 1, 35),
    hsrTemplate('missing-required', '4-1', ['core', 'other-required', 'missing-slot', 'sustain'], 2, 30),
    hsrTemplate('other-scope-valid', '4-2', ['core', 'other-required', 'missing-slot', 'sustain'], 1, 25),
    hsrTemplate('other-scope-wrong', '4-2', ['core', 'required', 'missing-slot', 'sustain'], 2, 20),
    hsrTemplate('other-mode', '4-1', ['core', 'required', 'missing-slot', 'sustain'], 1, 25, 'moc'),
  ];
  const owned = ['core', 'sustain', 'excluded', 'allowed-substitute'];
  const builds = allBuilds(owned, hsrFullBuild);
  const constraints = {
    'as|4-1': {required: ['required'], excluded: ['excluded']},
    'as|4-2': {required: ['other-required'], excluded: []},
    'moc|4-1': {required: [], excluded: ['required']},
  };
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(hsrData(rosterRows, teamTemplates), {mode: 'as', scope: '4-1', constraints, gap: '4'}, owned, builds);

  assert.deepEqual(
    plain(api.constraints('as', '4-1')),
    {required: ['required'], excluded: ['excluded']},
    'HSR constraints must be read from the exact mode and scope key',
  );
  assert.deepEqual(
    plain(api.constraints('as', '4-2')),
    {required: ['other-required'], excluded: []},
    'HSR constraints from another scope must remain isolated',
  );
  assert.deepEqual(
    plain(api.constraints('moc', '4-1')),
    {required: [], excluded: ['required']},
    'HSR constraints from another mode must remain isolated',
  );

  const ranked = plain(api.ranked('as', '4-1'));
  assert.deepEqual(
    ranked.map(item => item.id),
    ['valid-constrained-team'],
    'required and excluded characters must be applied as hard filters before ranking',
  );
  const requiredSubstitution = ranked[0].substitutions.find(entry => entry.missing === 'required');
  assert.deepEqual(
    requiredSubstitution.candidates,
    [],
    'a required but unowned character must stay in the team instead of receiving a substitute',
  );
  assert.ok(ranked[0].finalChars.includes('required'), 'the required missing character must remain in finalChars');
  assert.ok(!ranked[0].finalChars.includes('excluded'), 'an excluded character must never enter finalChars');
  assert.ok(
    ranked[0].substitutions.every(entry => !entry.candidates.includes('excluded')),
    'an excluded character must never appear among substitution candidates',
  );
  assert.deepEqual(
    plain(api.ranked('as', '4-2')).map(item => item.id),
    ['other-scope-valid'],
    'ranking a second scope must use that scope\'s constraints only',
  );
});

test('HSR reserved characters skip the first substitute and select the next valid candidate', () => {
  const rosterRows = [
    hsrCharacter('core', '火', 'main_dps', '毁灭', 10),
    hsrCharacter('open-support-slot', '冰', 'support', '同谐', 11),
    hsrCharacter('sustain', '虚数', 'sustain', '丰饶', 12),
    hsrCharacter('fixed-member', '量子', 'unknown', '记忆', 13),
    hsrCharacter('candidate-1', '雷', 'support', '同谐', 1),
    hsrCharacter('candidate-2', '风', 'support', '同谐', 2),
  ];
  const template = hsrTemplate(
    'substitution-team',
    'reserve-scope',
    ['core', 'open-support-slot', 'sustain', 'fixed-member'],
    1,
    20,
  );
  const owned = ['core', 'sustain', 'fixed-member', 'candidate-1', 'candidate-2'];
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(
    hsrData(rosterRows, [template]),
    {mode: 'as', scope: 'reserve-scope', gap: '4'},
    owned,
    allBuilds(owned, hsrFullBuild),
  );

  const baseline = plain(api.ranked('as', 'reserve-scope'))[0];
  const reserved = plain(api.ranked('as', 'reserve-scope', [], {reserved: ['candidate-1']}))[0];
  assert.equal(
    baseline.substitutions.find(entry => entry.missing === 'open-support-slot').candidates[0],
    'candidate-1',
    'the fixture must rank candidate-1 first before reservation',
  );
  assert.equal(
    reserved.substitutions.find(entry => entry.missing === 'open-support-slot').candidates[0],
    'candidate-2',
    'reserved candidate-1 must be skipped in favor of candidate-2',
  );
  assert.ok(!reserved.finalChars.includes('candidate-1'), 'a reserved character must not enter the final team');
});

test('HSR multiple missing slots receive distinct substitutes', () => {
  const rosterRows = [
    hsrCharacter('core', '火', 'main_dps', '毁灭', 10),
    hsrCharacter('missing-support-a', '冰', 'support', '同谐', 11),
    hsrCharacter('missing-support-b', '量子', 'support', '同谐', 12),
    hsrCharacter('sustain', '虚数', 'sustain', '丰饶', 13),
    hsrCharacter('candidate-1', '雷', 'support', '同谐', 1),
    hsrCharacter('candidate-2', '风', 'support', '同谐', 2),
  ];
  const template = hsrTemplate(
    'two-open-slots',
    'substitute-scope',
    ['core', 'missing-support-a', 'missing-support-b', 'sustain'],
    1,
    20,
  );
  const owned = ['core', 'sustain', 'candidate-1', 'candidate-2'];
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(
    hsrData(rosterRows, [template]),
    {mode: 'as', scope: 'substitute-scope', gap: '4'},
    owned,
    allBuilds(owned, hsrFullBuild),
  );

  const ranked = plain(api.ranked('as', 'substitute-scope'))[0];
  const assigned = ranked.substitutions.map(entry => entry.candidates[0]);
  assert.deepEqual(assigned, ['candidate-1', 'candidate-2']);
  assert.equal(new Set(ranked.finalChars).size, 4, 'the recommended final team must not repeat one substitute');
});

test('HSR joint planning assigns substitutes globally and caps theoretical evidence at C', () => {
  const rosterRows = [
    hsrCharacter('core-a', '火', 'main_dps', '毁灭', 10),
    hsrCharacter('missing-support-a', '冰', 'support', '同谐', 11),
    hsrCharacter('sustain-a', '虚数', 'sustain', '丰饶', 12),
    hsrCharacter('flex-a', '量子', 'sub_dps', '虚无', 13),
    hsrCharacter('core-b', '雷', 'main_dps', '智识', 20),
    hsrCharacter('missing-support-b', '风', 'support', '同谐', 21),
    hsrCharacter('sustain-b', '物理', 'sustain', '存护', 22),
    hsrCharacter('flex-b', '量子', 'sub_dps', '虚无', 23),
    hsrCharacter('shared-substitute', '冰', 'support', '同谐', 1),
    hsrCharacter('alternate-substitute', '风', 'support', '同谐', 2),
  ];
  const templates = [
    hsrTemplate('scope-a-team', '4-1', ['core-a', 'missing-support-a', 'sustain-a', 'flex-a'], 1, 30),
    hsrTemplate('scope-b-team', '4-2', ['core-b', 'missing-support-b', 'sustain-b', 'flex-b'], 1, 30),
  ];
  const owned = rosterRows.map(row => row.character_slug).filter(slug => !slug.startsWith('missing-'));
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(
    hsrData(rosterRows, templates),
    {mode: 'as', scope: '4-1', targetScopes: {as: ['4-1', '4-2']}, gap: '4'},
    owned,
    allBuilds(owned, hsrFullBuild),
  );

  const result = plain(api.slates());
  assert.equal(result.solver_meta.search_type, 'exact');
  const picks = result.plans[0].picks;
  assert.deepEqual(picks.map(item => item.id), ['scope-a-team', 'scope-b-team']);
  const assigned = picks.flatMap(item => item.substitutions.map(row => row.replacement));
  assert.equal(new Set(assigned).size, 2, 'two teams must not greedily claim the same substitute');
  assert.equal(new Set(picks.flatMap(item => item.finalChars)).size, 8, 'the final joint slate must not reuse any deployment entity');
  assert.ok(picks.every(item => item.evidenceConfidence === 'C'), 'any substituted team must remain theoretical C evidence');
  assert.ok(picks.every(item => item.finalMissingCount === 0));
  const originalScores = Object.fromEntries(plain(api.ranked('as', '4-1')).concat(plain(api.ranked('as', '4-2'))).map(item => [item.id, item.score]));
  assert.ok(picks.every(item => item.score > originalScores[item.id]), 'final owned substitutes must update the Box-aware objective instead of keeping the missing-template score');
});

test('HSR locked final teams reserve their deployment entities and invalid locks auto-clear', () => {
  const shared = 'shared-star';
  const leftShared = [shared, 'left-a', 'left-b', 'left-c'];
  const leftAlternative = ['left-alt-core', 'left-alt-a', 'left-alt-b', 'left-alt-c'];
  const rightShared = [shared, 'right-a', 'right-b', 'right-c'];
  const rightAlternative = ['right-alt-core', 'right-alt-a', 'right-alt-b', 'right-alt-c'];
  const slugs = [...new Set([...leftShared, ...leftAlternative, ...rightShared, ...rightAlternative])];
  const rosterRows = slugs.map((slug, index) => hsrCharacter(slug, '火', index % 4 === 0 ? 'main_dps' : 'support', '同谐', index + 1));
  const templates = [
    hsrTemplate('left-shared', '4-1', leftShared, 1, 35),
    hsrTemplate('left-alternative', '4-1', leftAlternative, 30, 1),
    hsrTemplate('right-shared', '4-2', rightShared, 1, 35),
    hsrTemplate('right-alternative', '4-2', rightAlternative, 30, 1),
  ];
  const api = loadContract(HSR_APP, HSR_HARNESS);
  api.reset(
    hsrData(rosterRows, templates),
    {mode: 'as', scope: '4-1', targetScopes: {as: ['4-1', '4-2']}, gap: '4'},
    slugs,
    allBuilds(slugs, hsrFullBuild),
  );

  const lockKey = api.lockCandidate('4-1', 'left-shared');
  assert.ok(lockKey);
  const locked = plain(api.slates()).plans[0].picks;
  assert.deepEqual(locked.map(item => item.id), ['left-shared', 'right-alternative']);
  assert.equal(new Set(locked.flatMap(item => item.finalChars)).size, 8);

  api.setConstraints('as', '4-1', [], [shared]);
  plain(api.slates());
  assert.deepEqual(plain(api.locks()), {}, 'a lock that violates a new hard constraint must be removed explicitly');
});

test('HSR exposes balanced, historical, and Box rankings for the reported Apocalyptic Shadow teams', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  const fixture = endgameRankingFixture();
  const snapshots = {};

  for (const sortMode of ['balanced', 'history', 'box']) {
    api.reset(fixture.data, {mode: 'as', scope: '4-2', sortMode, gap: '4'}, fixture.slugs, fixture.builds);
    const ranked = plain(api.ranked('as', '4-2'));
    snapshots[sortMode] = ranked;
    assert.ok(ranked.every(item => item.scoreMode === sortMode && item.score === item.scores[sortMode]));
    for (const item of ranked) {
      for (const mode of ['balanced', 'history', 'box']) {
        const total = item.scoreParts[mode].reduce((sum, part) => sum + (part.available ? part.value : 0), 0);
        assert.ok(Math.abs(total - item.scores[mode]) < 1e-9, `${mode} parts must add up for ${item.id}`);
      }
    }
  }

  assert.deepEqual(snapshots.balanced.map(item => item.id), ['elation-trailblazer-team', 'yao-guang-team']);
  assert.deepEqual(snapshots.history.map(item => item.id), ['yao-guang-team', 'elation-trailblazer-team']);
  assert.deepEqual(snapshots.box.map(item => item.id), ['elation-trailblazer-team', 'yao-guang-team']);

  const balancedById = Object.fromEntries(snapshots.balanced.map(item => [item.id, item]));
  assert.ok(Math.abs(balancedById['elation-trailblazer-team'].scores.box - 441.725) < 1e-9);
  assert.ok(Math.abs(balancedById['yao-guang-team'].scores.box - 405.635) < 1e-9);
  assert.ok(Math.abs(balancedById['elation-trailblazer-team'].scores.balanced - 493.001) < 1e-9);
  assert.ok(Math.abs(balancedById['yao-guang-team'].scores.balanced - 480.549) < 1e-9);
  assert.equal(balancedById['elation-trailblazer-team'].scores.history, 0);
  assert.equal(balancedById['yao-guang-team'].scores.history, 100);
  const firstPerformance = balancedById['elation-trailblazer-team'].scoreParts.balanced.find(part => part.key === 'performance');
  const secondPerformance = balancedById['yao-guang-team'].scoreParts.balanced.find(part => part.key === 'performance');
  assert.ok(secondPerformance.value > firstPerformance.value && firstPerformance.value > 0, 'AS high scores must participate with the correct direction');

  const stableReference = Object.fromEntries(snapshots.balanced.map(item => [item.id, {scores: item.scores, scoreParts: item.scoreParts}]));
  for (const sortMode of ['history', 'box']) {
    for (const item of snapshots[sortMode]) {
      assert.deepEqual({scores: item.scores, scoreParts: item.scoreParts}, stableReference[item.id], 'switching the view must not mutate the other reference scores');
    }
  }
});

test('HSR historical performance uses mode-specific direction and excludes sentinels', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  const chars = ['core', 'support-a', 'support-b', 'sustain'];
  const rosterRows = chars.map((slug, index) => hsrCharacter(slug, '火', index === 0 ? 'main_dps' : index === 3 ? 'sustain' : 'support', index === 3 ? '丰饶' : '同谐', index + 1));
  const builds = allBuilds(chars, hsrFullBuild);
  const templatesFor = (mode, values) => values.map(([id, value]) => ({...hsrTemplate(id, 'node', chars, 10, 10, mode), avg_round: value}));

  for (const mode of ['as', 'pf']) {
    const templates = templatesFor(mode, [['low-score', 3000], ['high-score', 4000], ['zero-sentinel', 0], ['ninety-nine-sentinel', 99.99]]);
    api.reset(hsrData(rosterRows, templates), {mode, scope: 'node', sortMode: 'history', gap: '4'}, chars, builds);
    const ranked = plain(api.ranked(mode, 'node'));
    assert.deepEqual(ranked.slice(0, 2).map(item => item.id), ['high-score', 'low-score'], `${mode} must prefer a higher valid score`);
    for (const id of ['zero-sentinel', 'ninety-nine-sentinel']) {
      const item = ranked.find(candidate => candidate.id === id);
      for (const scoreMode of ['history', 'balanced']) {
        const part = item.scoreParts[scoreMode].find(candidate => candidate.key === 'performance');
        assert.equal(part.available, false, `${mode} ${id} must not be valid ${scoreMode} evidence`);
        assert.equal(part.value, 0);
      }
    }
  }

  const mocTemplates = templatesFor('moc', [['low-round', 2], ['high-round', 8], ['zero-sentinel', 0], ['ninety-nine-sentinel', 99.99]]);
  api.reset(hsrData(rosterRows, mocTemplates), {mode: 'moc', scope: 'node', sortMode: 'history', gap: '4'}, chars, builds);
  const moc = plain(api.ranked('moc', 'node'));
  assert.deepEqual(moc.slice(0, 2).map(item => item.id), ['low-round', 'high-round'], 'MoC must prefer fewer valid rounds');
  for (const id of ['zero-sentinel', 'ninety-nine-sentinel']) {
    const item = moc.find(candidate => candidate.id === id);
    for (const scoreMode of ['history', 'balanced']) {
      const part = item.scoreParts[scoreMode].find(candidate => candidate.key === 'performance');
      assert.equal(part.available, false);
      assert.equal(part.value, 0);
    }
  }

  const aaTemplates = templatesFor('aa', [['aa-low', 1], ['aa-high', 9999], ['aa-zero-sentinel', 0], ['aa-ninety-nine-sentinel', 99.99]]);
  api.reset(hsrData(rosterRows, aaTemplates), {mode: 'aa', scope: 'node', sortMode: 'history', gap: '4'}, chars, builds);
  const aa = plain(api.ranked('aa', 'node'));
  assert.ok(aa.every(item => item.scores.history === aa[0].scores.history), 'AA performance values must not affect ranking before direction is verified');
  assert.ok(aa.every(item => item.scoreParts.history.find(part => part.key === 'performance').available === false));
  assert.ok(aa.every(item => item.scoreParts.balanced.find(part => part.key === 'performance').available === false));
  for (const id of ['aa-zero-sentinel', 'aa-ninety-nine-sentinel']) {
    const evidence = aa.find(item => item.id === id).performance;
    assert.equal(evidence.display, '缺失');
    assert.match(evidence.note, /视为缺失/);
  }
  for (const id of ['aa-low', 'aa-high']) {
    const evidence = aa.find(item => item.id === id).performance;
    assert.notEqual(evidence.display, '缺失');
    assert.match(evidence.note, /仅展示/);
  }
});

test('HSR analysis metrics use mode-specific scale, direction, and missing sentinels', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  const rows = values => values.map(([slug, avg_round], index) => ({
    character_slug: slug,
    collect_date: '2026-07-01',
    avg_round,
    app_rate: index + 1,
    rating: 0,
  }));

  const moc = plain(api.analysis(rows([
    ['high-round', 8],
    ['zero', 0],
    ['low-round', 2],
    ['sentinel', 99.99],
    ['missing', null],
  ]), 'moc'));
  assert.deepEqual(moc.policy, {label: '平均回合', higherBetter: false, sortable: true});
  assert.deepEqual(moc.order.slice(0, 2), ['low-round', 'high-round']);
  assert.deepEqual(moc.values, [8, null, 2, null, null]);

  for (const [mode, label] of [['pf', '虚构得分'], ['as', '末日得分']]) {
    const score = plain(api.analysis(rows([
      ['low-score', 3000],
      ['zero', 0],
      ['high-score', 4000],
      ['sentinel', 99.99],
    ]), mode));
    assert.deepEqual(score.policy, {label, higherBetter: true, sortable: true});
    assert.deepEqual(score.order.slice(0, 2), ['high-score', 'low-score']);
    assert.deepEqual(score.values, [3000, null, 4000, null]);
  }

  const aaRows = rows([
    ['aa-high', 9999],
    ['aa-low', 1],
    ['aa-zero', 0],
    ['aa-sentinel', 99.99],
  ]);
  const aa = plain(api.analysis(aaRows, 'aa'));
  assert.deepEqual(aa.policy, {label: '表现原值', higherBetter: null, sortable: false});
  assert.deepEqual(aa.order, aaRows.map(row => row.character_slug), 'AA raw values must preserve source order');
  assert.deepEqual(aa.values, [9999, 1, null, null]);
});

test('HSR deployment groups prevent Trailblazer and March 7th forms from crossing teams', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  assert.deepEqual(
    plain(api.deploymentGroups(['trailblazer-harmony', 'trailblazer-preservation', 'march-7th', 'march-7th-swordmaster', 'march-7th-the-hunt', 'evernight'])),
    ['trailblazer', 'trailblazer', 'march-7th', 'march-7th', 'march-7th', 'evernight'],
  );

  const assertMutuallyExclusivePlan = (leftForm, rightForm) => {
    const left = [leftForm, 'left-a', 'left-b', 'left-c'];
    const right = [rightForm, 'right-a', 'right-b', 'right-c'];
    const fallback = ['fallback-core', 'fallback-a', 'fallback-b', 'fallback-c'];
    const slugs = [...left, ...right, ...fallback];
    const rosterRows = slugs.map((slug, index) => hsrCharacter(slug, '火', index % 4 === 0 ? 'main_dps' : 'support', '同谐', index + 1));
    const templates = [
      hsrTemplate('left-form-team', '4-1', left, 1, 30),
      hsrTemplate('right-form-team', '4-2', right, 1, 30),
      hsrTemplate('right-fallback-team', '4-2', fallback, 20, 5),
    ];
    api.reset(
      hsrData(rosterRows, templates),
      {mode: 'as', scope: '4-1', strategy: 'final', targetScopes: {as: ['4-1', '4-2']}, gap: '4'},
      slugs,
      allBuilds(slugs, hsrFullBuild),
    );
    assert.deepEqual(plain(api.plan()), ['left-form-team', 'right-fallback-team']);
  };

  assertMutuallyExclusivePlan('trailblazer-harmony', 'trailblazer-preservation');
  assertMutuallyExclusivePlan('march-7th', 'march-7th-swordmaster');
});

test('HSR unknown build coverage is disclosed without becoming a low-build risk', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  const chars = ['core', 'support-a', 'support-b', 'sustain'];
  const rosterRows = chars.map((slug, index) => hsrCharacter(slug, '火', index === 0 ? 'main_dps' : index === 3 ? 'sustain' : 'support', index === 3 ? '丰饶' : '同谐', index + 1));
  const data = hsrData(rosterRows, [hsrTemplate('unknown-build-team', '4-1', chars, 1, 30)]);

  api.reset(data, {mode: 'as', scope: '4-1', riskMode: 'filter', gap: '4'}, chars, {});
  const unknown = plain(api.ranked('as', '4-1'));
  assert.equal(unknown.length, 1, 'missing build records must not be filtered as low build');
  assert.equal(unknown[0].ownedCount, 4);
  assert.equal(unknown[0].buildRecordedCount, 0);
  assert.equal(unknown[0].buildReadyCount, 0);
  assert.ok(!unknown[0].risks.some(risk => String(risk).startsWith('build-')));

  api.reset(data, {mode: 'as', scope: '4-1', riskMode: 'warn', gap: '4'}, chars, {
    core: {level: 20, lc: 20, eidolon: 0, signature: 'no', traces: 'low', relics: 'none'},
  });
  const recordedLow = plain(api.ranked('as', '4-1'))[0];
  assert.equal(recordedLow.buildRecordedCount, 1);
  assert.ok(recordedLow.risks.includes('build-low'), 'an explicitly recorded low core build must still warn');
});

test('HSR legacy and invalid recommendation settings default safely to balanced sorting', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  const fixture = endgameRankingFixture();
  api.reset(fixture.data, {mode: 'as', scope: '4-2'}, fixture.slugs, fixture.builds);
  assert.equal(plain(api.migrateSettings({})).sortMode, 'balanced');
  assert.equal(plain(api.migrateSettings({sortMode: 'invalid'})).sortMode, 'balanced');
  for (const sortMode of ['balanced', 'history', 'box']) {
    assert.equal(plain(api.migrateSettings({sortMode})).sortMode, sortMode);
  }
});

test('HSR treats Rank 0 as missing behind every positive Rank and displays it consistently', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  const validChars = ['valid-core', 'valid-a', 'valid-b', 'valid-sustain'];
  const zeroChars = ['zero-core', 'zero-a', 'zero-b', 'zero-sustain'];
  const slugs = [...validChars, ...zeroChars];
  const rosterRows = slugs.map((slug, index) => hsrCharacter(slug, '火', slug.includes('core') ? 'main_dps' : slug.includes('sustain') ? 'sustain' : 'support', '同谐', index + 1));
  const templates = [
    {...hsrTemplate('rank-zero', 'node', zeroChars, 0, 0), avg_round: 99.99},
    {...hsrTemplate('rank-valid', 'node', validChars, 10000, 0), avg_round: 99.99},
  ];
  api.reset(hsrData(rosterRows, templates), {mode: 'as', scope: 'node', sortMode: 'balanced', gap: '4'}, slugs, allBuilds(slugs, hsrFullBuild));
  const ranked = plain(api.ranked('as', 'node'));
  assert.equal(ranked[0].id, 'rank-valid');
  assert.equal(ranked[0].score, ranked[1].score, 'the regression requires an actual balanced-score tie');
  assert.equal(api.rankFacts(0).sortValue, Number.POSITIVE_INFINITY);
  assert.equal(api.rankFacts(0).display, '缺失');
  assert.equal(api.rankFacts(10000).sortValue, 10000);
  assert.equal(api.rankFacts(10000).display, '10000');

  const duplicateTemplates = [
    {...hsrTemplate('duplicate-rank-zero', '4-1', validChars, 0, 1), avg_round: 99.99},
    {...hsrTemplate('duplicate-rank-valid', '4-2', validChars, 10000, 1), avg_round: 99.99},
  ];
  api.reset(hsrData(rosterRows, duplicateTemplates), {mode: 'as', scope: 'custom-1', strategy: 'custom'}, slugs, allBuilds(slugs, hsrFullBuild));
  assert.deepEqual(plain(api.pool('as')).map(item => item.id), ['duplicate-rank-valid']);
});

test('HSR multi-team planning optimizes the selected score model instead of only reordering cards', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  const highA = ['shared-x', 'a1', 'a2', 'a3'];
  const historyB = ['shared-y', 'b1', 'b2', 'b3'];
  const highC = ['shared-y', 'c1', 'c2', 'c3'];
  const historyD = ['shared-x', 'd1', 'd2', 'd3'];
  const slugs = [...new Set([...highA, ...historyB, ...highC, ...historyD])];
  const rosterRows = slugs.map((slug, index) => hsrCharacter(slug, index % 2 ? '火' : '冰', index % 4 === 0 ? 'main_dps' : 'support', '同谐', index + 1));
  const templates = [
    {...hsrTemplate('box-left', '4-1', highA, 100, 1), avg_round: 3000},
    {...hsrTemplate('history-left', '4-1', historyB, 1, 30), avg_round: 4000},
    {...hsrTemplate('box-right', '4-2', highC, 100, 1), avg_round: 3000},
    {...hsrTemplate('history-right', '4-2', historyD, 1, 30), avg_round: 4000},
  ];
  const built = new Set([...highA, ...highC]);
  const builds = Object.fromEntries(slugs.filter(slug => built.has(slug)).map(slug => [slug, hsrFullBuild()]));
  const settings = {mode: 'as', scope: '4-1', strategy: 'final', targetScopes: {as: ['4-1', '4-2']}, gap: '4'};

  api.reset(hsrData(rosterRows, templates), {...settings, sortMode: 'box'}, slugs, builds);
  assert.deepEqual(plain(api.plan()), ['box-left', 'box-right']);
  api.reset(hsrData(rosterRows, templates), {...settings, sortMode: 'balanced'}, slugs, builds);
  assert.deepEqual(plain(api.plan()), ['box-left', 'box-right']);
  api.reset(hsrData(rosterRows, templates), {...settings, sortMode: 'history'}, slugs, builds);
  assert.deepEqual(plain(api.plan()), ['history-left', 'history-right']);
});

function zzzCharacter(slug, role, releaseOrder) {
  return {
    character_slug: slug,
    character_name_cn: slug,
    character_name_en: slug,
    element_cn: '物理',
    style_cn: role,
    role_group: role,
    role_group_cn: role,
    release_order: releaseOrder,
    icon_url: '',
  };
}

function zzzTemplate(id, scope, chars, rank, appRate, mode = 'sd') {
  return {
    id,
    mode,
    mode_cn: mode,
    scope_key: scope,
    scope_label: scope,
    chars,
    names_cn: [...chars],
    rank,
    app_rate: appRate,
    phase_name: 'test-phase',
  };
}

function zzzFullBuild() {
  return {level: 60, engine: 60, mindscape: 0, signature: 'no', skills: 'max', discs: 'great'};
}

function zzzLowBuild() {
  return {level: 20, engine: 20, mindscape: 0, signature: 'no', skills: 'low', discs: 'none'};
}

function zzzData(rosterRows, teamTemplates, tierRows = []) {
  return {rosterRows, teamTemplates, tierRows, usageRows: []};
}

test('ZZZ warn only displays risks, off keeps identical scores, and filter alone removes risky teams', () => {
  const safe = ['safe-core', 'safe-a', 'safe-b'];
  const risky = ['risky-core', 'risky-a', 'risky-b'];
  const slugs = [...safe, ...risky];
  const rosterRows = slugs.map((slug, index) => zzzCharacter(slug, slug.includes('core') ? 'crit_dps' : 'support', index + 1));
  const teamTemplates = [
    {...zzzTemplate('safe-team', 's1', safe, 10, 10), avg_score: 30_000},
    {...zzzTemplate('risky-team', 's1', risky, 10, 10), avg_score: 30_000},
  ];
  const tierRows = slugs.map(slug => ({character_slug: slug, tier_mode: 'sd', tier: slug === 'risky-core' ? 'T5' : 'T0'}));
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);

  api.reset(zzzData(rosterRows, teamTemplates, tierRows), {mode: 'sd', scope: 's1', riskMode: 'warn'}, slugs, allBuilds(slugs, zzzFullBuild));
  const warn = plain(api.ranked('sd', 's1'));
  assert.ok(warn.find(item => item.id === 'risky-team').risks.some(risk => risk.includes('T5')));

  api.reset(zzzData(rosterRows, teamTemplates, tierRows), {mode: 'sd', scope: 's1', riskMode: 'off'}, slugs, allBuilds(slugs, zzzFullBuild));
  const off = plain(api.ranked('sd', 's1'));
  assert.deepEqual(
    off.map(item => ({id: item.id, score: item.score, scores: item.scores})),
    warn.map(item => ({id: item.id, score: item.score, scores: item.scores})),
    'warn must not change any score or recommendation order relative to off',
  );

  api.reset(zzzData(rosterRows, teamTemplates, tierRows), {mode: 'sd', scope: 's1', riskMode: 'filter'}, slugs, allBuilds(slugs, zzzFullBuild));
  assert.deepEqual(plain(api.ranked('sd', 's1')).map(item => item.id), ['safe-team']);
});

test('ZZZ distinguishes unknown, T1, and T5 tiers without treating missing tier data as the worst tier', () => {
  const teams = [
    ['unknown-team', ['unknown-core', 'unknown-a', 'unknown-b']],
    ['t1-team', ['t1-core', 't1-a', 't1-b']],
    ['t5-team', ['t5-core', 't5-a', 't5-b']],
  ];
  const slugs = teams.flatMap(([, chars]) => chars);
  const rosterRows = slugs.map((slug, index) => zzzCharacter(slug, slug.includes('core') ? 'crit_dps' : 'support', index + 1));
  const templates = teams.map(([id, chars]) => ({...zzzTemplate(id, 's1', chars, 10, 10), avg_score: 30_000}));
  const tierRows = [
    {character_slug: 't1-core', tier_mode: 'sd', tier: 'T1'},
    {character_slug: 't5-core', tier_mode: 'sd', tier: 'T5'},
  ];
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);
  api.reset(zzzData(rosterRows, templates, tierRows), {mode: 'sd', scope: 's1', riskMode: 'warn'}, slugs, allBuilds(slugs, zzzFullBuild));
  const byId = Object.fromEntries(plain(api.ranked('sd', 's1')).map(item => [item.id, item]));

  assert.equal(api.tier('unknown-core', 'sd'), null);
  assert.equal(plain(api.tier('t1-core', 'sd')).tier, 'T1');
  assert.equal(plain(api.tier('t5-core', 'sd')).tier, 'T5');
  assert.deepEqual(byId['unknown-team'].risks, [], 'missing tier data is unknown evidence, not T5');
  assert.deepEqual(byId['t1-team'].risks, [], 'a fully built T1 agent does not need a low-investment warning');
  assert.ok(byId['t5-team'].risks.some(risk => risk.includes('T5')), 'an explicit T5 record remains a visible risk');
  assert.equal(byId['unknown-team'].score, byId['t1-team'].score, 'tier warnings must not silently change warn-mode scores');
  assert.equal(byId['t1-team'].score, byId['t5-team'].score, 'even an explicit T5 warning is display-only outside filter mode');
});

test('ZZZ treats unrecorded builds as neutral and penalizes only explicitly recorded low investment', () => {
  const unknown = ['unknown-core', 'unknown-a', 'unknown-b'];
  const low = ['low-core', 'low-a', 'low-b'];
  const ready = ['ready-core', 'ready-a', 'ready-b'];
  const slugs = [...unknown, ...low, ...ready];
  const rosterRows = slugs.map((slug, index) => zzzCharacter(slug, slug.includes('core') ? 'crit_dps' : 'support', index + 1));
  const templates = [
    {...zzzTemplate('unrecorded-team', 's1', unknown, 10, 10), avg_score: 30_000},
    {...zzzTemplate('low-team', 's1', low, 10, 10), avg_score: 30_000},
    {...zzzTemplate('ready-team', 's1', ready, 10, 10), avg_score: 30_000},
  ];
  const tierRows = slugs.map(slug => ({character_slug: slug, tier_mode: 'sd', tier: 'T0'}));
  const builds = {
    ...allBuilds(low, zzzLowBuild),
    ...allBuilds(ready, zzzFullBuild),
  };
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);
  api.reset(zzzData(rosterRows, templates, tierRows), {mode: 'sd', scope: 's1', riskMode: 'warn', sortMode: 'box'}, slugs, builds);
  const byId = Object.fromEntries(plain(api.ranked('sd', 's1')).map(item => [item.id, item]));

  assert.equal(byId['unrecorded-team'].recordedCount, 0);
  assert.equal(byId['low-team'].recordedCount, 3);
  assert.equal(byId['ready-team'].recordedCount, 3);
  assert.deepEqual(byId['unrecorded-team'].risks, [], 'an absent build record must not become a low-build warning');
  assert.ok(byId['low-team'].risks.every(risk => risk.includes('练度待补')));
  assert.ok(byId['ready-team'].scores.box > byId['unrecorded-team'].scores.box);
  assert.ok(byId['unrecorded-team'].scores.box > byId['low-team'].scores.box, 'unknown investment must use a neutral baseline above confirmed low investment');

  api.reset(zzzData(rosterRows, templates, tierRows), {mode: 'sd', scope: 's1', riskMode: 'filter', sortMode: 'box'}, slugs, builds);
  assert.deepEqual(
    plain(api.ranked('sd', 's1')).map(item => item.id),
    ['ready-team', 'unrecorded-team'],
    'filter mode must retain unknown build coverage and remove only the explicitly low team',
  );
});

test('ZZZ treats Rank null and zero as missing and uses positive average score only within the same mode', () => {
  const ids = ['rank-null', 'rank-zero', 'rank-one', 'score-null', 'score-zero', 'score-low', 'score-high'];
  const rosterRows = ids.flatMap((id, teamIndex) => [0, 1, 2].map(memberIndex => zzzCharacter(`${id}-${memberIndex}`, memberIndex === 0 ? 'crit_dps' : 'support', teamIndex * 3 + memberIndex)));
  const chars = id => [0, 1, 2].map(index => `${id}-${index}`);
  const templates = [
    {...zzzTemplate('rank-null', 'rank', chars('rank-null'), null, 0), avg_score: 0},
    {...zzzTemplate('rank-zero', 'rank', chars('rank-zero'), 0, 0), avg_score: 0},
    {...zzzTemplate('rank-one', 'rank', chars('rank-one'), 1, 0), avg_score: 0},
    {...zzzTemplate('score-null', 'score', chars('score-null'), 0, 0), avg_score: null},
    {...zzzTemplate('score-zero', 'score', chars('score-zero'), 0, 0), avg_score: 0},
    {...zzzTemplate('score-low', 'score', chars('score-low'), 0, 0), avg_score: 100},
    {...zzzTemplate('score-high', 'score', chars('score-high'), 0, 0), avg_score: 200},
    {...zzzTemplate('other-mode-outlier', 'score', chars('score-high'), 0, 0, 'da'), avg_score: 999_999},
  ];
  const slugs = rosterRows.map(row => row.character_slug);
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);
  api.reset(zzzData(rosterRows, templates), {mode: 'sd', scope: 'rank', sortMode: 'history'}, slugs, allBuilds(slugs, zzzFullBuild));
  const ranks = Object.fromEntries(plain(api.ranked('sd', 'rank')).map(item => [item.id, item]));
  assert.equal(ranks['rank-null'].scores.history, ranks['rank-zero'].scores.history);
  assert.ok(ranks['rank-one'].scores.history > ranks['rank-zero'].scores.history);
  assert.equal(api.rankFacts(null).positive, null);
  assert.equal(api.rankFacts(0).positive, null);
  assert.equal(api.rankFacts(1).positive, 1);

  api.reset(zzzData(rosterRows, templates), {mode: 'sd', scope: 'score', sortMode: 'history'}, slugs, allBuilds(slugs, zzzFullBuild));
  const scores = Object.fromEntries(plain(api.ranked('sd', 'score')).map(item => [item.id, item]));
  assert.equal(scores['score-null'].performance.valid, false);
  assert.equal(scores['score-zero'].performance.valid, false);
  assert.equal(scores['score-low'].performance.valid, true);
  assert.equal(scores['score-high'].performance.valid, true);
  assert.equal(scores['score-low'].performance.normalized, 0);
  assert.equal(scores['score-high'].performance.normalized, 1, 'the DA outlier must not affect SD normalization');
  assert.ok(scores['score-high'].scores.history > scores['score-low'].scores.history);
});

test('ZZZ exposes balanced, history, and Box score models with auditable additive parts', () => {
  const boxTeam = ['box-core', 'box-a', 'box-b'];
  const historyTeam = ['history-core', 'history-a', 'history-b'];
  const slugs = [...boxTeam, ...historyTeam];
  const rosterRows = slugs.map((slug, index) => zzzCharacter(slug, slug.includes('core') ? 'crit_dps' : 'support', index + 1));
  const templates = [
    {...zzzTemplate('box-team', 's1', boxTeam, 120, 1), avg_score: 10_000},
    {...zzzTemplate('history-team', 's1', historyTeam, 1, 35), avg_score: 40_000},
  ];
  const tierRows = slugs.map(slug => ({character_slug: slug, tier_mode: 'sd', tier: 'T0'}));
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);
  const index = readFileSync(ZZZ_INDEX, 'utf8');
  assert.match(index, /id="recSortSelect"/);
  for (const mode of ['balanced', 'history', 'box']) assert.match(index, new RegExp(`value="${mode}"`));
  const snapshots = {};
  for (const sortMode of ['balanced', 'history', 'box']) {
    api.reset(zzzData(rosterRows, templates, tierRows), {mode: 'sd', scope: 's1', sortMode, gap: '3'}, boxTeam, allBuilds(boxTeam, zzzFullBuild));
    snapshots[sortMode] = plain(api.ranked('sd', 's1'));
    for (const item of snapshots[sortMode]) {
      assert.equal(item.scoreMode, sortMode);
      assert.equal(item.score, item.scores[sortMode]);
      for (const mode of ['balanced', 'history', 'box']) {
        const total = item.scoreParts[mode].reduce((sum, part) => sum + (part.available ? part.value : 0), 0);
        assert.ok(Math.abs(total - item.scores[mode]) < 1e-9, `${mode} parts must add up for ${item.id}`);
      }
    }
  }
  assert.equal(snapshots.history[0].id, 'history-team');
  assert.equal(snapshots.box[0].id, 'box-team');
  assert.equal(snapshots.balanced[0].id, 'box-team');
  assert.equal(api.migrateSort({}), 'balanced');
  assert.equal(api.migrateSort({sortMode: 'invalid'}), 'balanced');
  assert.equal(api.migrateSort({sortMode: 'history'}), 'history');
});

test('ZZZ hard constraints are scope-isolated and reserved characters remove conflicting teams', () => {
  const rosterRows = [
    zzzCharacter('required', 'crit_dps', 1),
    zzzCharacter('other-required', 'anomaly_dps', 2),
    zzzCharacter('excluded', 'support', 3),
    zzzCharacter('common', 'support', 4),
    zzzCharacter('alpha', 'support', 5),
    zzzCharacter('beta', 'support', 6),
    zzzCharacter('reserved-star', 'crit_dps', 7),
    zzzCharacter('reserve-a', 'support', 8),
    zzzCharacter('reserve-b', 'support', 9),
    zzzCharacter('next-core', 'anomaly_dps', 10),
    zzzCharacter('next-a', 'support', 11),
    zzzCharacter('next-b', 'support', 12),
  ];
  const teamTemplates = [
    zzzTemplate('scope-1-valid', 's1', ['required', 'common', 'alpha'], 3, 15),
    zzzTemplate('scope-1-excluded', 's1', ['required', 'excluded', 'beta'], 1, 35),
    zzzTemplate('scope-1-missing-required', 's1', ['other-required', 'common', 'beta'], 2, 30),
    zzzTemplate('scope-2-valid', 's2', ['other-required', 'common', 'beta'], 1, 25),
    zzzTemplate('scope-2-wrong', 's2', ['required', 'common', 'alpha'], 2, 20),
    zzzTemplate('reserved-top', 's3', ['reserved-star', 'reserve-a', 'reserve-b'], 1, 35),
    zzzTemplate('reserved-next', 's3', ['next-core', 'next-a', 'next-b'], 2, 20),
  ];
  const slugs = rosterRows.map(row => row.character_slug);
  const tierRows = slugs.map(slug => ({character_slug: slug, tier_mode: 'sd', tier: 'T0'}));
  const constraints = {
    'sd|s1': {required: ['required'], excluded: ['excluded']},
    'sd|s2': {required: ['other-required'], excluded: []},
    'da|s1': {required: [], excluded: ['required']},
  };
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);
  api.reset(
    {rosterRows, teamTemplates, tierRows},
    {mode: 'sd', scope: 's1', constraints, gap: '3'},
    slugs,
    allBuilds(slugs, zzzFullBuild),
  );

  assert.deepEqual(
    plain(api.constraints('sd', 's1')),
    {required: ['required'], excluded: ['excluded']},
    'ZZZ constraints must be read from the exact scope key',
  );
  assert.deepEqual(
    plain(api.constraints('sd', 's2')),
    {required: ['other-required'], excluded: []},
    'ZZZ constraints from another scope must remain isolated',
  );
  assert.deepEqual(
    plain(api.constraints('da', 's1')),
    {required: [], excluded: ['required']},
    'ZZZ constraints from another mode must remain isolated',
  );
  assert.deepEqual(
    plain(api.ranked('sd', 's1')).map(item => item.id),
    ['scope-1-valid'],
    'ZZZ required and excluded agents must be hard filters before ranking',
  );
  assert.deepEqual(
    plain(api.ranked('sd', 's2')).map(item => item.id),
    ['scope-2-valid'],
    'ZZZ ranking a second scope must not inherit constraints from the first scope',
  );
  assert.equal(plain(api.ranked('sd', 's3'))[0].id, 'reserved-top', 'the fixture must rank the reserved team first');
  assert.equal(
    plain(api.ranked('sd', 's3', [], {reserved: ['reserved-star']}))[0].id,
    'reserved-next',
    'ZZZ reserved characters must remove a conflicting first choice and expose the next team',
  );
});

test('ZZZ supports non-contiguous target stages and recomputes the joint plan for only those stages', () => {
  const shared = ['shared-core', 'shared-support', 'shared-sustain'];
  const alternate = ['alternate-core', 'alternate-support', 'alternate-sustain'];
  const third = ['third-core', 'third-support', 'third-sustain'];
  const slugs = [...shared, ...alternate, ...third];
  const rosterRows = slugs.map((slug, index) => zzzCharacter(
    slug,
    slug.includes('core') ? 'crit_dps' : 'support',
    index + 1,
  ));
  const teamTemplates = [
    zzzTemplate('stage-1-best-shared', '1-1', shared, 1, 35, 'da'),
    zzzTemplate('stage-1-lower-alternate', '1-1', alternate, 30, 1, 'da'),
    zzzTemplate('stage-2-needs-shared', '1-2', shared, 1, 35, 'da'),
    zzzTemplate('stage-3-independent', '1-3', third, 1, 35, 'da'),
  ];
  const tierRows = slugs.map(slug => ({character_slug: slug, tier_mode: 'da', tier: 'T0'}));
  const data = {rosterRows, teamTemplates, tierRows};
  const builds = allBuilds(slugs, zzzFullBuild);
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);

  api.reset(data, {mode: 'da', scope: '1-1'}, slugs, builds);
  assert.deepEqual(plain(api.planScopes()), ['1-1', '1-2', '1-3'], 'legacy ZZZ settings must default to every concrete stage');
  assert.deepEqual(
    plain(api.plan()),
    ['stage-1-lower-alternate', 'stage-2-needs-shared', 'stage-3-independent'],
    'the three-stage model must reserve the shared agents for stage 2',
  );

  api.reset(data, {mode: 'da', scope: '1-1', targetScopes: {da: ['1-1', '1-3']}}, slugs, builds);
  assert.deepEqual(plain(api.planScopes()), ['1-1', '1-3'], 'Dangerous Assault target selection must support a non-contiguous stage subset');
  assert.deepEqual(
    plain(api.plan()),
    ['stage-1-best-shared', 'stage-3-independent'],
    'the selected-stage model must reclaim agents from the omitted stage instead of truncating the three-stage plan',
  );

  api.reset(data, {mode: 'da', scope: '1-2', targetScopes: {da: ['1-2']}}, slugs, builds);
  assert.deepEqual(plain(api.planScopes()), ['1-2'], 'Dangerous Assault must support a single-stage target');
  assert.deepEqual(plain(api.plan()), ['stage-2-needs-shared']);
});

test('ZZZ ranks each planned stage with that stage\'s own configured attributes', () => {
  const rosterRows = [
    {...zzzCharacter('fire-core', 'crit_dps', 1), element_cn: '火'},
    {...zzzCharacter('ice-core', 'crit_dps', 2), element_cn: '冰'},
    {...zzzCharacter('support-a', 'support', 3), element_cn: '物理'},
    {...zzzCharacter('support-b', 'support', 4), element_cn: '物理'},
  ];
  const teamTemplates = [
    zzzTemplate('current-fire-team', 's1', ['fire-core', 'support-a', 'support-b'], 1, 20),
    zzzTemplate('other-fire-team', 's2', ['fire-core', 'support-a', 'support-b'], 1, 20),
    zzzTemplate('other-ice-team', 's2', ['ice-core', 'support-a', 'support-b'], 1, 20),
  ];
  const slugs = rosterRows.map(row => row.character_slug);
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);
  api.reset(
    {rosterRows, teamTemplates, tierRows: slugs.map(slug => ({character_slug: slug, tier_mode: 'sd', tier: 'T0'}))},
    {mode: 'sd', scope: 's1', elements: {'sd|s1': ['火'], 'sd|s2': ['冰']}},
    slugs,
    allBuilds(slugs, zzzFullBuild),
  );

  const ranked = plain(api.ranked('sd', 's2'));
  assert.equal(ranked[0].id, 'other-ice-team', 'ranking s2 must not reuse the currently viewed s1 attribute setting');
  assert.equal(ranked[0].coreHits, 1);
  assert.equal(ranked.find(item => item.id === 'other-fire-team').coreHits, 0);
});

test('ZZZ normalizes the stale Nom alias and keeps Box cards in actual release order', () => {
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);
  const rosterRows = [
    {...zzzCharacter('ordinary', 'support', 10), character_name_cn: '普通代理人'},
    {...zzzCharacter('nom', 'support', 10_000), character_name_cn: '诺姆·霍洛维尔', source: 'banner_plan', tier: '未分档', banner_statuses: 'current', banner_phase_titles: '当期'},
    {...zzzCharacter('previous', 'support', 11), banner_statuses: 'previous'},
    {...zzzCharacter('satellite-a', 'support', 10_001), banner_statuses: 'satellite'},
    {...zzzCharacter('satellite-b', 'support', 10_002), banner_statuses: 'satellite'},
    {...zzzCharacter('next', 'support', 10_003), banner_statuses: 'next'},
    {...zzzCharacter('norma', 'support', 0), character_name_cn: '诺姆·霍洛维尔', character_name_en: 'Norma Hollowell', tier: 'T0', banner_statuses: 'previous'},
  ];
  const bannerRows = [
    {phase_id: 'previous-phase', phase_status: 'previous', character_slug: 'previous', analysis_tags: []},
    {phase_id: 'satellite-phase', phase_status: 'satellite', character_slug: 'satellite-a', analysis_tags: []},
    {phase_id: 'current-phase', phase_status: 'current', character_slug: 'nom', character_name_cn: '诺姆·霍洛维尔', analysis_tags: []},
    {phase_id: 'current-phase', phase_status: 'current', character_slug: 'norma', character_name_cn: '诺姆·霍洛维尔', analysis_tags: []},
    {phase_id: 'satellite-phase', phase_status: 'satellite', character_slug: 'satellite-b', analysis_tags: []},
    {phase_id: 'next-phase', phase_status: 'next', character_slug: 'next', analysis_tags: []},
  ];
  const data = {rosterRows, bannerRows, teamTemplates: [], tierRows: [], usageRows: []};

  const view = plain(api.identityView(data));
  assert.deepEqual(
    view.roster.filter(row => row.name === '诺姆·霍洛维尔'),
    [{slug: 'norma', name: '诺姆·霍洛维尔', statuses: 'current;previous'}],
    'the real Norma row and the stale banner-only nom row must merge into one identity',
  );
  assert.deepEqual(
    view.boxOrder,
    ['norma', 'ordinary', 'previous', 'satellite-a', 'satellite-b', 'next'],
    'Box ordering must follow release_order and must not be changed by banner status',
  );
  assert.deepEqual(
    view.bannerOrder,
    [
      {slug: 'norma', phase: 'current-phase', status: 'current'},
      {slug: 'next', phase: 'next-phase', status: 'next'},
      {slug: 'satellite-a', phase: 'satellite-phase', status: 'satellite'},
      {slug: 'satellite-b', phase: 'satellite-phase', status: 'satellite'},
      {slug: 'previous', phase: 'previous-phase', status: 'previous'},
    ],
    'banner all must use stage priority, preserve order within a stage, and dedupe one phase/identity',
  );

  const satelliteOnly = plain(api.identityView(data, {boxStatus: 'banner_satellite', bannerPhase: 'satellite'}));
  assert.deepEqual(satelliteOnly.boxOrder, ['satellite-a', 'satellite-b'], 'the existing Box stage filter must remain exact');
  assert.deepEqual(
    satelliteOnly.bannerOrder.map(row => row.slug),
    ['satellite-a', 'satellite-b'],
    'the existing banner stage filter must remain exact and stable',
  );
});

test('ZZZ Box release ordering is numeric, stable, and independent of banner status', () => {
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);
  const rosterRows = [
    {...zzzCharacter('current-old', 'support', 10), banner_statuses: 'current'},
    {...zzzCharacter('unknown-satellite', 'support', ''), banner_statuses: 'satellite'},
    {...zzzCharacter('next-mid', 'support', '5'), banner_statuses: 'next'},
    {...zzzCharacter('newest', 'support', 0)},
    {...zzzCharacter('unknown-current', 'support', 'not-known'), banner_statuses: 'current'},
    {...zzzCharacter('legacy-unknown', 'support', 9999)},
  ];

  assert.deepEqual(
    plain(api.identityView({rosterRows, bannerRows: [], teamTemplates: [], tierRows: [], usageRows: []})).boxOrder,
    ['newest', 'next-mid', 'current-old', 'legacy-unknown', 'unknown-satellite', 'unknown-current'],
    'Box must sort numeric release_order ascending, keep zero, and preserve input order for missing ties',
  );
});

test('ZZZ migrates legacy Nom Box state and scoped recommendation constraints without losing progress', () => {
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);
  const migratedBox = plain(api.migrateBox({
    owned: ['nom', 'norma', 'ally', '__codex_test__'],
    buildSlug: 'nom',
    builds: {
      nom: {level: 60, engine: 0, mindscape: 1, signature: 'yes', skills: 'high', discs: 'unset'},
      norma: {level: 40, engine: 60, mindscape: 0, signature: 'no', skills: 'max', discs: 'great'},
    },
  }));
  const expectedBuild = {level: 60, engine: 60, mindscape: 1, signature: 'yes', skills: 'max', discs: 'great'};
  assert.deepEqual(migratedBox.owned, ['ally', 'norma']);
  assert.equal(migratedBox.buildSlug, 'norma');
  assert.deepEqual(migratedBox.builds, {norma: expectedBuild});
  assert.deepEqual(
    migratedBox.payload,
    {owned: ['ally', 'norma'], buildSlug: 'norma', builds: {norma: expectedBuild}},
    'the next Box save/export must contain only the canonical identity',
  );

  const migratedConstraints = plain(api.migrateRec({
    mode: 'sd',
    scope: 's1',
    constraints: {
      'sd|s1': {required: ['nom', 'norma'], excluded: ['nom', 'other']},
      'sd|s2': {required: [], excluded: ['nom']},
    },
  }));
  assert.deepEqual(migratedConstraints, {
    'sd|s1': {required: ['norma'], excluded: ['other']},
    'sd|s2': {required: [], excluded: ['norma']},
  });
});

test('HSR Box import previews every replacement delta, rejects empty documents, and bounds undo history', () => {
  const api = loadContract(HSR_APP, HSR_HARNESS);
  const rosterRows = [
    hsrCharacter('alpha', '火', 'main_dps', '毁灭', 1),
    hsrCharacter('beta', '冰', 'support', '同谐', 2),
    hsrCharacter('gamma', '量子', 'sustain', '存护', 3),
  ];
  api.reset(
    hsrData(rosterRows, []),
    {},
    ['alpha', 'beta'],
    {
      alpha: hsrFullBuild(),
      beta: {level: 20, lc: 20, eidolon: 0, signature: 'no', traces: 'low', relics: 'none'},
    },
  );
  const preview = plain(api.boxPreview({
    version: 2,
    owned: ['beta', 'gamma'],
    builds: {
      beta: hsrFullBuild(),
      gamma: {level: 80, lc: 80, eidolon: 0, signature: 'no', traces: 'high', relics: 'good'},
    },
  }));
  assert.deepEqual(
    {
      ownedAdded: preview.ownedAdded,
      ownedRemoved: preview.ownedRemoved,
      buildAdded: preview.buildAdded,
      buildChanged: preview.buildChanged,
      buildCleared: preview.buildCleared,
    },
    {ownedAdded: 1, ownedRemoved: 1, buildAdded: 1, buildChanged: 1, buildCleared: 1},
  );
  assert.match(api.boxImportError({}), /没有 Box/);
  assert.match(api.boxImportError({version: 2}), /没有 Box/);
  assert.match(api.boxImportError({version: 2, owned: ['alpha']}), /缺少完整/);
  assert.match(api.boxImportError({version: 2, builds: {alpha: hsrFullBuild()}}), /缺少完整/);
  assert.match(api.boxImportError({version: 2, owned: [], builds: {}}), /清空整个 Box/);
  assert.deepEqual(plain(api.boxHistoryProbe(25)), {length: 20, first: 'unit-5', last: 'unit-24'});
});

test('ZZZ Box import preview canonicalizes aliases and applies the same empty-document and undo safeguards', () => {
  const api = loadContract(ZZZ_APP, ZZZ_HARNESS);
  const rosterRows = [zzzCharacter('norma', 'support', 1), zzzCharacter('beta', 'support', 2), zzzCharacter('gamma', 'support', 3)];
  api.reset(
    {rosterRows, bannerRows: [], teamTemplates: [], tierRows: [], usageRows: []},
    {},
    ['norma', 'beta'],
    {
      norma: zzzFullBuild(),
      beta: {level: 20, engine: 20, mindscape: 0, signature: 'no', skills: 'low', discs: 'none'},
    },
  );
  const preview = plain(api.boxPreview({
    version: 3,
    owned: ['beta', 'nom'],
    builds: {
      beta: zzzFullBuild(),
      nom: {level: 60, engine: 60, mindscape: 0, signature: 'no', skills: 'high', discs: 'good'},
    },
  }));
  assert.deepEqual(preview.next.owned, ['beta', 'norma']);
  assert.deepEqual(
    {
      ownedAdded: preview.ownedAdded,
      ownedRemoved: preview.ownedRemoved,
      buildAdded: preview.buildAdded,
      buildChanged: preview.buildChanged,
      buildCleared: preview.buildCleared,
    },
    {ownedAdded: 0, ownedRemoved: 0, buildAdded: 0, buildChanged: 2, buildCleared: 0},
  );
  assert.match(api.boxImportError({}), /没有 Box/);
  assert.match(api.boxImportError({version: 3, owned: ['beta']}), /缺少完整/);
  assert.match(api.boxImportError({version: 3, builds: {beta: zzzFullBuild()}}), /缺少完整/);
  assert.match(api.boxImportError({version: 3, owned: [], builds: {}}), /清空整个 Box/);
  assert.deepEqual(plain(api.boxHistoryProbe(24)), {length: 20, first: 'unit-4', last: 'unit-23'});
});

test('both visualizers read freshness from snake/camel data-quality fallbacks without blocking legacy data', () => {
  const hsr = loadContract(HSR_APP, HSR_HARNESS);
  hsr.reset({
    ...hsrData([], []),
    data_quality: {modes: {as: {freshness: {status: 'future', sample_date: '2026-08-01', source: 'fixture'}}}},
  });
  assert.deepEqual(plain(hsr.freshness('as')), {status: 'future', sampleDate: '2026-08-01', startDate: '', endDate: '', source: 'fixture'});
  assert.equal(plain(hsr.freshness('moc', {phase_status: 'expired'})).status, 'stale');

  const zzz = loadContract(ZZZ_APP, ZZZ_HARNESS);
  zzz.reset({
    rosterRows: [], bannerRows: [], teamTemplates: [], tierRows: [], usageRows: [],
    dataQuality: {modes: {da: {freshness: {status: 'unknown', sample_date: '2026-08-02', source: 'fixture-camel'}}}},
  });
  assert.deepEqual(plain(zzz.freshness('da')), {status: 'unknown', sampleDate: '2026-08-02', startDate: '', endDate: '', source: 'fixture-camel'});
  assert.equal(plain(zzz.freshness('sd', {phase_status: 'current'})).status, 'active');
});

for (const [game, appPath] of [['HSR', HSR_APP], ['ZZZ', ZZZ_APP]]) {
  test(`${game} flushBoxSave cancels debounce and waits for the real PUT`, async () => {
    const contract = loadBoxFlushContract(appPath);
    assert.equal(await contract.api.saveOne('unit-a'), '本机自动保存');
    assert.equal(contract.putCount(), 1);
    await new Promise(resolve => setTimeout(resolve, 220));
    assert.equal(contract.putCount(), 1, 'the cancelled debounce must not send a second PUT');
  });

  test(`${game} flushBoxSave rejects after a failed PUT`, async () => {
    const contract = loadBoxFlushContract(appPath, {putOk: false});
    await assert.rejects(contract.api.saveOne('unit-a'), /Box 保存失败，请重试/);
    assert.equal(contract.putCount(), 1);
  });
}
