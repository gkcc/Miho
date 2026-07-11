use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

const HUGGING_FACE_ORIGIN: &str = "https://huggingface.co";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HuggingFaceRepo {
    pub repo_id: String,
    pub revision: String,
    origin: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TreeEntry {
    #[serde(default)]
    pub path: String,
    #[serde(rename = "type", default)]
    pub kind: String,
    #[serde(flatten)]
    pub extra: serde_json::Map<String, serde_json::Value>,
}

impl HuggingFaceRepo {
    pub fn new(repo_id: impl Into<String>, revision: impl Into<String>) -> Self {
        Self {
            repo_id: repo_id.into(),
            revision: revision.into(),
            origin: HUGGING_FACE_ORIGIN.into(),
        }
    }

    pub fn with_origin(mut self, origin: impl Into<String>) -> Self {
        self.origin = origin.into().trim_end_matches('/').to_owned();
        self
    }

    pub fn tree_url(&self, path: &str, recursive: bool) -> String {
        let mut url = format!(
            "{}/api/datasets/{}/tree/{}",
            self.origin, self.repo_id, self.revision
        );
        let path = path.trim_matches('/');
        if !path.is_empty() {
            url.push('/');
            url.push_str(&quote_path(path));
        }
        url.push_str(if recursive {
            "?recursive=true&expand=false"
        } else {
            "?recursive=false&expand=false"
        });
        url
    }

    pub fn raw_url(&self, path: &str) -> String {
        format!(
            "{}/datasets/{}/resolve/{}/{}",
            self.origin,
            self.repo_id,
            self.revision,
            quote_path(path)
        )
    }
}

pub fn parse_tree_response(text: &str) -> Result<Vec<TreeEntry>, serde_json::Error> {
    serde_json::from_str(text)
}

/// Mirrors `raw_dir.joinpath(*source_path.split("/"))` used by the Python exporters.
pub fn cache_path(raw_dir: &Path, source_path: &str) -> PathBuf {
    source_path
        .split('/')
        .filter(|part| !part.is_empty())
        .fold(raw_dir.to_path_buf(), |path, part| path.join(part))
}

fn quote_path(value: &str) -> String {
    let mut output = String::new();
    for byte in value.as_bytes() {
        if byte.is_ascii_alphanumeric() || matches!(*byte, b'_' | b'-' | b'.' | b'~' | b'/') {
            output.push(*byte as char);
        } else {
            output.push_str(&format!("%{byte:02X}"));
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixture_matches_python_url_and_response_contract() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../../tests/fixtures/hf_client_cases.json"))
                .unwrap();
        for case in fixture["urls"].as_array().unwrap() {
            let repo = HuggingFaceRepo::new(
                case["repo_id"].as_str().unwrap(),
                case["revision"].as_str().unwrap(),
            );
            assert_eq!(
                repo.tree_url(
                    case["path"].as_str().unwrap(),
                    case["recursive"].as_bool().unwrap()
                ),
                case["tree_url"].as_str().unwrap()
            );
            assert_eq!(
                repo.raw_url(case["path"].as_str().unwrap()),
                case["raw_url"].as_str().unwrap()
            );
        }
        let entries = parse_tree_response(&fixture["tree_response"].to_string()).unwrap();
        assert_eq!(entries.len(), 2);
        assert_eq!(entries[0].kind, "file");
        assert_eq!(entries[0].extra["size"], 42);
    }

    #[test]
    fn cache_path_preserves_source_segments() {
        assert_eq!(
            cache_path(Path::new("raw/hf"), "4.3.2/moc/chars/a.json"),
            Path::new("raw/hf/4.3.2/moc/chars/a.json")
        );
    }
}
