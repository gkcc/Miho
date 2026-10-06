import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../crates/miho-core/assets/visualizer/solver.js', import.meta.url), 'utf8');

function solve(input) {
  const context = vm.createContext({});
  new vm.Script(source).runInContext(context);
  return JSON.parse(JSON.stringify(context.MihoSlateSolver.solve(input)));
}

function membersOf(lists, solution) {
  return solution.picks.flatMap((pick, scope) => pick == null ? [] : lists[scope][pick].members);
}

for (const requiredMembers of [[], ['required']]) {
  test(`three-team branch budget preserves the only complete low-ranked team (${requiredMembers.length ? 'required' : 'unconstrained'})`, () => {
    const lists = [
      [{key: 'first', score: 10, members: ['first']}],
      [
        ...Array.from({length: 240}, (_, index) => ({
          key: `dead-end-${index}`, score: 1000 - index,
          members: ['required', 'third', `extra-${index}`],
        })),
        {key: 'only-complete', score: 1, members: ['required', 'second']},
      ],
      [{key: 'third', score: 10, members: ['third']}],
    ];
    const result = solve({candidateLists: lists, requiredMembers, beamWidth: 720, branchLimit: 240, maxSolutions: 3});
    assert.deepEqual(result.solutions.map(solution => solution.picks), [[0, 240, 0]]);
    assert.equal(result.solutions[0].totalScore, 21);
    assert.equal(result.solver_meta.search_type, 'beam');
    assert.equal(result.solver_meta.exact, false);
    assert.equal(result.solver_meta.branch_limit, 240);
    const members = membersOf(lists, result.solutions[0]);
    assert.equal(new Set(members).size, members.length);
  });
}

test('required coverage on the highest bit preserves the viable first-team branch', () => {
  // Source order places required at character index 31. Bitwise operators
  // return signed integers, while the stored coverage mask is unsigned.
  const lists = [
    [
      {key: 'blocks-required', score: 100, members: ['blocker']},
      {key: 'allows-required', score: 1, members: ['free']},
    ],
    [
      ...Array.from({length: 29}, (_, index) => ({key: `ordinary-${index}`, score: 0, members: [`filler-${index}`]})),
      {key: 'required-team', score: 100, members: ['required', 'blocker']},
    ],
    [{key: 'third', score: 10, members: ['third']}],
  ];
  const result = solve({candidateLists: lists, requiredMembers: ['required'], beamWidth: 1, branchLimit: 2, maxSolutions: 1});
  assert.deepEqual(result.solutions.map(solution => solution.picks), [[1, 29, 0]]);
  assert.equal(result.solutions[0].totalScore, 111);
});

test('two-team exact search enforces every required member and preserves original indexes after exclusions', () => {
  const lists = [
    [
      {key: 'excluded', score: 1000, members: ['banned']},
      {key: 'left-required', score: 10, members: ['left', 'required-a']},
    ],
    [
      {key: 'ordinary', score: 1000, members: ['ordinary']},
      {key: 'right-required', score: 1, members: ['right', 'required-b']},
    ],
  ];
  const result = solve({candidateLists: lists, requiredMembers: ['required-a', 'required-b'], excludedMembers: ['banned']});
  assert.deepEqual(result.solutions.map(solution => solution.picks), [[1, 1]]);
  assert.equal(result.solver_meta.exact, true);
  const members = membersOf(lists, result.solutions[0]);
  assert.ok(members.includes('required-a') && members.includes('required-b'));
  assert.ok(!members.includes('banned'));
});

test('three-team search never relaxes an absent or simultaneously excluded required member', () => {
  const lists = ['first', 'second', 'third'].map(key => [{key, score: 10, members: [key]}]);
  for (const constraints of [
    {requiredMembers: ['missing']},
    {requiredMembers: ['first'], excludedMembers: ['first']},
  ]) {
    const result = solve({candidateLists: lists, ...constraints});
    assert.deepEqual(result.solutions, []);
    assert.equal(result.solver_meta.complete_solution_count, 0);
  }
});

test('valid complete solutions retain the score objective ahead of weakness metadata', () => {
  const lists = [
    [{key: 'required', score: 10, members: ['required']}],
    [
      {key: 'higher-score', score: 100, weaknessMatches: 0, members: ['second-a']},
      {key: 'more-weakness', score: 1, weaknessMatches: 100, members: ['second-b']},
    ],
    [{key: 'third', score: 10, members: ['third']}],
  ];
  const result = solve({candidateLists: lists, requiredMembers: ['required'], maxSolutions: 2});
  assert.deepEqual(result.solutions.map(solution => solution.totalScore), [120, 21]);
  assert.deepEqual(result.solutions[0].picks, [0, 0, 0]);
});

const qualityTradeoffLists = [
  [
    {key: 'strongest', score: 100, members: ['shared-a', 'shared-b']},
    {key: 'weakened', score: 50, members: ['shared-a']},
  ],
  [{key: 'second', score: 60, members: ['shared-b', 'required']}],
];

test('quality-first exact search keeps the strongest team even when every scope has candidates', () => {
  const filled = solve({candidateLists: qualityTradeoffLists, maxSolutions: 1});
  assert.deepEqual(filled.solutions.map(solution => solution.picks), [[1, 0]]);
  const quality = solve({candidateLists: qualityTradeoffLists, objective: 'quality-first', maxSolutions: 1});
  assert.deepEqual(quality.solutions.map(solution => solution.picks), [[0, null]]);
  assert.deepEqual(quality.solutions[0].sortedTeamScores, [100]);
  assert.equal(quality.solver_meta.selected_filled, 1);
  assert.equal(quality.solver_meta.complete_solution_count, 0);
  assert.equal(quality.solver_meta.partial_solution_count, 1);
  assert.deepEqual(quality.solver_meta.skipped_scope_reasons, [{scopeIndex: 1, reason: 'member_conflict'}]);
  const alternatives = solve({candidateLists: qualityTradeoffLists, objective: 'quality-first', maxSolutions: 3});
  assert.deepEqual(alternatives.solutions.map(solution => solution.picks), [[0, null], [1, 0]]);
});

test('quality-first compares descending individual scores and supplements an equal prefix', () => {
  const lists = [
    [
      {key: 'strong', score: 100, members: ['a', 'b']},
      {key: 'ordinary', score: 70, members: ['a']},
    ],
    [
      {key: 'ordinary-second', score: 80, members: ['b']},
      {key: 'supplement', score: -5, members: ['c']},
    ],
  ];
  const result = solve({candidateLists: lists, objective: 'quality-first', maxSolutions: 3});
  assert.deepEqual(result.solutions[0].picks, [0, 1]);
  assert.deepEqual(result.solutions[0].sortedTeamScores, [100, -5]);
  assert.ok(result.solutions.every(solution => solution.picks.every(pick => pick != null)), 'compatible supplements must not be omitted from alternatives');
  assert.equal(result.solutions.length, 3);
});

test('quality-first keeps global required, exclusions, and locked scopes mandatory', () => {
  for (const constraints of [
    {requiredMembers: ['required']},
    {mandatoryScopeIndexes: [1]},
    {lockedScopeIndexes: [1]},
  ]) {
    const result = solve({candidateLists: qualityTradeoffLists, objective: 'quality-first', maxSolutions: 1, ...constraints});
    assert.deepEqual(result.solutions.map(solution => solution.picks), [[1, 0]]);
  }
  for (const constraints of [
    {requiredMembers: ['missing']},
    {requiredMembers: ['required'], excludedMembers: ['required']},
    {mandatoryScopeIndexes: [1], excludedMembers: ['shared-b']},
    {mandatoryScopeIndexes: [2]},
    {mandatoryScopeIndexes: ['1']},
    {lockedScopeIndexes: '1'},
  ]) {
    assert.deepEqual(solve({candidateLists: qualityTradeoffLists, objective: 'quality-first', ...constraints}).solutions, []);
  }
});

test('quality-first exact single scope enforces required coverage and never emits an empty plan', () => {
  const lists = [[
    {key: 'high', score: 100, members: ['high']},
    {key: 'required', score: 1, members: ['required']},
  ]];
  assert.deepEqual(solve({candidateLists: lists, objective: 'quality-first', requiredMembers: ['required']}).solutions.map(solution => solution.picks), [[1]]);
  assert.deepEqual(solve({candidateLists: [[]], objective: 'quality-first'}).solutions, []);
});

test('quality-first beam fills available scopes around an empty scope, but never skips a locked empty scope', () => {
  const lists = [[{key: 'a', score: 100, members: ['a']}], [], [{key: 'b', score: 10, members: ['b']}]];
  const result = solve({candidateLists: lists, objective: 'quality-first', maxSolutions: 1});
  assert.deepEqual(result.solutions.map(solution => solution.picks), [[0, null, 0]]);
  assert.deepEqual(result.solver_meta.skipped_scope_reasons, [{scopeIndex: 1, reason: 'no_eligible_candidates'}]);
  assert.deepEqual(solve({candidateLists: lists}).solutions, []);
  assert.deepEqual(solve({candidateLists: lists, objective: 'quality-first', lockedScopeIndexes: [1]}).solutions, []);
});

test('quality-first beam preserves a stronger later team instead of filling with weaker teams', () => {
  const lists = [
    [{key: 'early', score: 90, members: ['shared']}],
    [{key: 'middle', score: 10, members: ['free']}],
    [
      {key: 'later-strong', score: 100, members: ['shared']},
      {key: 'later-weak', score: 1, members: ['other']},
    ],
  ];
  const result = solve({candidateLists: lists, objective: 'quality-first', beamWidth: 1, branchLimit: 1, maxSolutions: 1});
  assert.deepEqual(result.solutions.map(solution => solution.picks), [[null, 0, 0]]);
  assert.equal(result.solver_meta.search_type, 'beam');
  assert.equal(result.solver_meta.exact, false);
  assert.deepEqual(solve({candidateLists: lists, beamWidth: 1, branchLimit: 1, maxSolutions: 1}).solutions.map(solution => solution.picks), [[0, 0, 1]]);
});

test('quality-first beam branch pruning preserves locked scopes and global required coverage', () => {
  const lists = [
    [{key: 'first', score: 10, members: ['first']}],
    [
      ...Array.from({length: 8}, (_, index) => ({key: `blocked-${index}`, score: 100 - index, members: ['third']})),
      {key: 'required', score: 1, members: ['required']},
    ],
    [{key: 'third', score: 10, members: ['third']}],
  ];
  const result = solve({candidateLists: lists, objective: 'quality-first', mandatoryScopeIndexes: [2], requiredMembers: ['required'], beamWidth: 1, branchLimit: 1, maxSolutions: 1});
  assert.deepEqual(result.solutions.map(solution => solution.picks), [[0, 8, 0]]);
  assert.deepEqual(result.solver_meta.mandatory_scope_indexes, [2]);
});

test('quality-first beam supplements survivors without exposing dominated partial alternatives', () => {
  const independent = ['a', 'b', 'c'].map((key, index) => [{key, score: 100 - index * 10, members: [key]}]);
  assert.deepEqual(solve({candidateLists: independent, objective: 'quality-first', maxSolutions: 3}).solutions.map(solution => solution.picks), [[0, 0, 0]]);
  const lists = [
    [
      {key: 'early-blocking', score: 90, members: ['shared']},
      {key: 'early-supplement', score: 1, members: ['free']},
    ],
    [{key: 'middle', score: 10, members: ['middle']}],
    [{key: 'later-strongest', score: 100, members: ['shared']}],
  ];
  const result = solve({candidateLists: lists, objective: 'quality-first', beamWidth: 1, branchLimit: 1, maxSolutions: 1, requiredMembers: ['shared'], lockedScopeIndexes: [2]});
  assert.deepEqual(result.solutions.map(solution => solution.picks), [[1, 0, 0]]);
  assert.deepEqual(result.solutions[0].sortedTeamScores, [100, 10, 1]);
  assert.deepEqual(result.solutions[0].skippedScopes, []);
});


test('quality-first keeps two stronger teams instead of three weaker teams', () => {
  const candidateLists = [
    [{key:'strong-first',score:100,members:['a','x']},{key:'medium-first',score:80,members:['a']}],
    [{key:'strong-second',score:90,members:['b','y']},{key:'medium-second',score:80,members:['b']}],
    [{key:'medium-third',score:80,members:['x','y']}],
  ];
  assert.deepEqual(solve({candidateLists,objective:'quality-first',maxSolutions:1}).solutions[0].picks,[0,0,null]);
  assert.deepEqual(solve({candidateLists,maxSolutions:1}).solutions[0].picks,[1,1,0]);
});
