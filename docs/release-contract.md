# Release transaction contract

Status: implemented transaction boundary, not a product-release approval. A
build defaults to verification evidence even when the source is clean and the
bundle is complete. `-ProjectGatesApproved` is the explicit operator
attestation that the installer owner/upgrade/rollback and real matrix gates
elsewhere in the project are green; it is accepted only for a clean full
bundle. `-NoBundle`, dirty-source, and unapproved runs cannot publish active.

## Lease and mutation order

`scripts/build_rust_app.ps1 -Release` acquires the release lease before the
first `target`, bundle, release-context, staging, or dependency mutation:

- a workspace-keyed `Local\MihoReleaseBuildV1-<sha256>` mutex rejects a second
  process in the same Windows session without touching the filesystem;
- `target/.miho-release-build-v1.lock` is then opened with `FileShare.None` and
  held until the outermost `finally` finishes all cleanup and restores the
  working directory;
- the file handle is the system-wide/cross-session authority and pins target
  and workspace ancestors against rename while the release is active.
- after the lease is acquired, stale `release-workspace` and `release-staging`
  children from a killed prior run are removed by a scratch-only walker. It
  never traverses reparse targets: pnpm junctions are unlinked as objects, and
  an external canary proves their targets remain untouched. On success, the
  final frozen/output assertions run first, then every calibration and scratch
  tree is removed before publication can change the active anchor. On failure,
  the outer `finally` retries cleanup before lease release. Empty scratch
  parents are removed; content-addressed files under `target/release/bundle`
  are outside this cleanup boundary.

A rejected contender must not alter target contents or directory metadata.
The lock file is persistent; ownership is the open handle, not file presence.

## Frozen source and toolchain evidence

After acquiring the lease, the wrapper first captures the original Git
commit/status and the complete release-source digest. It then copies only the
hash-bound source inputs into a unique directory below
`target/release/release-workspace/`. Existing `node_modules`, `dist`, and
`target` directories are excluded recursively; any other reparse point is a
hard failure. The isolated source digest and file count must exactly equal the
original frozen values before dependency resolution is allowed.
The isolated source, copied dependency tree, Cargo target, and immutable
staging are verification scratch rather than release artifacts; they are
deleted before the wrapper exits. A published manifest therefore never relies
on either scratch path remaining present.

The wrapper validates the exact pinned `packageManager` and `engines` policy
in both roots, requires the isolated dependency tree to be absent, and runs in
the isolated root:

```text
pnpm install --frozen-lockfile --prefer-offline --force \
  --verify-store-integrity --package-import-method copy
```

The repository's pre-existing dependency tree is neither repaired nor
consumed. Package bytes are copied rather than linked from the pnpm store, so
later store mutation cannot change the build tree. TypeScript, Vite, Cargo,
the desktop ownership prebuild, and Tauri all execute from the isolated
workspace; its own `target` is therefore a unique `CARGO_TARGET_DIR`.

Only after the fresh install does the wrapper capture the evidence used by
every later freeze check. The complete root and desktop `node_modules` graph
is fingerprinted: regular files contribute relative path, size, and SHA-256;
directories and in-workspace reparse targets contribute their identities; an
escaping or unresolved target is rejected. Merely remaining inside the
workspace is not sufficient: reparse targets must stay below one of the two
dependency roots, except for pnpm's one exact self-workspace link to
`crates/miho-desktop`. Links to source-excluded `dist`, `target`, or any other
workspace location fail closed. The exact self link is backed by the frozen
source digest; generated frontend bytes are separately copied into and bound
by immutable staging. The root manifest has an exact schema and records:

- `source`: Git commit, `clean`/`dirty`, normalized porcelain-status SHA-256,
  and status-entry count;
- `inputs`: original workspace, isolated build workspace, and
  immutable-staging SHA-256 plus file counts; the first two must remain
  identical;
- `toolchain`: `package.json`, `Cargo.lock`, root `pnpm-lock.yaml`, installed
  `node_modules/.pnpm/lock.yaml`, node executable, pnpm launcher, TypeScript,
  Vite, Tauri CLI, and `rustc -vV` hashes, plus the actual and required
  Node/pnpm versions, Rust host/release, Cargo version, the complete dependency
  tree SHA-256/entry count/file count, dependency graph state, and
  frozen-install mode.

The two pnpm lock hashes must be byte-identical. The actual Node and pnpm
versions must satisfy `package.json`; the three named JavaScript entrypoints
are retained as diagnostic evidence, but do not substitute for the complete
dependency-tree digest. Git, both source roots, the full dependency graph,
staging, CLI, sidecar, desktop executable, and all external artifacts are
re-read before publication. A change aborts the transaction.

Vite 6's bundled config loader creates
`crates/miho-desktop/node_modules/.vite-temp`, deletes its generated config,
and leaves the empty directory behind. After a successful frontend build the
wrapper resolves that path as a normal in-workspace directory, refuses it if
it contains any entry, and removes only the empty directory before re-reading
the frozen dependency graph. The path is not ignored, so persistent output,
unexpected files, or a reparse point still abort the release transaction.

## Publication eligibility

The manifest's exact `publication` object is derived from frozen source state,
bundle mode, and the explicit project-gate attestation:

| Source | Bundle mode | Gate attestation | State | Reason |
| --- | --- | --- | --- | --- |
| clean | full NSIS + portable | absent | `verification-only` | `project-gates-not-approved` |
| clean | full NSIS + portable | `-ProjectGatesApproved` | `active` | `project-gates-approved-clean-source-and-full-bundle` |
| dirty | full NSIS + portable | absent | `verification-only` | `dirty-source-tree` |
| clean | `-NoBundle` | absent | `verification-only` | `no-bundle` |
| dirty | `-NoBundle` | absent | `verification-only` | `dirty-source-tree-and-no-bundle` |

Supplying the attestation for a dirty tree, a no-bundle build, or a non-release
invocation is a hard error. The switch is an approval boundary, not an
automated claim that the project gates were executed; the corresponding
`PROJECT.md` evidence and independent `Blocker=0 / High=0` review must exist
before an operator uses it.

Verification-only output is renamed to a unique
`miho-release-verification-v1.<nonce>.json`. It never replaces or removes
`miho-release-artifacts-v1.json`.

## Immutable artifact dependencies

An existing active manifest must remain truthful throughout a failed,
verification-only, or succeeding replacement build. New artifacts therefore
never overwrite paths referenced by the old manifest:

- Tauri receives the unique isolated workspace's `target` as
  `CARGO_TARGET_DIR`; a stale or missing
  `target/release/miho-desktop.exe` is never a packaging input;
- Tauri first runs `build --no-bundle` under a one-use build context. A full
  NSIS build then uses a separate `bundle --bundles nsis` calibration pass
  because Tauri writes the selected bundle type into the installer's PE copy
  only while bundling; the source executable remains byte-identical to the
  no-bundle build. The wrapper extracts the calibration container, requires
  every non-main static byte and the exact path set to match provisional
  staging, and treats the extracted patched main executable as the installed
  and portable payload identity. The calibration installer and complete
  provisional staging tree are then deleted; staging is re-materialized at the
  same path and verification nonce with an ownership manifest generated from
  those extracted bytes. The final tree is frozen from that point. A second
  bundle-only pass never invokes Cargo or mutates the source executable, and
  final container extraction must match the calibration-bound manifest. A
  no-bundle build simply re-materializes ownership from the actual Tauri-built
  executable and produces no container;
- the isolated desktop executable is passed explicitly to both installed and
  portable payload builders;
- NSIS is moved to
  `bundle/nsis/<generated-base>.sha256-<full-sha256>.exe`;
- the installed-payload manifest is finalized as
  `bundle/miho-static-installed-payload-v1.<full-sha256>.json`;
- portable directories and ZIPs retain their payload-manifest-derived ID and
  are byte-for-byte validated before an existing content-addressed path is
  reused.

Every hash-bound file record is ordered with `StringComparer.Ordinal`; shell
or locale collation is not a release input. Hash-bound JSON is compact UTF-8
without BOM plus one LF. Portable archives use the repository's stored-ZIP
writer with ordinal entry order, fixed UTF-8 flags, fixed DOS epoch, explicit
CRC32, and fixed headers instead of runtime ZIP defaults. The contract test
pins the complete fixture archive SHA-256
`6aff220e4deb530682ef402ee3111507292929f90d25bb9312c0ef9fc69bd3f5`
under both Windows PowerShell 5.1 and PowerShell 7.

The root assertion requires the portable and installed artifacts to be in
their canonical directories, requires the installed filename to contain its
actual full hash, revalidates every payload record and ZIP member, and (for a
full bundle) revalidates the exact immutable NSIS bytes, Authenticode status,
and isolated container-extraction receipt.

## Static ownership producer

Before Tauri bundles resources, Cargo prebuilds the desktop executable in the
same isolated target that Tauri will consume. The staging writer then creates
the fixed installed resource `miho-static-ownership-v1.json`. Its exact schema
is:

- top-level fields: `schema_version`, `product_version`, `target_triple`,
  `files`, and `ownership`;
- `schema_version`: `miho-static-ownership-v1`;
- every `files` record: `install_path`, integer `size`, and lowercase SHA-256;
- `ownership`: fixed manifest path, explicit non-self-inclusion, complete-set
  marker, mutable-data exclusion, and retired policy
  `delete-only-if-old-size-and-sha256-match`.

`files` is the complete installer-owned static set but deliberately excludes
the ownership manifest itself. It covers `miho-desktop.exe`, `miho.exe`, every
`defaults/configs/**` file, the three scheduler scripts, and
`installer/installer_transaction_v1.ps1`. Old-minus-new retired targets may be
deleted only when their current size and SHA-256 still match the old manifest;
otherwise the installer must preserve them and fail closed. The external
content-addressed `miho-static-installed-payload-v1` manifest includes all of
those records and additionally hashes the fixed ownership manifest itself,
avoiding an impossible self-hash.

NSIS carries the ownership manifest at the installation root. Portable output
also carries the same bytes for inspection, plus
`automation/portable_daily_update_task.ps1`; that portable-only wrapper is not
an installed-owned target. Conversely, `installer_transaction_v1.ps1` is an
installed NSIS helper and is not part of portable automation. The portable
files manifest still covers every portable byte.

After `tauri build`, the wrapper requires the final desktop executable to be
byte-for-byte identical to the ownership-bound prebuild. The ownership
manifest, immutable staging digest, installed manifest, extracted NSIS files,
and portable payload are all revalidated against the same final bytes.

## Installer dynamic state, rollback, and uninstall boundary

The static ownership manifest is only one half of the installed transaction.
Before NSIS mutates the existing product, `installer_transaction_v1.ps1`
captures a bounded dynamic before-image for Start Menu and optional desktop
shortcuts, the publisher/product install-location tree, the Windows uninstall
tree, the automation owner, and the scheduler handoff. An explicit
`MIHO_INSTALLER_START_MENU_ROOT_V1=1` marker distinguishes Tauri's valid
root-of-Programs policy from an absent environment variable; Windows deletes
an environment variable when NSIS sets it to an empty string, so the folder
string alone is not an unambiguous input.

Shortcut verification requires both the target executable and
`WorkingDirectory` to equal the final install root. NSIS resets `OutPath` to
that root before each `CreateShortcut`; a shortcut whose working directory
still points at immutable staging or `$PLUGINSDIR` fails `VerifyDynamic`.
Existing shortcut bytes are hash-bound in the before-image and restored on
rollback. A clean-install rollback removes the install root only when the
transaction proved it did not exist beforehand and it is empty after owned
state restoration.

Registry snapshots preserve the exact recursive key/value shape, value kinds,
bytes, and access DACL for the two product trees. Restore deletes the mutated
tree, recreates the typed snapshot, applies the saved access descriptor with
`ChangePermissions`, and reads it back. Windows' automatically added `AI`
control bit is ignored only for comparison; protection/auto-inherit-request
flags and every ACE remain exact inputs. Owner/group/SACL are deliberately
outside the current-user installer contract because restoring those sections
requires privileges the package does not request.

Any helper exception may atomically publish
`%LOCALAPPDATA%\com.miho.endgame.installer-last-failure-v1.json` with schema,
failed mode, transaction ID, phase, error text, and UTC time. The transaction
tree can then be rolled back and finalized without erasing this diagnostic;
the next normal install deletes the old receipt before starting. Receipt
publication is best effort and never hides the primary setup failure, while
the setup failure message names its durable location.

Uninstall always removes installer-owned product metadata, including the
uninstall registration, publisher/product install-location and language keys,
automation owner/task, shortcuts, and immutable installed payload. Those keys
are not user data and are removed even when the AppData checkbox is clear.
Conversely, `%APPDATA%\com.miho.endgame` and
`%LOCALAPPDATA%\com.miho.endgame` are mutable user-data roots and are never
recursively removed by this installer or uninstaller. The uninstall confirm
page deliberately exposes no generic Delete AppData checkbox. Any future data
deletion workflow requires a separately designed, path-bounded contract and
new real-machine canary evidence; it must not be reintroduced as an upstream
recursive branch. The separate zero-byte installer lease file may remain
after uninstall; its presence is not lock ownership and it contains no user
data.

## Pending validation and atomic commit

The root artifacts manifest is first written as a same-directory randomized
`.miho-release-artifacts-v1.<nonce>.pending.json`. The wrapper performs a full
strict semantic assertion, a final frozen-input and executable check, and a
second full output assertion. On success, publication is the only remaining
filesystem mutation:

- if no active manifest exists, `File.Move` performs one same-volume rename;
- if the initially observed active manifest still has the same size and hash,
  `File.Replace` atomically installs the pending bytes and creates one random
  superseded backup containing the old manifest bytes;
- if active presence or bytes drifted, publication fails without overwriting
  it.

After the rename/replace, the wrapper only reopens the published path and
checks its size and SHA-256. A pre-publication failure deletes the root pending
manifest and never creates a new active anchor. Static-manifest and portable
temporary paths have their own failure cleanup; already finalized
content-addressed artifacts may remain as harmless unreferenced evidence.

## Required verification and remaining gates

`tests/powershell/test_release_contract.ps1` must pass under Windows
PowerShell 5.1 and PowerShell 7. It covers strict JSON/type spoofing, semantic
portable/installed spoofing, clean/dirty Git and HEAD drift, frozen-lock and
pnpm-version mismatch, a persistent poisoned transitive dependency excluded
from the fresh isolated install, post-capture transitive dependency drift,
and a dependency junction into source-excluded `dist`, static-ownership
semantic spoofing, same-session process contention, target/workspace ancestor
rename, ordinal cross-shell record ordering, a byte-pinned deterministic
portable container, immutable NSIS/static publication, preservation of prior active
dependencies, verification-only isolation, active-anchor drift, superseded
old bytes, and stale/missing root desktop targets.
The regression also proves scratch cleanup removes only the two regenerable
parents, preserves bundle artifacts, and unlinks a junction without touching
its external canary. A cleanup fault injected immediately before publication
must leave the old active anchor byte-identical and remove the ephemeral
pending manifest; after the poison is removed and a new pending file is
written, the same helper cleans scratch before performing the active
replacement.

This contract does not clear the project-wide installer gate. A final active
release still requires the NSIS owner identity, upgrade recovery, rollback,
registry/shortcut/task restoration, and real clean install/upgrade/uninstall
matrix to have `Blocker=0 / High=0`. Cross-account or cross-session lease
evidence should also be captured on the final release machine even though the
filesystem handle is system-wide and the ancestor-rename regression is
permanent.
