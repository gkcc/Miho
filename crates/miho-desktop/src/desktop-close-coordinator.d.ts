export interface DesktopCloseCoordinatorOptions {
  beginClose(): void;
  getWorkspaceTransition(): PromiseLike<void> | null;
  getTaskStart(): PromiseLike<void> | null;
  hasActiveTask(): boolean;
  confirmActiveTaskClose(): boolean | PromiseLike<boolean>;
  shouldResetWorkspace(): boolean;
  resetWorkspace(): void;
  flushBoxes(): boolean | PromiseLike<boolean>;
  persist(): void;
  destroy(): void | PromiseLike<void>;
  finishClose(closed: boolean): void | PromiseLike<void>;
}

export function coordinateDesktopClose(
  options: DesktopCloseCoordinatorOptions,
): Promise<boolean>;
