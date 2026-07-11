use std::{collections::BTreeMap, path::Path};

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::{config, Result};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct BoxState {
    #[serde(default = "version")]
    pub version: u8,
    #[serde(default)]
    pub updated_at: String,
    #[serde(default)]
    pub owned: Vec<String>,
    #[serde(default)]
    pub build_slug: String,
    #[serde(default)]
    pub builds: BTreeMap<String, Value>,
}

const fn version() -> u8 {
    2
}

impl Default for BoxState {
    fn default() -> Self {
        Self {
            version: 2,
            updated_at: String::new(),
            owned: vec![],
            build_slug: String::new(),
            builds: BTreeMap::new(),
        }
    }
}

impl BoxState {
    pub fn normalize(mut self) -> Self {
        self.version = 2;
        self.owned = self
            .owned
            .into_iter()
            .map(|v| v.trim().to_owned())
            .filter(|v| !v.is_empty() && v != "__codex_test__")
            .collect();
        self.owned.sort();
        self.owned.dedup();
        if self.owned.is_empty() && self.builds.is_empty() && self.build_slug.is_empty() {
            self.updated_at.clear();
        }
        self
    }
}

pub fn load(path: &Path) -> Result<BoxState> {
    config::load::<BoxState>(path).map(BoxState::normalize)
}
pub fn save(path: &Path, state: BoxState) -> Result<()> {
    config::save_json(path, &state.normalize())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalization_matches_python_server_contract() {
        let state = BoxState {
            updated_at: "now".into(),
            owned: vec![" nom ".into(), "nom".into(), "__codex_test__".into()],
            ..Default::default()
        }
        .normalize();
        assert_eq!(state.owned, ["nom"]);
        assert_eq!(state.updated_at, "now");
        assert_eq!(state.version, 2);
    }
}
