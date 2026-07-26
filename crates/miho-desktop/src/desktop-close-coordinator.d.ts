export type DesktopCloseStage =
  | "idle"
  | "waiting-workspace-transition"
  | "waiting-task-start"
  | "waiting-background-read"
  | "checking-active-task"
  | "active-task-cancelled"
  | "flushing-boxes"
  | "flushing-hsr-box"
  | "flushing-zzz-box"
  | "box-flush-cancelled"
  | "destroying"
  | "destroy-resolved"
  | "failed";

export interface DesktopCloseCoordinatorOptions {
  beginClose(): void;
  setStage(stage: DesktopCloseStage): void;
  getWorkspaceTransition(): PromiseLike<void> | null;
  getTaskStart(): PromiseLike<void> | null;
  getBackgroundRead(): PromiseLike<void> | null;
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
