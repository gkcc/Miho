use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path, PathBuf},
};

use serde::Deserialize;
use serde_json::Value;

use crate::{
    hf::TreeEntry,
    hsr::{
        make_phase_row as make_hsr_phase, parse_builds_character_rows as parse_hsr_builds,
        parse_team_rows as parse_hsr_teams,
    },
    hsr_export::{build_minimal_export as build_hsr_export, TierRow},
    normalize::parse_date,
    output::ArtifactBundle,
    zzz::{
        make_phase_row as make_zzz_phase, parse_team_rows as parse_zzz_teams, parse_usage,
        PhaseInput,
    },
    zzz_export::{build_minimal_bundle as build_zzz_export, NameRow},
    MihoError, Result,
};

#[derive(Debug, Clone, Copy, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Game {
    Hsr,
    Zzz,
}

#[derive(Debug, Deserialize)]
pub struct OfflineManifest {
    pub schema_version: u8,
    pub game: Game,
    pub repo_id: String,
    #[serde(default = "main_revision")]
    pub revision: String,
    #[serde(default)]
    pub root_tree: Vec<TreeEntry>,
    #[serde(default)]
    pub trees: BTreeMap<String, Vec<TreeEntry>>,
    #[serde(default)]
    pub list_failures: BTreeMap<String, Value>,
    #[serde(default)]
    pub download_failures: BTreeMap<String, Value>,
}

fn main_revision() -> String {
    "main".into()
}

pub struct OfflineFixture {
    root: PathBuf,
    pub manifest: OfflineManifest,
}

pub struct PipelineRun {
    pub bundle: ArtifactBundle,
    pub warnings: Vec<String>,
    pub errors: Vec<String>,
}

impl OfflineFixture {
    pub fn load(root: impl Into<PathBuf>) -> Result<Self> {
        let root = root.into();
        let path = root.join("manifest.json");
        let text = fs::read_to_string(&path).map_err(|source| MihoError::Read {
            path: path.clone(),
            source,
        })?;
        let manifest: OfflineManifest =
            serde_json::from_str(&text).map_err(|source| MihoError::Json { path, source })?;
        if manifest.schema_version != 1 {
            return Err(MihoError::Unsupported(format!(
                "offline manifest schema {} is not supported",
                manifest.schema_version
            )));
        }
        Ok(Self { root, manifest })
    }

    pub fn snapshots(&self) -> Vec<String> {
        let mut snapshots = self
            .manifest
            .root_tree
            .iter()
            .filter(|entry| entry.kind == "directory" && is_version(&entry.path))
            .map(|entry| entry.path.clone())
            .collect::<Vec<_>>();
        snapshots.sort();
        snapshots
    }

    pub fn run_hsr(&self, snapshot: &str, mode: &str) -> Result<PipelineRun> {
        if self.manifest.game != Game::Hsr {
            return Err(MihoError::Unsupported("offline fixture is not hsr".into()));
        }
        self.require_snapshot(snapshot)?;
        let mut warnings = vec![];
        let errors = self.failure_messages();
        let config = self.read_json("config.json")?;
        let mut entry = config.get(snapshot).cloned().unwrap_or_else(|| {
            warnings.push(format!("{snapshot}: config missing; dates unavailable"));
            serde_json::json!({})
        });
        prepare_hsr_dates(&mut entry, mode);
        let paths = self.tree_paths(snapshot);
        let builds_path = format!("{snapshot}/builds.json");
        let builds = if paths.contains(&builds_path) {
            self.read_json(&builds_path)?
        } else {
            Value::Array(vec![])
        };
        let characters = parse_hsr_builds(&builds, mode);
        let comp_tree = format!("{snapshot}/{mode}/comps");
        let mut teams = vec![];
        for path in self.json_files(&comp_tree, &mut warnings) {
            teams.extend(parse_hsr_teams(
                &self.read_json(&path)?,
                mode,
                entry
                    .pointer(&format!("/{mode}/ver"))
                    .and_then(Value::as_str)
                    .unwrap_or(snapshot),
                &path,
                None,
            ));
        }
        let phase = make_hsr_phase(
            snapshot,
            &entry,
            mode,
            &format!("{snapshot}/"),
            !characters.is_empty(),
            !teams.is_empty(),
            paths.contains(&format!("{snapshot}/histograph.json")),
            entry
                .get("collect_date")
                .and_then(Value::as_str)
                .map(parse_date)
                .unwrap_or_default()
                .as_str(),
        );
        let bundle = build_hsr_export(&phase, &characters, &teams, &Vec::<TierRow>::new())?;
        Ok(PipelineRun {
            bundle,
            warnings,
            errors,
        })
    }

    pub fn run_zzz(&self, snapshot: &str, mode: &str) -> Result<PipelineRun> {
        if self.manifest.game != Game::Zzz {
            return Err(MihoError::Unsupported("offline fixture is not zzz".into()));
        }
        self.require_snapshot(snapshot)?;
        let mut warnings = vec![];
        let errors = self.failure_messages();
        let config = self.read_json("config.json")?;
        let entry = config.get(snapshot).cloned().unwrap_or_else(|| {
            warnings.push(format!("{snapshot}: config missing; dates unavailable"));
            serde_json::json!({"collect_date":"", mode:{"ver":snapshot}})
        });
        let mode_config = entry.get(mode).and_then(Value::as_object).ok_or_else(|| {
            MihoError::Unsupported(format!("{snapshot}/{mode}: mode config missing"))
        })?;
        let phase = make_zzz_phase(PhaseInput {
            snapshot_id: snapshot.into(),
            mode: mode.into(),
            collect_date: entry
                .get("collect_date")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .into(),
            ver: mode_config
                .get("ver")
                .and_then(Value::as_str)
                .unwrap_or(snapshot)
                .into(),
            name: mode_config
                .get("name")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .into(),
            start: mode_config
                .get("start")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .into(),
            end: mode_config
                .get("end")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .into(),
            source_path: format!("{snapshot}/"),
        });
        let paths = self.tree_paths(snapshot);
        let builds_path = format!("{snapshot}/builds.json");
        let mut usage = vec![];
        if paths.contains(&builds_path) {
            if let Some(rows) = self.read_json(&builds_path)?.as_array() {
                for row in rows {
                    usage.extend(parse_usage(row, mode));
                }
            } else {
                warnings.push(format!("{builds_path} was not a list; skipped"));
            }
        }
        let comp_tree = format!("{snapshot}/{mode}/comps");
        let mut teams = vec![];
        for path in self.json_files(&comp_tree, &mut warnings) {
            let data = self.read_json(&path)?;
            if let Some(rows) = data.as_array() {
                teams.extend(parse_zzz_teams(
                    rows.clone(),
                    mode,
                    Path::new(&path)
                        .file_name()
                        .and_then(|v| v.to_str())
                        .unwrap_or_default(),
                ));
            }
        }
        let bundle = build_zzz_export(&phase, &usage, &teams, &Vec::<NameRow>::new())?;
        Ok(PipelineRun {
            bundle,
            warnings,
            errors,
        })
    }

    fn read_json(&self, relative: &str) -> Result<Value> {
        if self.manifest.download_failures.contains_key(relative) {
            return Err(MihoError::Unsupported(format!(
                "offline download failure: {relative}"
            )));
        }
        let relative_path = Path::new(relative);
        if relative_path.is_absolute()
            || relative_path
                .components()
                .any(|part| !matches!(part, Component::Normal(_)))
        {
            return Err(MihoError::InvalidCacheKey(relative.into()));
        }
        let path = self.root.join("raw/hf").join(relative_path);
        let text = fs::read_to_string(&path).map_err(|source| MihoError::Read {
            path: path.clone(),
            source,
        })?;
        serde_json::from_str(&text).map_err(|source| MihoError::Json { path, source })
    }

    fn tree_paths(&self, key: &str) -> Vec<String> {
        self.manifest
            .trees
            .get(key)
            .into_iter()
            .flatten()
            .map(|entry| entry.path.clone())
            .collect()
    }

    fn json_files(&self, key: &str, warnings: &mut Vec<String>) -> Vec<String> {
        if let Some(failure) = self.manifest.list_failures.get(key) {
            warnings.push(format!("optional tree {key} unavailable: {failure}"));
            return vec![];
        }
        self.manifest
            .trees
            .get(key)
            .into_iter()
            .flatten()
            .filter(|entry| entry.kind == "file" && entry.path.ends_with(".json"))
            .map(|entry| entry.path.clone())
            .collect()
    }

    fn failure_messages(&self) -> Vec<String> {
        self.manifest
            .download_failures
            .keys()
            .map(|path| format!("offline download failure: {path}"))
            .collect()
    }

    fn require_snapshot(&self, snapshot: &str) -> Result<()> {
        if self.snapshots().iter().any(|value| value == snapshot) {
            Ok(())
        } else {
            Err(MihoError::Unsupported(format!(
                "snapshot not present in root tree: {snapshot}"
            )))
        }
    }
}

fn prepare_hsr_dates(entry: &mut Value, mode: &str) {
    if let Some(config) = entry.get_mut(mode).and_then(Value::as_object_mut) {
        for (source, target) in [("start", "start_iso"), ("end", "end_iso")] {
            let value = config
                .get(source)
                .and_then(Value::as_str)
                .map(parse_date)
                .unwrap_or_default();
            config.insert(target.into(), Value::String(value));
        }
    }
}

fn is_version(value: &str) -> bool {
    let parts = value.split('.').collect::<Vec<_>>();
    parts.len() == 3
        && parts
            .iter()
            .all(|part| !part.is_empty() && part.chars().all(|c| c.is_ascii_digit()))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(name: &str) -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../tests/fixtures")
            .join(name)
    }

    #[test]
    fn discovers_and_runs_hsr_fixture() {
        let fixture = OfflineFixture::load(fixture("offline_hsr")).unwrap();
        assert_eq!(fixture.snapshots(), ["4.3.2"]);
        let run = fixture.run_hsr("4.3.2", "moc").unwrap();
        assert!(run.errors.is_empty());
        assert!(run.bundle.get("phase_index.csv").is_some());
        assert!(run.bundle.get("team_rank_raw.csv").is_some());
        assert!(fixture.run_hsr("9.9.9", "moc").is_err());
        assert!(matches!(
            fixture.read_json("../escape.json"),
            Err(MihoError::InvalidCacheKey(_))
        ));
    }

    #[test]
    fn discovers_and_runs_zzz_fixture() {
        let fixture = OfflineFixture::load(fixture("offline_zzz")).unwrap();
        assert_eq!(fixture.snapshots(), ["3.0.1"]);
        let run = fixture.run_zzz("3.0.1", "sd").unwrap();
        assert!(run.errors.is_empty());
        assert!(run.bundle.get("character_usage_long.csv").is_some());
        assert!(run.bundle.get("team_rank_raw.csv").is_some());
    }
}
