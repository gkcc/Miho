# Native update runner contract

Status: V1 implementation contract. This replaces the business orchestration in
`scripts/update_endgame_data.ps1`; the script may remain only as a temporary
exit-code-preserving launcher while installed tasks migrate.

## Public entry point

The scheduled, CLI, and future desktop paths must call one Rust entry point:

```text
miho update run --workspace <trusted-native-path> [--config <workspace-relative-json>]
                [--skip-hsr] [--skip-zzz] [--force]
miho update health --workspace <trusted-native-path>
                   [--config <workspace-relative-json>]
                   [--skip-hsr] [--skip-zzz]
```

The WebView must not deserialize this pathful request. Exit codes are `0` for a
fully successful selected run, `1` for busy/runtime/partial/commit failure, and
`2` for invalid CLI usage. A partial run is never exit `0`.

V1 deliberately performs every selected online export on every invocation.
The old HF/Prydwen signature omits enabled sources such as HoYoWiki and cannot
prove freshness. `--force` is recorded for compatibility but cannot weaken the
always-refresh rule. An implicit fresh skip may be added only after every
enabled remote source and every local derived input has a verified digest.
The update-only HF adapter rejects any last-good cache fallback after a request
or payload-validation failure; direct interactive export keeps its historical
fallback behavior. The PowerShell compatibility launcher must preserve the
native `0/1/2` exit exactly under Windows PowerShell 5.1 and PowerShell 7, then
run config-bound `update health` after a successful update.

## Trust and concurrency boundary

- Resolve the workspace once, require an existing real directory, and reject a
  symlink/reparse root or unsafe `.miho` parent chain.
- Acquire `.miho/workspace-write-v1.lock` with an OS advisory exclusive lock.
  Keep the lock file; dropping the file handle releases the lease, including
  after process termination.
- The same lease must guard update, direct export/report CLI writes, and Tauri
  TaskManager writes before cross-process safety is advertised.
- A busy contender returns `1` and must not overwrite the canonical receipt.
- Single-file receipts and HTTP cache reads/writes reject every pre-existing
  symlink/reparse ancestor before directory creation or file access. Cache
  repo/revision components include the full SHA-256 of the original UTF-8
  identity, so sanitized names cannot alias one another.

## One invocation, ordered ownership

Capture one attempt ID, UTC timestamp, local datetime, and local date before
the first step. Pass that same clock into both export and report executors.
Within the lease, execute in this order:

1. HSR export, visualizer, manifest and output transaction (unless skipped).
2. ZZZ export, visualizer, manifest, output transaction and Hub transaction
   (unless skipped). The Hub uses the actual configured HSR and ZZZ top-level
   directory names; a successful custom-output run must not retain legacy
   `../out/...` links.
3. ZZZ coverage, pull-value, then review-packet, using the existing typed
   `miho-app` executor and the same invocation clock.
4. Validate every required artifact and manifest entry produced by the
   selected game.
5. Commit success state and the canonical success receipt last.

HSR and ZZZ results are independent: after one game fails, attempt the other
game when safe. ZZZ derived reports run only after a successful ZZZ export in
the current attempt. A failure in one derived step stops later ZZZ derived
steps. A selected game is successful only after all of its owned steps finish.

## Durable state and receipts

Files live below `.miho`:

- `update-state-v1.json`: last successful selected-game generations only.
- `last-update-receipt-v1.json`: canonical terminal receipt for the latest
  lock-owning attempt.
- `update-attempts/<attempt-id>.json`: per-attempt running/terminal receipt.

Before external work, atomically write a `running` attempt receipt. A later run
that finds an older `running` receipt records it as interrupted; it never
promotes it to success. Terminal receipt fields are path-safe and include:

- schema, attempt ID, started/finished timestamps, status and force flag;
- per-game selected/skipped/succeeded/failed state;
- ordered step status, stable error code, retryable flag and safe message;
- artifact relative paths plus verified size/hash where available;
- exact update-config SHA-256 used for the attempt;
- whether state and canonical receipt were committed.

The state records the attempt ID, completion time, exact update-config SHA-256
and the full verified artifact list (workspace-relative path, size and SHA-256)
for each game. It is audit state, not a remote freshness oracle. Health loads
the selected config and requires every requested game generation to match its
digest. This preserves independently refreshed HSR/ZZZ generations while
preventing a changed repo/revision/mode config from approving older output.

Health first requires the canonical success receipt to be byte-semantically
identical to `update-attempts/<canonical-attempt-id>.json`; a grammar-valid but
missing ID, an unsafe ID, or altered canonical fields fail closed. It then
anchors each requested game to the attempt recorded in state and verifies the
generation receipt, config digest and every artifact size/hash.

On full selected-run success, install `update-state-v1.json`, the terminal
attempt receipt and `last-update-receipt-v1.json` in one batch transaction. On
failure, do not change success state. Atomically replace only the attempt
receipt and canonical failure receipt. If receipt installation itself fails,
return `1`; stderr remains the final fallback evidence.

No receipt may contain an absolute workspace path, username, Box contents,
HTTP query/header/body, or a raw anyhow error chain.

## Failure invariants

- Probe/fetch/export/report/manifest failure cannot advance success state or
  the legacy local-date marker.
- Existing successful artifacts remain owned by their existing transaction.
  Output updated but state not committed is a safe false-negative and is
  refreshed again; state updated before output is forbidden.
- Missing or invalid Box/config is a structured ZZZ failure, never a warning
  followed by exit `0`.
- `LastTaskResult=0` alone is not health. Health requires a terminal success
  receipt, matching selected games, verified artifacts, and committed state.
- Strong process-kill/host-crash atomic recovery is not claimed until a real
  kill matrix proves every transaction point; a leftover `running` receipt is
  explicit evidence of interruption.

## Required V1 gates

- Unit/fixture: HSR fail + ZZZ success; HSR success + ZZZ fail; each ZZZ
  derived step failure; manifest/hash failure; state/receipt install failure;
  force/skip combinations; busy and lock reacquisition; unsafe path/reparse;
  stable redaction and exit `0/1/2`.
- Integration: two update processes and update versus direct CLI/Tauri writer;
  terminate a lock owner and reacquire; no Python executable on `PATH`.
- Scheduled task: action invokes installed `miho.exe` directly, has an explicit
  workspace/working directory, and is health-checked before replacing the old
  action. Upgrade/uninstall must preserve or remove only installer-owned task
  state and support rollback.

The runner/unit/integration portion is the gate for the native-runner commit;
the scheduled-task paragraph is deliberately the next gate. A runner commit
must not claim that the currently installed task, NSIS/portable resources or
the no-Python install/upgrade/uninstall matrix have already migrated.
