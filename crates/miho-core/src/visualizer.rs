use std::{
    collections::BTreeMap,
    path::{Component, Path},
};

use chrono::NaiveDate;
use serde::Serialize;

use crate::{output::ArtifactBundle, MihoError, Result};

pub const VISUALIZER_CONTEXT_SCHEMA_VERSION: u16 = 1;

const HSR_INDEX_HTML: &str = include_str!("../assets/visualizer/hsr/index.html");
const HSR_STYLES_CSS: &str = include_str!("../assets/visualizer/hsr/styles.css");
const HSR_APP_JS: &str = include_str!("../assets/visualizer/hsr/app.js");

#[derive(Debug, Clone)]
pub struct VisualizerContext {
    pub schema_version: u16,
    pub local_date: NaiveDate,
    sidecars: BTreeMap<String, Vec<u8>>,
    avatar_webp: BTreeMap<String, Vec<u8>>,
}

impl VisualizerContext {
    pub fn new(local_date: NaiveDate) -> Self {
        Self {
            schema_version: VISUALIZER_CONTEXT_SCHEMA_VERSION,
            local_date,
            sidecars: BTreeMap::new(),
            avatar_webp: BTreeMap::new(),
        }
    }

    pub fn validate(&self) -> Result<()> {
        if self.schema_version != VISUALIZER_CONTEXT_SCHEMA_VERSION {
            return Err(MihoError::Visualizer(format!(
                "visualizer context schema {} is not supported",
                self.schema_version
            )));
        }
        Ok(())
    }

    pub fn add_sidecar_bytes(
        &mut self,
        path: impl AsRef<Path>,
        value: impl Into<Vec<u8>>,
    ) -> Result<()> {
        let path = safe_relative_string(path.as_ref())?;
        self.sidecars.insert(path, value.into());
        Ok(())
    }

    pub fn add_sidecar_json<T: Serialize>(
        &mut self,
        path: impl AsRef<Path>,
        value: &T,
    ) -> Result<()> {
        let path = path.as_ref();
        let data = serde_json::to_vec(value).map_err(|source| MihoError::Json {
            path: path.to_path_buf(),
            source,
        })?;
        self.add_sidecar_bytes(path, data)
    }

    pub fn sidecar(&self, path: &str) -> Option<&[u8]> {
        self.sidecars.get(path).map(Vec::as_slice)
    }

    pub fn add_avatar_webp(&mut self, slug: &str, bytes: impl Into<Vec<u8>>) -> Result<()> {
        if slug.is_empty()
            || !slug
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
        {
            return Err(MihoError::Visualizer(format!(
                "unsafe avatar slug: {slug:?}"
            )));
        }
        let bytes = bytes.into();
        validate_webp(&bytes)?;
        self.avatar_webp.insert(slug.to_owned(), bytes);
        Ok(())
    }

    pub fn avatar_webp(&self, slug: &str) -> Option<&[u8]> {
        self.avatar_webp.get(slug).map(Vec::as_slice)
    }
}

pub fn attach_hsr_static_assets(bundle: &mut ArtifactBundle) -> Result<()> {
    bundle.add_text("visualizer/index.html", HSR_INDEX_HTML)?;
    bundle.add_text("visualizer/styles.css", HSR_STYLES_CSS)?;
    bundle.add_text("visualizer/app.js", HSR_APP_JS)?;
    Ok(())
}

pub fn attach_avatar_assets(
    bundle: &mut ArtifactBundle,
    context: &VisualizerContext,
) -> Result<()> {
    context.validate()?;
    for (slug, bytes) in &context.avatar_webp {
        bundle.add_bytes(
            format!("visualizer/assets/avatars/{slug}.webp"),
            bytes.clone(),
        )?;
    }
    Ok(())
}

pub fn local_avatar_url(context: &VisualizerContext, slug: &str) -> String {
    if context.avatar_webp(slug).is_some() {
        format!("./assets/avatars/{slug}.webp")
    } else {
        String::new()
    }
}

pub fn read_csv_rows(bundle: &ArtifactBundle, path: &str) -> Result<Vec<BTreeMap<String, String>>> {
    let bytes = bundle.get(path).ok_or_else(|| {
        MihoError::Visualizer(format!("required CSV artifact is missing: {path}"))
    })?;
    let mut reader = csv::ReaderBuilder::new().from_reader(bytes);
    let headers = reader
        .headers()?
        .iter()
        .enumerate()
        .map(|(index, value)| {
            if index == 0 {
                value.trim_start_matches('\u{feff}').to_owned()
            } else {
                value.to_owned()
            }
        })
        .collect::<Vec<_>>();
    reader
        .records()
        .map(|record| {
            let record = record?;
            Ok(headers
                .iter()
                .zip(record.iter())
                .map(|(key, value)| (key.to_owned(), value.to_owned()))
                .collect())
        })
        .collect()
}

pub fn compact_json<T: Serialize>(path: &str, value: &T) -> Result<Vec<u8>> {
    serde_json::to_vec(value).map_err(|source| MihoError::Json {
        path: path.into(),
        source,
    })
}

pub fn safe_link_url(value: &str) -> String {
    let text = value.trim();
    if text.is_empty()
        || text.contains('\\')
        || text.chars().any(|ch| ch.is_control())
        || text.starts_with('/')
    {
        return String::new();
    }
    if let Some((scheme, remainder)) = text.split_once(':') {
        if !matches!(scheme.to_ascii_lowercase().as_str(), "http" | "https")
            || !remainder.starts_with("//")
        {
            return String::new();
        }
        let authority = remainder[2..].split(['/', '?', '#']).next().unwrap_or("");
        if authority.is_empty() || authority.chars().any(char::is_whitespace) {
            return String::new();
        }
        return text.to_owned();
    }
    safe_relative_url(text)
}

pub fn safe_relative_url(value: &str) -> String {
    let text = value.trim();
    if text.is_empty()
        || text.starts_with('/')
        || text.contains('\\')
        || text.contains(':')
        || text.chars().any(|ch| ch.is_control())
    {
        return String::new();
    }
    let mut path = text.split(['?', '#']).next().unwrap_or("").to_owned();
    for _ in 0..3 {
        let decoded = percent_decode(&path);
        if decoded == path {
            break;
        }
        path = decoded;
    }
    if path.starts_with('/') || path.contains('\\') || path.split('/').any(|part| part == "..") {
        return String::new();
    }
    text.to_owned()
}

fn percent_decode(value: &str) -> String {
    let bytes = value.as_bytes();
    let mut output = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' && index + 2 < bytes.len() {
            let high = hex_value(bytes[index + 1]);
            let low = hex_value(bytes[index + 2]);
            if let (Some(high), Some(low)) = (high, low) {
                output.push((high << 4) | low);
                index += 3;
                continue;
            }
        }
        output.push(bytes[index]);
        index += 1;
    }
    String::from_utf8_lossy(&output).into_owned()
}

fn hex_value(value: u8) -> Option<u8> {
    match value {
        b'0'..=b'9' => Some(value - b'0'),
        b'a'..=b'f' => Some(value - b'a' + 10),
        b'A'..=b'F' => Some(value - b'A' + 10),
        _ => None,
    }
}

fn safe_relative_string(path: &Path) -> Result<String> {
    if path.as_os_str().is_empty()
        || path.is_absolute()
        || path
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
    {
        return Err(MihoError::Visualizer(format!(
            "unsafe visualizer context path: {}",
            path.display()
        )));
    }
    Ok(path.to_string_lossy().replace('\\', "/"))
}

fn validate_webp(bytes: &[u8]) -> Result<()> {
    let declared_size = bytes
        .get(4..8)
        .and_then(|value| value.try_into().ok())
        .map(u32::from_le_bytes)
        .map(|value| value as usize);
    if bytes.get(..4) != Some(b"RIFF")
        || bytes.get(8..12) != Some(b"WEBP")
        || declared_size != bytes.len().checked_sub(8)
    {
        return Err(MihoError::Visualizer(
            "avatar payload is not a complete WebP RIFF file".into(),
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use serde_json::Value;
    use sha2::{Digest, Sha256};

    use super::*;

    const AVATAR: &[u8] = &[
        82, 73, 70, 70, 30, 0, 0, 0, 87, 69, 66, 80, 86, 80, 56, 76, 17, 0, 0, 0, 47, 1, 64, 0, 0,
        7, 208, 177, 150, 116, 189, 255, 129, 136, 232, 127, 0, 0,
    ];

    fn normalized_hash(bytes: &[u8]) -> String {
        let text = String::from_utf8(bytes.to_vec()).unwrap();
        let normalized = text.replace("\r\n", "\n").replace('\r', "\n");
        format!("{:x}", Sha256::digest(normalized.as_bytes()))
    }

    #[test]
    fn context_rejects_traversal_bad_slugs_and_invalid_webp() {
        let mut context = VisualizerContext::new(NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        assert!(context.add_sidecar_bytes("../escape.json", b"{}").is_err());
        assert!(context.add_avatar_webp("../escape", AVATAR).is_err());
        assert!(context.add_avatar_webp("agent-alpha", b"not-webp").is_err());
    }

    #[test]
    fn hsr_static_assets_and_avatar_match_the_versioned_contract() {
        let contract: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/visualizer_contract/contract.json"
        ))
        .unwrap();
        let mut context = VisualizerContext::new(NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        context.add_avatar_webp("agent-alpha", AVATAR).unwrap();
        let mut bundle = ArtifactBundle::default();
        attach_hsr_static_assets(&mut bundle).unwrap();
        attach_avatar_assets(&mut bundle, &context).unwrap();

        for name in ["app.js", "index.html", "styles.css"] {
            let expected = contract["static_text_sha256"]["hsr"][name]
                .as_str()
                .unwrap();
            assert_eq!(
                normalized_hash(bundle.get(format!("visualizer/{name}")).unwrap()),
                expected
            );
        }
        let avatar = bundle
            .get("visualizer/assets/avatars/agent-alpha.webp")
            .unwrap();
        assert_eq!(
            format!("{:x}", Sha256::digest(avatar)),
            contract["binary_sha256"]["hsr"]["assets/avatars/agent-alpha.webp"]
                .as_str()
                .unwrap()
        );
        assert_eq!(
            local_avatar_url(&context, "agent-alpha"),
            "./assets/avatars/agent-alpha.webp"
        );
        assert_eq!(local_avatar_url(&context, "missing"), "");
    }

    #[test]
    fn shared_helpers_preserve_csv_strings_and_reject_active_urls() {
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_bytes("table.csv", b"\xef\xbb\xbfa,b\r\n1,2.0\r\n".to_vec())
            .unwrap();
        assert_eq!(
            read_csv_rows(&bundle, "table.csv").unwrap()[0],
            BTreeMap::from([("a".into(), "1".into()), ("b".into(), "2.0".into())])
        );
        for value in [
            "javascript:alert(1)",
            "data:text/html,owned",
            "file:///C:/secret",
            "../escape",
            "%252e%252e/escape",
            "\\\\server\\share",
            "/absolute",
        ] {
            assert_eq!(safe_relative_url(value), "");
            assert_eq!(safe_link_url(value), "");
        }
        assert_eq!(
            safe_relative_url("./assets/avatars/agent-alpha.webp"),
            "./assets/avatars/agent-alpha.webp"
        );
        assert_eq!(
            safe_link_url("https://invalid.example/source"),
            "https://invalid.example/source"
        );
    }

    #[test]
    fn visualizer_files_enter_the_refreshed_manifest_before_writeout() {
        let contract: Value = serde_json::from_str(include_str!(
            "../../../tests/fixtures/visualizer_contract/contract.json"
        ))
        .unwrap();
        let mut context = VisualizerContext::new(NaiveDate::from_ymd_opt(2026, 7, 12).unwrap());
        context.add_avatar_webp("agent-alpha", AVATAR).unwrap();
        let mut bundle = ArtifactBundle::default();
        attach_hsr_static_assets(&mut bundle).unwrap();
        attach_avatar_assets(&mut bundle, &context).unwrap();
        bundle
            .add_bytes("visualizer/data.json", b"{}".to_vec())
            .unwrap();
        bundle.refresh_manifest("artifact_manifest.json").unwrap();

        let manifest: Vec<crate::output::ArtifactManifestEntry> =
            serde_json::from_slice(bundle.get("artifact_manifest.json").unwrap()).unwrap();
        let actual = manifest
            .iter()
            .filter_map(|entry| entry.path.strip_prefix("visualizer/").map(str::to_owned))
            .collect::<Vec<_>>();
        let expected = contract["file_sets"]["hsr"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| value.as_str().unwrap().to_owned())
            .collect::<Vec<_>>();
        assert_eq!(actual, expected);
    }
}
