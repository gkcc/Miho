export const VISUALIZER_STARTUP_STATUS: Readonly<{
  IDLE: "idle";
  PENDING: "pending";
  READY: "ready";
  FAILED: "failed";
}>;

export const VISUALIZER_STARTUP_CODE: Readonly<{
  LEGACY_PROTOCOL_MISSING: "legacy_protocol_missing";
  DATA_LOAD_FAILED: "data_load_failed";
  READY_HANDSHAKE_REJECTED: "ready_handshake_rejected";
  READY_TIMEOUT: "ready_timeout";
}>;

export type VisualizerStartupStatus = "idle" | "pending" | "ready" | "failed";
export type VisualizerStartupCode =
  | "legacy_protocol_missing"
  | "data_load_failed"
  | "ready_handshake_rejected"
  | "ready_timeout";
export type VisualizerStartupOutcome = "accepted" | "ignored";

export interface VisualizerStartupIdentity {
  navigation_id: string;
  data_revision: string;
  src: string;
}

export interface VisualizerStartupState {
  generation: number;
  navigation_id: string | null;
  data_revision: string | null;
  src: string | null;
  status: VisualizerStartupStatus;
  code: VisualizerStartupCode | null;
  frame_loaded: boolean;
  initializing_seen: boolean;
}

export interface VisualizerStartupResult extends Readonly<VisualizerStartupState> {
  outcome: VisualizerStartupOutcome;
}

interface VisualizerStartupEventBase extends VisualizerStartupIdentity {
  generation: number;
}

export interface VisualizerStartupInitializingEvent extends VisualizerStartupEventBase {
  type: "initializing";
}

export interface VisualizerStartupFailedEvent extends VisualizerStartupEventBase {
  type: "failed";
  code: string;
}

export interface VisualizerStartupReadyEvent extends VisualizerStartupEventBase {
  type: "ready";
}

export interface VisualizerStartupFrameLoadEvent extends VisualizerStartupEventBase {
  type: "frame_load";
}

export interface VisualizerStartupTimeoutEvent extends VisualizerStartupEventBase {
  type: "timeout";
}

export type VisualizerStartupEvent =
  | VisualizerStartupInitializingEvent
  | VisualizerStartupFailedEvent
  | VisualizerStartupReadyEvent
  | VisualizerStartupFrameLoadEvent
  | VisualizerStartupTimeoutEvent;

export function createVisualizerStartupState(): VisualizerStartupState;
export function beginVisualizerStartup(
  state: VisualizerStartupState,
  identity: VisualizerStartupIdentity,
): VisualizerStartupResult;
export function transitionVisualizerStartup(
  state: VisualizerStartupState,
  event: VisualizerStartupEvent,
): VisualizerStartupResult;
export function resetVisualizerStartup(
  state: VisualizerStartupState,
): VisualizerStartupResult;
