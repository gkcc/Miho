import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import {
  coordinateDesktopClose,
  type DesktopCloseStage,
} from "./desktop-close-coordinator.js";
import {
  advanceVisualizerRefresh,
  bindPendingVisualizerRefresh,
  captureVisualizerRefresh,
  clearPendingVisualizerRefresh,
  finishPendingVisualizerRefresh,
  hasPendingVisualizerRefresh,
} from "./visualizer-refresh-state.js";
import {
  beginVisualizerStartup,
  createVisualizerStartupState,
  resetVisualizerStartup,
  transitionVisualizerStartup,
  VISUALIZER_STARTUP_CODE,
  VISUALIZER_STARTUP_STATUS,
  type VisualizerStartupCode,
  type VisualizerStartupIdentity,
  type VisualizerStartupState,
} from "./visualizer-startup-state.js";
import {
  ENDGAME_SAMPLE_STALE_AFTER_DAYS,
  localDateKey,
  nextLocalDateBoundary,
  sampleAgeDays,
  sampleAgeSuffix,
  staleSampleAgeDays,
} from "./freshness-age.js";
import "./styles.css";

type Game = "hsr" | "zzz";
type ExportOperation = "hsr-export" | "zzz-export";
type FormalOperation = "evidence" | "coverage" | "pull-value" | "review-packet";
type TaskOperation = ExportOperation | FormalOperation | "decision";
type TaskStatus =
  | "queued"
  | "running"
  | "committing"
  | "succeeded"
  | "failed"
  | "cancelling"
  | "cancelled";

type WorkspaceSummary = {
  schema_version: string;
  workspace_id: string;
  label: string;
  source: string;
  revision: number;
};

type OperationCapability = {
  operation: TaskOperation;
  enabled: boolean;
  missing_inputs: string[];
};

type DesktopCapabilities = {
  schema_version: string;
  workspace: WorkspaceSummary;
  workspace_selection_enabled: boolean;
  operations: OperationCapability[];
  max_concurrent_tasks: number;
  supports_cancel: boolean;
  task_history_persistent: boolean;
  task_update_event: string;
  task_queries_are_authoritative: boolean;
  abrupt_termination_supported: boolean;
  cross_process_recovery_supported: boolean;
  warnings: string[];
};

type PublicArtifact = {
  artifact_id: string;
  name: string;
  kind: string;
};

type PublicTaskFailure = {
  code: string;
  stage: string;
  retryable: boolean;
  message: string;
  action: string;
};

type TaskModeFreshness = {
  status: string;
  sample_date: string;
  start_date: string;
  end_date: string;
};

type TaskFreshnessSummary = {
  status: string;
  modes: Record<string, TaskModeFreshness>;
};

type PublicTaskSnapshot = {
  schema_version: string;
  task_id: string;
  operation: TaskOperation;
  status: TaskStatus;
  status_history: TaskStatus[];
  cancellation_requested: boolean;
  artifacts: PublicArtifact[];
  failure: PublicTaskFailure | null;
  freshness?: TaskFreshnessSummary;
};

type TaskUpdate = {
  schema_version: string;
  sequence: number;
  task: PublicTaskSnapshot;
};

type CancelOutcome = "requested" | "too_late" | "already_terminal" | "not_found";

type CommandFailure = {
  code: string;
  message: string;
  retryable?: boolean;
};

type VisualizerDescriptor = {
  schema_version: "miho-visualizer-descriptor-v1";
  url: string;
  data_revision: string;
};

type DesktopUpdateHealthGame = {
  game: Game;
  attempt_id: string;
  completed_at_utc: string;
  freshness: TaskFreshnessSummary;
};

type DesktopUpdateHealth = {
  schema_version: "miho-desktop-update-health-v2";
  workspace_id: string;
  healthy: boolean;
  attempt_id?: string;
  checked_games: Game[];
  games: DesktopUpdateHealthGame[];
  failure_code?: string;
  retryable: boolean;
};

type VisualizerPage = "box" | "analysis" | "banner" | "recommender";

type VisualizerStartupTicket = VisualizerStartupIdentity & {
  generation: number;
};

type VisualizerFrameState = {
  frame: HTMLIFrameElement;
  requestGeneration: number;
  refreshGeneration: number;
  loadedRevision: string | null;
  pendingRevision: string | null;
  pendingUrl: string | null;
  pendingNavigationId: string | null;
  readyTimeout: number | null;
  pendingRefreshGeneration: number | null;
  page: VisualizerPage;
  startup: VisualizerStartupState;
  startupLoadTicket: VisualizerStartupTicket | null;
};

type TaskFormState = {
  operation: FormalOperation;
  plannedSlugs: string;
  planStatuses: string;
  limit: string;
  minRate: string;
  includeMissing: boolean;
};

const OPERATIONS: ReadonlyArray<{ value: FormalOperation; label: string; description: string }> = [
  { value: "evidence", label: "整理可用证据", description: "汇总当前公开数据，并标出证据是否足够可靠。" },
  { value: "coverage", label: "检查队伍覆盖", description: "查看当前 Box 和规划角色能覆盖哪些终局队伍。" },
  { value: "pull-value", label: "分析抽卡价值", description: "结合当前 Box 分析当期和后续角色的补强价值。" },
  { value: "review-packet", label: "生成复核材料", description: "整理一份可交给外部复核的分析材料。" },
];

const EXPORT_OPERATIONS: ReadonlyArray<{
  value: ExportOperation;
  game: Game;
  label: string;
  description: string;
}> = [
  {
    value: "hsr-export",
    game: "hsr",
    label: "更新星穹铁道数据",
    description: "获取最新公开数据并刷新星铁 Box、卡池和终局分析页面。",
  },
  {
    value: "zzz-export",
    game: "zzz",
    label: "更新绝区零数据",
    description: "获取最新公开数据并刷新绝区零 Box、卡池和终局分析页面。",
  },
];

const CAPABILITY_OPERATIONS: ReadonlyArray<{ value: TaskOperation; label: string }> = [
  ...EXPORT_OPERATIONS,
  ...OPERATIONS,
];

const STATUS_LABELS: Record<TaskStatus, string> = {
  queued: "等待开始",
  running: "正在处理",
  committing: "正在保存",
  succeeded: "完成",
  failed: "未完成",
  cancelling: "正在取消",
  cancelled: "已取消",
};

const TERMINAL_STATUSES = new Set<TaskStatus>(["succeeded", "failed", "cancelled"]);
const GAMES = ["hsr", "zzz"] as const;
const VISUALIZER_REVISION_CHECK_INTERVAL_MS = 60_000;
const VISUALIZER_READY_TIMEOUT_MS = 30_000;
const UPDATE_HEALTH_STALE_AFTER_MS = 36 * 60 * 60 * 1_000;
const UPDATE_HEALTH_BUSY_RETRY_DELAYS_MS = [1_000, 2_500, 5_000, 10_000, 30_000] as const;
const MAX_BROWSER_TIMER_DELAY_MS = 2_147_000_000;
const app = document.querySelector<HTMLDivElement>("#app");

if (!app) {
  throw new Error("Application root is missing.");
}

let game: Game = "zzz";
let capabilities: DesktopCapabilities | null = null;
let taskForm: TaskFormState = {
  operation: "evidence",
  plannedSlugs: "",
  planStatuses: "next",
  limit: "0",
  minRate: "10.0",
  includeMissing: false,
};
let capabilitiesRequestGeneration = 0;
let workspaceBusy = false;
let taskBusy = false;
let taskRefreshBusy = false;
let unlistenTaskUpdates: UnlistenFn | null = null;
let unlistenWindowClose: UnlistenFn | null = null;
let boxTransitionBusy = false;
let boxTransitionDepth = 0;
let allowWindowClose = false;
let closeGuardRunning = false;
let closeRequestRunning = false;
let pendingTaskStart: Promise<void> | null = null;
let pendingWorkspaceTransition: Promise<void> | null = null;
let workspaceReconcilePending = false;

type PendingBoxFlush = {
  frame: HTMLIFrameElement;
  resolve: () => void;
  reject: (error: Error) => void;
  timeout: number;
};

type BoxFlushOptions = {
  failureMode?: "prompt" | "cancel";
  beforeFlush?: (targetGame: Game) => void;
};

const pendingBoxFlushes = new Map<string, PendingBoxFlush>();
const pendingUpdateHealthReads = new Set<Promise<unknown>>();
const visualizerLoading = new Set<Game>();
const pendingVisualizerRefreshes = new Set<Game>();
let boxFlushSequence = 0;
let visualizerRefreshDrainScheduled = false;
let visualizerRefreshDrainRunning = false;
let visualizerRevisionCheckRunning = false;
let visualizerRevisionCheckQueued = false;
let visualizerRevisionCheckInterval: number | null = null;
let updateHealthRequestGeneration = 0;
let updateHealthBusyRetryTimer: number | null = null;
let updateHealthStaleTimer: number | null = null;
let updateHealthBusyRetryAttempt = 0;
const observedVisualizerRevisions = new Map<Game, string>();
const updateHealthRefreshedTaskIds = new Set<string>();

const tasks = new Map<string, PublicTaskSnapshot>();
const authoritativeTaskSequences = new Map<string, number>();
const eventTaskSequences = new Map<string, number>();
const taskQueries = new Map<string, number>();
const restoredTaskIds = new Set<string>();
let historyWorkspaceId = "";

function taskHistoryKey(workspaceId: string): string {
  return `miho-desktop:task-history-v1:${workspaceId}`;
}

function persistTaskHistory(): void {
  if (!historyWorkspaceId) return;
  const recent = [...tasks.values()].slice(-20);
  try {
    localStorage.setItem(taskHistoryKey(historyWorkspaceId), JSON.stringify(recent));
  } catch {
    // History persistence is best effort and never blocks task execution.
  }
}

function restoreTaskHistory(workspaceId: string): void {
  tasks.clear();
  restoredTaskIds.clear();
  authoritativeTaskSequences.clear();
  eventTaskSequences.clear();
  taskQueries.clear();
  historyWorkspaceId = workspaceId;
  let interrupted = 0;
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(taskHistoryKey(workspaceId)) || "[]");
    if (!Array.isArray(parsed)) return;
    for (const value of parsed.slice(-20)) {
      if (!isPublicTaskSnapshot(value)) continue;
      let snapshot = value;
      if (!TERMINAL_STATUSES.has(snapshot.status)) {
        interrupted += 1;
        snapshot = {
          ...snapshot,
          status: "failed",
          status_history: [...snapshot.status_history, "failed"],
          cancellation_requested: false,
          failure: {
            code: "task.interrupted",
            stage: "runtime",
            retryable: true,
            message: "上次关闭程序时任务仍在运行，已记录为中断。",
            action: "确认工作区状态后可手动重新开始；程序不会自动重跑。",
          },
        };
      }
      tasks.set(snapshot.task_id, snapshot);
      restoredTaskIds.add(snapshot.task_id);
    }
  } catch {
    localStorage.removeItem(taskHistoryKey(workspaceId));
  }
  persistTaskHistory();
  renderTasks();
  if (interrupted) {
    setNotice(taskMessage, `检测到 ${interrupted} 条上次中断的任务记录；未自动重跑。`, "error");
  }
}

function element<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function labeledControl(label: string, control: HTMLElement, hint?: string): HTMLLabelElement {
  const wrapper = element("label", "field");
  wrapper.append(element("span", "field-label", label), control);
  if (hint) wrapper.append(element("small", "field-hint", hint));
  return wrapper;
}

function makeButton(label: string, className: string, handler: () => void | Promise<void>): HTMLButtonElement {
  const button = element("button", className, label);
  button.type = "button";
  button.addEventListener("click", () => void handler());
  return button;
}

function splitValues(value: string): string[] {
  return [...new Set(value.split(/[\s,，;；]+/u).map((item) => item.trim()).filter(Boolean))];
}

function operationLabel(operation: TaskOperation): string {
  if (operation === "decision") return "旧版兼容检查";
  const exportOperation = EXPORT_OPERATIONS.find((candidate) => candidate.value === operation);
  if (exportOperation) return exportOperation.label;
  return OPERATIONS.find((candidate) => candidate.value === operation)?.label ?? operation;
}

function modeLabel(mode: string): string {
  return ({ moc: "混沌回忆", pf: "虚构叙事", as: "末日幻影", aa: "异相仲裁", sd: "式舆防卫", da: "危局强袭" } as Record<string, string>)[mode] ?? mode;
}

function freshnessLabel(status: string): string {
  return status === "active" ? "当前"
    : status === "stale" ? "历史样本"
      : status === "future" ? "未来周期"
        : "周期未知";
}

function freshnessPeriodLabel(freshness: TaskModeFreshness): string {
  if (freshness.start_date && freshness.end_date) {
    return `周期 ${freshness.start_date} 至 ${freshness.end_date}`;
  }
  if (freshness.start_date) return `周期起始 ${freshness.start_date}`;
  if (freshness.end_date) return `周期截至 ${freshness.end_date}`;
  return "周期边界未知";
}

function effectiveFreshnessStatus(freshness: TaskModeFreshness, today = localDateKey()): string {
  const hasStart = /^\d{4}-\d{2}-\d{2}$/.test(freshness.start_date);
  const hasEnd = /^\d{4}-\d{2}-\d{2}$/.test(freshness.end_date);
  if (hasStart && today < freshness.start_date) return "future";
  if (hasEnd && today > freshness.end_date) return "stale";
  if (hasStart || hasEnd) return "active";
  return freshness.status;
}

function summarizeFreshness(freshness: TaskFreshnessSummary, today = localDateKey()): {
  latestSampleDate: string | null;
  staleSamples: number;
  futureSamples: number;
  missingSamples: number;
  active: number;
  stale: number;
  future: number;
  unknown: number;
} {
  const modes = Object.values(freshness.modes).map((mode) => ({
    ...mode,
    effectiveStatus: effectiveFreshnessStatus(mode, today),
    sampleAgeDays: sampleAgeDays(mode.sample_date, today),
  }));
  const sampleDates = modes
    .filter((mode) => mode.sampleAgeDays !== null)
    .map((mode) => mode.sample_date)
    .sort();
  const latestSampleDate = sampleDates.at(-1) ?? null;
  return {
    latestSampleDate,
    staleSamples: modes.filter((mode) => staleSampleAgeDays(mode.sample_date, today) !== null).length,
    futureSamples: modes.filter((mode) => mode.sampleAgeDays !== null && mode.sampleAgeDays < 0).length,
    missingSamples: modes.filter((mode) => mode.sampleAgeDays === null).length,
    active: modes.filter((mode) => mode.effectiveStatus === "active").length,
    stale: modes.filter((mode) => mode.effectiveStatus === "stale").length,
    future: modes.filter((mode) => mode.effectiveStatus === "future").length,
    unknown: modes.filter((mode) => mode.effectiveStatus === "unknown").length,
  };
}

function safeError(error: unknown): CommandFailure {
  if (typeof error === "object" && error !== null) {
    const record = error as Record<string, unknown>;
    return {
      code: typeof record.code === "string" ? record.code : "desktop.command_failed",
      message: typeof record.message === "string" ? record.message : "本机命令执行失败。",
      retryable: typeof record.retryable === "boolean" ? record.retryable : undefined,
    };
  }
  return { code: "desktop.command_failed", message: typeof error === "string" ? error : "本机命令执行失败。" };
}

const header = element("header", "app-header");
const brand = element("div", "brand");
brand.append(element("p", "eyebrow", "MIHO ENDGAME"), element("h1", undefined, "终局数据中心"));
const gameNav = element("nav", "game-nav");
gameNav.setAttribute("aria-label", "游戏选择");
const gameButtons = new Map<Game, HTMLButtonElement>();
for (const [value, label] of [["hsr", "崩坏：星穹铁道"], ["zzz", "绝区零"]] as const) {
  const button = makeButton(label, "game-button", async () => {
    if (game === value || workspaceBusy || boxTransitionBusy) return;
    setBoxTransitionBusy(true);
    updateWorkspaceControls();
    try {
      if (!await ensureVisualizerBoxesSaved([game], "切换游戏")) return;
      game = value;
      updateGameUI();
      await loadVisualizer(false, value);
    } finally {
      setBoxTransitionBusy(false);
      updateWorkspaceControls();
    }
  });
  gameButtons.set(value, button);
  gameNav.append(button);
}
header.append(brand, gameNav);

const main = element("main", "dashboard");

const workspaceSection = element("section", "panel workspace-panel");
const workspaceHeading = element("div", "section-heading");
const workspaceTitleBlock = element("div");
workspaceTitleBlock.append(element("p", "eyebrow", "TRUSTED NATIVE WORKSPACE"), element("h2", undefined, "工作区"));
const workspaceActions = element("div", "button-row");
const selectWorkspaceButton = makeButton("切换工作区", "button secondary", selectWorkspace);
const refreshWorkspaceButton = makeButton("刷新", "button", refreshAll);
const openLogButton = makeButton("打开日志", "button secondary", openLogLocation);
workspaceActions.append(selectWorkspaceButton, openLogButton, refreshWorkspaceButton);
workspaceHeading.append(workspaceTitleBlock, workspaceActions);
const workspaceSummary = element("div", "workspace-summary");
const workspaceMessage = element("p", "notice", "正在读取本机能力…");
const capabilityGrid = element("div", "capability-grid");
const runtimeLimits = element("div", "runtime-limits");
const workspaceWarnings = element("div", "warning-list");
workspaceSection.append(workspaceHeading, workspaceSummary, capabilityGrid, runtimeLimits, workspaceWarnings, workspaceMessage);

const exportSection = element("section", "panel export-panel");
const exportHeading = element("div", "section-heading");
const exportTitleBlock = element("div");
exportTitleBlock.append(
  element("p", "eyebrow", "DATA UPDATE"),
  element("h2", undefined, "更新公开数据"),
  element("p", "muted", "需要刷新角色、卡池或终局数据时再运行；更新会在后台完成。"),
);
exportHeading.append(exportTitleBlock);
const exportControls = element("div", "export-controls");
const exportButtons = new Map<ExportOperation, HTMLButtonElement>();
const exportStatuses = new Map<ExportOperation, HTMLElement>();
for (const operation of EXPORT_OPERATIONS) {
  const card = element("article", "export-card");
  card.append(element("h3", undefined, operation.label), element("p", "muted", operation.description));
  const button = makeButton("立即更新", "button primary", () => startExport(operation.value));
  const status = element("p", "notice", "等待本机能力信息。");
  exportButtons.set(operation.value, button);
  exportStatuses.set(operation.value, status);
  card.append(button, status);
  exportControls.append(card);
}
const exportMessage = element("p", "notice", "更新进度会显示在下方“本次运行进度”中。");
exportSection.append(exportHeading, exportControls, exportMessage);

const taskSection = element("section", "panel task-panel");
const taskHeading = element("div", "section-heading");
const taskTitleBlock = element("div");
taskTitleBlock.append(
  element("p", "eyebrow", "ADVANCED REPORTS"),
  element("h2", undefined, "生成分析报告（高级）"),
  element("p", "muted", "只有需要导出专项分析时才使用；日常维护 Box 不需要运行这些操作。"),
);
const taskRefreshButton = makeButton("刷新任务", "button secondary", refreshTasks);
taskHeading.append(taskTitleBlock, taskRefreshButton);

const taskFormElement = element("form", "task-form");
taskFormElement.noValidate = true;
const operationSelect = element("select", "control");
for (const operation of OPERATIONS) {
  const option = element("option", undefined, operation.label);
  option.value = operation.value;
  operationSelect.append(option);
}
operationSelect.value = taskForm.operation;
operationSelect.addEventListener("change", () => {
  taskForm.operation = operationSelect.value as FormalOperation;
  if (taskForm.operation === "pull-value" || taskForm.operation === "review-packet") {
    taskForm.planStatuses = "current, next";
  } else if (taskForm.planStatuses === "current, next") {
    taskForm.planStatuses = "next";
  }
  updateTaskForm();
});

const plannedInput = element("textarea", "control compact-textarea");
plannedInput.placeholder = "可选，以空格、逗号或换行分隔";
plannedInput.spellcheck = false;
plannedInput.addEventListener("input", () => { taskForm.plannedSlugs = plannedInput.value; });

const statusesInput = element("input", "control");
statusesInput.type = "text";
statusesInput.placeholder = "next";
statusesInput.spellcheck = false;
statusesInput.addEventListener("input", () => { taskForm.planStatuses = statusesInput.value; });

const limitInput = element("input", "control");
limitInput.type = "number";
limitInput.min = "0";
limitInput.step = "1";
limitInput.inputMode = "numeric";
limitInput.addEventListener("input", () => { taskForm.limit = limitInput.value; });

const minRateInput = element("input", "control");
minRateInput.type = "text";
minRateInput.placeholder = "10.0 或 sd=8;default=10";
minRateInput.spellcheck = false;
minRateInput.addEventListener("input", () => { taskForm.minRate = minRateInput.value; });

const includeMissingInput = element("input");
includeMissingInput.type = "checkbox";
includeMissingInput.addEventListener("change", () => { taskForm.includeMissing = includeMissingInput.checked; });
const includeMissingField = element("label", "checkbox-field");
includeMissingField.append(includeMissingInput, element("span", undefined, "证据池包含缺失角色"));

const operationField = labeledControl("报告类型", operationSelect);
const plannedField = labeledControl("规划角色 slugs", plannedInput, "只提交 slug 文本，不提交路径。");
const statusesField = labeledControl("规划状态", statusesInput, "例如 next，或 current, next。");
const limitField = labeledControl("记录上限", limitInput, "0 表示使用后端默认范围。");
const minRateField = labeledControl("A 档最低使用率", minRateInput, "可按模式配置，例如 sd=8;default=10。");
const formGrid = element("div", "form-grid");
formGrid.append(operationField, plannedField, statusesField, limitField, minRateField, includeMissingField);
const operationDescription = element("p", "operation-description");
const taskMessage = element("p", "notice");
const startTaskButton = element("button", "button primary", "开始任务");
startTaskButton.type = "submit";
taskFormElement.append(formGrid, operationDescription, startTaskButton, taskMessage);
taskFormElement.addEventListener("submit", (event) => {
  event.preventDefault();
  void startTask();
});

const diagnostic = element("details", "diagnostic");
const diagnosticSummary = element("summary", undefined, "兼容诊断");
const diagnosticText = element("p", "muted", "Legacy decision 仅保留兼容诊断能力，不作为正式报告入口，也不会默认执行。");
diagnostic.append(diagnosticSummary, diagnosticText);
taskSection.append(taskHeading, taskFormElement, diagnostic);

const historySection = element("section", "panel history-panel");
const historyHeading = element("div", "section-heading");
const historyTitleBlock = element("div");
historyTitleBlock.append(element("p", "eyebrow", "CURRENT SESSION"), element("h2", undefined, "本次运行进度"));
const historyMeta = element("p", "muted", "这些不是你的待办，只是本次打开程序后进行的数据更新和报告生成记录。");
historyHeading.append(historyTitleBlock, historyMeta);
const taskList = element("div", "task-list");
historySection.append(historyHeading, taskList);

const visualizerSection = element("section", "panel visualizer-panel");
const visualizerHeading = element("div", "section-heading");
const visualizerTitleBlock = element("div");
const visualizerTitle = element("h2", undefined, "绝区零 · 我的 Box 与终局分析");
visualizerTitleBlock.append(element("p", "eyebrow", "MY BOX"), visualizerTitle);
const reloadVisualizerButton = makeButton("重新载入", "button secondary", async () => {
  if (boxTransitionBusy) return;
  setBoxTransitionBusy(true);
  updateWorkspaceControls();
  try {
    if (await ensureVisualizerBoxesSaved([game], "重新载入")) {
      await Promise.all([loadVisualizer(true), refreshUpdateHealth()]);
    }
  } finally {
    setBoxTransitionBusy(false);
    updateWorkspaceControls();
  }
});
visualizerHeading.append(visualizerTitleBlock);
const updateHealthPanel = element("aside", "update-health loading");
updateHealthPanel.setAttribute("aria-label", "自动更新健康状态");
updateHealthPanel.setAttribute("aria-live", "polite");
const updateHealthHeading = element("div", "update-health-heading");
const updateHealthTitle = element("strong", undefined, "自动更新状态");
const updateHealthBadge = element("span", "update-health-badge", "读取中");
updateHealthHeading.append(updateHealthTitle, updateHealthBadge);
const updateHealthCopy = element("div", "update-health-copy");
const updateHealthSummary = element("p", "update-health-summary", "正在读取最近自动更新记录…");
const updateHealthDetail = element("p", "update-health-detail", "完成后会显示 HSR 与 ZZZ 的本机成功时间和终局最新采样。");
updateHealthCopy.append(updateHealthSummary, updateHealthDetail);
const updateHealthGames = element("div", "update-health-games");
updateHealthGames.hidden = true;
updateHealthPanel.append(updateHealthHeading, updateHealthCopy, updateHealthGames);
const visualizerMessage = element("p", "notice", "正在向本机后端请求 Visualizer 地址…");
const visualizerFrames = new Map<Game, VisualizerFrameState>();

function isWindowClosing(): boolean {
  return allowWindowClose || closeGuardRunning;
}

function setDesktopCloseStage(stage: DesktopCloseStage): void {
  document.documentElement.dataset.desktopCloseStage = stage;
}

setDesktopCloseStage("idle");

function beginTaskStartTracking(): () => void {
  if (pendingTaskStart) throw new Error("A task start is already being tracked.");
  let resolveCompletion!: () => void;
  const completion = new Promise<void>((resolve) => {
    resolveCompletion = resolve;
  });
  pendingTaskStart = completion;
  let finished = false;
  return () => {
    if (finished) return;
    finished = true;
    if (pendingTaskStart === completion) pendingTaskStart = null;
    resolveCompletion();
  };
}

function beginWorkspaceTransitionTracking(): () => void {
  if (pendingWorkspaceTransition) throw new Error("A workspace transition is already being tracked.");
  let resolveCompletion!: () => void;
  const completion = new Promise<void>((resolve) => {
    resolveCompletion = resolve;
  });
  pendingWorkspaceTransition = completion;
  let finished = false;
  return () => {
    if (finished) return;
    finished = true;
    if (pendingWorkspaceTransition === completion) pendingWorkspaceTransition = null;
    resolveCompletion();
  };
}

function setBoxTransitionBusy(busy: boolean): void {
  boxTransitionDepth = busy ? boxTransitionDepth + 1 : Math.max(0, boxTransitionDepth - 1);
  boxTransitionBusy = boxTransitionDepth > 0 || isWindowClosing();
  updateVisualizerFrameVisibility();
  if (!boxTransitionBusy && !visualizerRefreshDrainRunning) schedulePendingVisualizerRefresh();
}

const visualizerDirty = new Set<Game>(["hsr", "zzz"]);

function clearVisualizerReadyTimeout(visualizerState: VisualizerFrameState): void {
  if (visualizerState.readyTimeout === null) return;
  window.clearTimeout(visualizerState.readyTimeout);
  visualizerState.readyTimeout = null;
}

function syncVisualizerStartupDiagnostics(targetGame: Game, visualizerState: VisualizerFrameState): void {
  visualizerState.frame.dataset.startupState = visualizerState.startup.status;
  if (visualizerState.startup.code) {
    visualizerState.frame.dataset.startupFailureCode = visualizerState.startup.code;
  } else {
    delete visualizerState.frame.dataset.startupFailureCode;
  }
  if (targetGame !== game) return;
  document.documentElement.dataset.visualizerStartupGame = targetGame;
  document.documentElement.dataset.visualizerStartupState = visualizerState.startup.status;
  if (visualizerState.startup.code) {
    document.documentElement.dataset.visualizerStartupFailureCode = visualizerState.startup.code;
  } else {
    delete document.documentElement.dataset.visualizerStartupFailureCode;
  }
}

function visualizerStartupFailureMessage(code: VisualizerStartupCode): string {
  switch (code) {
    case VISUALIZER_STARTUP_CODE.LEGACY_PROTOCOL_MISSING:
      return "Visualizer 页面已载入，但版本过旧，未提供启动协议。请重新构建或更新本机程序。";
    case VISUALIZER_STARTUP_CODE.DATA_LOAD_FAILED:
      return "Visualizer 已启动，但本机数据载入失败。请先更新该游戏数据后重试。";
    case VISUALIZER_STARTUP_CODE.READY_HANDSHAKE_REJECTED:
      return "Visualizer 就绪回执与当前数据版本不一致，已阻止显示。请重新载入；若仍出现请检查日志。";
    case VISUALIZER_STARTUP_CODE.READY_TIMEOUT:
      return "Visualizer 未在限定时间内完成初始化。请重新载入或检查本机生成状态。";
  }
}

function finishVisualizerStartupFailure(
  targetGame: Game,
  ticket: VisualizerStartupTicket,
  code: VisualizerStartupCode,
): void {
  const visualizerState = visualizerFrames.get(targetGame);
  if (!visualizerState
    || visualizerState.startup.generation !== ticket.generation
    || visualizerState.startup.status !== VISUALIZER_STARTUP_STATUS.FAILED
    || visualizerState.startup.code !== code) return;
  const { frame } = visualizerState;
  visualizerState.requestGeneration += 1;
  clearVisualizerReadyTimeout(visualizerState);
  visualizerState.startupLoadTicket = null;
  visualizerState.loadedRevision = null;
  visualizerState.pendingRevision = null;
  visualizerState.pendingUrl = null;
  visualizerState.pendingNavigationId = null;
  const failedCurrentRefresh = finishPendingVisualizerRefresh(visualizerState);
  if (failedCurrentRefresh) pendingVisualizerRefreshes.delete(targetGame);
  visualizerLoading.delete(targetGame);
  delete frame.dataset.loadedRevision;
  frame.dataset.loaded = "false";
  frame.removeAttribute("src");
  visualizerDirty.add(targetGame);
  syncVisualizerStartupDiagnostics(targetGame, visualizerState);
  updateVisualizerFrameVisibility();
  updateWorkspaceControls();
  if (game === targetGame) {
    visualizerMessage.hidden = false;
    utilities.open = true;
    setNotice(visualizerMessage, visualizerStartupFailureMessage(code), "error");
  }
  if (!failedCurrentRefresh && pendingVisualizerRefreshes.has(targetGame)) {
    schedulePendingVisualizerRefresh();
  }
}

function failVisualizerStartupOnTimeout(targetGame: Game, ticket: VisualizerStartupTicket): void {
  const visualizerState = visualizerFrames.get(targetGame);
  if (!visualizerState) return;
  const result = transitionVisualizerStartup(visualizerState.startup, {
    type: "timeout",
    ...ticket,
  });
  syncVisualizerStartupDiagnostics(targetGame, visualizerState);
  if (result.outcome === "accepted"
    && result.status === VISUALIZER_STARTUP_STATUS.FAILED
    && result.code) {
    finishVisualizerStartupFailure(targetGame, ticket, result.code);
  }
}

for (const targetGame of GAMES) {
  const frame = element("iframe", "visualizer-frame");
  const visualizerState: VisualizerFrameState = {
    frame,
    requestGeneration: 0,
    refreshGeneration: 0,
    loadedRevision: null,
    pendingRevision: null,
    pendingUrl: null,
    pendingNavigationId: null,
    readyTimeout: null,
    pendingRefreshGeneration: null,
    page: "box",
    startup: createVisualizerStartupState(),
    startupLoadTicket: null,
  };
  frame.title = `${targetGame === "hsr" ? "崩坏：星穹铁道" : "绝区零"}终局数据 Visualizer`;
  frame.dataset.game = targetGame;
  frame.dataset.page = visualizerState.page;
  frame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-downloads");
  frame.referrerPolicy = "no-referrer";
  frame.hidden = true;
  frame.setAttribute("aria-hidden", "true");
  frame.tabIndex = -1;
  visualizerFrames.set(targetGame, visualizerState);
  syncVisualizerStartupDiagnostics(targetGame, visualizerState);
  frame.addEventListener("load", () => {
    const ticket = visualizerState.startupLoadTicket;
    if (!ticket) return;
    const result = transitionVisualizerStartup(visualizerState.startup, {
      type: "frame_load",
      ...ticket,
    });
    if (result.outcome === "accepted") {
      syncVisualizerStartupDiagnostics(targetGame, visualizerState);
    }
  });
}
window.addEventListener("message", (event) => {
  if (!isRecord(event.data)) return;
  if (event.data.schema_version === "miho-visualizer-box-flush-result-v1"
    && typeof event.data.request_id === "string"
    && typeof event.data.ok === "boolean") {
    const pending = pendingBoxFlushes.get(event.data.request_id);
    if (!pending || event.source !== pending.frame.contentWindow) return;
    window.clearTimeout(pending.timeout);
    pendingBoxFlushes.delete(event.data.request_id);
    if (event.data.ok) pending.resolve();
    else pending.reject(new Error("Box 保存未成功。"));
    return;
  }
  const sourceState = [...visualizerFrames.values()]
    .find((visualizerState) => event.source === visualizerState.frame.contentWindow);
  if (!sourceState) return;
  const lifecycleSchema = event.data.schema_version;
  if (lifecycleSchema === "miho-visualizer-initializing-v1"
    || lifecycleSchema === "miho-visualizer-failed-v1"
    || lifecycleSchema === "miho-visualizer-ready-v1") {
    const failedMessage = lifecycleSchema === "miho-visualizer-failed-v1";
    const expectedKeys = failedMessage
      ? ["schema_version", "navigation_id", "data_revision", "code"]
      : ["schema_version", "navigation_id", "data_revision"];
    if (!hasExactKeys(event.data, expectedKeys)
      || typeof event.data.navigation_id !== "string"
      || event.data.navigation_id.length === 0
      || event.data.navigation_id.length > 128
      || typeof event.data.data_revision !== "string"
      || event.data.data_revision.length > 128
      || (failedMessage && (typeof event.data.code !== "string" || event.data.code.length > 96))) return;
    const ticket = sourceState.startupLoadTicket;
    if (!ticket) return;
    const identity = {
      generation: ticket.generation,
      navigation_id: event.data.navigation_id,
      data_revision: event.data.data_revision,
      src: sourceState.frame.getAttribute("src") ?? "",
    };
    const transition = lifecycleSchema === "miho-visualizer-initializing-v1"
      ? transitionVisualizerStartup(sourceState.startup, { type: "initializing", ...identity })
      : lifecycleSchema === "miho-visualizer-failed-v1"
        ? transitionVisualizerStartup(sourceState.startup, {
          type: "failed",
          code: event.data.code as string,
          ...identity,
        })
        : transitionVisualizerStartup(sourceState.startup, { type: "ready", ...identity });
    const sourceGame = sourceState.frame.dataset.game as Game;
    if (transition.outcome === "accepted") {
      syncVisualizerStartupDiagnostics(sourceGame, sourceState);
    }
    if (transition.status === VISUALIZER_STARTUP_STATUS.FAILED && transition.code) {
      finishVisualizerStartupFailure(sourceGame, ticket, transition.code);
      return;
    }
    if (lifecycleSchema !== "miho-visualizer-ready-v1"
      || transition.outcome !== "accepted"
      || transition.status !== VISUALIZER_STARTUP_STATUS.READY) return;
    const completedCurrentRefresh = finishPendingVisualizerRefresh(sourceState);
    clearVisualizerReadyTimeout(sourceState);
    sourceState.startupLoadTicket = null;
    sourceState.loadedRevision = event.data.data_revision;
    sourceState.frame.dataset.loadedRevision = event.data.data_revision;
    sourceState.pendingRevision = null;
    sourceState.pendingUrl = null;
    sourceState.pendingNavigationId = null;
    sourceState.frame.dataset.loaded = "true";
    syncVisualizerStartupDiagnostics(sourceGame, sourceState);
    if (completedCurrentRefresh) {
      visualizerDirty.delete(sourceGame);
      pendingVisualizerRefreshes.delete(sourceGame);
    }
    updateVisualizerFrameVisibility();
    if (sourceState.frame.dataset.game === game) visualizerMessage.hidden = true;
    if (sourceState.frame.dataset.game === game && pendingVisualizerRefreshes.has(game)) {
      schedulePendingVisualizerRefresh();
    }
    return;
  }
  if (event.data.schema_version === "miho-visualizer-page-v1"
    && typeof event.data.page === "string"
    && sourceState.frame.dataset.loaded === "true"
    && ["box", "analysis", "banner", "recommender"].includes(event.data.page)) {
    sourceState.page = event.data.page as VisualizerPage;
    sourceState.frame.dataset.page = sourceState.page;
    return;
  }
  const activeFrame = visualizerFrames.get(game)?.frame;
  if (!activeFrame || sourceState.frame !== activeFrame) return;
  if (event.data.schema_version === "miho-visualizer-external-link-v1" && typeof event.data.url === "string") {
    if (isWindowClosing() || boxTransitionBusy) return;
    void invoke("open_external_https", { url: event.data.url }).catch((error) => {
      const failure = safeError(error);
      setNotice(visualizerMessage, `来源链接无法打开（${failure.code}）：${failure.message}`, "error");
    });
  }
});
visualizerSection.append(
  visualizerHeading,
  updateHealthPanel,
  visualizerMessage,
  ...[...visualizerFrames.values()].map((visualizerState) => visualizerState.frame),
);

const utilities = element("details", "utilities");
const utilitiesSummary = element("summary", undefined, "更新数据、生成报告与设置");
const utilitiesContent = element("div", "utilities-content");
utilitiesContent.append(exportSection, taskSection, historySection, workspaceSection);
utilities.append(utilitiesSummary, utilitiesContent);
const visualizerActions = element("div", "visualizer-actions");
visualizerActions.append(reloadVisualizerButton, utilities);
visualizerHeading.append(visualizerActions);

main.append(visualizerSection);
app.replaceChildren(header, main);
document.documentElement.dataset.mihoAppReady = "v1";
history.replaceState(null, "", "#miho-app-ready-v1");

function updateGameUI(): void {
  for (const [value, button] of gameButtons) {
    const active = value === game;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  }
  const gameName = game === "zzz" ? "绝区零" : "崩坏：星穹铁道";
  visualizerTitle.textContent = `${gameName} · 我的 Box 与终局分析`;
  const visualizerState = visualizerFrames.get(game);
  if (visualizerState) syncVisualizerStartupDiagnostics(game, visualizerState);
  updateVisualizerFrameVisibility();
}

async function showUpdatedGame(targetGame: Game): Promise<void> {
  if (workspaceBusy || boxTransitionBusy || isWindowClosing()) {
    if (!isWindowClosing()) setNotice(taskMessage, "页面正在同步最新数据，请稍后再查看。", "normal");
    return;
  }
  setBoxTransitionBusy(true);
  updateWorkspaceControls();
  try {
    if (!await ensureVisualizerBoxesSaved([game], "查看更新结果") || isWindowClosing()) return;
    game = targetGame;
    updateGameUI();
    markVisualizerDirty(targetGame, false);
    await loadVisualizer(false, targetGame);
    if (isWindowClosing()) return;
    utilities.open = false;
    visualizerSection.scrollIntoView({ behavior: "smooth" });
  } finally {
    setBoxTransitionBusy(false);
    updateWorkspaceControls();
  }
}

function updateVisualizerFrameVisibility(): void {
  for (const [targetGame, visualizerState] of visualizerFrames) {
    const { frame } = visualizerState;
    const ready = Boolean(frame.getAttribute("src"))
      && frame.dataset.loaded === "true"
      && visualizerState.pendingNavigationId === null;
    const active = targetGame === game && ready;
    frame.hidden = !active;
    frame.inert = boxTransitionBusy || !active;
    frame.setAttribute("aria-hidden", String(!active));
    frame.setAttribute("aria-busy", String(boxTransitionBusy || !ready));
    frame.tabIndex = active ? 0 : -1;
  }
}

function rejectFrameFlushes(frame: HTMLIFrameElement): void {
  for (const [requestId, pending] of pendingBoxFlushes) {
    if (pending.frame !== frame) continue;
    window.clearTimeout(pending.timeout);
    pendingBoxFlushes.delete(requestId);
    pending.reject(new Error("Box 页面已离开。"));
  }
}

function discardVisualizerBoxChanges(targetGames: ReadonlyArray<Game>): void {
  for (const targetGame of new Set(targetGames)) {
    const visualizerState = visualizerFrames.get(targetGame);
    const frame = visualizerState?.frame;
    if (!visualizerState || !frame?.getAttribute("src")) continue;
    rejectFrameFlushes(frame);
    visualizerState.requestGeneration += 1;
    advanceVisualizerRefresh(visualizerState);
    visualizerState.loadedRevision = null;
    visualizerState.pendingRevision = null;
    visualizerState.pendingUrl = null;
    visualizerState.pendingNavigationId = null;
    clearVisualizerReadyTimeout(visualizerState);
    visualizerState.startupLoadTicket = null;
    resetVisualizerStartup(visualizerState.startup);
    clearPendingVisualizerRefresh(visualizerState);
    visualizerState.page = "box";
    frame.dataset.loaded = "false";
    delete frame.dataset.loadedRevision;
    frame.dataset.page = visualizerState.page;
    frame.removeAttribute("src");
    frame.hidden = true;
    frame.setAttribute("aria-hidden", "true");
    frame.tabIndex = -1;
    visualizerDirty.add(targetGame);
    pendingVisualizerRefreshes.delete(targetGame);
    syncVisualizerStartupDiagnostics(targetGame, visualizerState);
  }
}

function flushVisualizerBox(targetGame: Game): Promise<void> {
  const frame = visualizerFrames.get(targetGame)?.frame;
  if (!frame?.getAttribute("src") || frame.dataset.loaded !== "true") return Promise.resolve();
  const target = frame.contentWindow;
  if (!target) return Promise.reject(new Error("Box 页面尚未就绪。"));
  const requestId = `box-flush-${Date.now()}-${++boxFlushSequence}`;
  return new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      pendingBoxFlushes.delete(requestId);
      reject(new Error("等待 Box 保存确认超时。"));
    }, 8_000);
    pendingBoxFlushes.set(requestId, { frame, resolve, reject, timeout });
    target.postMessage({
      schema_version: "miho-visualizer-box-flush-request-v1",
      request_id: requestId,
    }, "*");
  });
}

async function ensureVisualizerBoxesSaved(
  targetGames: ReadonlyArray<Game>,
  action: string,
  options: BoxFlushOptions = {},
): Promise<boolean> {
  const loadedGames = [...new Set(targetGames)].filter((targetGame) => {
    const frame = visualizerFrames.get(targetGame)?.frame;
    return Boolean(frame?.getAttribute("src") && frame.dataset.loaded === "true");
  });
  if (!loadedGames.length) return true;
  while (true) {
    try {
      for (const targetGame of loadedGames) {
        options.beforeFlush?.(targetGame);
        await flushVisualizerBox(targetGame);
      }
      return true;
    } catch {
      setNotice(visualizerMessage, `${action}前未能确认 Box 已保存。`, "error");
      if (options.failureMode === "cancel") return false;
      if (window.confirm(`${action}前保存 Box 失败。\n\n选择“确定”重试，选择“取消”查看放弃选项。`)) continue;
      if (window.confirm("是否放弃这些尚未保存的 Box 修改并继续？此操作无法撤销。")) {
        discardVisualizerBoxChanges(loadedGames);
        return true;
      }
      return false;
    }
  }
}

function markVisualizerDirty(targetGame: Game, refreshWhenActive: boolean): void {
  const visualizerState = visualizerFrames.get(targetGame);
  if (!visualizerState) return;
  advanceVisualizerRefresh(visualizerState);
  visualizerDirty.add(targetGame);
  if (refreshWhenActive) {
    pendingVisualizerRefreshes.add(targetGame);
    schedulePendingVisualizerRefresh();
  }
}

function schedulePendingVisualizerRefresh(): void {
  if (visualizerRefreshDrainScheduled
    || visualizerRefreshDrainRunning
    || allowWindowClose
    || closeGuardRunning) return;
  visualizerRefreshDrainScheduled = true;
  queueMicrotask(() => {
    visualizerRefreshDrainScheduled = false;
    void drainPendingVisualizerRefresh();
  });
}

async function drainPendingVisualizerRefresh(): Promise<void> {
  if (visualizerRefreshDrainRunning
    || workspaceBusy
    || boxTransitionBusy
    || allowWindowClose
    || closeGuardRunning) return;
  const targetGame = game;
  if (!pendingVisualizerRefreshes.has(targetGame)) return;
  const visualizerState = visualizerFrames.get(targetGame);
  if (!visualizerState) return;
  if (visualizerState.pendingRevision
    || visualizerState.pendingUrl
    || hasPendingVisualizerRefresh(visualizerState)) return;

  const refreshGeneration = visualizerState.refreshGeneration;
  visualizerRefreshDrainRunning = true;
  setBoxTransitionBusy(true);
  updateWorkspaceControls();
  try {
    if (!await ensureVisualizerBoxesSaved([targetGame], "载入最新数据")) return;
    if (isWindowClosing() || targetGame !== game) return;
    await loadVisualizer(false, targetGame);
  } finally {
    setBoxTransitionBusy(false);
    visualizerRefreshDrainRunning = false;
    updateWorkspaceControls();
    const nextState = visualizerFrames.get(game);
    if (nextState
      && pendingVisualizerRefreshes.has(game)
      && nextState.refreshGeneration !== refreshGeneration) {
      schedulePendingVisualizerRefresh();
    }
  }
}

function requestVisualizerRevisionCheck(): void {
  if (allowWindowClose || closeGuardRunning) return;
  if (visualizerRevisionCheckRunning) {
    visualizerRevisionCheckQueued = true;
    return;
  }
  void checkVisualizerRevisions();
}

async function checkVisualizerRevisions(): Promise<void> {
  if (visualizerRevisionCheckRunning || allowWindowClose || closeGuardRunning) return;
  visualizerRevisionCheckRunning = true;
  const workspaceId = capabilities?.workspace.workspace_id ?? "";
  try {
    const descriptors = await Promise.all(GAMES.map(async (targetGame) => {
      try {
        const result = await invoke<unknown>("get_visualizer_url", { game: targetGame });
        return [targetGame, backendVisualizerDescriptor(result, targetGame)] as const;
      } catch {
        return [targetGame, null] as const;
      }
    }));
    if (isWindowClosing()) return;
    if (workspaceId !== (capabilities?.workspace.workspace_id ?? "")) return;
    let observedRevisionChanged = false;
    for (const [targetGame, descriptor] of descriptors) {
      if (!descriptor) continue;
      const previousObservedRevision = observedVisualizerRevisions.get(targetGame);
      observedVisualizerRevisions.set(targetGame, descriptor.data_revision);
      if (previousObservedRevision !== descriptor.data_revision) {
        observedRevisionChanged = true;
      }
      const visualizerState = visualizerFrames.get(targetGame);
      if (!visualizerState) continue;
      const displayedRevision = visualizerState.pendingRevision ?? visualizerState.loadedRevision;
      if (displayedRevision === descriptor.data_revision) continue;
      markVisualizerDirty(targetGame, targetGame === game);
    }
    if (observedRevisionChanged) await refreshUpdateHealth();
  } finally {
    visualizerRevisionCheckRunning = false;
    if (visualizerRevisionCheckQueued) {
      visualizerRevisionCheckQueued = false;
      requestVisualizerRevisionCheck();
    }
  }
}

function handleWindowFocus(): void {
  requestVisualizerRevisionCheck();
}

function handleVisibilityChange(): void {
  if (!document.hidden) requestVisualizerRevisionCheck();
}

function installVisualizerRevisionWatchers(): void {
  if (visualizerRevisionCheckInterval !== null) return;
  window.addEventListener("focus", handleWindowFocus);
  document.addEventListener("visibilitychange", handleVisibilityChange);
  visualizerRevisionCheckInterval = window.setInterval(() => {
    if (!document.hidden) requestVisualizerRevisionCheck();
  }, VISUALIZER_REVISION_CHECK_INTERVAL_MS);
}

function uninstallVisualizerRevisionWatchers(): void {
  window.removeEventListener("focus", handleWindowFocus);
  document.removeEventListener("visibilitychange", handleVisibilityChange);
  if (visualizerRevisionCheckInterval !== null) {
    window.clearInterval(visualizerRevisionCheckInterval);
    visualizerRevisionCheckInterval = null;
  }
}

function setNotice(target: HTMLElement, message: string, kind: "normal" | "error" | "success" = "normal"): void {
  target.textContent = message;
  target.className = kind === "normal" ? "notice" : `notice ${kind}`;
}

function setUpdateHealthView(
  state: "loading" | "healthy" | "warning" | "busy" | "error",
  badge: string,
  summary: string,
  detail: string,
): void {
  updateHealthPanel.className = `update-health ${state}`;
  updateHealthBadge.textContent = badge;
  updateHealthSummary.textContent = summary;
  updateHealthDetail.textContent = detail;
  updateHealthGames.replaceChildren();
  updateHealthGames.hidden = true;
}

function renderUpdateHealthLoading(detail = "完成后会显示 HSR 与 ZZZ 的本机成功时间和终局最新采样。"): void {
  setUpdateHealthView("loading", "读取中", "正在读取最近自动更新记录…", detail);
}

function clearUpdateHealthTimers(resetBusyAttempt = true): void {
  if (updateHealthBusyRetryTimer !== null) {
    window.clearTimeout(updateHealthBusyRetryTimer);
    updateHealthBusyRetryTimer = null;
  }
  if (updateHealthStaleTimer !== null) {
    window.clearTimeout(updateHealthStaleTimer);
    updateHealthStaleTimer = null;
  }
  if (resetBusyAttempt) updateHealthBusyRetryAttempt = 0;
}

function scheduleBusyUpdateHealthRetry(): void {
  if (isWindowClosing() || updateHealthBusyRetryTimer !== null) return;
  const delay = UPDATE_HEALTH_BUSY_RETRY_DELAYS_MS[
    Math.min(updateHealthBusyRetryAttempt, UPDATE_HEALTH_BUSY_RETRY_DELAYS_MS.length - 1)
  ];
  updateHealthBusyRetryAttempt += 1;
  const workspaceId = capabilities?.workspace.workspace_id ?? "";
  updateHealthBusyRetryTimer = window.setTimeout(() => {
    updateHealthBusyRetryTimer = null;
    if (isWindowClosing() || !workspaceId || workspaceId !== capabilities?.workspace.workspace_id) return;
    void refreshUpdateHealth(true);
  }, delay);
}

function scheduleUpdateHealthStaleDeadline(health: DesktopUpdateHealth): void {
  if (isWindowClosing()) return;
  const now = Date.now();
  const localUpdateDeadlines = health.games
    .map((entry) => Date.parse(entry.completed_at_utc) + UPDATE_HEALTH_STALE_AFTER_MS)
    .filter((deadline) => deadline > now);
  const freshnessDeadlines = health.games.flatMap((entry) => Object.values(entry.freshness.modes)
    .flatMap((mode) => {
      const deadlines: number[] = [];
      for (const [date, dayOffset] of [[mode.start_date, 0], [mode.end_date, 1]] as const) {
        if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
        const [year, month, day] = date.split("-").map(Number);
        const deadline = new Date(year, month - 1, day + dayOffset).getTime();
        if (Number.isFinite(deadline) && deadline > now) deadlines.push(deadline);
      }
      return deadlines;
    }));
  const nextDateBoundary = nextLocalDateBoundary(new Date(now));
  const futureDeadlines = [
    ...localUpdateDeadlines,
    ...freshnessDeadlines,
    ...(nextDateBoundary === null ? [] : [nextDateBoundary]),
  ];
  if (!futureDeadlines.length) return;
  const workspaceId = health.workspace_id;
  const delay = Math.min(Math.max(1, Math.min(...futureDeadlines) - now), MAX_BROWSER_TIMER_DELAY_MS);
  updateHealthStaleTimer = window.setTimeout(() => {
    updateHealthStaleTimer = null;
    if (isWindowClosing() || workspaceId !== capabilities?.workspace.workspace_id) return;
    void refreshUpdateHealth();
  }, delay);
}

function invalidateUpdateHealth(detail: string): void {
  clearUpdateHealthTimers();
  updateHealthRequestGeneration += 1;
  renderUpdateHealthLoading(detail);
}

function invokeTrackedUpdateHealth(): Promise<unknown> {
  const read = invoke<unknown>("get_update_health");
  pendingUpdateHealthReads.add(read);
  void read.then(
    () => pendingUpdateHealthReads.delete(read),
    () => pendingUpdateHealthReads.delete(read),
  );
  return read;
}

function pendingUpdateHealthRead(): Promise<void> | null {
  const reads = [...pendingUpdateHealthReads];
  if (!reads.length) return null;
  return Promise.allSettled(reads).then(() => undefined);
}

function formatUpdateHealthTime(completedAtUtc: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(completedAtUtc));
}

function renderHealthyUpdateHealth(health: DesktopUpdateHealth): void {
  const games = new Map(health.games.map((entry) => [entry.game, entry]));
  const today = localDateKey();
  const freshnessSummaries = new Map(GAMES.flatMap((targetGame) => {
    const entry = games.get(targetGame);
    return entry ? [[targetGame, summarizeFreshness(entry.freshness, today)] as const] : [];
  }));
  const staleLocalGames = GAMES.filter((targetGame) => {
    const entry = games.get(targetGame);
    return entry && Date.now() - Date.parse(entry.completed_at_utc) >= UPDATE_HEALTH_STALE_AFTER_MS;
  });
  const staleSampleGames = GAMES.filter((targetGame) => (
    (freshnessSummaries.get(targetGame)?.staleSamples ?? 0) > 0
  ));
  const historicalSampleGames = GAMES.filter((targetGame) => {
    return (freshnessSummaries.get(targetGame)?.stale ?? 0) > 0;
  });
  const qualityWarningGames = GAMES.filter((targetGame) => {
    const entry = games.get(targetGame);
    if (!entry) return false;
    const summary = freshnessSummaries.get(targetGame);
    if (!summary) return false;
    return entry.freshness.status === "warning"
      || summary.latestSampleDate === null
      || summary.unknown > 0
      || summary.futureSamples > 0
      || summary.missingSamples > 0;
  });
  const localStale = staleLocalGames.length > 0;
  const hasStaleSamples = staleSampleGames.length > 0;
  const hasHistoricalSamples = historicalSampleGames.length > 0;
  const hasQualityWarnings = qualityWarningGames.length > 0;
  setUpdateHealthView(
    localStale || hasStaleSamples || hasHistoricalSamples || hasQualityWarnings ? "warning" : "healthy",
    localStale
      ? "计划待查"
      : hasStaleSamples
        ? "样本陈旧"
        : hasHistoricalSamples
          ? "本机正常"
          : hasQualityWarnings
            ? "数据待查"
            : "正常",
    localStale
      ? `本机产物校验通过，但 ${staleLocalGames.map(gameShortLabel).join("、")} 的成功记录已超过 36 小时。`
      : hasStaleSamples
        ? `本机产物校验通过；${staleSampleGames.map(gameShortLabel).join("、")} 存在已超过 ${ENDGAME_SAMPLE_STALE_AFTER_DAYS - 1} 天未更新的终局样本。`
        : hasHistoricalSamples
          ? `本机产物校验通过；${historicalSampleGames.map(gameShortLabel).join("、")} 上游仍有历史终局样本。`
          : hasQualityWarnings
            ? `本机产物校验通过；${qualityWarningGames.map(gameShortLabel).join("、")} 上游数据质量有告警。`
            : "本机产物校验通过。",
    localStale
      ? "计划任务可能未运行；请手动更新对应游戏并检查每日计划任务。终局采样取决于上游发布，历史样本不等于本机刷新失败。"
      : hasQualityWarnings && !hasHistoricalSamples && !hasStaleSamples
        ? "最近更新记录正常，但上游数据质量需留意；终局分析继续使用已校验产物。"
        : "最近更新记录正常。终局采样取决于上游发布；历史样本不等于本机刷新失败，具体样本年龄见游戏卡。",
  );
  for (const targetGame of GAMES) {
    const entry = games.get(targetGame);
    if (!entry) continue;
    const summary = freshnessSummaries.get(targetGame);
    if (!summary) continue;
    const latestSampleAgeSuffix = summary.latestSampleDate
      ? sampleAgeSuffix(summary.latestSampleDate, today)
      : "";
    const modeStates = [
      summary.active ? `当前 ${summary.active}` : "",
      summary.stale ? `历史 ${summary.stale}` : "",
      summary.future ? `未来 ${summary.future}` : "",
      summary.unknown ? `未知 ${summary.unknown}` : "",
    ].filter(Boolean);
    const item = element("details", "update-health-game");
    item.dataset.game = targetGame;
    item.dataset.completedAtUtc = entry.completed_at_utc;
    if (summary.stale) item.classList.add("has-history");
    if (summary.staleSamples) item.classList.add("has-stale-sample");
    const itemSummary = element("summary", "update-health-game-summary");
    itemSummary.setAttribute(
      "aria-label",
      `${gameShortLabel(targetGame)} 最近成功 ${formatUpdateHealthTime(entry.completed_at_utc)}；终局最新采样 ${summary.latestSampleDate ?? "未知"}${latestSampleAgeSuffix}${modeStates.length ? `；${modeStates.join("，")}` : ""}；各模式状态、采样日、样本年龄与周期边界`,
    );
    itemSummary.append(
      element("strong", undefined, `${gameShortLabel(targetGame)} 最近成功`),
      element("span", "update-health-completed", formatUpdateHealthTime(entry.completed_at_utc)),
      element(
        "span",
        "update-health-sample",
        `终局最新采样 ${summary.latestSampleDate ?? "未知"}${latestSampleAgeSuffix}${modeStates.length ? ` · ${modeStates.join(" / ")}` : ""}`,
      ),
      element("span", "update-health-toggle", "各模式详情"),
    );
    const modeList = element("ul", "update-health-mode-list");
    modeList.setAttribute("aria-label", `${gameShortLabel(targetGame)} 各模式终局数据时效`);
    for (const [mode, modeFreshness] of Object.entries(entry.freshness.modes)
      .sort(([left], [right]) => left.localeCompare(right))) {
      const modeItem = element("li", "update-health-mode");
      const modeSampleAgeSuffix = modeFreshness.sample_date
        ? sampleAgeSuffix(modeFreshness.sample_date, today)
        : "";
      if (staleSampleAgeDays(modeFreshness.sample_date, today) !== null) {
        modeItem.classList.add("has-stale-sample");
      }
      const modeHeading = element("span", "update-health-mode-heading");
      modeHeading.append(
        element("strong", "update-health-mode-name", modeLabel(mode)),
        element(
          "span",
          "update-health-mode-status",
          freshnessLabel(effectiveFreshnessStatus(modeFreshness)),
        ),
      );
      modeItem.append(
        modeHeading,
        element(
          "span",
          "update-health-mode-dates",
          `${modeFreshness.sample_date ? `采样 ${modeFreshness.sample_date}${modeSampleAgeSuffix}` : "采样日未知"} · ${freshnessPeriodLabel(modeFreshness)}`,
        ),
      );
      modeList.append(modeItem);
    }
    item.append(itemSummary, modeList);
    updateHealthGames.append(item);
  }
  updateHealthGames.hidden = false;
  updateHealthBusyRetryAttempt = 0;
  scheduleUpdateHealthStaleDeadline(health);
}

function gameShortLabel(targetGame: Game): string {
  return targetGame === "hsr" ? "HSR" : "ZZZ";
}

function isBusyUpdateHealthFailure(failureCode: string): boolean {
  return failureCode === "workspace.busy"
    || failureCode === "workspace.write_busy"
    || /(?:^|[._-])(busy|locked|in_progress|already_running)(?:$|[._-])/.test(failureCode);
}

function renderUpdateHealthFailure(failureCode: string, retryable: boolean): void {
  const publicCode = /^[a-z0-9._-]{1,96}$/.test(failureCode)
    ? failureCode
    : "desktop.update_health_failed";
  if (isBusyUpdateHealthFailure(publicCode)) {
    setUpdateHealthView(
      "busy",
      "更新中",
      "数据正在更新，完成后会自动重新检查。",
      `当前工作区正由更新任务占用（${publicCode}）。`,
    );
    scheduleBusyUpdateHealthRetry();
    return;
  }
  setUpdateHealthView(
    "error",
    "需处理",
    "最近自动更新未通过完整校验。",
    retryable
      ? `可以重试：建议稍后点击刷新；若仍异常，请分别手动更新 HSR 与 ZZZ，并打开日志排查。（${publicCode}）`
      : `需要修正后再重试：请先检查本机更新配置，再分别手动更新 HSR 与 ZZZ；若仍异常，请打开日志排查。（${publicCode}）`,
  );
}

async function refreshUpdateHealth(fromBusyRetry = false): Promise<void> {
  if (isWindowClosing()) return;
  clearUpdateHealthTimers(!fromBusyRetry);
  const workspaceId = capabilities?.workspace.workspace_id ?? "";
  const request = ++updateHealthRequestGeneration;
  if (!workspaceId) {
    renderUpdateHealthFailure("desktop.workspace_unavailable", true);
    return;
  }
  renderUpdateHealthLoading();
  try {
    const result = await invokeTrackedUpdateHealth();
    if (isWindowClosing()
      || request !== updateHealthRequestGeneration
      || workspaceId !== (capabilities?.workspace.workspace_id ?? "")) return;
    const health = backendUpdateHealth(result);
    if (!health) {
      renderUpdateHealthFailure("desktop.update_health_invalid_response", true);
      return;
    }
    if (health.workspace_id !== workspaceId) {
      renderUpdateHealthFailure("desktop.update_health_workspace_mismatch", true);
      return;
    }
    if (health.healthy) {
      renderHealthyUpdateHealth(health);
      return;
    }
    renderUpdateHealthFailure(health.failure_code ?? "update.health_unknown", health.retryable);
  } catch (error) {
    if (isWindowClosing()
      || request !== updateHealthRequestGeneration
      || workspaceId !== (capabilities?.workspace.workspace_id ?? "")) return;
    const failure = safeError(error);
    renderUpdateHealthFailure(failure.code, failure.retryable ?? true);
  }
}

function updateWorkspaceControls(): void {
  for (const button of gameButtons.values()) button.disabled = workspaceBusy || boxTransitionBusy;
  selectWorkspaceButton.disabled = workspaceBusy
    || boxTransitionBusy
    || capabilities?.workspace_selection_enabled === false
    || hasActiveTask();
  openLogButton.disabled = workspaceBusy || boxTransitionBusy;
  refreshWorkspaceButton.disabled = workspaceBusy || boxTransitionBusy;
  reloadVisualizerButton.disabled = workspaceBusy || boxTransitionBusy || visualizerLoading.has(game);
}

function capabilityFor(operation: TaskOperation): OperationCapability | undefined {
  return capabilities?.operations.find((item) => item.operation === operation);
}

function renderCapabilities(): void {
  workspaceSummary.replaceChildren();
  capabilityGrid.replaceChildren();
  runtimeLimits.replaceChildren();
  workspaceWarnings.replaceChildren();
  if (!capabilities) {
    updateWorkspaceControls();
    updateExportControls();
    updateTaskForm();
    return;
  }

  const summaryItems: ReadonlyArray<[string, string]> = [
    ["名称", capabilities.workspace.label],
    ["来源", capabilities.workspace.source],
    ["修订", String(capabilities.workspace.revision)],
    ["会话标识", capabilities.workspace.workspace_id],
  ];
  for (const [label, value] of summaryItems) {
    const item = element("div", "summary-item");
    item.append(element("span", "muted", label), element("strong", undefined, value));
    workspaceSummary.append(item);
  }

  for (const operation of CAPABILITY_OPERATIONS) {
    const capability = capabilityFor(operation.value);
    const card = element("article", `capability-card ${capability?.enabled ? "ready" : "blocked"}`);
    card.append(element("strong", undefined, operation.label));
    if (!capability) {
      card.append(element("span", "muted", "后端未声明此能力"));
    } else if (capability.enabled) {
      card.append(element("span", "success-text", "输入就绪"));
    } else {
      card.append(element("span", "warning-text", "缺少输入"));
      const list = element("ul", "missing-list");
      for (const missing of capability.missing_inputs) list.append(element("li", undefined, missing));
      card.append(list);
    }
    capabilityGrid.append(card);
  }

  const decisionCapability = capabilityFor("decision");
  diagnosticText.textContent = decisionCapability?.enabled
    ? "Legacy decision 兼容诊断输入已就绪；正式 UI 不提供运行入口，也不会默认执行。"
    : `Legacy decision 仅作兼容诊断；当前缺少：${decisionCapability?.missing_inputs.join("、") || "后端能力声明"}。`;

  const limits: ReadonlyArray<[string, boolean, string, string]> = [
    ["任务历史持久化", capabilities.task_history_persistent, "支持", "不支持（关闭应用后不会保留）"],
    ["任务状态权威查询", capabilities.task_queries_are_authoritative, "已启用", "未启用"],
    ["异常终止保护", capabilities.abrupt_termination_supported, "支持", "不支持"],
    ["跨进程恢复", capabilities.cross_process_recovery_supported, "支持", "不支持"],
  ];
  for (const [label, enabled, yes, no] of limits) {
    const item = element("div", "runtime-limit");
    item.append(element("span", "muted", label), element("strong", enabled ? yes : no));
    runtimeLimits.append(item);
  }
  historyMeta.textContent = capabilities.task_history_persistent
    ? "这些不是你的待办，只显示数据更新和报告生成的运行记录。"
    : "这些不是你的待办，只显示本次打开程序后的数据更新和报告生成记录。";

  for (const warning of capabilities.warnings) {
    workspaceWarnings.append(element("p", "notice warning", warning));
  }
  updateWorkspaceControls();
  updateExportControls();
  updateTaskForm();
}

async function refreshCapabilities(): Promise<boolean> {
  const request = ++capabilitiesRequestGeneration;
  setNotice(workspaceMessage, "正在读取本机能力…");
  try {
    const next = await invoke<DesktopCapabilities>("get_capabilities");
    if (isWindowClosing() || request !== capabilitiesRequestGeneration) return false;
    const workspaceChanged = historyWorkspaceId !== next.workspace.workspace_id;
    capabilities = next;
    if (workspaceChanged) restoreTaskHistory(next.workspace.workspace_id);
    renderCapabilities();
    setNotice(workspaceMessage, "能力与缺失输入已刷新。", "success");
    return true;
  } catch (error) {
    if (isWindowClosing() || request !== capabilitiesRequestGeneration) return false;
    capabilities = null;
    renderCapabilities();
    const failure = safeError(error);
    setNotice(workspaceMessage, `能力读取失败（${failure.code}）：${failure.message}`, "error");
    return false;
  }
}

async function reloadSelectedWorkspaceState(): Promise<boolean> {
  capabilitiesRequestGeneration += 1;
  invalidateUpdateHealth("正在读取当前工作区的自动更新记录…");
  resetVisualizerFrames();
  const capabilitiesReady = await refreshCapabilities();
  if (!capabilitiesReady || isWindowClosing()) {
    if (!isWindowClosing()) renderUpdateHealthFailure("desktop.workspace_unavailable", true);
    return false;
  }
  await Promise.all([refreshTasks(), loadVisualizer(false), refreshUpdateHealth()]);
  return !isWindowClosing();
}

async function reconcileWorkspaceAfterCloseCancellation(): Promise<void> {
  if (!workspaceReconcilePending || isWindowClosing() || pendingWorkspaceTransition) return;
  workspaceBusy = true;
  setBoxTransitionBusy(true);
  const finishWorkspaceTransition = beginWorkspaceTransitionTracking();
  renderCapabilities();
  try {
    if (await reloadSelectedWorkspaceState()) {
      workspaceReconcilePending = false;
      setNotice(workspaceMessage, "工作区状态已重新同步。", "success");
    }
  } catch (error) {
    const failure = safeError(error);
    setNotice(workspaceMessage, `工作区重新同步失败（${failure.code}）：${failure.message}`, "error");
  } finally {
    workspaceBusy = false;
    setBoxTransitionBusy(false);
    finishWorkspaceTransition();
    renderCapabilities();
  }
}

async function selectWorkspace(): Promise<void> {
  if (workspaceBusy || boxTransitionBusy || hasActiveTask() || isWindowClosing()) return;
  workspaceBusy = true;
  setBoxTransitionBusy(true);
  const finishWorkspaceTransition = beginWorkspaceTransitionTracking();
  let workspaceSelectionUncertain = false;
  renderCapabilities();
  try {
    if (!await ensureVisualizerBoxesSaved(["hsr", "zzz"], "切换工作区")) {
      setNotice(workspaceMessage, "工作区未切换；请先处理 Box 保存问题。", "error");
      return;
    }
    if (isWindowClosing()) return;
    setNotice(workspaceMessage, "请选择可信的本机工作区…");
    workspaceSelectionUncertain = true;
    const result = await invoke<{ selected: boolean; workspace: WorkspaceSummary }>("select_workspace");
    if (!result.selected) {
      workspaceSelectionUncertain = false;
      if (!isWindowClosing()) setNotice(workspaceMessage, "未更改工作区；现有 Box 保持不变。");
      return;
    }
    workspaceReconcilePending = true;
    if (isWindowClosing()) return;
    setNotice(workspaceMessage, "工作区已切换，正在刷新…", "success");
    if (await reloadSelectedWorkspaceState()) {
      workspaceSelectionUncertain = false;
      workspaceReconcilePending = false;
    }
  } catch (error) {
    const reconcileAfterFailure = workspaceSelectionUncertain;
    let reconciledAfterFailure = false;
    if (reconcileAfterFailure) {
      workspaceReconcilePending = true;
      if (!isWindowClosing()) {
        try {
          if (await reloadSelectedWorkspaceState()) {
            workspaceSelectionUncertain = false;
            workspaceReconcilePending = false;
            reconciledAfterFailure = true;
          }
        } catch {
          // Preserve the original, authoritative selection failure below.
        }
      }
    }
    const failure = safeError(error);
    if (!isWindowClosing()) {
      setNotice(
        workspaceMessage,
        reconcileAfterFailure
          ? `${reconciledAfterFailure ? "切换结果未能确认，已按后端当前工作区重新同步" : "切换结果未能确认，工作区仍需重新同步"}（${failure.code}）：${failure.message}`
          : `切换失败（${failure.code}）：${failure.message}`,
        "error",
      );
    }
  } finally {
    if (workspaceSelectionUncertain && isWindowClosing()) workspaceReconcilePending = true;
    workspaceBusy = false;
    setBoxTransitionBusy(false);
    finishWorkspaceTransition();
    renderCapabilities();
  }
}

async function openLogLocation(): Promise<void> {
  if (isWindowClosing()) return;
  try {
    await invoke("open_log_location");
    setNotice(workspaceMessage, "已打开脱敏诊断日志目录。", "success");
  } catch (error) {
    const failure = safeError(error);
    setNotice(workspaceMessage, `日志目录无法打开（${failure.code}）：${failure.message}`, "error");
  }
}

function updateExportControls(): void {
  for (const operation of EXPORT_OPERATIONS) {
    const capability = capabilityFor(operation.value);
    const button = exportButtons.get(operation.value);
    const status = exportStatuses.get(operation.value);
    if (!button || !status) continue;
    button.disabled = taskBusy
      || hasActiveTask()
      || boxTransitionBusy
      || isWindowClosing()
      || !capability?.enabled;
    if (!capabilities) {
      setNotice(status, "等待本机能力信息。");
    } else if (!capability) {
      setNotice(status, "本机后端未声明此导出能力。", "error");
    } else if (capability.missing_inputs.length > 0) {
      setNotice(status, `缺少输入：${capability.missing_inputs.join("、")}`, "error");
    } else if (hasActiveTask()) {
      setNotice(status, "已有任务运行中；导出与报告不会并行写入。", "normal");
    } else if (!taskBusy) {
      setNotice(status, "本机配置已通过校验。", "success");
    }
  }
}

function buildExportIntent(operation: ExportOperation): string {
  return JSON.stringify({
    schema_version: "miho-export-task-intent-v1",
    task: { operation, params: {} },
  });
}

async function startExport(operation: ExportOperation): Promise<void> {
  const capability = capabilityFor(operation);
  if (taskBusy
    || hasActiveTask()
    || boxTransitionBusy
    || isWindowClosing()
    || !capabilities
    || !capability?.enabled) return;
  taskBusy = true;
  setBoxTransitionBusy(true);
  const finishTaskStart = beginTaskStartTracking();
  updateExportControls();
  updateTaskForm();
  setNotice(exportMessage, "正在交给全局本机后台任务管理器…");
  try {
    if (!await ensureVisualizerBoxesSaved(GAMES, "更新数据") || isWindowClosing()) return;
    const snapshot = await invoke<PublicTaskSnapshot>("start_export_task", {
      workspaceId: capabilities.workspace.workspace_id,
      intentJson: buildExportIntent(operation),
    });
    mergeQueriedTask(snapshot);
    setNotice(exportMessage, `${operationLabel(operation)}已开始。`, "success");
    await queryTask(snapshot.task_id);
  } catch (error) {
    const failure = safeError(error);
    setNotice(exportMessage, `导出启动失败（${failure.code}）：${failure.message}`, "error");
    if (failure.retryable) await Promise.all([refreshCapabilities(), refreshTasks()]);
  } finally {
    taskBusy = false;
    finishTaskStart();
    setBoxTransitionBusy(false);
    updateExportControls();
    updateTaskForm();
  }
}

function updateTaskForm(): void {
  const evidenceOrCoverage = taskForm.operation === "evidence" || taskForm.operation === "coverage";
  const evidence = taskForm.operation === "evidence";
  plannedInput.value = taskForm.plannedSlugs;
  statusesInput.value = taskForm.planStatuses;
  limitInput.value = taskForm.limit;
  minRateInput.value = taskForm.minRate;
  includeMissingInput.checked = taskForm.includeMissing;
  limitField.hidden = !evidenceOrCoverage;
  minRateField.hidden = !evidenceOrCoverage;
  includeMissingField.hidden = !evidence;
  const operation = OPERATIONS.find((candidate) => candidate.value === taskForm.operation);
  operationDescription.textContent = operation?.description ?? "";
  const capability = capabilityFor(taskForm.operation);
  const missing = capability?.missing_inputs ?? [];
  const disabled = taskBusy
    || hasActiveTask()
    || boxTransitionBusy
    || isWindowClosing()
    || !capability?.enabled;
  startTaskButton.disabled = disabled;
  if (!capabilities) {
    setNotice(taskMessage, "等待本机能力信息。", "normal");
  } else if (!capability) {
    setNotice(taskMessage, "本机后端未声明此报告能力。", "error");
  } else if (missing.length > 0) {
    setNotice(taskMessage, `缺少输入：${missing.join("、")}`, "error");
  } else if (hasActiveTask()) {
    setNotice(taskMessage, "已有任务运行中；完成或取消后可开始新任务。", "normal");
  } else if (!taskBusy) {
    setNotice(taskMessage, "输入就绪。", "success");
  }
}

function buildIntent(): string | null {
  const plannedSlugs = splitValues(taskForm.plannedSlugs);
  const planStatuses = splitValues(taskForm.planStatuses);
  if (planStatuses.length === 0) {
    setNotice(taskMessage, "规划状态不能为空。", "error");
    return null;
  }

  let params: Record<string, unknown> = { planned_slugs: plannedSlugs, plan_statuses: planStatuses };
  if (taskForm.operation === "evidence" || taskForm.operation === "coverage") {
    const limit = Number(taskForm.limit);
    if (!Number.isSafeInteger(limit) || limit < 0) {
      setNotice(taskMessage, "记录上限必须是非负安全整数。", "error");
      return null;
    }
    if (!taskForm.minRate.trim()) {
      setNotice(taskMessage, "A 档最低使用率不能为空。", "error");
      return null;
    }
    params = { ...params, limit, min_a_app_rate: taskForm.minRate.trim() };
    if (taskForm.operation === "evidence") params.include_missing = taskForm.includeMissing;
  }

  return JSON.stringify({
    schema_version: "miho-task-intent-v1",
    task: { operation: taskForm.operation, params },
  });
}

async function startTask(): Promise<void> {
  const capability = capabilityFor(taskForm.operation);
  if (taskBusy
    || hasActiveTask()
    || boxTransitionBusy
    || isWindowClosing()
    || !capabilities
    || !capability?.enabled) return;
  const intentJson = buildIntent();
  if (!intentJson) return;
  taskBusy = true;
  const finishTaskStart = beginTaskStartTracking();
  updateExportControls();
  updateTaskForm();
  setNotice(taskMessage, "正在交给本机后台任务管理器…");
  try {
    const snapshot = await invoke<PublicTaskSnapshot>("start_task", {
      workspaceId: capabilities.workspace.workspace_id,
      intentJson,
    });
    mergeQueriedTask(snapshot);
    setNotice(taskMessage, "任务已开始。", "success");
    await queryTask(snapshot.task_id);
  } catch (error) {
    const failure = safeError(error);
    setNotice(taskMessage, `启动失败（${failure.code}）：${failure.message}`, "error");
    if (failure.retryable) await Promise.all([refreshCapabilities(), refreshTasks()]);
  } finally {
    taskBusy = false;
    finishTaskStart();
    updateExportControls();
    updateTaskForm();
  }
}

function mergeQueriedTask(snapshot: PublicTaskSnapshot): void {
  const querySequence = snapshot.status_history.length;
  const knownSequence = authoritativeTaskSequences.get(snapshot.task_id) ?? 0;
  if (querySequence < knownSequence) return;
  authoritativeTaskSequences.set(snapshot.task_id, querySequence);
  tasks.set(snapshot.task_id, snapshot);
  restoredTaskIds.delete(snapshot.task_id);
  persistTaskHistory();
  renderTasks();
}

async function queryTask(taskId: string): Promise<void> {
  const generation = (taskQueries.get(taskId) ?? 0) + 1;
  taskQueries.set(taskId, generation);
  try {
    const snapshot = await invoke<PublicTaskSnapshot>("get_task", { taskId });
    if (taskQueries.get(taskId) !== generation) return;
    mergeQueriedTask(snapshot);
    if (TERMINAL_STATUSES.has(snapshot.status)) {
      await refreshCapabilities();
      const exportedGame = snapshot.operation === "hsr-export" ? "hsr" : snapshot.operation === "zzz-export" ? "zzz" : null;
      if (snapshot.status === "succeeded" && exportedGame) {
        markVisualizerDirty(exportedGame, exportedGame === game);
      }
      if (exportedGame && !updateHealthRefreshedTaskIds.has(snapshot.task_id)) {
        updateHealthRefreshedTaskIds.add(snapshot.task_id);
        await refreshUpdateHealth();
      }
    }
  } catch (error) {
    if (taskQueries.get(taskId) !== generation) return;
    const failure = safeError(error);
    setNotice(taskMessage, `任务查询失败（${failure.code}）：${failure.message}`, "error");
  }
}

async function refreshTasks(): Promise<void> {
  if (taskRefreshBusy || isWindowClosing()) return;
  taskRefreshBusy = true;
  taskRefreshButton.disabled = true;
  try {
    const snapshots = await invoke<PublicTaskSnapshot[]>("list_tasks");
    let updateHealthAfterTerminalExport = false;
    for (const snapshot of snapshots) {
      const previous = tasks.get(snapshot.task_id);
      mergeQueriedTask(snapshot);
      const current = tasks.get(snapshot.task_id);
      const exported = snapshot.operation === "hsr-export" || snapshot.operation === "zzz-export";
      if (current === snapshot
        && previous
        && !TERMINAL_STATUSES.has(previous.status)
        && TERMINAL_STATUSES.has(snapshot.status)
        && exported
        && !updateHealthRefreshedTaskIds.has(snapshot.task_id)) {
        updateHealthRefreshedTaskIds.add(snapshot.task_id);
        updateHealthAfterTerminalExport = true;
      }
    }
    renderTasks();
    if (updateHealthAfterTerminalExport) await refreshUpdateHealth();
  } catch (error) {
    const failure = safeError(error);
    setNotice(taskMessage, `任务列表刷新失败（${failure.code}）：${failure.message}`, "error");
  } finally {
    taskRefreshBusy = false;
    taskRefreshButton.disabled = boxTransitionBusy || isWindowClosing();
  }
}

async function cancelTask(taskId: string): Promise<void> {
  if (isWindowClosing()) return;
  try {
    const result = await invoke<{ outcome: CancelOutcome; task: PublicTaskSnapshot | null }>("cancel_task", { taskId });
    if (result.task) mergeQueriedTask(result.task);
    if (result.outcome !== "not_found" && result.task) await queryTask(taskId);
    const feedback: Record<CancelOutcome, [string, "normal" | "error" | "success"]> = {
      requested: ["取消请求已提交；后台任务会在安全检查点停止。", "success"],
      too_late: ["任务已经进入不可中断的写入阶段，当前取消请求过晚。", "normal"],
      already_terminal: ["任务已经结束，无需再次取消。", "normal"],
      not_found: ["任务不存在，或已不在当前进程的临时历史中。", "error"],
    };
    const outcome = feedback[result.outcome];
    if (outcome) setNotice(taskMessage, outcome[0], outcome[1]);
    else setNotice(taskMessage, "后端返回了无法识别的取消结果。", "error");
  } catch (error) {
    const failure = safeError(error);
    setNotice(taskMessage, `取消失败（${failure.code}）：${failure.message}`, "error");
  }
}

async function useArtifact(command: "open_artifact" | "reveal_artifact", artifact: PublicArtifact): Promise<void> {
  if (isWindowClosing()) return;
  try {
    await invoke(command, { artifactId: artifact.artifact_id });
    setNotice(
      taskMessage,
      command === "open_artifact" ? `已打开 ${artifact.name}。` : `已在资源管理器中定位 ${artifact.name}。`,
      "success",
    );
  } catch (error) {
    const failure = safeError(error);
    setNotice(taskMessage, `结果文件操作失败（${failure.code}）：${failure.message}`, "error");
  }
}

function hasActiveTask(): boolean {
  return [...tasks.values()].some((task) => !TERMINAL_STATUSES.has(task.status));
}

function renderTasks(): void {
  taskList.replaceChildren();
  taskRefreshButton.disabled = taskRefreshBusy || boxTransitionBusy || isWindowClosing();
  const ordered = [...tasks.values()].sort((left, right) => right.task_id.localeCompare(left.task_id));
  if (ordered.length === 0) {
    taskList.append(element("p", "empty-state", "还没有进行数据更新或报告生成。"));
  }
  for (const task of ordered) {
    const exportedGame = task.operation === "hsr-export" ? "hsr"
      : task.operation === "zzz-export" ? "zzz"
        : null;
    const card = element("article", `task-card status-${task.status}`);
    const titleRow = element("div", "task-title-row");
    const title = element("div");
    title.append(element("h3", undefined, operationLabel(task.operation)));
    const badge = element("span", `status-badge ${task.status}`, STATUS_LABELS[task.status]);
    titleRow.append(title, badge);
    const historicalSample = task.freshness ? summarizeFreshness(task.freshness).stale > 0 : false;
    const taskFreshnessSummary = task.freshness ? summarizeFreshness(task.freshness) : null;
    const freshnessWarning = task.freshness?.status === "warning"
      || taskFreshnessSummary?.latestSampleDate === null
      || (taskFreshnessSummary?.unknown ?? 0) > 0;
    const outcome = task.status === "succeeded"
      ? exportedGame
        ? historicalSample
          ? "本机更新与校验成功；Box 与卡池已刷新，终局分析保留上游最新可用的历史样本。"
          : freshnessWarning
            ? "本机更新与校验成功；Box 与卡池已刷新，终局数据质量有告警。"
            : task.freshness
              ? "本机更新与校验成功；Box、卡池和终局分析已刷新。"
            : "本机更新已完成；打开对应游戏查看本次结果。"
        : "操作已经完成，报告已生成。"
      : task.status === "failed"
        ? "操作没有完成，请查看下方原因。"
        : task.status === "cancelled"
          ? "操作已取消，没有继续写入。"
          : task.status === "committing"
            ? "处理完成，正在安全保存结果。"
            : "正在后台处理，可以继续查看 Box。";
    card.append(titleRow, element("p", "task-summary muted", outcome));
    if (task.freshness) {
      const modes = Object.entries(task.freshness.modes)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([mode, freshness]) => `${modeLabel(mode)}：${freshnessLabel(effectiveFreshnessStatus(freshness))}${freshness.sample_date ? `（采样 ${freshness.sample_date}）` : ""}`);
      if (modes.length) card.append(element("p", "task-summary", `数据时效 · ${modes.join("；")}`));
    }

    const technical = element("details", "technical-details");
    technical.append(element("summary", undefined, "技术详情"), element("p", "task-id", `运行编号：${task.task_id}`));
    const timeline = element("ol", "status-history");
    for (const status of task.status_history) timeline.append(element("li", undefined, STATUS_LABELS[status]));
    technical.append(timeline);

    if (task.failure) {
      const failure = element("div", "failure-box");
      failure.append(
        element("strong", undefined, "没有完成"),
        element("p", undefined, task.failure.message),
        element("p", "muted", task.failure.action),
        element("span", "muted", task.failure.retryable ? "可以稍后重试" : `失败阶段：${task.failure.stage}`),
      );
      card.append(failure);
      technical.append(element("p", "task-id", `错误代码：${task.failure.code}`));
    }

    if (task.artifacts.length > 0) {
      card.append(element("p", "task-summary", `已生成 ${task.artifacts.length} 个结果文件。`));
      const artifacts = element("div", "artifacts");
      artifacts.append(element("h4", undefined, "结果文件"));
      const list = element("ul");
      for (const artifact of task.artifacts) {
        const item = element("li");
        const identity = element("div", "artifact-identity");
        identity.append(element("span", undefined, artifact.name), element("small", undefined, artifact.kind));
        const actions = element("div", "artifact-actions");
        if (restoredTaskIds.has(task.task_id)) {
          actions.append(element("span", "muted", "历史回执"));
        } else {
          const openArtifact = makeButton("打开", "button compact", () => useArtifact("open_artifact", artifact));
          const revealArtifact = makeButton("定位", "button compact secondary", () => useArtifact("reveal_artifact", artifact));
          openArtifact.disabled = isWindowClosing();
          revealArtifact.disabled = isWindowClosing();
          actions.append(openArtifact, revealArtifact);
        }
        item.append(identity, actions);
        list.append(item);
      }
      artifacts.append(list);
      technical.append(artifacts);
    }

    if (task.status === "succeeded" && exportedGame) {
      const viewUpdate = makeButton("查看本次更新结果", "button secondary", () => showUpdatedGame(exportedGame));
      viewUpdate.disabled = workspaceBusy || boxTransitionBusy || isWindowClosing();
      card.append(viewUpdate);
    }

    if (!TERMINAL_STATUSES.has(task.status) && capabilities?.supports_cancel) {
      const cancel = makeButton(task.cancellation_requested ? "取消已请求" : "取消任务", "button danger", () => cancelTask(task.task_id));
      cancel.disabled = task.cancellation_requested || task.status === "committing" || isWindowClosing();
      card.append(cancel);
    }
    card.append(technical);
    taskList.append(card);
  }
  updateWorkspaceControls();
  updateExportControls();
  updateTaskForm();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasExactKeys(record: Record<string, unknown>, expected: readonly string[]): boolean {
  const actual = Object.keys(record);
  return actual.length === expected.length && expected.every((key) => Object.hasOwn(record, key));
}

function isUpdateAttemptId(value: unknown): value is string {
  return typeof value === "string" && /^[A-Za-z0-9_-]{1,96}$/.test(value);
}

function isUpdateHealthTimestamp(value: unknown): value is string {
  return typeof value === "string"
    && value.length <= 64
    && /(?:Z|[+-]\d{2}:\d{2})$/.test(value)
    && Number.isFinite(Date.parse(value));
}

function isDesktopUpdateHealthGame(value: unknown): value is DesktopUpdateHealthGame {
  return isRecord(value)
    && hasExactKeys(value, ["game", "attempt_id", "completed_at_utc", "freshness"])
    && GAMES.includes(value.game as Game)
    && isUpdateAttemptId(value.attempt_id)
    && isUpdateHealthTimestamp(value.completed_at_utc)
    && isTaskFreshness(value.freshness);
}

function backendUpdateHealth(value: unknown): DesktopUpdateHealth | null {
  if (!isRecord(value)) return null;
  const expectedKeys = ["schema_version", "workspace_id", "healthy", "checked_games", "games", "retryable"];
  if (Object.hasOwn(value, "attempt_id")) expectedKeys.push("attempt_id");
  if (Object.hasOwn(value, "failure_code")) expectedKeys.push("failure_code");
  if (!hasExactKeys(value, expectedKeys)
    || value.schema_version !== "miho-desktop-update-health-v2"
    || typeof value.workspace_id !== "string"
    || !/^[A-Za-z0-9-]{1,128}$/.test(value.workspace_id)
    || typeof value.healthy !== "boolean"
    || typeof value.retryable !== "boolean") return null;
  if (!Array.isArray(value.checked_games)) return null;
  const checkedGames = value.checked_games;
  if (checkedGames.length !== GAMES.length
    || !GAMES.every((targetGame) => checkedGames.includes(targetGame))
    || new Set(checkedGames).size !== checkedGames.length) return null;
  if (!Array.isArray(value.games)
    || value.games.length > GAMES.length
    || !value.games.every(isDesktopUpdateHealthGame)) return null;
  const games = value.games as DesktopUpdateHealthGame[];
  if (new Set(games.map((entry) => entry.game)).size !== games.length
    || (Object.hasOwn(value, "attempt_id") && !isUpdateAttemptId(value.attempt_id))
    || (Object.hasOwn(value, "failure_code")
      && (typeof value.failure_code !== "string" || !/^[a-z0-9._-]{1,96}$/.test(value.failure_code)))) return null;
  if (value.healthy && !GAMES.every((targetGame) => games.some((entry) => entry.game === targetGame))) return null;
  const health: DesktopUpdateHealth = {
    schema_version: "miho-desktop-update-health-v2",
    workspace_id: value.workspace_id,
    healthy: value.healthy,
    checked_games: checkedGames as Game[],
    games,
    retryable: value.retryable,
  };
  if (isUpdateAttemptId(value.attempt_id)) health.attempt_id = value.attempt_id;
  if (typeof value.failure_code === "string") health.failure_code = value.failure_code;
  return health;
}

function isTaskStatus(value: unknown): value is TaskStatus {
  return typeof value === "string" && Object.hasOwn(STATUS_LABELS, value);
}

function isTaskOperation(value: unknown): value is TaskOperation {
  return value === "decision"
    || EXPORT_OPERATIONS.some((operation) => operation.value === value)
    || OPERATIONS.some((operation) => operation.value === value);
}

function isPublicArtifact(value: unknown): value is PublicArtifact {
  if (!isRecord(value) || !hasExactKeys(value, ["artifact_id", "name", "kind"])) return false;
  return typeof value.artifact_id === "string" && typeof value.name === "string" && typeof value.kind === "string";
}

function isPublicFailure(value: unknown): value is PublicTaskFailure | null {
  if (value === null) return true;
  if (!isRecord(value) || !hasExactKeys(value, ["code", "stage", "retryable", "message", "action"])) return false;
  return typeof value.code === "string"
    && typeof value.stage === "string"
    && typeof value.retryable === "boolean"
    && typeof value.message === "string"
    && typeof value.action === "string";
}

function isTaskFreshnessDate(value: unknown): value is string {
  if (value === "") return true;
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  if (year < 1) return false;
  const parsed = new Date(0);
  parsed.setUTCHours(0, 0, 0, 0);
  parsed.setUTCFullYear(year, month - 1, day);
  return parsed.getUTCFullYear() === year
    && parsed.getUTCMonth() === month - 1
    && parsed.getUTCDate() === day;
}

function isTaskFreshness(value: unknown): value is TaskFreshnessSummary {
  if (!isRecord(value) || !hasExactKeys(value, ["status", "modes"]) || !isRecord(value.modes)) return false;
  if (value.status !== "ok" && value.status !== "warning") return false;
  const modes = Object.entries(value.modes);
  if (modes.length > 8) return false;
  return modes.every(([mode, freshness]) => {
    if (!/^[a-z]{1,8}$/.test(mode)
      || !isRecord(freshness)
      || !hasExactKeys(freshness, ["status", "sample_date", "start_date", "end_date"])
      || !["active", "stale", "future", "unknown"].includes(String(freshness.status))) return false;
    const boundaryShapeMatches = freshness.status === "future"
      ? freshness.start_date !== ""
      : freshness.status === "stale"
        ? freshness.end_date !== ""
        : freshness.status === "active"
          ? freshness.start_date !== "" || freshness.end_date !== ""
          : freshness.start_date === "" && freshness.end_date === "";
    return boundaryShapeMatches
      && isTaskFreshnessDate(freshness.sample_date)
      && isTaskFreshnessDate(freshness.start_date)
      && isTaskFreshnessDate(freshness.end_date);
  });
}

function isPublicTaskSnapshot(value: unknown): value is PublicTaskSnapshot {
  if (!isRecord(value)) return false;
  const expectedKeys = [
    "schema_version", "task_id", "operation", "status", "status_history",
    "cancellation_requested", "artifacts", "failure",
  ];
  if (Object.hasOwn(value, "freshness")) expectedKeys.push("freshness");
  if (!hasExactKeys(value, expectedKeys)) return false;
  return value.schema_version === "miho-public-task-snapshot-v1"
    && typeof value.task_id === "string"
    && value.task_id.length > 0
    && isTaskOperation(value.operation)
    && isTaskStatus(value.status)
    && Array.isArray(value.status_history)
    && value.status_history.length > 0
    && value.status_history.every(isTaskStatus)
    && value.status_history[value.status_history.length - 1] === value.status
    && typeof value.cancellation_requested === "boolean"
    && Array.isArray(value.artifacts)
    && value.artifacts.every(isPublicArtifact)
    && isPublicFailure(value.failure)
    && (!Object.hasOwn(value, "freshness") || isTaskFreshness(value.freshness));
}

function isTaskUpdate(value: unknown): value is TaskUpdate {
  if (!isRecord(value) || !hasExactKeys(value, ["schema_version", "sequence", "task"])) return false;
  return value.schema_version === "miho-task-update-v1"
    && typeof value.sequence === "number"
    && Number.isSafeInteger(value.sequence)
    && value.sequence >= 1
    && isPublicTaskSnapshot(value.task)
    && value.sequence === value.task.status_history.length;
}

async function installTaskListener(): Promise<void> {
  if (unlistenTaskUpdates) return;
  unlistenTaskUpdates = await listen<unknown>("miho-task-update-v1", (event) => {
    if (!isTaskUpdate(event.payload)) return;
    const { sequence, task } = event.payload;
    const knownSequence = eventTaskSequences.get(task.task_id) ?? 0;
    if (sequence <= knownSequence) return;
    eventTaskSequences.set(task.task_id, sequence);
    // Event payloads only wake an authoritative native query; they are never rendered directly.
    void queryTask(task.task_id);
  });
}

function backendVisualizerDescriptor(value: unknown, targetGame: Game): VisualizerDescriptor | null {
  if (!isRecord(value)
    || !hasExactKeys(value, ["schema_version", "url", "data_revision"])
    || value.schema_version !== "miho-visualizer-descriptor-v1"
    || typeof value.url !== "string"
    || typeof value.data_revision !== "string"
    || !/^[a-f0-9]{64}$/.test(value.data_revision)) return null;
  try {
    const parsed = new URL(value.url);
    const windowsProtocol = parsed.protocol === "https:" && parsed.host === "miho-visualizer.localhost";
    const nativeProtocol = parsed.protocol === "miho-visualizer:" && parsed.host === "localhost";
    let queryCount = 0;
    let validWorkspace = false;
    parsed.searchParams.forEach((queryValue, queryKey) => {
      queryCount += 1;
      validWorkspace = queryKey === "workspace" && /^[A-Za-z0-9-]{1,128}$/.test(queryValue);
    });
    if ((!windowsProtocol && !nativeProtocol)
      || parsed.username
      || parsed.password
      || parsed.pathname !== `/${targetGame}/index.html`
      || parsed.hash
      || queryCount !== 1
      || !validWorkspace) return null;
    return {
      schema_version: "miho-visualizer-descriptor-v1",
      url: value.url,
      data_revision: value.data_revision,
    };
  } catch {
    return null;
  }
}

function resetVisualizerFrames(): void {
  visualizerDirty.clear();
  visualizerLoading.clear();
  pendingVisualizerRefreshes.clear();
  observedVisualizerRevisions.clear();
  for (const [targetGame, visualizerState] of visualizerFrames) {
    const { frame } = visualizerState;
    rejectFrameFlushes(frame);
    visualizerState.requestGeneration += 1;
    advanceVisualizerRefresh(visualizerState);
    visualizerState.loadedRevision = null;
    visualizerState.pendingRevision = null;
    visualizerState.pendingUrl = null;
    visualizerState.pendingNavigationId = null;
    clearVisualizerReadyTimeout(visualizerState);
    visualizerState.startupLoadTicket = null;
    resetVisualizerStartup(visualizerState.startup);
    clearPendingVisualizerRefresh(visualizerState);
    visualizerState.page = "box";
    frame.hidden = true;
    frame.setAttribute("aria-hidden", "true");
    frame.tabIndex = -1;
    frame.dataset.loaded = "false";
    delete frame.dataset.loadedRevision;
    frame.dataset.page = visualizerState.page;
    frame.removeAttribute("src");
    visualizerDirty.add(targetGame);
    syncVisualizerStartupDiagnostics(targetGame, visualizerState);
  }
  updateWorkspaceControls();
}

async function loadVisualizer(force = false, targetGame: Game = game): Promise<void> {
  if (isWindowClosing()) return;
  const visualizerState = visualizerFrames.get(targetGame);
  if (!visualizerState) return;
  const { frame } = visualizerState;
  updateVisualizerFrameVisibility();
  if (!force
    && frame.getAttribute("src")
    && frame.dataset.loaded === "true"
    && !visualizerDirty.has(targetGame)) {
    if (targetGame === game) visualizerMessage.hidden = true;
    return;
  }
  const request = ++visualizerState.requestGeneration;
  const refreshGeneration = captureVisualizerRefresh(visualizerState);
  const workspaceId = capabilities?.workspace.workspace_id ?? "";
  visualizerLoading.add(targetGame);
  updateWorkspaceControls();
  if (targetGame === game) {
    visualizerMessage.hidden = false;
    setNotice(visualizerMessage, "正在检查 Visualizer 数据版本…");
  }
  try {
    const result = await invoke<unknown>("get_visualizer_url", { game: targetGame });
    if (isWindowClosing()
      || request !== visualizerState.requestGeneration
      || workspaceId !== (capabilities?.workspace.workspace_id ?? "")) return;
    const descriptor = backendVisualizerDescriptor(result, targetGame);
    if (!descriptor) {
      if (targetGame === game) {
        setNotice(visualizerMessage, "Visualizer 暂不可用；后端未返回受支持的版本描述。", "error");
      }
      return;
    }
    observedVisualizerRevisions.set(targetGame, descriptor.data_revision);
    if (!force
      && frame.dataset.loaded === "true"
      && visualizerState.loadedRevision === descriptor.data_revision) {
      if (refreshGeneration === visualizerState.refreshGeneration) {
        visualizerDirty.delete(targetGame);
        pendingVisualizerRefreshes.delete(targetGame);
      }
      updateVisualizerFrameVisibility();
      if (targetGame === game) visualizerMessage.hidden = true;
      return;
    }
    const pageUrl = new URL(descriptor.url);
    const navigationId = `${targetGame}-${request}`;
    pageUrl.searchParams.set("revision", descriptor.data_revision);
    pageUrl.searchParams.set("navigation_id", navigationId);
    if (force) pageUrl.searchParams.set("reload", String(request));
    pageUrl.hash = visualizerState.page;
    const navigationUrl = pageUrl.toString();
    if (!force
      && visualizerState.pendingRevision === descriptor.data_revision
      && visualizerState.pendingUrl === navigationUrl
      && frame.getAttribute("src") === navigationUrl) return;
    rejectFrameFlushes(frame);
    clearVisualizerReadyTimeout(visualizerState);
    visualizerState.pendingRevision = descriptor.data_revision;
    visualizerState.pendingUrl = navigationUrl;
    visualizerState.pendingNavigationId = navigationId;
    bindPendingVisualizerRefresh(visualizerState, refreshGeneration);
    const startup = beginVisualizerStartup(visualizerState.startup, {
      navigation_id: navigationId,
      data_revision: descriptor.data_revision,
      src: navigationUrl,
    });
    const startupTicket: VisualizerStartupTicket = {
      generation: startup.generation,
      navigation_id: navigationId,
      data_revision: descriptor.data_revision,
      src: navigationUrl,
    };
    visualizerState.startupLoadTicket = startupTicket;
    syncVisualizerStartupDiagnostics(targetGame, visualizerState);
    visualizerState.readyTimeout = window.setTimeout(
      () => failVisualizerStartupOnTimeout(targetGame, startupTicket),
      VISUALIZER_READY_TIMEOUT_MS,
    );
    frame.dataset.loaded = "false";
    delete frame.dataset.loadedRevision;
    frame.src = navigationUrl;
    updateVisualizerFrameVisibility();
    if (targetGame === game) {
      setNotice(visualizerMessage, "Visualizer 正在载入已验证的数据版本…", "success");
    }
  } catch (error) {
    if (request !== visualizerState.requestGeneration) return;
    const failure = safeError(error);
    if (targetGame === game) {
      utilities.open = true;
      setNotice(visualizerMessage, `Visualizer 不可用（${failure.code}）：${failure.message}`, "error");
    }
  } finally {
    if (request === visualizerState.requestGeneration) visualizerLoading.delete(targetGame);
    updateWorkspaceControls();
  }
}

async function refreshAll(): Promise<void> {
  if (workspaceBusy || boxTransitionBusy || isWindowClosing()) return;
  workspaceBusy = true;
  setBoxTransitionBusy(true);
  renderCapabilities();
  try {
    if (!await ensureVisualizerBoxesSaved(GAMES, "刷新页面")) return;
    if (isWindowClosing()) return;
    invalidateUpdateHealth("正在刷新当前工作区的自动更新记录…");
    await refreshCapabilities();
    if (isWindowClosing()) return;
    for (const targetGame of GAMES) markVisualizerDirty(targetGame, false);
    await Promise.all([
      refreshTasks(),
      refreshUpdateHealth(),
      ...GAMES.map((targetGame) => loadVisualizer(false, targetGame)),
    ]);
  } finally {
    workspaceBusy = false;
    setBoxTransitionBusy(false);
    renderCapabilities();
  }
}

async function installWindowCloseHandler(): Promise<void> {
  const appWindow = getCurrentWindow();
  unlistenWindowClose = await appWindow.onCloseRequested(async (event) => {
    event.preventDefault();
    if (allowWindowClose || closeRequestRunning) return;
    closeRequestRunning = true;
    try {
      await coordinateDesktopClose({
        beginClose() {
          closeGuardRunning = true;
          clearUpdateHealthTimers();
          updateHealthRequestGeneration += 1;
          uninstallVisualizerRevisionWatchers();
          setBoxTransitionBusy(true);
          renderTasks();
          persistTaskHistory();
        },
        setStage: setDesktopCloseStage,
        getWorkspaceTransition() {
          return pendingWorkspaceTransition;
        },
        getTaskStart() {
          return pendingTaskStart;
        },
        getBackgroundRead() {
          return pendingUpdateHealthRead();
        },
        hasActiveTask,
        confirmActiveTaskClose() {
          return window.confirm("仍有任务正在运行。现在关闭会将它记录为中断，且下次启动不会自动重跑。仍要关闭吗？");
        },
        shouldResetWorkspace() {
          return workspaceReconcilePending;
        },
        resetWorkspace() {
          capabilitiesRequestGeneration += 1;
          updateHealthRequestGeneration += 1;
          resetVisualizerFrames();
        },
        flushBoxes() {
          return ensureVisualizerBoxesSaved(["hsr", "zzz"], "关闭程序", {
            failureMode: "cancel",
            beforeFlush(targetGame) {
              setDesktopCloseStage(targetGame === "hsr" ? "flushing-hsr-box" : "flushing-zzz-box");
            },
          });
        },
        persist: persistTaskHistory,
        async destroy() {
          allowWindowClose = true;
          try {
            await appWindow.destroy();
          } catch (error) {
            allowWindowClose = false;
            throw error;
          }
        },
        async finishClose(closed) {
          closeGuardRunning = false;
          if (closed) return;
          setBoxTransitionBusy(false);
          if (workspaceReconcilePending) await reconcileWorkspaceAfterCloseCancellation();
          if (!isWindowClosing()) {
            installVisualizerRevisionWatchers();
            await refreshUpdateHealth();
          }
          renderTasks();
        },
      });
    } catch (error) {
      const failure = safeError(error);
      setNotice(workspaceMessage, `程序未能关闭（${failure.code}）：${failure.message}`, "error");
    } finally {
      closeRequestRunning = false;
    }
  });
}

window.addEventListener("beforeunload", (event) => {
  persistTaskHistory();
  if (!allowWindowClose && (hasActiveTask() || taskBusy || pendingTaskStart !== null)) {
    event.preventDefault();
    event.returnValue = "";
    return;
  }
  clearUpdateHealthTimers();
  resetVisualizerFrames();
  uninstallVisualizerRevisionWatchers();
  unlistenTaskUpdates?.();
  unlistenTaskUpdates = null;
  unlistenWindowClose?.();
  unlistenWindowClose = null;
});

updateGameUI();
updateTaskForm();
void (async () => {
  try {
    await installTaskListener();
  } catch (error) {
    const failure = safeError(error);
    setNotice(taskMessage, `任务事件监听不可用（${failure.code}）：${failure.message}`, "error");
  }
  try {
    await installWindowCloseHandler();
  } catch (error) {
    const failure = safeError(error);
    setNotice(workspaceMessage, `关闭前保存保护不可用（${failure.code}）：${failure.message}`, "error");
  }
  await refreshAll();
  installVisualizerRevisionWatchers();
})();
