export type VisualizerRefreshGenerationState = {
  refreshGeneration: number;
  pendingRefreshGeneration: number | null;
};

export function advanceVisualizerRefresh(state: VisualizerRefreshGenerationState): number;
export function captureVisualizerRefresh(state: VisualizerRefreshGenerationState): number;
export function bindPendingVisualizerRefresh(
  state: VisualizerRefreshGenerationState,
  generation: number,
): void;
export function clearPendingVisualizerRefresh(state: VisualizerRefreshGenerationState): void;
export function hasPendingVisualizerRefresh(state: VisualizerRefreshGenerationState): boolean;
export function hasCurrentPendingVisualizerRefresh(
  state: VisualizerRefreshGenerationState,
): boolean;
export function finishPendingVisualizerRefresh(state: VisualizerRefreshGenerationState): boolean;
