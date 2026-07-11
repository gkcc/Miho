use crate::hsr_sources::{OfficialName, HOYOWIKI_SOURCE};
use crate::normalize::{character_slug, character_slug_to_english};
use serde::{Deserialize, Serialize};
use std::collections::{btree_map::Entry, BTreeMap};

pub type NameCandidates = BTreeMap<String, (String, String)>;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct NameRow {
    pub character_slug: String,
    pub character_name_en: String,
    pub character_name_cn: String,
    pub source: String,
    pub needs_manual_check: String,
    pub aliases: String,
}

#[derive(Debug, Clone, Default)]
pub struct NameResolver {
    rows: BTreeMap<String, NameRow>,
}

impl NameResolver {
    pub fn new(rows: &[NameRow]) -> Self {
        Self {
            rows: rows
                .iter()
                .filter_map(|row| {
                    let slug = character_slug(&row.character_slug);
                    (!slug.is_empty()).then_some((slug, row.clone()))
                })
                .collect(),
        }
    }

    pub fn english(&self, raw_slug: &str, fallback: &str) -> String {
        let slug = character_slug(raw_slug);
        self.rows
            .get(&slug)
            .map(|row| row.character_name_en.as_str())
            .filter(|name| !name.is_empty())
            .or_else(|| (!fallback.is_empty()).then_some(fallback))
            .map(str::to_owned)
            .unwrap_or_else(|| character_slug_to_english(&slug))
    }

    pub fn chinese(&self, raw_slug: &str) -> String {
        self.rows
            .get(&character_slug(raw_slug))
            .map(|row| row.character_name_cn.clone())
            .unwrap_or_default()
    }
}

/// Add a candidate using the same first-source/first-nonempty-English rules as
/// the Python `NameMapBuilder`.
pub fn add_candidate(
    candidates: &mut NameCandidates,
    raw_slug: &str,
    english_name: &str,
    source: &str,
) {
    let slug = character_slug(raw_slug);
    if slug.is_empty() {
        return;
    }
    match candidates.entry(slug) {
        Entry::Vacant(entry) => {
            entry.insert((english_name.to_owned(), source.to_owned()));
        }
        Entry::Occupied(mut entry) => {
            if !english_name.is_empty() && entry.get().0.is_empty() {
                entry.get_mut().0 = english_name.to_owned();
            }
        }
    }
}

pub fn parse_seed_csv(bytes: &[u8]) -> csv::Result<BTreeMap<String, NameRow>> {
    let mut reader =
        csv::Reader::from_reader(bytes.strip_prefix(&[0xef, 0xbb, 0xbf]).unwrap_or(bytes));
    let mut out = BTreeMap::new();
    for raw in reader.deserialize::<BTreeMap<String, String>>() {
        let raw = raw?;
        let pick = |keys: &[&str]| {
            keys.iter()
                .find_map(|k| raw.get(*k).filter(|v| !v.is_empty()))
                .cloned()
                .unwrap_or_default()
        };
        let slug = character_slug(&pick(&[
            "character_slug",
            "slug",
            "character_name_en",
            "name_en",
        ]));
        if slug.is_empty() {
            continue;
        }
        let row = NameRow {
            character_slug: slug.clone(),
            character_name_en: {
                let v = pick(&["character_name_en", "name_en"]);
                if v.is_empty() {
                    character_slug_to_english(&slug)
                } else {
                    v
                }
            },
            character_name_cn: pick(&["character_name_cn", "name_cn", "cn"]),
            source: {
                let v = pick(&["source"]);
                if v.is_empty() {
                    "seed".into()
                } else {
                    v
                }
            },
            needs_manual_check: "0".into(),
            aliases: pick(&["aliases"]),
        };
        out.insert(slug.clone(), row.clone());
        for alias in row
            .aliases
            .split([';', ',', '|'])
            .map(character_slug)
            .filter(|v| !v.is_empty())
        {
            out.insert(alias, row.clone());
        }
    }
    Ok(out)
}
pub fn build_name_rows(
    candidates: &NameCandidates,
    seed: &BTreeMap<String, NameRow>,
    official: &BTreeMap<String, OfficialName>,
) -> (Vec<NameRow>, Vec<NameRow>) {
    let mut rows = vec![];
    for (raw, (english, source)) in candidates {
        let slug = character_slug(raw);
        if slug.is_empty() {
            continue;
        }
        let row = if let Some(v) = seed.get(&slug).filter(|v| !v.character_name_cn.is_empty()) {
            let mut v = v.clone();
            v.character_slug = slug.clone();
            if v.character_name_en.is_empty() {
                v.character_name_en = candidate_english(english, &slug);
            }
            v
        } else if let Some(v) = official
            .get(&slug)
            .filter(|v| !v.character_name_cn.is_empty())
        {
            NameRow {
                character_slug: slug.clone(),
                character_name_en: if v.character_name_en.is_empty() {
                    candidate_english(english, &slug)
                } else {
                    v.character_name_en.clone()
                },
                character_name_cn: v.character_name_cn.clone(),
                source: HOYOWIKI_SOURCE.into(),
                needs_manual_check: "0".into(),
                aliases: v.aliases.clone(),
            }
        } else {
            NameRow {
                character_slug: slug.clone(),
                character_name_en: candidate_english(english, &slug),
                character_name_cn: String::new(),
                source: if source.is_empty() {
                    "source".to_owned()
                } else {
                    source.clone()
                },
                needs_manual_check: "1".into(),
                aliases: String::new(),
            }
        };
        rows.push(row);
    }
    rows.sort_by(|a, b| a.character_slug.cmp(&b.character_slug));
    let unresolved = rows
        .iter()
        .filter(|v| v.needs_manual_check == "1")
        .cloned()
        .collect();
    (rows, unresolved)
}

pub fn chinese_name(
    seed: &BTreeMap<String, NameRow>,
    official: &BTreeMap<String, OfficialName>,
    raw_slug: &str,
) -> String {
    let slug = character_slug(raw_slug);
    if let Some(row) = seed
        .get(&slug)
        .filter(|row| !row.character_name_cn.is_empty())
    {
        return row.character_name_cn.clone();
    }
    official
        .get(&slug)
        .map(|row| row.character_name_cn.clone())
        .unwrap_or_default()
}

pub fn english_name(
    candidates: &NameCandidates,
    seed: &BTreeMap<String, NameRow>,
    official: &BTreeMap<String, OfficialName>,
    raw_slug: &str,
) -> String {
    let slug = character_slug(raw_slug);
    if slug.is_empty() {
        return String::new();
    }
    if let Some(row) = seed
        .get(&slug)
        .filter(|row| !row.character_name_en.is_empty())
    {
        return row.character_name_en.clone();
    }
    if let Some(row) = official
        .get(&slug)
        .filter(|row| !row.character_name_en.is_empty())
    {
        return row.character_name_en.clone();
    }
    if let Some((name, _)) = candidates.get(&slug).filter(|(name, _)| !name.is_empty()) {
        return name.clone();
    }
    character_slug_to_english(&slug)
}

fn candidate_english(english: &str, slug: &str) -> String {
    if english.is_empty() {
        character_slug_to_english(slug)
    } else {
        english.to_owned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn official(slug: &str, english: &str, chinese: &str) -> OfficialName {
        OfficialName {
            character_slug: slug.to_owned(),
            character_name_en: english.to_owned(),
            character_name_cn: chinese.to_owned(),
            aliases: String::new(),
        }
    }

    #[test]
    fn bom_seed_supports_legacy_headers_and_aliases() {
        let bytes = b"\xef\xbb\xbfslug,name_en,cn,source,aliases\nMarch 7th,March 7th,\xe4\xb8\x89\xe6\x9c\x88\xe4\xb8\x83,manual,March 7th Swordmaster|Evernight\n";
        let rows = parse_seed_csv(bytes).unwrap();
        assert_eq!(rows["march-7th"].character_name_cn, "三月七");
        assert_eq!(rows["march-7th-swordmaster"].character_slug, "march-7th");
        assert_eq!(rows["evernight"].source, "manual");
    }

    #[test]
    fn candidates_keep_first_source_and_first_nonempty_english_name() {
        let mut candidates = NameCandidates::new();
        add_candidate(&mut candidates, "March 7th", "", "first");
        add_candidate(&mut candidates, "march-7th", "March 7th", "second");
        add_candidate(&mut candidates, "March. 7th", "Ignored", "third");
        assert_eq!(
            candidates["march-7th"],
            ("March 7th".to_owned(), "first".to_owned())
        );
    }

    #[test]
    fn build_and_resolve_follow_seed_official_candidate_precedence() {
        let mut candidates = NameCandidates::new();
        add_candidate(&mut candidates, "seeded", "Candidate Seeded", "hf");
        add_candidate(&mut candidates, "official", "Candidate Official", "hf");
        add_candidate(&mut candidates, "unresolved", "", "");

        let seed = BTreeMap::from([
            (
                "seeded".to_owned(),
                NameRow {
                    character_slug: "seeded".to_owned(),
                    character_name_en: "Seed Name".to_owned(),
                    character_name_cn: "种子名".to_owned(),
                    source: "seed".to_owned(),
                    needs_manual_check: "0".to_owned(),
                    aliases: String::new(),
                },
            ),
            (
                "official".to_owned(),
                NameRow {
                    character_slug: "official".to_owned(),
                    character_name_en: "Ignored Seed".to_owned(),
                    character_name_cn: String::new(),
                    source: "seed".to_owned(),
                    needs_manual_check: "0".to_owned(),
                    aliases: String::new(),
                },
            ),
        ]);
        let official = BTreeMap::from([
            (
                "seeded".to_owned(),
                official("seeded", "Official Seeded", "官方种子"),
            ),
            (
                "official".to_owned(),
                official("official", "Official Name", "官方名"),
            ),
        ]);
        let (rows, unresolved) = build_name_rows(&candidates, &seed, &official);
        let by_slug = rows
            .iter()
            .map(|row| (row.character_slug.as_str(), row))
            .collect::<BTreeMap<_, _>>();
        assert_eq!(by_slug["seeded"].character_name_cn, "种子名");
        assert_eq!(by_slug["official"].character_name_cn, "官方名");
        assert_eq!(by_slug["official"].source, HOYOWIKI_SOURCE);
        assert_eq!(by_slug["unresolved"].character_name_en, "Unresolved");
        assert_eq!(by_slug["unresolved"].source, "source");
        assert_eq!(unresolved.len(), 1);
        let resolver = NameResolver::new(&rows);
        assert_eq!(resolver.english("official", "fallback"), "Official Name");
        assert_eq!(resolver.chinese("official"), "官方名");
        assert_eq!(resolver.english("missing", "Fallback"), "Fallback");
        assert_eq!(chinese_name(&seed, &official, "seeded"), "种子名");
        assert_eq!(
            english_name(&candidates, &seed, &official, "official"),
            "Ignored Seed"
        );
        assert_eq!(
            english_name(&candidates, &seed, &official, "unresolved"),
            "Unresolved"
        );
    }
}
