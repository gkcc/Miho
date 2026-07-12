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
- Review-packet payloads containing backticks may use a fence longer than Python's fixed three backticks: Rust chooses one more than the payload's longest consecutive run. The JSON payload and recommendation content remain unchanged.

No calculation, row, column, filename, exit-code or default-path difference is allowed unless added here with a reason and regression fixture.

## Decision and report method corrections

- The report contract and dependency graph live in `docs/decision-report-contract.md`.
- `evidence-first-v1-20260712` intentionally corrects the old Python evidence method: evidence is mode-scoped (`mode|full_team_signature`), so SD/DA and distinct HSR modes never share a best score or confidence calculation.
- A source confidence now requires mode-specific repetition/breadth, sufficient non-sentinel results and a known stability component. Account confidence separately requires explicit build readiness; unknown/unbuilt state caps source A/B+ at account B, and ownership or level never implies ready.
- Non-finite app rates are unusable and non-finite performance values are missing/sentinel. This is an approved safety correction rather than preserving `nan`/`inf` report text.
- Evidence/coverage use one explicit local datetime and batch rollback. Colliding output paths fail before replacing old artifacts.
- Pull-value `高/中高` is now constrained by same-mode qualifying A/B evidence. Stable `evidence_ids`/`evidence_keys` and embedded refs contain only A/B+/B main evidence; risk fields contain B-/C context. This method correction is intentional and hash-locked.
- For an unowned candidate, primary evidence requires `plan_dependency == [candidate]`; teams that also require another planned unit are conditional risk and cannot raise that candidate's main evidence count.
- `decision` is labeled `legacy-v0`; its cross-mode heuristic, raw-team dependency and alias limitations are not accepted as evidence-first completion. The Rust compatibility gate is lifted only for explicit `--method legacy-v0`; `pull-value` remains the sole formal recommendation path.
- The Rust `pull-value` and `review-packet` gates are lifted. Review packets directly serialize the existing Rust pull cards and rename only `pull_value` to `local_rule_pull_value`; they do not recompute recommendations. Default current/next files and explicit combined output share one clock and one batch installation; failures preserve all old reports and do not mutate manifest, visualizer, legacy decision, pull-value or coverage consumers.
- JSON lexical form is part of packet compatibility rather than an allowed difference: small exponents are normalized to Python spelling such as `1e-07`, while `-0.0` and large integers retain Python-compatible representation.
- Shared YAML config parsing matches the Python oracle for UTF-8 BOM, PyYAML 1.1 booleans, merge keys, empty/falsey roots and recursive non-finite rejection. JSON/YAML plan, Box, baseline and mechanism inputs therefore share the same safety boundary.
- Shared report IPC, Tauri background tasks, progress/cancellation/error propagation and file selection are not yet migrated; lifting the Rust CLI report gates does not complete the Tauri product stage.

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
