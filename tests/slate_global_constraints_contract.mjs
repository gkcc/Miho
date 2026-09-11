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
  return solution.picks.flatMap((pick, scope) => lists[scope][pick].members);
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
