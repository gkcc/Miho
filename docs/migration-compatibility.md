# Rust migration compatibility contract

The Python implementation remains the behavioral oracle until each Rust command passes golden-file comparison.

## Stable interfaces

- Games: `hsr`, `zzz`.
- HSR commands: `export`, `visualizer`.
- ZZZ commands: `export`, `decision`, `evidence`, `coverage`, `pull-value`, `review-packet`, `visualizer`, `serve`.
- Existing JSON, YAML, CSV and Box State v2 files remain readable.
- Box State normalization removes blanks and `__codex_test__`, sorts/deduplicates `owned`, and clears `updatedAt` only when the state is otherwise empty.
- Text output remains UTF-8. Persistent state uses temporary-file replacement.

## Allowed golden-output differences

- Generation timestamps and collection timestamps.
- JSON object key order and insignificant whitespace.
- Network-origin content that changed between captures.

No calculation, row, column, filename, exit-code or default-path difference is allowed unless added here with a reason and regression fixture.

## Migration gate

A Rust command must not silently produce partial output. Until its golden suite passes, it exits with an explicit staged-migration message and the scheduled task continues to call Python.
