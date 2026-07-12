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

## Current gate

The CLI now translates arguments into the trusted request and uses the shared executor; its existing golden, 0/1/2, junction and rollback contracts remain active.

This does not complete Tauri IPC. The next gate must add a native TaskManager and workspace resolver with:

- `start/get/list/cancel` and capabilities/workspace commands;
- output/workspace mutual exclusion;
- cancellation checkpoints before commit;
- explicit `too_late` once commit begins;
- queryable state that survives lost UI events;
- no direct WebView-provided filesystem paths.
