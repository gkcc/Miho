# Desktop visualizer security contract

This contract freezes the desktop-only boundary between the trusted Tauri main WebView, mutable workspace visualizer data, and the embedded HSR/ZZZ visualizer application.

## Trust split

- The main WebView is trusted product UI. It renders with `createElement`, `textContent` and `replaceChildren`; it does not use `innerHTML`, `srcdoc`, `document.write`, `eval` or a dialog capability.
- HSR/ZZZ `index.html`, `app.js` and `styles.css` are executable assets embedded in `miho-core` at compile time. Workspace copies with the same names are never executed by the desktop protocol.
- Workspace `data.json`, local avatar files and Box State are mutable data. They are served only after the active workspace, route and filesystem chain have been validated.
- The visualizer iframe is a different origin and uses `sandbox="allow-scripts allow-same-origin"`. Tauri runs in isolation mode; the generated context test must remain `Pattern::Isolation`. The visualizer CSP blocks the isolation child frame that Wry attempts to inject into the untrusted subframe, while the main frame retains normal IPC.

## Workspace-scoped protocol

The registered `miho-visualizer` protocol accepts only the main WebView label and these fixed routes:

- `/{hsr|zzz}/{index.html|app.js|styles.css|data.json}`
- `/{hsr|zzz}/assets/avatars/<one-safe-file-name>`
- `/api/{hsr|zzz}/box`

Every request, including `HEAD` and `OPTIONS`, must carry exactly one `workspace` token. Tokens are 1–128 ASCII alphanumeric/hyphen bytes and must equal the current opaque workspace ID. Missing tokens fail closed, malformed or duplicate tokens are rejected, and an A token after switching to B returns conflict before any read or write.

The trusted index response adds the access token to its script and stylesheet URLs. The trusted app response is derived in memory by prepending a fixed bootstrap that:

- adds the current token to every same-origin string/URL `fetch` request, covering `data.json` and Box GET/PUT;
- namespaces `localStorage.getItem/setItem/removeItem` by a stable opaque storage scope derived from the canonical workspace identity, so an old workspace Box or recommender cache cannot be replayed into a newly selected workspace, while the same physical workspace still recovers browser-only state after a revision change or application restart. The short-lived access token is never used as the storage identity.

The static app asset itself is unchanged, so Rust export, independent visualizer, Hub, Python oracle and their hash contract keep their original standalone behavior. The desktop `data.json` response is parsed and reserialized only in memory; valid `./assets/avatars/<safe-name>` references receive the current token while external links and invalid paths are not rewritten.

## Filesystem and response boundary

- Routes are strictly percent-decoded once. Backslashes, traversal, empty/dot segments, double encoding and unknown files are rejected.
- The workspace root and every existing visualizer/Box component reject symlinks and Windows reparse points.
- Box GET rejects an existing file over 1 MiB before reading. PUT limits the request, normalizes Box State, limits `builds` nesting to 32, verifies the actual pretty-JSON-plus-LF storage bytes remain within 1 MiB, and holds the same workspace gate used by native workspace selection through the final write. Main IPC and protocol use the same normalized limits.
- `data.json` is limited to 64 MiB and must parse before the main UI publishes a visualizer URL. Every referenced local avatar must exist and be at most 8 MiB; readiness checks avatar metadata rather than reading every image into memory. Protocol GET repeats the same bounds before allocation.
- Static executable responses come from compile-time bytes. `index.html`, `app.js`, data and avatars use `no-store` where workspace identity matters. Responses include CSP, `nosniff`, `no-referrer`, fixed MIME and restricted methods.
- Public errors, task snapshots, artifacts, workspace summaries and visualizer URLs do not contain native workspace paths or raw native error chains.

## Verification gate

The gate requires all of the following:

- protocol route, token, traversal, reparse, Box, data/avatar rewrite and stale A→B Rust tests;
- generated Tauri context proves isolation mode and the identity isolation hook;
- source contracts prove the main UI has no unsafe HTML sink and consumes only strict public schemas;
- Python/Rust visualizer hash and real CLI tests remain green because desktop derivation does not alter artifact bytes;
- Windows WebView2 smoke covers both games rendering data and avatars, Box read/write, A→B no replay, B→A, settings replacement and application restart.

On 2026-07-13 the Windows smoke rendered both games, wrote Box State, switched A→B with B remaining empty after the iframe settled, switched B→A, and restarted with the persisted revision. The first replacement of an existing settings file reproduced `workspace.persist_failed`: the virtualized AppData filesystem returned `CrossesDevices` even for sibling rename. `atomic::write` now applies the synced copy fallback to both backup and install moves, and the same smoke then passed revisions 2→3→4.

DevTools showed the main frame, the visualizer frame and the main isolation frame, and recorded that the visualizer frame's attempted isolation child was blocked by its CSP. A direct console `invoke` probe was not executed because DevTools required bypassing its self-XSS paste safety barrier. That barrier was not bypassed; IPC isolation therefore remains additionally backed by the compiled isolation context, origin check and observed frame/CSP behavior rather than a pasted console call.

## Explicitly deferred

This gate does not claim export background tasks, task-history persistence, abrupt-kill/power-loss recovery, GUI/CLI cross-process locking, the Rust update runner, scheduled-task migration, installer/portable resource completeness, or no-Python release validation. Desktop capabilities must continue to report unsupported recovery properties as false until those later gates are implemented.
