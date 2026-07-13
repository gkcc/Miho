//! Strict native-only update configuration boundary.
//!
//! The JSON structs in this module deliberately keep path fields private and
//! implement `Deserialize` only.  Browser/WebView commands must never accept
//! either the raw or resolved types; a trusted native adapter loads the file
//! and resolves it against an authorized workspace.

use std::{
    fs,
    path::{Component, Path, PathBuf},
};

use anyhow::{bail, Context};
use miho_core::contract::{Game, GameMode};
use serde::Deserialize;
use sha2::{Digest, Sha256};

pub const UPDATE_CONFIG_SCHEMA_V1: &str = "miho-update-config-v1";
pub const MIN_UPDATE_DAYS_V1: u32 = 1;
pub const MAX_UPDATE_DAYS_V1: u32 = 3_650;
pub const MAX_UPDATE_CONFIG_BYTES_V1: usize = 1024 * 1024;
pub const MIN_PRYDWEN_TOP_N_V1: usize = 1;
pub const MAX_PRYDWEN_TOP_N_V1: usize = 10_000;

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct UpdateConfigV1 {
    schema_version: String,
    days: u32,
    hsr: HsrUpdateConfigV1,
    zzz: ZzzUpdateConfigV1,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct HsrUpdateConfigV1 {
    output: String,
    repo_id: String,
    revision: String,
    modes: Vec<GameMode>,
    prydwen_top_n: usize,
}

#[derive(Debug, Clone, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
struct ZzzUpdateConfigV1 {
    output: String,
    repo_id: String,
    revision: String,
    modes: Vec<GameMode>,
    prydwen_top_n: usize,
    #[serde(rename = "box")]
    box_path: String,
    banner_plan: String,
    mechanism_notes: String,
    decision_baseline: String,
}

/// Fully validated update inputs for a trusted native runner.
///
/// This type intentionally has no serde traits and is not a WebView wire type.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolvedUpdateConfigV1 {
    pub workspace: PathBuf,
    pub days: u32,
    pub hsr: ResolvedGameUpdateConfigV1,
    pub zzz: ResolvedZzzUpdateConfigV1,
}

/// Native-only resolved settings common to one game's export.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolvedGameUpdateConfigV1 {
    pub output: PathBuf,
    pub repo_id: String,
    pub revision: String,
    pub modes: Vec<GameMode>,
    pub prydwen_top_n: usize,
}

/// Native-only ZZZ settings, including workspace-confined report inputs.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolvedZzzUpdateConfigV1 {
    pub export: ResolvedGameUpdateConfigV1,
    pub box_path: PathBuf,
    pub banner_plan: PathBuf,
    pub mechanism_notes: PathBuf,
    pub decision_baseline: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LoadedUpdateConfigV1 {
    pub config: UpdateConfigV1,
    pub sha256: String,
}

impl UpdateConfigV1 {
    /// Parse an untrusted JSON document and validate all lexical invariants.
    pub fn parse(bytes: &[u8]) -> anyhow::Result<Self> {
        if bytes.len() > MAX_UPDATE_CONFIG_BYTES_V1 {
            bail!("update config exceeds the {MAX_UPDATE_CONFIG_BYTES_V1}-byte limit");
        }
        let config: Self = serde_json::from_slice(bytes).context("invalid update config JSON")?;
        config.validate()?;
        Ok(config)
    }

    /// Resolve every configured path below one existing, real workspace.
    ///
    /// Existing path components are checked without following links. Missing
    /// leaf paths are allowed because outputs can be created by the runner.
    pub fn resolve(&self, workspace: &Path) -> anyhow::Result<ResolvedUpdateConfigV1> {
        let workspace = resolve_workspace(workspace)?;
        let hsr_output = resolve_workspace_relative(&workspace, &self.hsr.output, "hsr.output")?;
        let zzz_output = resolve_workspace_relative(&workspace, &self.zzz.output, "zzz.output")?;
        let zzz_box = resolve_workspace_relative(&workspace, &self.zzz.box_path, "zzz.box")?;
        let zzz_banner_plan =
            resolve_workspace_relative(&workspace, &self.zzz.banner_plan, "zzz.banner_plan")?;
        let zzz_mechanism_notes = resolve_workspace_relative(
            &workspace,
            &self.zzz.mechanism_notes,
            "zzz.mechanism_notes",
        )?;
        let zzz_decision_baseline = resolve_workspace_relative(
            &workspace,
            &self.zzz.decision_baseline,
            "zzz.decision_baseline",
        )?;

        Ok(ResolvedUpdateConfigV1 {
            workspace,
            days: self.days,
            hsr: ResolvedGameUpdateConfigV1 {
                output: hsr_output,
                repo_id: self.hsr.repo_id.clone(),
                revision: self.hsr.revision.clone(),
                modes: self.hsr.modes.clone(),
                prydwen_top_n: self.hsr.prydwen_top_n,
            },
            zzz: ResolvedZzzUpdateConfigV1 {
                export: ResolvedGameUpdateConfigV1 {
                    output: zzz_output,
                    repo_id: self.zzz.repo_id.clone(),
                    revision: self.zzz.revision.clone(),
                    modes: self.zzz.modes.clone(),
                    prydwen_top_n: self.zzz.prydwen_top_n,
                },
                box_path: zzz_box,
                banner_plan: zzz_banner_plan,
                mechanism_notes: zzz_mechanism_notes,
                decision_baseline: zzz_decision_baseline,
            },
        })
    }

    fn validate(&self) -> anyhow::Result<()> {
        if self.schema_version != UPDATE_CONFIG_SCHEMA_V1 {
            bail!(
                "unsupported update config schema {}; expected {}",
                self.schema_version,
                UPDATE_CONFIG_SCHEMA_V1
            );
        }
        if !(MIN_UPDATE_DAYS_V1..=MAX_UPDATE_DAYS_V1).contains(&self.days) {
            bail!("update days must be between {MIN_UPDATE_DAYS_V1} and {MAX_UPDATE_DAYS_V1}");
        }
        validate_game_config(
            Game::Hsr,
            &self.hsr.repo_id,
            &self.hsr.revision,
            &self.hsr.modes,
            self.hsr.prydwen_top_n,
            "hsr",
        )?;
        validate_game_config(
            Game::Zzz,
            &self.zzz.repo_id,
            &self.zzz.revision,
            &self.zzz.modes,
            self.zzz.prydwen_top_n,
            "zzz",
        )?;
        validate_relative_path(&self.hsr.output, "hsr.output")?;
        validate_relative_path(&self.zzz.output, "zzz.output")?;
        validate_output_path(&self.hsr.output, "hsr.output")?;
        validate_output_path(&self.zzz.output, "zzz.output")?;
        let hsr_output = windows_component_identity(&self.hsr.output);
        let zzz_output = windows_component_identity(&self.zzz.output);
        if hsr_output == zzz_output {
            bail!("hsr.output and zzz.output must be distinct");
        }
        if hsr_output == "visualizer" || zzz_output == "visualizer" {
            bail!("game output must not overlap the workspace visualizer Hub");
        }
        validate_relative_path(&self.zzz.box_path, "zzz.box")?;
        validate_relative_path(&self.zzz.banner_plan, "zzz.banner_plan")?;
        validate_relative_path(&self.zzz.mechanism_notes, "zzz.mechanism_notes")?;
        validate_relative_path(&self.zzz.decision_baseline, "zzz.decision_baseline")?;
        Ok(())
    }
}

/// Load and strictly validate a V1 update config from a native filesystem path.
pub fn load_update_config_v1(path: &Path) -> anyhow::Result<UpdateConfigV1> {
    Ok(load_update_config_with_digest_v1(path)?.config)
}

/// Load one safe config file and retain the exact byte identity used by the
/// runner so health checks cannot silently approve an older configuration.
pub fn load_update_config_with_digest_v1(path: &Path) -> anyhow::Result<LoadedUpdateConfigV1> {
    reject_reparse_path(path, true)
        .with_context(|| format!("unsafe update config path {}", path.display()))?;
    let bytes =
        fs::read(path).with_context(|| format!("cannot read update config {}", path.display()))?;
    let config = UpdateConfigV1::parse(&bytes)
        .with_context(|| format!("cannot load update config {}", path.display()))?;
    Ok(LoadedUpdateConfigV1 {
        config,
        sha256: format!("{:x}", Sha256::digest(&bytes)),
    })
}

fn validate_game_config(
    game: Game,
    repo_id: &str,
    revision: &str,
    modes: &[GameMode],
    prydwen_top_n: usize,
    label: &str,
) -> anyhow::Result<()> {
    validate_non_empty_trimmed(repo_id, &format!("{label}.repo_id"))?;
    validate_non_empty_trimmed(revision, &format!("{label}.revision"))?;
    if modes.is_empty() {
        bail!("{label}.modes must not be empty");
    }
    if let Some(mode) = modes.iter().find(|mode| mode.game() != game) {
        bail!("mode {} does not belong to {label}", mode.code());
    }
    if !(MIN_PRYDWEN_TOP_N_V1..=MAX_PRYDWEN_TOP_N_V1).contains(&prydwen_top_n) {
        bail!(
            "{label}.prydwen_top_n must be between {MIN_PRYDWEN_TOP_N_V1} and {MAX_PRYDWEN_TOP_N_V1}"
        );
    }
    Ok(())
}

fn validate_non_empty_trimmed(value: &str, label: &str) -> anyhow::Result<()> {
    if value.trim().is_empty() {
        bail!("{label} must not be empty");
    }
    if value != value.trim() {
        bail!("{label} must not have leading or trailing whitespace");
    }
    Ok(())
}

fn validate_relative_path(value: &str, label: &str) -> anyhow::Result<()> {
    if value.trim().is_empty() {
        bail!("{label} must not be empty");
    }

    // Check both separator styles so a config remains safe if moved between
    // platforms and Windows drive-relative prefixes are rejected on Unix too.
    let normalized = value.replace('\\', "/");
    if normalized.starts_with('/')
        || normalized.contains(':')
        || normalized
            .as_bytes()
            .get(1)
            .is_some_and(|value| *value == b':')
    {
        bail!("{label} must be a workspace-relative path");
    }
    for component in normalized.split('/') {
        if component.is_empty() || matches!(component, "." | "..") {
            bail!("{label} contains an unsafe path component");
        }
    }

    let path = Path::new(value);
    if path.is_absolute()
        || path.components().any(|component| {
            matches!(
                component,
                Component::Prefix(_)
                    | Component::RootDir
                    | Component::CurDir
                    | Component::ParentDir
            )
        })
    {
        bail!("{label} must contain only normal relative path components");
    }
    Ok(())
}

fn validate_output_path(value: &str, label: &str) -> anyhow::Result<()> {
    let normalized = value.replace('\\', "/");
    if normalized.contains('/') {
        bail!("{label} must be one top-level workspace directory");
    }
    if !value
        .bytes()
        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
        || value.trim_end_matches([' ', '.']) != value
    {
        bail!("{label} must use a stable ASCII directory name");
    }
    let identity = windows_component_identity(value);
    if matches!(
        identity.as_str(),
        "con"
            | "prn"
            | "aux"
            | "nul"
            | "com1"
            | "com2"
            | "com3"
            | "com4"
            | "com5"
            | "com6"
            | "com7"
            | "com8"
            | "com9"
            | "lpt1"
            | "lpt2"
            | "lpt3"
            | "lpt4"
            | "lpt5"
            | "lpt6"
            | "lpt7"
            | "lpt8"
            | "lpt9"
    ) {
        bail!("{label} is a reserved Windows device name");
    }
    if normalized.split('/').any(|component| {
        let windows_normalized = component.trim_end_matches([' ', '.']);
        windows_normalized.eq_ignore_ascii_case(".miho")
            || windows_normalized.eq_ignore_ascii_case("configs")
    }) {
        bail!("{label} must not overlap the .miho or configs sensitive area");
    }
    Ok(())
}

fn windows_component_identity(value: &str) -> String {
    value.trim_end_matches([' ', '.']).to_ascii_lowercase()
}

fn resolve_workspace(workspace: &Path) -> anyhow::Result<PathBuf> {
    let metadata = fs::symlink_metadata(workspace)
        .with_context(|| format!("cannot inspect workspace {}", workspace.display()))?;
    if is_reparse_or_symlink(&metadata) || !metadata.is_dir() {
        bail!(
            "workspace is not an existing real directory: {}",
            workspace.display()
        );
    }
    fs::canonicalize(workspace)
        .with_context(|| format!("cannot resolve workspace {}", workspace.display()))
}

fn resolve_workspace_relative(
    workspace: &Path,
    relative: &str,
    label: &str,
) -> anyhow::Result<PathBuf> {
    validate_relative_path(relative, label)?;
    let relative = Path::new(relative);
    reject_existing_relative_chain(workspace, relative)
        .with_context(|| format!("{label} is not a trusted workspace path"))?;
    let resolved = workspace.join(relative);
    if !resolved.starts_with(workspace) {
        bail!("{label} escapes the workspace");
    }
    Ok(resolved)
}

fn reject_existing_relative_chain(workspace: &Path, relative: &Path) -> anyhow::Result<()> {
    let mut current = workspace.to_path_buf();
    let component_count = relative.components().count();
    for (index, component) in relative.components().enumerate() {
        let Component::Normal(component) = component else {
            bail!("unsafe relative path component");
        };
        current.push(component);
        match fs::symlink_metadata(&current) {
            Ok(metadata) => {
                if is_reparse_or_symlink(&metadata) {
                    bail!("refusing symlink or reparse path: {}", current.display());
                }
                if index + 1 < component_count && !metadata.is_dir() {
                    bail!("path ancestor is not a directory: {}", current.display());
                }
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => break,
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

fn reject_reparse_path(path: &Path, require_leaf: bool) -> anyhow::Result<()> {
    let mut current = PathBuf::new();
    let components = path.components().collect::<Vec<_>>();
    for (index, component) in components.iter().enumerate() {
        current.push(component.as_os_str());
        match fs::symlink_metadata(&current) {
            Ok(metadata) => {
                if is_reparse_or_symlink(&metadata) {
                    bail!("refusing symlink or reparse path: {}", current.display());
                }
                if index + 1 < components.len() && !metadata.is_dir() {
                    bail!("path ancestor is not a directory: {}", current.display());
                }
            }
            Err(error)
                if error.kind() == std::io::ErrorKind::NotFound
                    && (!require_leaf || index + 1 < components.len()) =>
            {
                break;
            }
            Err(error) => return Err(error.into()),
        }
    }
    Ok(())
}

fn is_reparse_or_symlink(metadata: &fs::Metadata) -> bool {
    if metadata.file_type().is_symlink() {
        return true;
    }
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;

        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
        metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
    }
    #[cfg(not(windows))]
    {
        false
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicU64, Ordering};

    use super::*;

    static NEXT_TEST_ID: AtomicU64 = AtomicU64::new(0);

    fn valid_json() -> String {
        r#"{
          "schema_version":"miho-update-config-v1",
          "days":183,
          "hsr":{
            "output":"out",
            "repo_id":"owner/hsr",
            "revision":"main",
            "modes":["moc","pf","as","aa"],
            "prydwen_top_n":100
          },
          "zzz":{
            "output":"out_zzz",
            "repo_id":"owner/zzz",
            "revision":"main",
            "modes":["sd","da"],
            "prydwen_top_n":100,
            "box":".miho/zzz_box_state.json",
            "banner_plan":"configs/zzz_banner_plan.json",
            "mechanism_notes":"configs/zzz_mechanism_notes",
            "decision_baseline":"configs/zzz_decision_baseline.json"
          }
        }"#
        .to_owned()
    }

    fn replace_once(json: &str, from: &str, to: &str) -> String {
        assert!(json.contains(from));
        json.replacen(from, to, 1)
    }

    fn test_workspace() -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "miho-update-config-{}-{}",
            std::process::id(),
            NEXT_TEST_ID.fetch_add(1, Ordering::Relaxed)
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join(".miho")).unwrap();
        fs::create_dir_all(root.join("configs/zzz_mechanism_notes")).unwrap();
        root
    }

    #[test]
    fn malformed_and_unknown_fields_are_rejected() {
        assert!(UpdateConfigV1::parse(br#"{"schema_version":}"#).is_err());
        let top_level = replace_once(&valid_json(), "\"days\":183", "\"days\":183,\"extra\":true");
        assert!(UpdateConfigV1::parse(top_level.as_bytes()).is_err());
        let nested = replace_once(
            &valid_json(),
            "\"prydwen_top_n\":100",
            "\"prydwen_top_n\":100,\"extra\":true",
        );
        assert!(UpdateConfigV1::parse(nested.as_bytes()).is_err());
    }

    #[test]
    fn invalid_days_modes_and_empty_dataset_fields_are_rejected() {
        for days in [0, MAX_UPDATE_DAYS_V1 + 1] {
            let json = replace_once(&valid_json(), "\"days\":183", &format!("\"days\":{days}"));
            assert!(UpdateConfigV1::parse(json.as_bytes()).is_err());
        }
        let empty_modes = replace_once(
            &valid_json(),
            "\"modes\":[\"moc\",\"pf\",\"as\",\"aa\"]",
            "\"modes\":[]",
        );
        assert!(UpdateConfigV1::parse(empty_modes.as_bytes()).is_err());
        let foreign_mode = replace_once(
            &valid_json(),
            "\"modes\":[\"sd\",\"da\"]",
            "\"modes\":[\"moc\"]",
        );
        assert!(UpdateConfigV1::parse(foreign_mode.as_bytes()).is_err());
        let empty_repo = replace_once(
            &valid_json(),
            "\"repo_id\":\"owner/hsr\"",
            "\"repo_id\":\"\"",
        );
        assert!(UpdateConfigV1::parse(empty_repo.as_bytes()).is_err());
        let empty_revision =
            replace_once(&valid_json(), "\"revision\":\"main\"", "\"revision\":\" \"");
        assert!(UpdateConfigV1::parse(empty_revision.as_bytes()).is_err());

        for top_n in [0, MAX_PRYDWEN_TOP_N_V1 + 1] {
            let json = replace_once(
                &valid_json(),
                "\"prydwen_top_n\":100",
                &format!("\"prydwen_top_n\":{top_n}"),
            );
            assert!(UpdateConfigV1::parse(json.as_bytes()).is_err());
        }
    }

    #[test]
    fn oversized_config_is_rejected_before_json_parsing() {
        let oversized = vec![b' '; MAX_UPDATE_CONFIG_BYTES_V1 + 1];
        let error = UpdateConfigV1::parse(&oversized).unwrap_err();
        assert!(error.to_string().contains("byte limit"));
    }

    #[test]
    fn path_traversal_absolute_and_windows_prefixes_are_rejected() {
        for value in [
            "",
            ".",
            "..",
            "../out",
            "safe/../out",
            "/absolute/out",
            r"\absolute\out",
            r"C:\absolute\out",
            r"C:drive-relative\out",
            r"\\server\share\out",
            "safe:name",
        ] {
            let json = replace_once(
                &valid_json(),
                "\"output\":\"out\"",
                &format!("\"output\":{}", serde_json::to_string(value).unwrap()),
            );
            assert!(
                UpdateConfigV1::parse(json.as_bytes()).is_err(),
                "unsafe path unexpectedly accepted: {value:?}"
            );
        }
    }

    #[test]
    fn output_sensitive_areas_are_rejected_case_insensitively() {
        for value in [
            ".miho/output",
            ".MIHO/output",
            "configs/output",
            "safe/ConFiGs/output",
            "CONFIGS./output",
            "visualizer",
            "VISUALIZER. ",
            "Öut",
            "CON",
        ] {
            let json = replace_once(
                &valid_json(),
                "\"output\":\"out\"",
                &format!("\"output\":{}", serde_json::to_string(value).unwrap()),
            );
            assert!(
                UpdateConfigV1::parse(json.as_bytes()).is_err(),
                "sensitive output unexpectedly accepted: {value:?}"
            );
        }

        let overlapping = replace_once(
            &valid_json(),
            "\"output\":\"out_zzz\"",
            "\"output\":\"OUT. \"",
        );
        assert!(UpdateConfigV1::parse(overlapping.as_bytes()).is_err());
    }

    #[test]
    fn valid_config_resolves_only_native_workspace_paths() {
        let workspace = test_workspace();
        let config = UpdateConfigV1::parse(valid_json().as_bytes()).unwrap();
        let resolved = config.resolve(&workspace).unwrap();
        let canonical = fs::canonicalize(&workspace).unwrap();
        assert_eq!(resolved.workspace, canonical);
        assert_eq!(resolved.days, 183);
        assert_eq!(resolved.hsr.output, canonical.join("out"));
        assert_eq!(resolved.zzz.export.output, canonical.join("out_zzz"));
        assert_eq!(
            resolved.zzz.banner_plan,
            canonical.join("configs/zzz_banner_plan.json")
        );
        for path in [
            &resolved.hsr.output,
            &resolved.zzz.export.output,
            &resolved.zzz.box_path,
            &resolved.zzz.banner_plan,
            &resolved.zzz.mechanism_notes,
            &resolved.zzz.decision_baseline,
        ] {
            assert!(path.is_absolute());
            assert!(path.starts_with(&canonical));
        }
        fs::remove_dir_all(workspace).unwrap();
    }

    #[test]
    fn repository_update_config_matches_the_typed_contract() {
        let config = UpdateConfigV1::parse(include_bytes!("../../../configs/update_v1.json"))
            .expect("repository update config must remain a valid V1 document");
        assert_eq!(config.days, 183);
        assert_eq!(config.hsr.modes.first(), Some(&GameMode::HsrMoc));
        assert_eq!(config.zzz.modes, [GameMode::ZzzSd, GameMode::ZzzDa]);
    }

    #[cfg(windows)]
    #[test]
    fn existing_windows_reparse_ancestor_is_rejected() {
        use std::os::windows::fs::symlink_dir;
        use std::process::Command;

        let workspace = test_workspace();
        let outside = test_workspace();
        let linked = workspace.join("linked");
        match symlink_dir(&outside, &linked) {
            Ok(()) => {}
            Err(error)
                if error.kind() == std::io::ErrorKind::PermissionDenied
                    || error.raw_os_error() == Some(1_314) =>
            {
                let status = Command::new("cmd.exe")
                    .args(["/d", "/c", "mklink", "/J"])
                    .arg(&linked)
                    .arg(&outside)
                    .status()
                    .expect("cannot invoke mklink for Windows reparse test");
                assert!(status.success(), "cannot create Windows junction");
            }
            Err(error) => panic!("cannot create Windows reparse test path: {error}"),
        }
        let json = replace_once(
            &valid_json(),
            "\"banner_plan\":\"configs/zzz_banner_plan.json\"",
            "\"banner_plan\":\"linked/plan.json\"",
        );
        let config = UpdateConfigV1::parse(json.as_bytes()).unwrap();
        assert!(config.resolve(&workspace).is_err());
        fs::remove_dir(&linked).unwrap();
        fs::remove_dir_all(workspace).unwrap();
        fs::remove_dir_all(outside).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn existing_symlink_ancestor_is_rejected() {
        use std::os::unix::fs::symlink;

        let workspace = test_workspace();
        let outside = test_workspace();
        symlink(&outside, workspace.join("linked")).unwrap();
        let json = replace_once(
            &valid_json(),
            "\"banner_plan\":\"configs/zzz_banner_plan.json\"",
            "\"banner_plan\":\"linked/plan.json\"",
        );
        let config = UpdateConfigV1::parse(json.as_bytes()).unwrap();
        assert!(config.resolve(&workspace).is_err());
        fs::remove_dir_all(workspace).unwrap();
        fs::remove_dir_all(outside).unwrap();
    }
}
