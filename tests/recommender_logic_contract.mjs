import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import test from 'node:test';
import vm from 'node:vm';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const HSR_APP = path.join(ROOT, 'crates/miho-core/assets/visualizer/hsr/app.js');
const ZZZ_APP = path.join(ROOT, 'crates/miho-core/assets/visualizer/zzz/app.js');

const HSR_HARNESS = String.raw`
;globalThis.__recommenderContract = {
  reset(data, settings = {}, owned = [], builds = {}) {
    DATA = data;
    rec = {
      mode: settings.mode || 'as',
      scope: settings.scope || '4-1',
      strategy: settings.strategy || 'final',
      teamCounts: settings.teamCounts || {...DEFAULT_REC_TEAM_COUNTS},
      targetScopes: settings.targetScopes || {},
      elements: settings.elements || {},
      constraints: settings.constraints || {},
      gap: settings.gap || '4',
      riskMode: settings.riskMode || 'warn',
      limit: settings.limit || '20',
      search: settings.search || '',
    };
    box = {...box, owned: new Set(owned), builds, buildSlug: ''};
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
      elementHits: item.elementHits,
      coreElementHits: item.coreElementHits,
      weaknessMatched: item.weaknessMatched,
      targetScope: item.targetScope,
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
    return bestRecSlatePlan(scopes).map(item => item ? {id: item.template.id, score: item.score} : null);
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
      gap: settings.gap || '3',
      riskMode: settings.riskMode || 'warn',
      limit: settings.limit || '20',
      search: settings.search || '',
    };
    box = {...box, owned: new Set(owned), builds, buildSlug: ''};
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
    return bestRecSlatePlan(recPlanScopes()).map(item => item ? {id: item.template.id, score: item.score} : null);
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
  const source = `${readFileSync(appPath, 'utf8')}\n${harness}`;
  new vm.Script(source, {filename: appPath}).runInContext(context, {timeout: 2_000});
  return context.__recommenderContract;
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

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
