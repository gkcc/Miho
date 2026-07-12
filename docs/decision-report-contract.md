# Decision and report migration contract

This document freezes the dependency graph and gate conditions for the twelfth migration batch. The five public commands are not one pipeline and must not be implemented by reading each other's Markdown output.

```text
final export CSV + name map + Box + optional plan
  -> evidence core
     -> evidence Markdown
     -> current/target coverage Markdown + aggregate CSV
     -> pull-value cards
        -> pull-value Markdown
        -> GPT review packet

final export CSV + Decision Box profile + legacy rules
  -> legacy decision cards JSON + Markdown
  -> ZZZ visualizer sidecar
```

## Method versions

- `evidence-first-v1-20260712`: formal evidence/coverage and pull-value method.
- `legacy-v0`: current Python `decision` heuristic. It is retained as a compatibility oracle only and is not evidence-first.
- `tests/fixtures/decision_report_contract/contract.json` is a five-command bundle smoke with canonical hashes. It explicitly is not sufficient to lift the decision or pull-value Rust gates.

## Evidence-first V1 invariants

- Read the full `team_rank_dedup_unordered.csv`; raw/Top-N tables are not substitutes.
- Canonicalize `name_map.csv` aliases before resolving owned or planned membership.
- The target account is owned plus explicitly selected planned agents. Owned and built are distinct; build readiness is read only from explicit `built`/`builds` data.
- The aggregation key is `mode|full_team_signature`. The same composition in SD and DA produces two evidence records. Scores, app-rate statistics and confidence never cross modes.
- HSR `0`/`99.99` round values and ZZZ `0` score values are sentinel; missing/non-finite performance is missing. A literal ZZZ score of `99.99` is not treated as an HSR round sentinel. Non-finite app rates are unusable rows.
- `A` requires the mode policy's record/phase/breadth thresholds, sufficient non-sentinel density and an identified stability component. Unknown stability caps confidence at `B+`.
- `B+`, `B` and `B-` are evidence-confidence subdivisions, not character tiers.
- Every record exposes a content-stable evidence ID derived from `evidence_key`, plus metric name/direction, duplicate count, phase/scope/source trace and observation keys. Adding an unrelated planned unit cannot renumber an existing citation.
- Source confidence and account confidence are separate. Missing/explicitly unbuilt account state caps source A/B+ at account B; only an explicitly fully built team retains A/B+.
- High-priority pull advice must cite qualifying `A/B+/B` evidence IDs. `B-/C` IDs are separated into `risk_evidence_ids`.
- Pull `高` requires A under the current conservative policy. `中高` requires A/B+, or at least two independent B records. Tier, usage and evidence must support the threshold inside the same mode; their global best values cannot be spliced across modes. A single B caps the result at `中`; new unreleased characters remain `等实测` without treating absent history as negative.
- Pull/review embeds stable evidence keys and compact trace records with each card; links to a separately generated coverage file are convenience links, not the sole citation payload.
- One explicit local datetime drives plan status and report generation time for each command invocation.

## Inputs and outputs

| Command | Required inputs | Optional inputs | Outputs |
| --- | --- | --- | --- |
| `evidence` | Box, dedup team CSV | name map, banner plan, explicit planned slugs, per-mode threshold | one evidence Markdown |
| `coverage` | Box, dedup team CSV | name map, banner plan, explicit planned slugs, per-mode threshold | current Markdown, target Markdown, aggregate CSV |
| `decision` | Decision Box profile | six export CSV files, legacy rules | `decision_cards.json`, `decision_report.md` |
| `pull-value` | Box, dedup team CSV, CLI banner plan by default | name/usage/tier, mechanism notes, baseline, explicit planned slugs | combined output or one Markdown per status |
| `review-packet` | same card inputs as pull-value | same optional inputs | combined output or one packet per status |

The core Rust APIs must receive bytes/typed documents and an explicit context. Path defaults, cwd resolution, file globbing and local-clock capture belong to the trusted CLI/Tauri adapter.

## Failure and installation contract

- Argument errors exit 2; runtime failures exit 1; success exits 0, including an empty candidate list.
- Error prefixes are command-specific, not the export-only prefix.
- Missing dedup team or Box input is fatal. Missing name/usage/tier data is tolerated where the Python command currently treats it as empty.
- Evidence and coverage pre-render all files, reject colliding destinations, stage sibling files and roll back the entire batch if installation fails.
- Decision and split pull/review writes remain non-atomic in `legacy-v0`; their Rust gates cannot lift until batch transaction tests pass.
- Strict JSON output must reject non-finite values. If this differs from legacy Python `NaN`/`Infinity`, it is an approved safety correction with a regression test.
- PyYAML is a declared oracle dependency; installed and fallback-parser environments must no longer silently select different config semantics.

## Legacy decision boundary

`decision` currently mixes the maximum usage average from one mode with the worst trend from another, uses `team_rank_raw.csv`, ignores `name_map.csv` aliases and can emit non-standard JSON numbers. These are known method conflicts. The migration must either:

1. expose exact `legacy-v0` compatibility explicitly; and
2. provide a versioned evidence-first default that does not use those conflicts,

or document a narrower product decision before removing the gate. Exact happy-path hashes alone do not make `legacy-v0` a formal evidence-first recommendation engine.

### Product resolution (2026-07-12)

The narrower product decision is now fixed:

- `decision` is compatibility-only and may run only when the request explicitly selects `legacy-v0` (CLI: `--method legacy-v0`). Its legacy JSON/Markdown payload remains byte-compatible and therefore does not gain an in-payload method field.
- CLI help/request/receipt and the visualizer adapter boundary must identify the output as `legacy-v0 / compatibility only`; the product UI must not present it as the formal evidence-first recommendation.
- `pull-value` is the only formal `evidence-first-v1-20260712` recommendation engine. `review-packet` serializes the same pull cards and evidence references; it does not recompute a second decision.
- A future standalone Decision V1 requires a separately versioned ruleset and output schema. It must not be inferred from LegacyV0 compatibility work.

For an unowned pull candidate, a target-pool team is primary evidence only when its non-owned plan dependency is exactly that candidate. Teams that also require other planned candidates are conditional risk, not proof that pulling one candidate completes the team.

## Remaining gate matrices

- Evidence/coverage: mode separation, A/B boundaries, sentinel density, stability, explicit build state, alias collision, plan clock boundaries, ordering/E-ID stability, UTF-8/config failures, output collision and rollback.
- Decision: priority table, alias identity, mode methodology, non-finite types, missing/invalid inputs, clock/cwd, two-file rollback and visualizer freshness.
- Pull/review: A/B gate matrix, new-character exception, low rarity, baseline delta, mechanism-note precedence, strict packet JSON, Markdown fence safety, clock/cwd and split-output rollback.
- Real Rust CLI: exact output set, semantic/byte oracle as applicable, command-specific stderr and 0/1/2 exits.
