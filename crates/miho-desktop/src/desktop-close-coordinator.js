/**
 * Coordinate one guarded desktop close attempt.
 *
 * Transition getters are intentionally called in sequence: a task start may
 * become tracked while an existing workspace transition is still settling.
 */
export async function coordinateDesktopClose(options) {
  let closed = false;
  try {
    options.beginClose();

    options.setStage("waiting-workspace-transition");
    const workspaceTransition = options.getWorkspaceTransition();
    if (workspaceTransition) await workspaceTransition;

    options.setStage("waiting-task-start");
    const taskStart = options.getTaskStart();
    if (taskStart) await taskStart;

    options.setStage("waiting-background-read");
    const backgroundRead = options.getBackgroundRead();
    if (backgroundRead) await backgroundRead;

    options.setStage("checking-active-task");
    if (options.hasActiveTask() && !await options.confirmActiveTaskClose()) {
      options.setStage("active-task-cancelled");
      return false;
    }

    if (options.shouldResetWorkspace()) options.resetWorkspace();
    options.setStage("flushing-boxes");
    if (!await options.flushBoxes()) {
      options.setStage("box-flush-cancelled");
      return false;
    }

    options.persist();
    options.setStage("destroying");
    await options.destroy();
    closed = true;
    options.setStage("destroy-resolved");
    return true;
  } catch (error) {
    options.setStage("failed");
    throw error;
  } finally {
    await options.finishClose(closed);
  }
}
