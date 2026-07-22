(function (root) {
  'use strict';

  const DEFAULT_MAX_SOLUTIONS = 3;
  const DEFAULT_BEAM_WIDTH = 720;
  const DEFAULT_BRANCH_LIMIT = 240;

  function numeric(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function candidateOrder(left, right) {
    return numeric(right.score) - numeric(left.score)
      || numeric(right.weaknessMatches) - numeric(left.weaknessMatches)
      || String(left.key || '').localeCompare(String(right.key || ''));
  }

  function stateOrder(left, right) {
    return numeric(right.filled) - numeric(left.filled)
      || numeric(right.totalScore) - numeric(left.totalScore)
      || numeric(right.weaknessMatches) - numeric(left.weaknessMatches)
      || String(left.key || '').localeCompare(String(right.key || ''));
  }

  function buildPreparedLists(candidateLists) {
    const characterIndex = new Map();
    for (const list of candidateLists) {
      for (const candidate of list) {
        for (const member of candidate.members || []) {
          if (!characterIndex.has(member)) characterIndex.set(member, characterIndex.size);
        }
      }
    }
    const wordCount = Math.max(1, Math.ceil(characterIndex.size / 32));
    return {
      characterCount: characterIndex.size,
      wordCount,
      lists: candidateLists.map((list) => list.map((candidate, index) => {
        const mask = new Uint32Array(wordCount);
        for (const member of candidate.members || []) {
          const bit = characterIndex.get(member);
          if (bit == null) continue;
          mask[bit >>> 5] |= (1 << (bit & 31)) >>> 0;
        }
        return {
          index,
          key: String(candidate.key || index),
          teamKey: String(candidate.teamKey || candidate.key || index),
          memberSignature: JSON.stringify([...new Set(candidate.members || [])].sort()),
          score: numeric(candidate.score),
          weaknessMatches: numeric(candidate.weaknessMatches),
          mask,
        };
      }).sort(candidateOrder)),
    };
  }

  function conflicts(left, right) {
    for (let index = 0; index < left.length; index += 1) {
      if ((left[index] & right[index]) !== 0) return true;
    }
    return false;
  }

  function mergeMasks(left, right) {
    const merged = new Uint32Array(left.length);
    for (let index = 0; index < left.length; index += 1) merged[index] = left[index] | right[index];
    return merged;
  }

  function emptyState(scopeCount, wordCount) {
    return {
      picks: Array(scopeCount).fill(null),
      teamKeys: Array(scopeCount).fill(null),
      memberSignatures: Array(scopeCount).fill(null),
      mask: new Uint32Array(wordCount),
      filled: 0,
      weaknessMatches: 0,
      totalScore: 0,
      key: '',
    };
  }

  function extendState(state, scopeIndex, candidate) {
    const picks = state.picks.slice();
    const teamKeys = state.teamKeys.slice();
    const memberSignatures = state.memberSignatures.slice();
    picks[scopeIndex] = candidate.index;
    teamKeys[scopeIndex] = candidate.teamKey;
    memberSignatures[scopeIndex] = candidate.memberSignature;
    return {
      picks,
      teamKeys,
      memberSignatures,
      mask: mergeMasks(state.mask, candidate.mask),
      filled: state.filled + 1,
      weaknessMatches: state.weaknessMatches + candidate.weaknessMatches,
      totalScore: state.totalScore + candidate.score,
      key: `${state.key}|${candidate.key}`,
    };
  }

  function skipState(state) {
    return {
      ...state,
      picks: state.picks.slice(),
      teamKeys: state.teamKeys.slice(),
      memberSignatures: state.memberSignatures.slice(),
      key: `${state.key}|~`,
    };
  }

  function selectSolutions(states, maxSolutions, requiredFilled) {
    const ordered = states.slice().sort(stateOrder);
    const maxFilled = ordered[0]?.filled ?? 0;
    if (maxFilled < requiredFilled) return {solutions: [], maxFilled};
    const seen = new Set();
    const eligible = [];
    for (const state of ordered) {
      if (state.filled !== requiredFilled) break;
      const signature = state.memberSignatures.map((value) => value == null ? '~' : value).join('|');
      if (seen.has(signature)) continue;
      seen.add(signature);
      eligible.push(state);
    }
    if (!eligible.length) return {solutions: [], maxFilled};

    // Prefer alternatives that change at least one whole source team compared
    // with the first solution. Variants of the same team (for example HSR
    // substitute choices) are used only when there are not enough genuinely
    // different team slates. The selected set is sorted again afterwards so
    // the public solutions remain monotonic by the original objective.
    const selected = [eligible[0]];
    const selectedKeys = new Set([eligible[0].key]);
    const bestTeamSignature = eligible[0].teamKeys.map((key) => key == null ? '~' : key).join('|');
    for (const state of eligible.slice(1)) {
      const teamSignature = state.teamKeys.map((key) => key == null ? '~' : key).join('|');
      if (teamSignature === bestTeamSignature) continue;
      selected.push(state);
      selectedKeys.add(state.key);
      if (selected.length >= maxSolutions) break;
    }
    if (selected.length < maxSolutions) {
      for (const state of eligible.slice(1)) {
        if (selectedKeys.has(state.key)) continue;
        selected.push(state);
        selectedKeys.add(state.key);
        if (selected.length >= maxSolutions) break;
      }
    }
    return {maxFilled, solutions: selected.sort(stateOrder).map((state) => ({
        picks: state.picks,
        teamKeys: state.teamKeys,
        memberSignatures: state.memberSignatures,
        filled: state.filled,
        weaknessMatches: state.weaknessMatches,
        totalScore: state.totalScore,
        key: state.key,
      }))};
  }

  function solveExactOne(prepared, maxSolutions) {
    const base = emptyState(1, prepared.wordCount);
    const states = [skipState(base)];
    for (const candidate of prepared.lists[0] || []) states.push(extendState(base, 0, candidate));
    return selectSolutions(states, maxSolutions, 1);
  }

  function solveExactTwo(prepared, maxSolutions) {
    const [leftItems = [], rightItems = []] = prepared.lists;
    const base = emptyState(2, prepared.wordCount);
    const states = [skipState(skipState(base))];

    for (const right of rightItems.slice(0, maxSolutions)) {
      states.push(extendState(skipState(base), 1, right));
    }

    for (const left of leftItems) {
      const leftState = extendState(base, 0, left);
      states.push(skipState(leftState));
      let compatible = 0;
      const distinctTeamKeys = new Set();
      const included = new Set();
      for (const right of rightItems) {
        if (conflicts(left.mask, right.mask)) continue;
        const includeByScore = compatible < maxSolutions;
        const includeByTeam = !distinctTeamKeys.has(right.teamKey) && distinctTeamKeys.size < maxSolutions;
        if (includeByScore) compatible += 1;
        if (includeByTeam) distinctTeamKeys.add(right.teamKey);
        if ((includeByScore || includeByTeam) && !included.has(right.index)) {
          states.push(extendState(leftState, 1, right));
          included.add(right.index);
        }
        // For a fixed left candidate, retain both the ordinary Top N and the
        // first N distinct source teams so diverse alternatives stay visible.
        if (compatible >= maxSolutions && distinctTeamKeys.size >= maxSolutions) break;
      }
    }
    return selectSolutions(states, maxSolutions, 2);
  }

  function solveBeam(prepared, maxSolutions, beamWidth, branchLimit) {
    const scopeCount = prepared.lists.length;
    let states = [emptyState(scopeCount, prepared.wordCount)];
    prepared.lists.forEach((candidates, scopeIndex) => {
      const next = [];
      for (const state of states) {
        next.push(skipState(state));
        let compatible = 0;
        for (const candidate of candidates) {
          if (conflicts(state.mask, candidate.mask)) continue;
          next.push(extendState(state, scopeIndex, candidate));
          compatible += 1;
          if (compatible >= branchLimit) break;
        }
      }
      states = next.sort(stateOrder).slice(0, beamWidth);
    });
    return selectSolutions(states, maxSolutions, scopeCount);
  }

  function solve(input = {}) {
    const started = typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now();
    const candidateLists = Array.isArray(input.candidateLists)
      ? input.candidateLists.map((list) => Array.isArray(list) ? list : [])
      : [];
    const maxSolutions = Math.max(1, Math.min(10, numeric(input.maxSolutions, DEFAULT_MAX_SOLUTIONS)));
    const beamWidth = Math.max(maxSolutions, numeric(input.beamWidth, DEFAULT_BEAM_WIDTH));
    const branchLimit = Math.max(maxSolutions, numeric(input.branchLimit, DEFAULT_BRANCH_LIMIT));
    const prepared = buildPreparedLists(candidateLists);
    const scopeCount = prepared.lists.length;
    let outcome;
    let searchType;
    if (scopeCount <= 1) {
      searchType = 'exact';
      outcome = scopeCount ? solveExactOne(prepared, maxSolutions) : {solutions: [], maxFilled: 0};
    } else if (scopeCount === 2) {
      searchType = 'exact';
      outcome = solveExactTwo(prepared, maxSolutions);
    } else {
      searchType = 'beam';
      outcome = solveBeam(prepared, maxSolutions, beamWidth, branchLimit);
    }
    const ended = typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now();
    return {
      solutions: outcome.solutions,
      solver_meta: {
        search_type: searchType,
        exact: searchType === 'exact',
        scope_count: scopeCount,
        max_filled: outcome.maxFilled,
        complete_solution_count: outcome.solutions.length,
        raw_candidate_counts: Array.isArray(input.rawCandidateCounts)
          ? input.rawCandidateCounts.map((value) => numeric(value))
          : candidateLists.map((list) => list.length),
        eligible_candidate_counts: Array.isArray(input.eligibleCandidateCounts)
          ? input.eligibleCandidateCounts.map((value) => numeric(value))
          : candidateLists.map((list) => list.length),
        searched_candidate_counts: candidateLists.map((list) => list.length),
        original_candidate_counts: Array.isArray(input.originalCandidateCounts)
          ? input.originalCandidateCounts.map((value) => numeric(value))
          : candidateLists.map((list) => list.length),
        filtered_candidate_counts: candidateLists.map((list) => list.length),
        character_count: prepared.characterCount,
        beam_width: searchType === 'beam' ? beamWidth : null,
        branch_limit: searchType === 'beam' ? branchLimit : null,
        elapsed_ms: Math.max(0, ended - started),
      },
    };
  }

  const api = Object.freeze({solve});
  Object.defineProperty(root, 'MihoSlateSolver', {value: api, configurable: false, writable: false});

  if (typeof WorkerGlobalScope !== 'undefined' && root instanceof WorkerGlobalScope) {
    root.onmessage = (event) => {
      const request = event?.data || {};
      try {
        root.postMessage({requestId: request.requestId, ok: true, result: solve(request.input)});
      } catch (error) {
        root.postMessage({requestId: request.requestId, ok: false, error: String(error?.message || error)});
      }
    };
  }
})(globalThis);
