use std::{
    collections::BTreeMap,
    path::{Component, Path, PathBuf},
};

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::{atomic, MihoError, Result};

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct ArtifactManifestEntry {
    pub path: String,
    pub bytes: usize,
    pub sha256: String,
}

#[derive(Debug, Default)]
pub struct ArtifactBundle {
    files: BTreeMap<PathBuf, Vec<u8>>,
}

impl ArtifactBundle {
    pub fn add_csv<I, R, V>(
        &mut self,
        path: impl AsRef<Path>,
        headers: &[&str],
        rows: I,
    ) -> Result<()>
    where
        I: IntoIterator<Item = R>,
        R: IntoIterator<Item = V>,
        V: AsRef<str>,
    {
        let path = validate_relative(path.as_ref())?;
        let mut writer = csv::WriterBuilder::new()
            .terminator(csv::Terminator::CRLF)
            .from_writer(vec![0xEF, 0xBB, 0xBF]);
        writer.write_record(headers)?;
        for row in rows {
            let values = row
                .into_iter()
                .map(|value| value.as_ref().to_owned())
                .collect::<Vec<_>>();
            if values.len() != headers.len() {
                return Err(MihoError::CsvWidth {
                    expected: headers.len(),
                    actual: values.len(),
                });
            }
            writer.write_record(values)?;
        }
        let data = writer.into_inner().map_err(|error| MihoError::Write {
            path: path.clone(),
            source: error.into_error(),
        })?;
        self.files.insert(path, data);
        Ok(())
    }

    pub fn add_json<T: Serialize>(&mut self, path: impl AsRef<Path>, value: &T) -> Result<()> {
        let path = validate_relative(path.as_ref())?;
        let mut data = serde_json::to_vec_pretty(value).map_err(|source| MihoError::Json {
            path: path.clone(),
            source,
        })?;
        data.push(b'\n');
        self.files.insert(path, data);
        Ok(())
    }

    pub fn add_text(&mut self, path: impl AsRef<Path>, value: impl AsRef<str>) -> Result<()> {
        self.files.insert(
            validate_relative(path.as_ref())?,
            value.as_ref().as_bytes().to_vec(),
        );
        Ok(())
    }

    pub fn write_to(&self, root: &Path) -> Result<()> {
        for (path, data) in &self.files {
            atomic::write(&root.join(path), data)?;
        }
        Ok(())
    }

    pub fn manifest(&self) -> Vec<ArtifactManifestEntry> {
        self.files
            .iter()
            .map(|(path, data)| ArtifactManifestEntry {
                path: path.to_string_lossy().replace('\\', "/"),
                bytes: data.len(),
                sha256: format!("{:x}", Sha256::digest(data)),
            })
            .collect()
    }

    pub fn get(&self, path: impl AsRef<Path>) -> Option<&[u8]> {
        self.files.get(path.as_ref()).map(Vec::as_slice)
    }
}

pub fn csv_float(value: Option<f64>) -> String {
    let Some(value) = value else {
        return String::new();
    };
    let text = format!("{value:.6}");
    let trimmed = text.trim_end_matches('0').trim_end_matches('.');
    if trimmed == "-0" || trimmed == "0" {
        "0.0".to_owned()
    } else if !trimmed.contains('.') {
        format!("{trimmed}.0")
    } else {
        trimmed.to_owned()
    }
}

pub fn csv_number(value: Option<f64>) -> String {
    match value {
        Some(value) if value.fract() == 0.0 => format!("{value:.0}"),
        _ => csv_float(value),
    }
}

fn validate_relative(path: &Path) -> Result<PathBuf> {
    if path.as_os_str().is_empty()
        || path.is_absolute()
        || path
            .components()
            .any(|part| !matches!(part, Component::Normal(_)))
    {
        return Err(MihoError::InvalidArtifactPath(path.display().to_string()));
    }
    Ok(path.to_path_buf())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn csv_keeps_headers_when_empty_and_has_stable_manifest() {
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_csv::<Vec<Vec<&str>>, Vec<&str>, &str>("tables/empty.csv", &["a", "b"], vec![])
            .unwrap();
        assert_eq!(
            bundle.get("tables/empty.csv"),
            Some(&b"\xEF\xBB\xBFa,b\r\n"[..])
        );
        let manifest = bundle.manifest();
        assert_eq!(manifest[0].path, "tables/empty.csv");
        assert_eq!(manifest[0].bytes, 8);
        assert_eq!(manifest[0].sha256.len(), 64);
    }

    #[test]
    fn rejects_traversal_and_wrong_csv_width() {
        let mut bundle = ArtifactBundle::default();
        assert!(matches!(
            bundle.add_text("../escape", "bad"),
            Err(MihoError::InvalidArtifactPath(_))
        ));
        assert!(matches!(
            bundle.add_csv("bad.csv", &["a", "b"], [["one"]]),
            Err(MihoError::CsvWidth {
                expected: 2,
                actual: 1
            })
        ));
    }

    #[test]
    fn float_cells_match_python_rounding_contract() {
        assert_eq!(csv_float(None), "");
        assert_eq!(csv_float(Some(12.3456789)), "12.345679");
        assert_eq!(csv_float(Some(12.0)), "12.0");
        assert_eq!(csv_float(Some(-0.0)), "0.0");
        assert_eq!(csv_number(Some(12.0)), "12");
        assert_eq!(csv_number(Some(12.5)), "12.5");
    }
}
