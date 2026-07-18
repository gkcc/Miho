import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
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
  retryable: boolean;
  message: string;
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
let visualizerRequest = 0;
let unlistenTaskUpdates: UnlistenFn | null = null;

const tasks = new Map<string, PublicTaskSnapshot>();
const authoritativeTaskSequences = new Map<string, number>();
const eventTaskSequences = new Map<string, number>();
const taskQueries = new Map<string, number>();

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
    if (game === value || workspaceBusy) return;
    game = value;
    updateGameUI();
    await loadVisualizer();
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
workspaceActions.append(selectWorkspaceButton, refreshWorkspaceButton);
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
const reloadVisualizerButton = makeButton("重新载入", "button secondary", loadVisualizer);
visualizerHeading.append(visualizerTitleBlock);
const visualizerMessage = element("p", "notice", "正在向本机后端请求 Visualizer 地址…");
const visualizerFrame = element("iframe", "visualizer-frame");
visualizerFrame.title = "终局数据 Visualizer";
visualizerFrame.setAttribute("sandbox", "allow-scripts allow-same-origin allow-downloads");
visualizerFrame.referrerPolicy = "no-referrer";
visualizerFrame.hidden = true;
visualizerFrame.addEventListener("error", () => {
  visualizerFrame.hidden = true;
  visualizerMessage.hidden = false;
  utilities.open = true;
  visualizerMessage.textContent = "Visualizer 页面加载失败。请刷新或检查本机生成状态。";
  visualizerMessage.className = "notice error";
});
visualizerFrame.addEventListener("load", () => {
  if (visualizerFrame.src) visualizerMessage.hidden = true;
});
visualizerSection.append(visualizerHeading, visualizerMessage, visualizerFrame);

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
}

function setNotice(target: HTMLElement, message: string, kind: "normal" | "error" | "success" = "normal"): void {
  target.textContent = message;
  target.className = kind === "normal" ? "notice" : `notice ${kind}`;
}

function updateWorkspaceControls(): void {
  for (const button of gameButtons.values()) button.disabled = workspaceBusy;
  selectWorkspaceButton.disabled = workspaceBusy
    || capabilities?.workspace_selection_enabled === false
    || hasActiveTask();
  refreshWorkspaceButton.disabled = workspaceBusy;
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

async function refreshCapabilities(): Promise<void> {
  const request = ++capabilitiesRequestGeneration;
  setNotice(workspaceMessage, "正在读取本机能力…");
  try {
    const next = await invoke<DesktopCapabilities>("get_capabilities");
    if (request !== capabilitiesRequestGeneration) return;
    capabilities = next;
    renderCapabilities();
    setNotice(workspaceMessage, "能力与缺失输入已刷新。", "success");
  } catch (error) {
    if (request !== capabilitiesRequestGeneration) return;
    capabilities = null;
    renderCapabilities();
    const failure = safeError(error);
    setNotice(workspaceMessage, `能力读取失败（${failure.code}）：${failure.message}`, "error");
  }
}

async function selectWorkspace(): Promise<void> {
  if (workspaceBusy || hasActiveTask()) return;
  workspaceBusy = true;
  renderCapabilities();
  setNotice(workspaceMessage, "请选择可信的本机工作区…");
  try {
    const result = await invoke<{ selected: boolean; workspace: WorkspaceSummary }>("select_workspace");
    if (!result.selected) {
      setNotice(workspaceMessage, "未更改工作区；现有 Box 保持不变。");
      return;
    }
    setNotice(workspaceMessage, "工作区已切换，正在刷新…", "success");
    await refreshCapabilities();
    await Promise.all([refreshTasks(), loadVisualizer()]);
  } catch (error) {
    const failure = safeError(error);
    setNotice(workspaceMessage, `切换失败（${failure.code}）：${failure.message}`, "error");
  } finally {
    workspaceBusy = false;
    renderCapabilities();
  }
}

function updateExportControls(): void {
  for (const operation of EXPORT_OPERATIONS) {
    const capability = capabilityFor(operation.value);
    const button = exportButtons.get(operation.value);
    const status = exportStatuses.get(operation.value);
    if (!button || !status) continue;
    button.disabled = taskBusy || hasActiveTask() || !capability?.enabled;
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
  if (taskBusy || hasActiveTask() || !capabilities || !capability?.enabled) return;
  taskBusy = true;
  updateExportControls();
  updateTaskForm();
  setNotice(exportMessage, "正在交给全局本机后台任务管理器…");
  try {
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
  const disabled = taskBusy || hasActiveTask() || !capability?.enabled;
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
  if (taskBusy || hasActiveTask() || !capabilities || !capability?.enabled) return;
  const intentJson = buildIntent();
  if (!intentJson) return;
  taskBusy = true;
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
      const currentExport = game === "hsr" ? "hsr-export" : "zzz-export";
      if (snapshot.status === "succeeded" && snapshot.operation === currentExport) {
        await loadVisualizer();
      }
    }
  } catch (error) {
    if (taskQueries.get(taskId) !== generation) return;
    const failure = safeError(error);
    setNotice(taskMessage, `任务查询失败（${failure.code}）：${failure.message}`, "error");
  }
}

async function refreshTasks(): Promise<void> {
  taskRefreshButton.disabled = true;
  try {
    const snapshots = await invoke<PublicTaskSnapshot[]>("list_tasks");
    for (const snapshot of snapshots) mergeQueriedTask(snapshot);
    renderTasks();
  } catch (error) {
    const failure = safeError(error);
    setNotice(taskMessage, `任务列表刷新失败（${failure.code}）：${failure.message}`, "error");
  } finally {
    taskRefreshButton.disabled = false;
  }
}

async function cancelTask(taskId: string): Promise<void> {
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

function hasActiveTask(): boolean {
  return [...tasks.values()].some((task) => !TERMINAL_STATUSES.has(task.status));
}

function renderTasks(): void {
  taskList.replaceChildren();
  const ordered = [...tasks.values()].sort((left, right) => right.task_id.localeCompare(left.task_id));
  if (ordered.length === 0) {
    taskList.append(element("p", "empty-state", "还没有进行数据更新或报告生成。"));
  }
  for (const task of ordered) {
    const card = element("article", `task-card status-${task.status}`);
    const titleRow = element("div", "task-title-row");
    const title = element("div");
    title.append(element("h3", undefined, operationLabel(task.operation)));
    const badge = element("span", `status-badge ${task.status}`, STATUS_LABELS[task.status]);
    titleRow.append(title, badge);
    const outcome = task.status === "succeeded"
      ? "操作已经完成，相关页面或报告已刷新。"
      : task.status === "failed"
        ? "操作没有完成，请查看下方原因。"
        : task.status === "cancelled"
          ? "操作已取消，没有继续写入。"
          : task.status === "committing"
            ? "处理完成，正在安全保存结果。"
            : "正在后台处理，可以继续查看 Box。";
    card.append(titleRow, element("p", "task-summary muted", outcome));

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
        element("span", "muted", task.failure.retryable ? "可以稍后重试" : "请根据错误说明检查输入"),
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
        item.append(element("span", undefined, artifact.name), element("small", undefined, artifact.kind));
        list.append(item);
      }
      artifacts.append(list);
      technical.append(artifacts);
    }

    if (task.status === "succeeded" && (task.operation === "hsr-export" || task.operation === "zzz-export")) {
      card.append(makeButton("查看 Box 和分析", "button secondary", () => visualizerSection.scrollIntoView({ behavior: "smooth" })));
    }

    if (!TERMINAL_STATUSES.has(task.status) && capabilities?.supports_cancel) {
      const cancel = makeButton(task.cancellation_requested ? "取消已请求" : "取消任务", "button danger", () => cancelTask(task.task_id));
      cancel.disabled = task.cancellation_requested || task.status === "committing";
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
  if (!isRecord(value) || !hasExactKeys(value, ["code", "retryable", "message"])) return false;
  return typeof value.code === "string" && typeof value.retryable === "boolean" && typeof value.message === "string";
}

function isPublicTaskSnapshot(value: unknown): value is PublicTaskSnapshot {
  if (!isRecord(value) || !hasExactKeys(value, [
    "schema_version", "task_id", "operation", "status", "status_history",
    "cancellation_requested", "artifacts", "failure",
  ])) return false;
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
    && isPublicFailure(value.failure);
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

function backendVisualizerUrl(value: unknown): string | null {
  const candidate = typeof value === "string"
    ? value
    : typeof value === "object" && value !== null && typeof (value as Record<string, unknown>).url === "string"
      ? (value as Record<string, unknown>).url as string
      : null;
  if (!candidate) return null;
  try {
    const parsed = new URL(candidate);
    const windowsProtocol = parsed.protocol === "https:" && parsed.hostname === "miho-visualizer.localhost";
    const nativeProtocol = parsed.protocol === "miho-visualizer:" && parsed.hostname === "localhost";
    return windowsProtocol || nativeProtocol ? candidate : null;
  } catch {
    return null;
  }
}

async function loadVisualizer(): Promise<void> {
  const request = ++visualizerRequest;
  reloadVisualizerButton.disabled = true;
  visualizerFrame.hidden = true;
  visualizerFrame.removeAttribute("src");
  visualizerMessage.hidden = false;
  setNotice(visualizerMessage, "正在向本机后端请求 Visualizer 地址…");
  try {
    const result = await invoke<unknown>("get_visualizer_url", { game });
    if (request !== visualizerRequest) return;
    const url = backendVisualizerUrl(result);
    if (!url) {
      setNotice(visualizerMessage, "Visualizer 暂不可用；后端未返回受支持的地址。", "error");
      return;
    }
    const pageUrl = new URL(url);
    pageUrl.hash = "box";
    visualizerFrame.src = pageUrl.toString();
    visualizerFrame.hidden = false;
    setNotice(visualizerMessage, "Visualizer 由本机后端提供，并在受限 iframe 中运行。", "success");
  } catch (error) {
    if (request !== visualizerRequest) return;
    const failure = safeError(error);
    utilities.open = true;
    setNotice(visualizerMessage, `Visualizer 不可用（${failure.code}）：${failure.message}`, "error");
  } finally {
    if (request === visualizerRequest) reloadVisualizerButton.disabled = false;
  }
}

async function refreshAll(): Promise<void> {
  if (workspaceBusy) return;
  workspaceBusy = true;
  renderCapabilities();
  try {
    await refreshCapabilities();
    await Promise.all([refreshTasks(), loadVisualizer()]);
  } finally {
    workspaceBusy = false;
    renderCapabilities();
  }
}

window.addEventListener("beforeunload", () => {
  unlistenTaskUpdates?.();
  unlistenTaskUpdates = null;
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
  await refreshAll();
})();
