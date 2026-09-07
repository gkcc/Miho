# Project rules

- Deliver one complete, usable goal at a time. Defer unrelated features, refactors, polish, and extra proof; verify the requested user entry point.
- The product is the Tauri desktop app: prioritize Rust, reliable data, and usable UI.
- For any HSR/ZZZ product capability change, audit the other game's matching entry point for data semantics, interaction, persistence, and real-path verification. Implement parity in the same task unless a documented game-mechanic difference applies.

## Local delivery

- Runtime code, configuration, resources, or dependencies: rebuild and update the current runnable Tauri app. Deliver the matching update CLI; changes to `miho-core`, `miho-app`, `miho-cli`, or Visualizer resources require an owner-aware transaction synchronizing the daily update task.
- Shared data-generation changes also require rebuilding the CLI, switching the scheduled-task generation, and validating the new artifact contract.
- Build/test NSIS, installers, portable or release packages only when explicitly requested. Keep their existing code as historical compatibility assets; ordinary fixes must not expand this pipeline. Documentation-only changes do not create a new app version.

## Verification, records, and Git

- Run targeted checks; expand to a full matrix or independent adversarial review only for release pipelines, security/permission boundaries, data deletion/migration, or broad shared-code changes. Reuse unaffected valid evidence; state checks run and material omissions.
- Make one local commit per completed deliverable/milestone. After verification, promptly push to the configured reachable remote unless the user requests local-only/delayed push. Check `git status`, diff, and relevant tests first; include only this task's changes. Create PRs or merge only on explicit request.
- Update `PROJECT.md` or the relevant tracker only when goals, status, key decisions, evidence, or material remaining risks change. Keep records brief; avoid copied logs and documentation/build loops. Record difficulties only when they change future workflow.
- Remove only regenerable caches/old candidates confirmed unused by the current app and retained rollback evidence. Never delete user AppData, the running app, production owners/tasks, or unidentified files.
