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
      || numeric(right.requiredCount) - numeric(left.requiredCount)
      || numeric(right.totalScore) - numeric(left.totalScore)
      || numeric(right.weaknessMatches) - numeric(left.weaknessMatches)
      || String(left.key || '').localeCompare(String(right.key || ''));
  }

  function qualityOrder(left, right) {
    const leftScores = left.sortedTeamScores;
    const rightScores = right.sortedTeamScores;
    for (let index = 0; index < Math.min(leftScores.length, rightScores.length); index += 1) {
      if (leftScores[index] !== rightScores[index]) return rightScores[index] - leftScores[index];
    }
    return rightScores.length - leftScores.length
      || numeric(right.weaknessMatches) - numeric(left.weaknessMatches)
      || String(left.key || '').localeCompare(String(right.key || ''));
  }

  function mandatoryScopes(input, scopeCount) {
    const indexes = new Set();
    let valid = true;
    for (const values of [input.mandatoryScopeIndexes, input.lockedScopeIndexes]) {
      if (values == null) continue;
      if (!Array.isArray(values)) { valid = false; continue; }
      for (const index of values) {
        if (!Number.isInteger(index) || index < 0 || index >= scopeCount) valid = false;
        else indexes.add(index);
      }
    }
    return {indexes, valid};
  }

  function normalizedMembers(values) {
    return [...new Set((Array.isArray(values) ? values : []).map(value => String(value || '')).filter(Boolean))];
  }

  function buildPreparedLists(candidateLists, requiredMembers = [], excludedMembers = []) {
    const required = normalizedMembers(requiredMembers);
    const requiredSet = new Set(required);
    const excludedSet = new Set(normalizedMembers(excludedMembers));
    const sourceLists = candidateLists.map(list => list.map((candidate, index) => ({candidate, index})).filter(({candidate}) => (
      !(candidate.members || []).some(member => excludedSet.has(String(member || '')))
    )));
    const characterIndex = new Map();
    for (const list of sourceLists) {
      for (const {candidate} of list) {
        for (const member of candidate.members || []) {
          if (!characterIndex.has(member)) characterIndex.set(member, characterIndex.size);
        }
      }
    }
    const wordCount = Math.max(1, Math.ceil(characterIndex.size / 32));
    const requiredMask = new Uint32Array(wordCount);
    for (const member of required) {
      const bit = characterIndex.get(member);
      if (bit != null) requiredMask[bit >>> 5] |= (1 << (bit & 31)) >>> 0;
    }
    return {
      characterCount: characterIndex.size,
      wordCount,
      requiredCount: required.length,
      requiredMask,
      excludedCount: excludedSet.size,
      lists: sourceLists.map((list) => list.map(({candidate, index}) => {
        const mask = new Uint32Array(wordCount);
        const candidateMembers = new Set((candidate.members || []).map(member => String(member || '')).filter(Boolean));
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
          requiredCount: [...candidateMembers].filter(member => requiredSet.has(member)).length,
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
      requiredCount: 0,
      weaknessMatches: 0,
      totalScore: 0,
      sortedTeamScores: [],
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
      requiredCount: state.requiredCount + candidate.requiredCount,
      weaknessMatches: state.weaknessMatches + candidate.weaknessMatches,
      totalScore: state.totalScore + candidate.score,
      sortedTeamScores: [...state.sortedTeamScores, candidate.score].sort((left, right) => right - left),
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

  function supplementOptionalScopes(state, prepared) {
    if (state.requiredCount !== prepared.requiredCount
      || [...prepared.mandatoryScopeIndexes].some(index => state.picks[index] == null)) return state;
    let completed = state;
    while (true) {
      let best = null;
      let bestScope = -1;
      for (let index = 0; index < prepared.lists.length; index += 1) {
        if (completed.picks[index] != null) continue;
        const candidate = prepared.lists[index].find(item => !conflicts(completed.mask, item.mask));
        if (candidate && (!best || candidateOrder(candidate, best) < 0)) {
          best = candidate;
          bestScope = index;
        }
      }
      if (!best) return completed;
      completed = extendState(completed, bestScope, best);
    }
  }

  function selectSolutions(states, maxSolutions, prepared) {
    const requiredFilled = prepared.lists.length;
    const order = prepared.qualityFirst ? qualityOrder : stateOrder;
    const ordered = states.slice().sort(order);
    const maxFilled = states.reduce((maximum, state) => Math.max(maximum, state.filled), 0);
    if (!prepared.qualityFirst && maxFilled < requiredFilled) return {solutions: [], maxFilled};
    const seen = new Set();
    const eligible = [];
    for (const state of ordered) {
      if (!prepared.qualityFirst && state.filled !== requiredFilled) break;
      if (!state.filled || state.requiredCount !== prepared.requiredCount
        || [...prepared.mandatoryScopeIndexes].some(index => state.picks[index] == null)) continue;
      // Once hard constraints are met, adding any compatible team strictly
      // improves the shared score prefix (including a negative-score team).
      // A strict subset must not become a misleading diverse alternative.
      if (prepared.qualityFirst && state.picks.some((pick, index) => pick == null
        && prepared.lists[index].some(candidate => !conflicts(state.mask, candidate.mask)))) continue;
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
      if (selected.length >= maxSolutions) break;
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
    return {maxFilled, solutions: selected.sort(order).map((state) => ({
        picks: state.picks,
        teamKeys: state.teamKeys,
        memberSignatures: state.memberSignatures,
        filled: state.filled,
        weaknessMatches: state.weaknessMatches,
        totalScore: state.totalScore,
        sortedTeamScores: state.sortedTeamScores,
        skippedScopes: state.picks.flatMap((pick, scopeIndex) => pick != null ? [] : [{
          scopeIndex,
          reason: !prepared.lists[scopeIndex].length ? 'no_eligible_candidates'
            : prepared.lists[scopeIndex].every(candidate => conflicts(state.mask, candidate.mask))
              ? 'member_conflict' : 'quality_first_tradeoff',
        }]),
        key: state.key,
      }))};
  }

  function solveExactOne(prepared, maxSolutions) {
    const base = emptyState(1, prepared.wordCount);
    const states = [skipState(base)];
    for (const candidate of prepared.lists[0] || []) states.push(extendState(base, 0, candidate));
    return selectSolutions(states, maxSolutions, prepared);
  }

  function solveExactTwo(prepared, maxSolutions) {
    const [leftItems = [], rightItems = []] = prepared.lists;
    const base = emptyState(2, prepared.wordCount);
    const states = [skipState(skipState(base))];

    for (const right of prepared.qualityFirst ? rightItems : rightItems.slice(0, maxSolutions)) {
      states.push(extendState(skipState(base), 1, right));
    }

    for (const left of leftItems) {
      const leftState = extendState(base, 0, left);
      states.push(skipState(leftState));
      let compatible = 0;
      let requiredCompatible = 0;
      const distinctTeamKeys = new Set();
      const requiredDistinctTeamKeys = new Set();
      const included = new Set();
      for (const right of rightItems) {
        if (conflicts(left.mask, right.mask)) continue;
        const includeByScore = compatible < maxSolutions;
        const includeByTeam = !distinctTeamKeys.has(right.teamKey) && distinctTeamKeys.size < maxSolutions;
        const completesRequired = leftState.requiredCount + right.requiredCount === prepared.requiredCount;
        const includeByRequiredScore = prepared.requiredCount > 0 && completesRequired && requiredCompatible < maxSolutions;
        const includeByRequiredTeam = prepared.requiredCount > 0 && completesRequired
          && !requiredDistinctTeamKeys.has(right.teamKey) && requiredDistinctTeamKeys.size < maxSolutions;
        if (includeByScore) compatible += 1;
        if (includeByTeam) distinctTeamKeys.add(right.teamKey);
        if (includeByRequiredScore) requiredCompatible += 1;
        if (includeByRequiredTeam) requiredDistinctTeamKeys.add(right.teamKey);
        if ((includeByScore || includeByTeam || includeByRequiredScore || includeByRequiredTeam) && !included.has(right.index)) {
          states.push(extendState(leftState, 1, right));
          included.add(right.index);
        }
        // For a fixed left candidate, retain both the ordinary Top N and the
        // first N distinct source teams so diverse alternatives stay visible.
        const ordinaryFilled = compatible >= maxSolutions && distinctTeamKeys.size >= maxSolutions;
        const requiredFilled = prepared.requiredCount === 0
          || (requiredCompatible >= maxSolutions && requiredDistinctTeamKeys.size >= maxSolutions);
        if (ordinaryFilled && requiredFilled) break;
      }
    }
    return selectSolutions(states, maxSolutions, prepared);
  }

  function addsRequiredCoverage(state, candidate, requiredMask) {
    for (let index = 0; index < requiredMask.length; index += 1) {
      if ((candidate.mask[index] & requiredMask[index] & ~state.mask[index]) !== 0) return true;
    }
    return false;
  }

  function requiredCoverageRemainsPossible(state, remainingLists, requiredMask, requiredCount) {
    if (state.requiredCount === requiredCount) return true;
    if (!remainingLists.length) return false;
    const possible = new Uint32Array(state.mask);
    for (const list of remainingLists) {
      for (const candidate of list) {
        if (conflicts(state.mask, candidate.mask)) continue;
        for (let index = 0; index < possible.length; index += 1) possible[index] |= candidate.mask[index];
      }
    }
    for (let index = 0; index < requiredMask.length; index += 1) {
      if (((possible[index] & requiredMask[index]) >>> 0) !== requiredMask[index]) return false;
    }
    return true;
  }

  function solveBeam(prepared, maxSolutions, beamWidth, branchLimit) {
    const scopeCount = prepared.lists.length;
    let states = [emptyState(scopeCount, prepared.wordCount)];
    prepared.lists.forEach((candidates, scopeIndex) => {
      const next = [];
      const remainingLists = prepared.lists.slice(scopeIndex + 1);
      const remainsViable = state => remainingLists.every((list, index) => (
        prepared.qualityFirst && !prepared.mandatoryScopeIndexes.has(scopeIndex + index + 1)
      ) || list.some(candidate => !conflicts(state.mask, candidate.mask)))
        && requiredCoverageRemainsPossible(state, remainingLists, prepared.requiredMask, prepared.requiredCount);
      // Rank partial quality-first paths by a compatible future upper bound.
      // Otherwise an early ordinary team can evict the skip needed to keep a
      // much stronger later team. Future candidates may still conflict with
      // each other, so this remains an explicitly approximate beam search.
      const optimisticStates = new WeakMap();
      const optimistic = state => {
        if (optimisticStates.has(state)) return optimisticStates.get(state);
        const upperBound = {...state, sortedTeamScores: [
          ...state.sortedTeamScores,
          ...remainingLists.flatMap(list => {
            const best = list.find(candidate => !conflicts(state.mask, candidate.mask));
            return best ? [best.score] : [];
          }),
        ].sort((a, b) => b - a)};
        optimisticStates.set(state, upperBound);
        return upperBound;
      };
      const beamOrder = prepared.qualityFirst ? (left, right) => (
        qualityOrder(optimistic(left), optimistic(right)) || qualityOrder(left, right)
      ) : stateOrder;
      for (const state of states) {
        if (!prepared.mandatoryScopeIndexes.has(scopeIndex)) {
          const skipped = skipState(state);
          if (!prepared.qualityFirst || remainsViable(skipped)) next.push(skipped);
        }
        let compatible = 0;
        let requiredCompatible = 0;
        let blockedCompatible = 0;
        for (const candidate of candidates) {
          if (conflicts(state.mask, candidate.mask)) continue;
          const extended = extendState(state, scopeIndex, candidate);
          // Dead ends must not consume the branch budget before a lower-ranked
          // candidate can preserve a complete slate and its required members.
          // Retain a bounded sample only for incomplete-search diagnostics.
          if (!remainsViable(extended)) {
            if (!prepared.qualityFirst && blockedCompatible < branchLimit) next.push(extended);
            blockedCompatible += 1;
            continue;
          }
          const includeByScore = compatible < branchLimit;
          const includeByRequired = prepared.requiredCount > state.requiredCount
            && addsRequiredCoverage(state, candidate, prepared.requiredMask)
            && requiredCompatible < branchLimit;
          if (includeByScore) compatible += 1;
          if (includeByRequired) requiredCompatible += 1;
          if (includeByScore || includeByRequired) next.push(extended);
          const requiredFilled = prepared.requiredCount === state.requiredCount || requiredCompatible >= branchLimit;
          if (compatible >= branchLimit && requiredFilled) break;
        }
      }
      if (!remainingLists.length) {
        states = next.sort(prepared.qualityFirst ? qualityOrder : stateOrder).slice(0, beamWidth);
        return;
      }
      const viable = [];
      const blocked = [];
      for (const state of next) {
        const target = remainsViable(state) ? viable : blocked;
        target.push(state);
      }
      states = [...viable.sort(beamOrder), ...blocked.sort(beamOrder)].slice(0, beamWidth);
    });
    // The bounded beam may have dropped a low-ranked compatible supplement
    // in an earlier scope. Complete surviving valid states before dominance
    // filtering, preserving their stronger teams and every hard constraint.
    if (prepared.qualityFirst) states = states.map(state => supplementOptionalScopes(state, prepared));
    return selectSolutions(states, maxSolutions, prepared);
  }

  function solve(input = {}) {
    const started = typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now();
    const candidateLists = Array.isArray(input.candidateLists)
      ? input.candidateLists.map((list) => Array.isArray(list) ? list : [])
      : [];
    const maxSolutions = Math.max(1, Math.min(10, numeric(input.maxSolutions, DEFAULT_MAX_SOLUTIONS)));
    const beamWidth = Math.max(maxSolutions, numeric(input.beamWidth, DEFAULT_BEAM_WIDTH));
    const branchLimit = Math.max(maxSolutions, numeric(input.branchLimit, DEFAULT_BRANCH_LIMIT));
    const prepared = buildPreparedLists(candidateLists, input.requiredMembers, input.excludedMembers);
    const scopeCount = prepared.lists.length;
    const mandatory = mandatoryScopes(input, scopeCount);
    prepared.mandatoryScopeIndexes = mandatory.indexes;
    prepared.qualityFirst = input.objective === 'quality-first';
    let outcome;
    let searchType;
    if (!mandatory.valid || [...mandatory.indexes].some(index => !prepared.lists[index].length)) {
      searchType = scopeCount <= 2 ? 'exact' : 'beam';
      outcome = {solutions: [], maxFilled: 0};
    } else if (scopeCount <= 1) {
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
        objective: prepared.qualityFirst ? 'quality-first' : 'fill-first',
        mandatory_scope_indexes: [...mandatory.indexes].sort((a, b) => a - b),
        invalid_mandatory_scope_indexes: !mandatory.valid,
        max_filled: outcome.maxFilled,
        solution_count: outcome.solutions.length,
        complete_solution_count: outcome.solutions.filter(solution => solution.filled === scopeCount).length,
        partial_solution_count: outcome.solutions.filter(solution => solution.filled < scopeCount).length,
        selected_filled: outcome.solutions[0]?.filled ?? 0,
        skipped_scope_reasons: outcome.solutions[0]?.skippedScopes || [],
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
        required_member_count: prepared.requiredCount,
        excluded_member_count: prepared.excludedCount,
        beam_width: searchType === 'beam' ? beamWidth : null,
        branch_limit: searchType === 'beam' ? branchLimit : null,
        elapsed_ms: Math.max(0, ended - started),
      },
    };
  }

  function hydrateVisualizerData(raw) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)
      || raw.schema_version !== 'miho-visualizer-data-v2') return raw;
    const rootKeys = Object.keys(raw).sort();
    if (JSON.stringify(rootKeys) !== JSON.stringify(['payload', 'schema_version', 'tables'])) {
      throw new Error('Visualizer data v2 envelope has unexpected fields.');
    }
    if (!raw.payload || typeof raw.payload !== 'object' || Array.isArray(raw.payload)
      || !raw.tables || typeof raw.tables !== 'object' || Array.isArray(raw.tables)) {
      throw new Error('Visualizer data v2 payload or tables are invalid.');
    }
    const expanded = Object.create(null);
    for (const [name, value] of Object.entries(raw.payload)) {
      Object.defineProperty(expanded, name, {
        value,
        enumerable: true,
        configurable: true,
        writable: true,
      });
    }
    for (const [name, table] of Object.entries(raw.tables)) {
      if (Object.prototype.hasOwnProperty.call(expanded, name)
        || !table || typeof table !== 'object' || Array.isArray(table)
        || JSON.stringify(Object.keys(table).sort()) !== JSON.stringify(['columns', 'rows'])
        || !Array.isArray(table.columns) || !table.columns.length
        || table.columns.some(column => typeof column !== 'string')
        || new Set(table.columns).size !== table.columns.length
        || !Array.isArray(table.rows)) {
        throw new Error('Visualizer data v2 table is invalid or colliding.');
      }
      const rows = table.rows.map(values => {
        if (!Array.isArray(values) || values.length !== table.columns.length) {
          throw new Error('Visualizer data v2 row width does not match columns.');
        }
        return Object.fromEntries(table.columns.map((column, index) => [column, values[index]]));
      });
      Object.defineProperty(expanded, name, {
        value: rows,
        enumerable: true,
        configurable: true,
        writable: true,
      });
    }
    return expanded;
  }

  function pushIndex(map, key, value) {
    if (key == null || key === '') return;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(value);
  }

  function buildDataIndex(data = {}) {
    const rosterBySlug = new Map();
    for (const row of data.rosterRows || []) {
      const slug = String(row?.character_slug || '');
      if (slug && !rosterBySlug.has(slug)) rosterBySlug.set(slug, row);
    }
    const teamsByMode = new Map();
    const teamsByModeScope = new Map();
    const teamsByCharacter = new Map();
    for (const row of data.teamTemplates || []) {
      const mode = String(row?.mode || '');
      const scope = String(row?.scope_key || '');
      pushIndex(teamsByMode, mode, row);
      pushIndex(teamsByModeScope, `${mode}|${scope}`, row);
      for (const slug of row?.chars || []) pushIndex(teamsByCharacter, String(slug || ''), row);
    }
    const usageByMode = new Map();
    const usageByModeSubMode = new Map();
    const usageByModeCharacter = new Map();
    const usageByCharacter = new Map();
    const usageRows = Array.isArray(data.usageRows) && data.usageRows.length
      ? data.usageRows
      : (Array.isArray(data.trendRows) ? data.trendRows : []);
    for (const row of usageRows) {
      const mode = String(row?.tier_mode || row?.mode || '');
      const subMode = String(row?.sub_mode || '');
      const slug = String(row?.character_slug || '');
      pushIndex(usageByMode, mode, row);
      pushIndex(usageByModeSubMode, `${mode}|${subMode}`, row);
      pushIndex(usageByModeCharacter, `${mode}|${slug}`, row);
      pushIndex(usageByCharacter, slug, row);
    }
    const tiersByMode = new Map();
    const tiersByModeCharacter = new Map();
    for (const row of data.tierRows || []) {
      const mode = String(row?.tier_mode || row?.mode || '');
      const slug = String(row?.character_slug || '');
      pushIndex(tiersByMode, mode, row);
      pushIndex(tiersByModeCharacter, `${mode}|${slug}`, row);
    }
    const phasesByMode = new Map();
    const phasesByModeVersion = new Map();
    for (const row of data.phaseInfoRows || []) {
      const mode = String(row?.mode || '');
      const version = String(row?.phase_ver || '');
      pushIndex(phasesByMode, mode, row);
      pushIndex(phasesByModeVersion, `${mode}|${version}`, row);
    }
    return Object.freeze({
      rosterBySlug,
      teamsByMode,
      teamsByModeScope,
      teamsByCharacter,
      usageByMode,
      usageByModeSubMode,
      usageByModeCharacter,
      usageByCharacter,
      tiersByMode,
      tiersByModeCharacter,
      phasesByMode,
      phasesByModeVersion,
    });
  }

  function yieldToMain() {
    return new Promise(resolve => setTimeout(resolve, 0));
  }

  function runtimeNow() {
    return typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now();
  }

  async function cooperativeMap(items, mapper, options = {}) {
    const budgetMs = Math.max(1, numeric(options.budgetMs, 8));
    const output = [];
    let sliceStarted = runtimeNow();
    for (let index = 0; index < items.length; index += 1) {
      output.push(mapper(items[index], index));
      const now = runtimeNow();
      if (now - sliceStarted >= budgetMs && index + 1 < items.length) {
        await yieldToMain();
        sliceStarted = runtimeNow();
      }
    }
    return output;
  }

  async function cooperativeFlatMap(items, mapper, options = {}) {
    const nested = await cooperativeMap(items, mapper, options);
    return nested.flat();
  }

  async function cooperativeSort(items, comparator, options = {}) {
    const budgetMs = Math.max(1, numeric(options.budgetMs, 8));
    const chunkSize = Math.max(32, Math.floor(numeric(options.chunkSize, 512)));
    let source = Array.from(items || []);
    if (source.length < 2) return source;
    let sliceStarted = runtimeNow();
    for (let start = 0; start < source.length; start += chunkSize) {
      const end = Math.min(source.length, start + chunkSize);
      const sorted = source.slice(start, end).sort(comparator);
      for (let index = 0; index < sorted.length; index += 1) source[start + index] = sorted[index];
      if (runtimeNow() - sliceStarted >= budgetMs && end < source.length) {
        await yieldToMain();
        sliceStarted = runtimeNow();
      }
    }
    let target = new Array(source.length);
    for (let width = chunkSize; width < source.length; width *= 2) {
      for (let start = 0; start < source.length; start += width * 2) {
        const middle = Math.min(source.length, start + width);
        const end = Math.min(source.length, middle + width);
        let left = start;
        let right = middle;
        let output = start;
        while (left < middle || right < end) {
          if (right >= end || (left < middle && comparator(source[left], source[right]) <= 0)) {
            target[output] = source[left];
            left += 1;
          } else {
            target[output] = source[right];
            right += 1;
          }
          output += 1;
          if ((output & 511) === 0 && runtimeNow() - sliceStarted >= budgetMs) {
            await yieldToMain();
            sliceStarted = runtimeNow();
          }
        }
      }
      [source, target] = [target, source];
      if (runtimeNow() - sliceStarted >= budgetMs && width * 2 < source.length) {
        await yieldToMain();
        sliceStarted = runtimeNow();
      }
    }
    return source;
  }

  const api = Object.freeze({
    solve,
    hydrateVisualizerData,
    buildDataIndex,
    cooperativeMap,
    cooperativeFlatMap,
    cooperativeSort,
    yieldToMain,
  });
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

// Encounter advice is a bounded suitability estimate, never a damage simulation.
(function (root) {
  'use strict';
  const LABELS = {break:'击破',follow_up:'追加攻击',dot:'持续伤害',ultimate:'终结技',aoe:'群体',anomaly:'异常',disorder:'紊乱',crit:'直伤暴击',rupture:'锐化（命破）',stun:'失衡窗口'};
  const ALIASES = {fua:'follow_up','follow-up':'follow_up','追加攻击':'follow_up','击破':'break','持续伤害':'dot',DoT:'dot','终结技':'ultimate','群体':'aoe','异常':'anomaly','紊乱':'disorder','暴击':'crit','贯穿':'rupture','锐化':'rupture','锐化伤害':'rupture','失衡':'stun'};
  const signature = chars => JSON.stringify([...new Set((chars || []).map(String))].sort());
  const tags = values => [...new Set((Array.isArray(values) ? values : String(values || '').split(/[;,|]/)).map(value => {const normalized=String(value).trim().toLowerCase();return ALIASES[value] || ALIASES[normalized] || normalized;}).filter(value => LABELS[value]))];
  const safeUrl = value => /^https?:\/\//i.test(String(value || '')) ? String(value) : '';
  function rows(data, game, mode) {
    return (data?.encounterRows || []).filter(row => row && row.game === game && row.mode === mode && typeof row.scope_key === 'string' && row.scope_key);
  }
  function targetPhase(data, row) {
    if (!row.phase_ver || !row.start_date || !row.end_date) return {};
    const matches = (data?.phaseInfoRows || []).filter(phase => phase.mode === row.mode && String(phase.phase_ver || '') === String(row.phase_ver || '') && phase.start_date === row.start_date && phase.end_date === row.end_date);
    const official = matches.filter(phase => /第[0-9一二三四五六七八九十百]+期/.test(phase.phase_name_cn || ''));
    const names = [...new Set(official.map(phase => phase.phase_name_cn))];
    return names.length === 1 ? official[0] : matches.length === 1 ? matches[0] : {};
  }
  function targetStatus(row, today) {
    const valid = value => /^\d{4}-\d{2}-\d{2}$/.test(String(value || ''));
    if (valid(row.start_date) && row.start_date > today) return 'future';
    if (valid(row.end_date) && row.end_date < today) return 'expired';
    if (valid(row.start_date) && valid(row.end_date)) return 'current';
    return ['current','expired','future'].includes(row.phase_status) ? row.phase_status : 'unknown';
  }
  function targetLabel(data, row) {
    if (row.user_provided) return row.label || '自定义敌情';
    const phase = targetPhase(data,row), dates = row.start_date && row.end_date ? `${row.start_date} — ${row.end_date}` : '日期未知';
    if (row.game === 'zzz' && row.mode === 'sd') {
      const numerals = ['零','一','二','三','四','五','六','七','八','九','十'], floor = String(row.floor || ''), defense = /^[1-9]$|^10$/.test(floor) ? `第${numerals[Number(floor)]}防线` : String(row.label || '').split(' · ')[0].replace(/第(\d+)防线/,(_,value)=>`第${numerals[Number(value)] || value}防线`);
      const side = String(row.label || '').split(' · ').slice(1).join(' · ') || '队伍 / 房间未知';
      return `剧变节点 · ${defense || '防线未知'} · ${side} · ${dates}`;
    }
    if (row.game === 'zzz' && row.mode === 'da') {
      const issue = String(phase.phase_name_cn || '').match(/第[0-9一二三四五六七八九十百]+期/)?.[0] || '期数未知';
      const label = String(row.label || ''), difficulty = label.match(/试炼强敌|绝境强敌/)?.[0] || '难度未知', boss = (row.enemies || []).map(enemy=>enemy.name).filter(Boolean).join(' / ') || (row.quality_status==='phase_only' ? 'Boss 未知' : label.replace(/^(?:试炼强敌|绝境强敌)\s*·\s*/, '') || 'Boss 未知');
      return `危局强袭战 · ${issue} · ${boss} · ${difficulty} · ${dates}`;
    }
    const theme = String(phase.phase_name_cn || (/[\u4e00-\u9fff]/.test(phase.phase_name || '') ? phase.phase_name : '') || '').trim(), label = row.label || '关卡名称未知';
    return `${theme && !theme.includes(row.phase_ver || '\u0000') && !label.includes(theme) ? `${theme} · ` : ''}${label} · ${dates}`;
  }
  function targetGroups(data, game, mode, today) {
    const all = rows(data,game,mode).slice().sort((left,right)=>String(right.start_date || '').localeCompare(String(left.start_date || '')) || String(right.end_date || '').localeCompare(String(left.end_date || '')) || String(left.scope_key).localeCompare(String(right.scope_key),undefined,{numeric:true}));
    return {current:all.filter(row=>targetStatus(row,today)==='current'),other:all.filter(row=>['future','unknown'].includes(targetStatus(row,today))),history:all.filter(row=>targetStatus(row,today)==='expired')};
  }
  function profile(data, game, members, mode = '') {
    const chars = members.map(member => member.slug), exact = (data?.teamProfileRows || []).find(row => (!row.game || row.game === game) && (!row.mode || row.mode === mode) && signature(row.chars) === signature(chars));
    if (exact && safeUrl(exact.source_url) && exact.inferred !== true && ['A','B'].includes(exact.evidence_grade)) {
      const primary = tags(exact.primary_tags), secondary = tags(exact.secondary_tags).filter(tag => !primary.includes(tag));
      return {primary,secondary,inferred:false,source_url:safeUrl(exact.source_url),unknown:primary.length ? [] : ['队伍主导伤害类型未确认']};
    }
    const core = members.filter(member => member.core || /(?:crit_dps|anomaly_dps|rupture_dps)/.test(member.info?.role_group || '') || member.info?.style_cn === '命破' || game==='hsr' && /(?:^|;)(?:main_dps|sub_dps)(?:;|$)/.test(member.info?.role_groups || ''));
    const perCore = core.map(member => {
      const info = member.info || {}, explicit = tags(info.damage_tags || info.combat_tags || []), roles = String(info.role_groups || info.role_group || '');
      if (game === 'zzz') {
        if(info.style_cn==='命破') {explicit.splice(0,explicit.length,...explicit.filter(tag=>!['crit','anomaly','disorder'].includes(tag)),'rupture');}
        else {
          if (roles.includes('anomaly_dps') || info.style_cn === '异常') explicit.push('anomaly');
          if (roles.includes('crit_dps') || info.style_cn === '强攻') explicit.push('crit');
          if (roles.includes('rupture_dps')) explicit.push('rupture');
        }
      } else {
        for (const [pattern,tag] of [[/break|击破/,'break'],[/follow_up|followup|fua|追加/,'follow_up'],[/dot|持续伤害/,'dot'],[/ultimate|终结技/,'ultimate'],[/aoe|群体/,'aoe']]) if (pattern.test(roles)) explicit.push(tag);
      }
      return [...new Set(explicit)];
    });
    const all = [...new Set(perCore.flat())], primary = all.filter(tag => perCore.length && perCore.every(row => row.includes(tag))), secondary = all.filter(tag => !primary.includes(tag));
    if (game === 'zzz' && members.some(member => member.info?.style_cn === '击破' || member.info?.role_group === 'stun')) secondary.push('stun');
    // Two different anomaly elements permit disorder; a single anomaly member does not describe the party.
    if (game === 'zzz' && core.filter((member,index) => perCore[index].includes('anomaly')).length >= 2 && new Set(core.filter((member,index) => perCore[index].includes('anomaly')).map(member => member.info?.element_cn).filter(Boolean)).size >= 2) secondary.push('disorder');
    const unknown = ['画像来自角色标签推断，队伍伤害占比与实战轴未确认'];
    if (!primary.length) unknown.push('队伍主导伤害类型未知');
    if (perCore.some(row => !row.length) || !core.length) unknown.push('部分输出角色缺少伤害类型资料');
    return {primary,secondary:[...new Set(secondary)],inferred:true,source_url:'',tag_sources:[...new Set(core.map(member=>safeUrl(member.info?.tag_source_url)).filter(Boolean))],unknown};
  }
  function parseEffect(effect, encounter) {
    const text = String(effect?.text || '').trim();
    const enemyBound = effect?.scope === 'enemy' && (encounter.enemies || []).length === 1 && (!effect.enemy_id || String(encounter.enemies[0].id) === String(effect.enemy_id));
    if ((effect?.verified !== true && !((encounter.user_provided === true || encounter.user_input_overlay === true) && effect?.user_confirmed === true)) || !text || !(['phase','encounter'].includes(effect.scope) || enemyBound)) return {unknown:text || effect?.name || '未核验机制'};
    // Choice, uptime, enemy attacks and conditional phases must never become permanent party buffs.
    if (/当|如果|每|后|前|期间|条件|阶段|状态|层|秒|回合|持续|触发|累计|至多|最多|至少|交替|选择|任选|敌人造成|敌方造成|我方受到|角色受到|敌人伤害|攻击力|受到的伤害降低|所受伤害降低/.test(text.replace(/持续伤害/g,'DOT'))) return {unknown:text};
    const percentages = text.match(/\d+(?:\.\d+)?\s*[%％]/g) || [];
    if (percentages.length !== 1) return {unknown:text};
    const subject = '(?:(?:全体|所有)?(?:我方)?(?:代理人|角色)(?:的)?(?:造成)?(?:的)?|我方(?:造成)?(?:的)?|造成(?:的)?|(?:全体|所有)?(?:敌人|敌方目标|敌方)受到(?:的)?)?';
    const category = '((?:所有|全部|全)?伤害|击破伤害|(?:追加攻击|追击|终结技|群体|对群|属性异常|异常|紊乱|暴击|锐化|贯穿)(?:的)?伤害|持续伤害|(?:物理|火|冰|雷|风|量子|虚数|电|以太)(?:属性)?(?:的)?伤害)';
    // Match the complete supported phrase. Recognizing an element inside an unknown
    // qualifier (for example summon or counter damage) does not establish party coverage.
    const match = text.replace(/\s+/g,'').match(new RegExp(`^${subject}${category}(?:的)?(提升|提高|增加|降低|减少)(?:了)?(\\d+(?:\\.\\d+)?)\\s*[%％][。.!！]?$`));
    if (!match) return {unknown:text};
    const tagPatterns = [[/击破伤害/,'break'],[/追加攻击|追击伤害/,'follow_up'],[/DOT|持续伤害/,'dot'],[/终结技/,'ultimate'],[/群体伤害|对群伤害/,'aoe'],[/异常伤害|属性异常/,'anomaly'],[/紊乱/,'disorder'],[/暴击/,'crit'],[/锐化|贯穿/,'rupture']];
    const normalizedCategory = match[1].replace(/的/g,'');
    const parsedText = normalizedCategory.replace(/持续伤害/g,'DOT'), matchedTags = tagPatterns.filter(([pattern]) => pattern.test(parsedText)).map(([,tag]) => tag);
    const element = ['物理','火','冰','雷','风','量子','虚数','电','以太'].find(value => new RegExp(`^${value}(?:属性)?伤害$`).test(normalizedCategory));
    if(!matchedTags.length&&!element&&!/^(?:所有|全部|全)?伤害$/.test(normalizedCategory))return{unknown:text};
    const direction = /降低|减少/.test(match[0]) ? -1 : 1;
    return {text,tag:matchedTags[0] || '',element:element || '',value:Math.min(100,Number(match[3])) * .9 * direction};
  }
  function records(data, encounter, chars) {
    return (data?.battleRecordRows || []).filter(row => {
      const value = Number(row.metric_value);
      return row.game === encounter.game && row.mode === encounter.mode && String(row.phase_ver) === String(encounter.phase_ver) && row.encounter_key === encounter.scope_key && signature(row.chars) === signature(chars) && row.chars?.length === chars.length && row.is_quick_clear === false && ['A','B'].includes(row.evidence_grade) && safeUrl(row.source_url) && ['encounter','floor','node','stage','side'].includes(row.metric_scope) && ['score','points','cycles','rounds','duration','seconds','clear_time'].includes(row.metric_kind) && Number.isFinite(value) && (value > 0 || value === 0 && row.metric_kind==='cycles') && Math.abs(value-99.99) > .001;
    });
  }
  function evaluate(data, encounter, members) {
    const image = profile(data,encounter.game,members,encounter.mode), reasons = [], unknown = [...image.unknown], parts = [], core = members.filter(member => member.core || member.info?.style_cn === '命破');
    const weaknessHits = core.filter(member => (encounter.weaknesses || []).includes(member.info?.element_cn));
    const resistanceHits = core.filter(member => (encounter.resistances || []).includes(member.info?.element_cn));
    if ((encounter.weaknesses || []).length && core.length) {
      const value = weaknessHits.length ? 28 : -16, detail = weaknessHits.length ? '核心输出命中敌方弱点' : '核心输出未命中弱点，仍可由词缀或实战证据补足';
      parts.push({key:'encounter-weakness',label:'关卡弱点',value,detail,available:true});reasons.push(detail);
    }
    if (resistanceHits.length) {
      const detail = `核心输出遇到抗性：${[...new Set(resistanceHits.map(member => member.info.element_cn))].join(' / ')}（未提供抗性倍率）`;
      parts.push({key:'encounter-resistance',label:'敌方抗性',value:-55 * resistanceHits.length / Math.max(1,core.length),detail,available:true});reasons.push(detail);
    }
    const dimensions = new Map();
    for (const effect of encounter.effects || []) {
      const parsed = parseEffect(effect,encounter);
      if (parsed.unknown) {unknown.push(parsed.unknown);continue;}
      const weight = parsed.tag ? image.primary.includes(parsed.tag) ? 1 : image.secondary.includes(parsed.tag) ? .35 : image.primary.length ? 0 : null : parsed.element ? core.length ? core.filter(member => member.info?.element_cn === parsed.element).length / core.length : null : 1;
      if (weight == null) {unknown.push(`${parsed.text}：队伍资料不足，未计分`);continue;}
      if (!weight) {reasons.push(`未匹配：${parsed.text}`);continue;}
      const dimension = parsed.tag || parsed.element || 'all', value = parsed.value * weight * (parsed.tag && image.inferred ? .7 : 1), old = dimensions.get(dimension) || {positive:0,negative:0,texts:[]};
      old.positive = Math.max(old.positive,value);old.negative = Math.min(old.negative,value);old.texts.push(parsed.text);dimensions.set(dimension,old);
    }
    let effectValue = 0;
    for (const dimension of dimensions.values()) {effectValue += dimension.positive + dimension.negative;reasons.push(`${dimension.negative < 0 ? '冲突' : '适配'}：${dimension.texts.join('；')}`);}
    if (dimensions.size) parts.push({key:'encounter-effects',label:'词缀适配',value:Math.max(-150,Math.min(150,effectValue)),detail:'仅无条件已核验规则；同类取最强正负项，适配分不代表伤害倍率',available:true});
    const exactRecords = records(data,encounter,members.map(member => member.slug));
    if (exactRecords.length) {parts.push({key:'encounter-record',label:'同关阵容实战证据',value:600,detail:`完整成员 / 同模式 / 同期 / 同关卡 / 非速通有效记录 ${exactRecords.length} 条；整层成绩只证明同关阵容出现，不预测单侧成绩`,available:true});reasons.push(exactRecords.some(row=>row.metric_scope==='floor')?'有完整成员同关实战记录；整层成绩不能视为单侧成绩':'有完整成员同目标实战记录');}
    else unknown.push('无完整成员同目标有效实战样本；原模板成绩仅作跨关参考');
    if (!encounter.effects?.length) unknown.push('未提供已核验词缀');
    if (encounter.mechanic_text && !(encounter.effects || []).some(effect => effect.text === encounter.mechanic_text)) unknown.push(encounter.mechanic_text);
    return {encounter,profile:image,parts,reasons,unknown:[...new Set(unknown)],exactRecords};
  }
  function html(advice, escape) {
    if (!advice) return '';
    const image = advice.profile, label = values => values.map(tag => LABELS[tag]).join(' / ') || '未知';
    const metricLabel=row=>row.metric_scope==='floor'?(['score','points'].includes(row.metric_kind)?'整层总得分':['cycles','rounds'].includes(row.metric_kind)?'整层总回合':'整层总耗时'):({score:'分数',points:'得分',cycles:'回合',rounds:'回合',duration:'耗时',seconds:'秒',clear_time:'通关耗时'}[row.metric_kind]||'成绩');
    const recordText = advice.exactRecords.length ? advice.exactRecords.map(row => `${metricLabel(row)} ${row.metric_value} · ${row.evidence_grade} 级${row.metric_scope==='floor'?'（不是单侧成绩）':''}${row.build_context?' · 配置背景见来源':''}${row.metric_kind==='cycles'&&Number(row.metric_value)===0?' · 零回合高配参考':''}`).join('；') : '跨关迁移参考 · 目标证据 C';
    return `<div class="rec-encounter-advice"><b>${escape(advice.encounter.label || advice.encounter.scope_key)}${advice.encounter.user_input_overlay ? ' · 用户补充敌情' : ''}${advice.encounter.user_provided ? ' · 用户提供' : ''}</b><p>主：${escape(label(image.primary))} · 次：${escape(label(image.secondary))} · ${image.inferred ? '角色标签推断' : '来源画像'}</p><p>${escape(recordText)}</p>${advice.exactRecords.map(row => `<a href="${escape(safeUrl(row.source_url))}" target="_blank" rel="noopener noreferrer">同目标实战来源</a>`).join(' ')}${(image.tag_sources||[]).map(url=>`<a href="${escape(url)}" target="_blank" rel="noopener noreferrer">角色伤害标签来源</a>`).join(' ')}${image.source_url ? `<a href="${escape(image.source_url)}" target="_blank" rel="noopener noreferrer">队伍画像来源</a>` : ''}${advice.reasons.map(text => `<p>${escape(text)}</p>`).join('')}<details><summary>未知与条件机制 ${advice.unknown.length} 项</summary>${advice.unknown.map(text => `<p>${escape(text)}</p>`).join('')}</details></div>`;
  }
  Object.defineProperty(root,'MihoEncounterAdvisor',{value:Object.freeze({rows,targetPhase,targetStatus,targetLabel,targetGroups,profile,evaluate,records,html,safeUrl}),configurable:false,writable:false});
})(globalThis);
