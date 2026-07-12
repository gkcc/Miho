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

## Visualizer artifact contract

- The versioned oracle lives in `tests/fixtures/visualizer_contract` and is regenerated explicitly with `python tests/test_visualizer_contract.py`.
- Its input boundary is the complete final CSV set plus versioned Banner/Decision sidecars and a preseeded local avatar store. A visualizer is not assumed to be reversible from CSV alone.
- JSON object member order is ignored; JSON types and array order are strict. Only `/meta/localDate` is dynamic.
- The directory file set, normalized-LF UTF-8 static assets, and every binary avatar are hash-locked. URL traversal/active schemes, non-finite JSON numbers, workspace-path leaks, and live network access are rejected.
- HSR and ZZZ export paths must write final CSV artifacts first, then call the same disk-backed rebuild used by their independent `visualizer` commands.
- The Rust HSR suite proves both fallback and HoYoWiki roster paths with a dense multi-phase/multi-team oracle, then repeats the exact JSON/file-set/hash comparison through the real disk-backed CLI. Browser Banner/Box/XSS/console smoke also passes, so the HSR online export gate is lifted.
- The Rust ZZZ suite now proves dense phase/roster/Bangboo/team/Banner/Decision behavior, strict UTF-8 and JSON-number/URL safety, real CLI ownership/transaction semantics, exact sibling Hub output, and browser Banner/Box/XSS/console behavior. Both games receive an explicit versioned local datetime down to seconds, so the ZZZ online export gate is lifted. For legacy outputs without a manifest, `raw/hf/**` is a reserved managed namespace; unrelated files elsewhere are preserved but never promoted into the refreshed manifest.
- Approved safety difference: if a sidecar is already malformed JSON and also contains an unquoted `NaN`/`Infinity` token, Rust rejects it instead of taking Python's malformed-JSON fallback. This prevents a non-finite payload from being silently hidden; ordinary malformed UTF-8-valid JSON without such tokens keeps the Python fallback behavior.
