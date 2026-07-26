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

    const workspaceTransition = options.getWorkspaceTransition();
    if (workspaceTransition) await workspaceTransition;

    const taskStart = options.getTaskStart();
    if (taskStart) await taskStart;

    if (options.hasActiveTask() && !await options.confirmActiveTaskClose()) {
      return false;
    }

    if (options.shouldResetWorkspace()) options.resetWorkspace();
    if (!await options.flushBoxes()) return false;

    options.persist();
    await options.destroy();
    closed = true;
    return true;
  } finally {
    await options.finishClose(closed);
  }
}
