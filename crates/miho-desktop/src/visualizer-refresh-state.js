export function advanceVisualizerRefresh(state) {
  state.refreshGeneration += 1;
  return state.refreshGeneration;
}

export function captureVisualizerRefresh(state) {
  return state.refreshGeneration;
}

export function bindPendingVisualizerRefresh(state, generation) {
  state.pendingRefreshGeneration = generation;
}

export function clearPendingVisualizerRefresh(state) {
  state.pendingRefreshGeneration = null;
}

export function hasPendingVisualizerRefresh(state) {
  return state.pendingRefreshGeneration !== null;
}

export function hasCurrentPendingVisualizerRefresh(state) {
  return state.pendingRefreshGeneration !== null
    && state.pendingRefreshGeneration === state.refreshGeneration;
}

export function finishPendingVisualizerRefresh(state) {
  const completedGeneration = state.pendingRefreshGeneration;
  state.pendingRefreshGeneration = null;
  return completedGeneration !== null && completedGeneration === state.refreshGeneration;
}
