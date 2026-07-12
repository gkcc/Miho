# Shared application task contract

This contract freezes the boundary between the existing Rust cores, trusted native adapters, and the future Tauri/WebView task surface.

## Ownership

`miho-core` owns evidence, recommendation, rendering, visualizer and export semantics. `miho-app` owns report input discovery, one invocation clock, native path resolution, rendering orchestration and final batch installation. CLI and Tauri must not rebuild these rules.

The five report operations currently supported by the shared executor are:

- `decision` (`legacy-v0` compatibility only)
- `evidence`
- `coverage`
- `pull-value`
- `review-packet`

## Untrusted intent versus trusted request

`TaskIntentV1` is the only report type suitable for an untrusted WebView boundary. It is versioned, rejects unknown fields at every level and contains no workspace, path, output or file field. Invalid JSON or unknown fields return `TaskFailureV1` with `request.invalid`; a known intent with an unsupported schema returns `request.unsupported_schema`.

`WorkspaceLayout`, `TaskRequestV1`, `TaskSpecV1` and the operation-specific native task structs may contain arbitrary paths for CLI compatibility. They intentionally do not implement `Serialize` or `Deserialize`. A native adapter must construct them only after resolving a saved workspace or an opaque native file selection. They must never appear directly in a `#[tauri::command]` parameter.

```text
WebView JSON
  -> parse_task_intent_v1 (pathless, strict)
  -> native workspace / opaque selection authorization
  -> TaskRequestV1 (trusted paths, not serde)
  -> execute_task_v1
  -> TaskReceiptV1 | TaskFailureV1
```

## Execution invariants

- Capture `AppInvocation` once per command. The same local datetime drives plan selection and all outputs.
- Resolve data, Box, plan, rules, notes, baseline and output paths through that invocation.
- Build/render every requested output before one `atomic::write_batch` commit.
- Preserve collision, reparse-point and later-install rollback behavior.
- Do not update artifact manifests, visualizers or sibling consumer reports unless the selected operation owns them.
- `review-packet` consumes the same pull bundle and does not recompute recommendations.
- Return receipts only after the batch commit succeeds. Output paths are ordered by the operation contract.

## TaskManager and desktop backend

The CLI now translates arguments into the trusted request and uses the shared executor; its existing golden, 0/1/2, junction and rollback contracts remain active.

The process-local `TaskManager` and Tauri backend are now implemented:

- first release: one active task for the process;
- `queued/running/cancelling/committing/succeeded/failed/cancelled` state;
- one lock-protected `before_commit` decision: cancellation wins before it, otherwise cancel returns `too_late`;
- spawn/panic/failure cleanup and task-ID ownership checks;
- native and public snapshots are separate; public artifacts and failures contain no native paths or raw error chain;
- `public_updates_since(sequence)` reconstructs every transition from the authoritative history, so a polling event adapter can emit contiguous revisions without losing fast states;
- Tauri `capabilities/select_workspace/start/get/list/cancel` commands accept only opaque workspace IDs and pathless intent JSON;
- the folder picker is invoked by Rust; the WebView capability does not grant direct dialog access;
- workspace settings are persisted atomically and Box State follows the active workspace.

The following remain explicitly outside this gate: GUI/CLI cross-process locking, graceful manager shutdown/join, task-history persistence, abrupt process termination, power-loss journal/recovery, export tasks and visualizer hosting. Desktop capabilities report abrupt and cross-process recovery as unsupported.

## Next gate

The frontend must consume only the public snapshot/update and authoritative query APIs. It must not receive native receipts, paths or dialog capability. The next product gate adds the safe task UI and a constrained visualizer/Box protocol bridge.
