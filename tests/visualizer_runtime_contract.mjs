import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import vm from 'node:vm';

const ROOT = fileURLToPath(new URL('../', import.meta.url));
const SOLVER_PATH = path.join(ROOT, 'crates/miho-core/assets/visualizer/solver.js');
const SOLVER_SOURCE = readFileSync(SOLVER_PATH, 'utf8');

function loadRuntime(overrides = {}) {
  const context = vm.createContext({
    console,
    performance,
    setTimeout,
    clearTimeout,
    ...overrides,
  });
  vm.runInContext(SOLVER_SOURCE, context, {filename: SOLVER_PATH});
  return context.MihoSlateSolver;
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function ids(rows) {
  return rows ? Array.from(rows, (row) => row.id) : [];
}

function v2Envelope({payload = {}, tables = {}} = {}) {
  return {
    schema_version: 'miho-visualizer-data-v2',
    payload,
    tables,
  };
}

test('hydrateVisualizerData exactly restores v2 tables and preserves legacy object identity', () => {
  const {hydrateVisualizerData} = loadRuntime();
  const legacy = {
    meta: {game: 'legacy'},
    rosterRows: [{character_slug: 'legacy-alpha'}],
  };
  assert.strictEqual(hydrateVisualizerData(legacy), legacy);

  const envelope = v2Envelope({
    payload: {
      meta: {game: 'hsr', generatedAt: '2026-07-23'},
      freshness: {status: 'active'},
      nullable: null,
    },
    tables: {
      rosterRows: {
        columns: ['character_slug', 'rarity', 'owned'],
        rows: [
          ['alpha', 5, true],
          ['beta', 4, false],
        ],
      },
      teamTemplates: {
        columns: ['id', 'mode', 'scope_key', 'chars'],
        rows: [
          ['team-a', 'as', '4-1', ['alpha', 'beta']],
          ['team-b', 'pf', '4-2', ['beta', 'gamma']],
        ],
      },
    },
  });
  const before = plain(envelope);
  assert.deepEqual(plain(hydrateVisualizerData(envelope)), {
    meta: {game: 'hsr', generatedAt: '2026-07-23'},
    freshness: {status: 'active'},
    nullable: null,
    rosterRows: [
      {character_slug: 'alpha', rarity: 5, owned: true},
      {character_slug: 'beta', rarity: 4, owned: false},
    ],
    teamTemplates: [
      {id: 'team-a', mode: 'as', scope_key: '4-1', chars: ['alpha', 'beta']},
      {id: 'team-b', mode: 'pf', scope_key: '4-2', chars: ['beta', 'gamma']},
    ],
  });
  assert.deepEqual(plain(envelope), before, 'hydration must not mutate the wire envelope');
});

test('hydrateVisualizerData rejects colliding tables and malicious row widths', () => {
  const {hydrateVisualizerData} = loadRuntime();
  assert.throws(() => hydrateVisualizerData(v2Envelope({
    payload: {rosterRows: [{character_slug: 'payload'}]},
    tables: {
      rosterRows: {columns: ['character_slug'], rows: [['table']]},
    },
  })), /invalid or colliding/i);

  for (const values of [['only-one'], ['one', 'two', 'three']]) {
    assert.throws(() => hydrateVisualizerData(v2Envelope({
      tables: {
        rosterRows: {columns: ['character_slug', 'rarity'], rows: [values]},
      },
    })), /row width does not match columns/i);
  }

  assert.throws(() => hydrateVisualizerData(v2Envelope({
    tables: {
      rosterRows: {columns: ['character_slug', 'character_slug'], rows: [['alpha', 'beta']]},
    },
  })), /invalid or colliding/i);
  assert.throws(() => hydrateVisualizerData({
    ...v2Envelope(),
    unexpected: true,
  }), /unexpected fields/i);
});

test('hydrateVisualizerData preserves prototype-sensitive JSON keys as own data', () => {
  const {hydrateVisualizerData} = loadRuntime();
  const envelope = JSON.parse(JSON.stringify(v2Envelope({
    payload: {constructor: 'payload-constructor', prototype: 'payload-prototype'},
    tables: JSON.parse(`{
      "__proto__":{"columns":["__proto__","constructor","prototype"],"rows":[["row-proto","row-constructor","row-prototype"]]}
    }`),
  })));
  const before = plain(envelope);

  const hydrated = hydrateVisualizerData(envelope);
  assert.equal(Object.getPrototypeOf(hydrated), null);
  assert.equal(Object.prototype.hasOwnProperty.call(hydrated, '__proto__'), true);
  assert.equal(hydrated.constructor, 'payload-constructor');
  assert.equal(hydrated.prototype, 'payload-prototype');
  assert.deepEqual(plain(hydrated.__proto__), JSON.parse(`[
    {"__proto__":"row-proto","constructor":"row-constructor","prototype":"row-prototype"}
  ]`));
  assert.deepEqual(plain(envelope), before,
    'hydration must not mutate prototype-sensitive wire data');
});

test('buildDataIndex groups mode, scope, phase, tier, usage, and character evidence correctly', () => {
  const {buildDataIndex} = loadRuntime();
  const data = {
    rosterRows: [
      {id: 'roster-alpha-first', character_slug: 'alpha'},
      {id: 'roster-alpha-duplicate', character_slug: 'alpha'},
      {id: 'roster-beta', character_slug: 'beta'},
    ],
    teamTemplates: [
      {id: 'team-as-1', mode: 'as', scope_key: '4-1', chars: ['alpha', 'beta']},
      {id: 'team-as-2', mode: 'as', scope_key: '4-2', chars: ['beta', 'gamma']},
      {id: 'team-pf-1', mode: 'pf', scope_key: '4-1', chars: ['alpha', 'delta']},
    ],
    usageRows: [
      {id: 'usage-as-alpha', tier_mode: 'as', sub_mode: 'main_dps', character_slug: 'alpha'},
      {id: 'usage-as-beta', mode: 'as', sub_mode: 'support', character_slug: 'beta'},
      {id: 'usage-pf-alpha', tier_mode: 'pf', sub_mode: 'main_dps', character_slug: 'alpha'},
    ],
    tierRows: [
      {id: 'tier-as-alpha', tier_mode: 'as', character_slug: 'alpha'},
      {id: 'tier-as-beta', mode: 'as', character_slug: 'beta'},
      {id: 'tier-pf-alpha', tier_mode: 'pf', character_slug: 'alpha'},
    ],
    phaseInfoRows: [
      {id: 'phase-as-431', mode: 'as', phase_ver: '4.3.1'},
      {id: 'phase-as-432', mode: 'as', phase_ver: '4.3.2'},
      {id: 'phase-pf-431', mode: 'pf', phase_ver: '4.3.1'},
    ],
  };
  const index = buildDataIndex(data);

  assert.equal(index.rosterBySlug.get('alpha').id, 'roster-alpha-first');
  assert.equal(index.rosterBySlug.get('beta').id, 'roster-beta');
  assert.deepEqual(ids(index.teamsByMode.get('as')), ['team-as-1', 'team-as-2']);
  assert.deepEqual(ids(index.teamsByModeScope.get('as|4-2')), ['team-as-2']);
  assert.deepEqual(ids(index.teamsByCharacter.get('alpha')), ['team-as-1', 'team-pf-1']);
  assert.deepEqual(ids(index.teamsByCharacter.get('beta')), ['team-as-1', 'team-as-2']);

  assert.deepEqual(ids(index.usageByMode.get('as')), ['usage-as-alpha', 'usage-as-beta']);
  assert.deepEqual(ids(index.usageByModeSubMode.get('as|main_dps')), ['usage-as-alpha']);
  assert.deepEqual(ids(index.usageByModeCharacter.get('as|beta')), ['usage-as-beta']);
  assert.deepEqual(ids(index.usageByCharacter.get('alpha')), ['usage-as-alpha', 'usage-pf-alpha']);

  assert.deepEqual(ids(index.tiersByMode.get('as')), ['tier-as-alpha', 'tier-as-beta']);
  assert.deepEqual(ids(index.tiersByModeCharacter.get('pf|alpha')), ['tier-pf-alpha']);
  assert.deepEqual(ids(index.phasesByMode.get('as')), ['phase-as-431', 'phase-as-432']);
  assert.deepEqual(ids(index.phasesByModeVersion.get('as|4.3.2')), ['phase-as-432']);
  assert.equal(index.teamsByMode.get('missing'), undefined);
});

test('buildDataIndex falls back to trendRows when usageRows exists but is empty', () => {
  const {buildDataIndex} = loadRuntime();
  const index = buildDataIndex({
    usageRows: [],
    trendRows: [
      {id: 'legacy-as-alpha', tier_mode: 'as', sub_mode: 'all', character_slug: 'alpha'},
    ],
  });
  assert.deepEqual(ids(index.usageByMode.get('as')), ['legacy-as-alpha']);
  assert.deepEqual(ids(index.usageByCharacter.get('alpha')), ['legacy-as-alpha']);
});

test('cooperativeMap preserves order and yields to the event loop when its budget is exhausted', async () => {
  let clock = 0;
  let scheduledYields = 0;
  const instrumentedSetTimeout = (callback, delay, ...args) => {
    scheduledYields += 1;
    return setTimeout(callback, delay, ...args);
  };
  const {cooperativeMap} = loadRuntime({
    performance: {now: () => {
      clock += 2;
      return clock;
    }},
    setTimeout: instrumentedSetTimeout,
  });

  let outsideTimerRan = false;
  setTimeout(() => {
    outsideTimerRan = true;
  }, 0);
  const visited = [];
  const output = await cooperativeMap([5, 2, 9, 1], (value, index) => {
    visited.push([index, value]);
    return `${index}:${value * 10}`;
  }, {budgetMs: 1});

  assert.deepEqual(visited, [[0, 5], [1, 2], [2, 9], [3, 1]]);
  assert.deepEqual(Array.from(output), ['0:50', '1:20', '2:90', '3:10']);
  assert.ok(scheduledYields >= 1, 'cooperativeMap must schedule at least one main-loop yield');
  assert.equal(outsideTimerRan, true, 'an outside timer must run while cooperativeMap is awaiting its yield');
});

test('cooperativeSort preserves deterministic order while yielding between large merge slices', async () => {
  let now = 0;
  let timerYields = 0;
  const {cooperativeSort} = loadRuntime({
    performance: {now: () => {
      now += 0.4;
      return now;
    }},
    setTimeout(callback) {
      timerYields += 1;
      callback();
      return timerYields;
    },
  });
  const input = Array.from({length: 4097}, (_, index) => ({score: index % 17, key: `k-${4097 - index}`}));
  const expected = [...input].sort((left, right) => right.score - left.score || left.key.localeCompare(right.key));
  const actual = await cooperativeSort(
    input,
    (left, right) => right.score - left.score || left.key.localeCompare(right.key),
    {budgetMs: 2, chunkSize: 64},
  );
  assert.deepEqual(plain(actual), plain(expected));
  assert.ok(timerYields > 1, 'large sorts must yield repeatedly');
  assert.notStrictEqual(actual, input, 'cooperative sorting must not mutate the caller array');
});
