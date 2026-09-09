//! Complete the official release timeline for every roster provenance in one place.
//! Banner status and a transient `isNew` badge are not release dates.
use std::collections::BTreeMap;

use serde_json::Value;

use crate::{
    hsr_sources::{decode_prydwen_payload, extract_characters},
    output::ArtifactBundle,
    visualizer::{strict_utf8, VisualizerContext},
    Result,
};

type Version = Vec<u32>;

fn version(value: &str) -> Option<Version> {
    let parts = value.trim().split('.').collect::<Vec<_>>();
    if parts.len() < 2
        || parts
            .iter()
            .any(|part| part.is_empty() || !part.bytes().all(|b| b.is_ascii_digit()))
    {
        return None;
    }
    parts.into_iter().map(|part| part.parse().ok()).collect()
}

fn text<'a>(row: &'a Value, key: &str) -> &'a str {
    row.get(key).and_then(Value::as_str).unwrap_or("")
}

/// Only insert rows lacking a catalog position. Never reorder catalog characters
/// because they are featured again, or interpret a source ID as a release date.
pub(crate) fn complete_release_order(
    roster: &mut Vec<Value>,
    bundle: &ArtifactBundle,
    context: &VisualizerContext,
    canonical: fn(&str) -> String,
) -> Result<()> {
    let path = "raw/prydwen_tier/tier-list_latest.html";
    let characters = match bundle.get(path).or_else(|| context.sidecar(path)) {
        Some(bytes) => extract_characters(&decode_prydwen_payload(strict_utf8(bytes, path)?)),
        None => vec![],
    };
    let metadata = characters
        .iter()
        .map(|row| (canonical(text(row, "slug")), row))
        .collect::<BTreeMap<_, _>>();
    for row in roster.iter_mut() {
        if let Some(meta) = metadata.get(&canonical(text(row, "character_slug"))) {
            let release = ["releasePatch", "upcomingVersion"]
                .into_iter()
                .map(|key| text(meta, key))
                .find(|value| version(value).is_some());
            if let Some(release) = release {
                row["release_version"] = release.into();
            }
            // An explicit released flag overrides a stale upcoming flag.
            let released = meta.get("isReleased").and_then(Value::as_bool);
            let upcoming = meta.get("upcoming").and_then(Value::as_bool);
            if released.is_some() || upcoming.is_some() {
                row["release_upcoming"] = (released != Some(true)
                    && (released == Some(false) || upcoming == Some(true)))
                .into();
            }
        }
    }

    let (mut catalog, mut missing): (Vec<_>, Vec<_>) = roster.drain(..).partition(|row| {
        row.get("catalog_release_order")
            .and_then(Value::as_f64)
            .is_some()
    });
    catalog.sort_by(|a, b| {
        a["catalog_release_order"]
            .as_f64()
            .unwrap()
            .total_cmp(&b["catalog_release_order"].as_f64().unwrap())
            .then_with(|| text(a, "character_slug").cmp(text(b, "character_slug")))
    });
    // Stable within a patch: without a release date, do not invent half-patch order.
    missing.sort_by_key(|row| std::cmp::Reverse(version(text(row, "release_version"))));
    let mut slots = vec![Vec::new(); catalog.len() + 1];
    let mut future = Vec::new();
    for mut row in missing {
        let satellite = text(&row, "banner_statuses")
            .split(';')
            .any(|value| value == "satellite");
        let upcoming = row.get("release_upcoming").and_then(Value::as_bool);
        if upcoming == Some(true) || (upcoming.is_none() && satellite) {
            row["release_order_source"] = "unreleased".into();
            future.push(row);
            continue;
        }
        let release = version(text(&row, "release_version"));
        let position = release.as_ref().and_then(|release| {
            // Equal-version peers stay together. Otherwise insert before the
            // first older catalog anchor. With no comparable anchor, stay unknown.
            catalog
                .iter()
                .rposition(|anchor| {
                    version(text(anchor, "release_version")).as_ref() == Some(release)
                })
                .map(|index| index + 1)
                .or_else(|| {
                    catalog.iter().position(|anchor| {
                        version(text(anchor, "release_version"))
                            .is_some_and(|value| value < *release)
                    })
                })
        });
        row["release_order_source"] = if position.is_some() {
            "prydwen_version"
        } else {
            "unknown"
        }
        .into();
        slots[position.unwrap_or(catalog.len())].push(row);
    }
    for (index, mut row) in catalog.into_iter().enumerate() {
        future.append(&mut slots[index]);
        row["release_order_source"] = "official_catalog".into();
        future.push(row);
    }
    future.append(slots.last_mut().unwrap());
    for (index, row) in future.iter_mut().enumerate() {
        row["release_order"] = index.into();
    }
    *roster = future;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn visualizer_release_order_uses_versions_without_new_badges_or_rerun_priority() {
        let context = VisualizerContext::new(chrono::NaiveDate::from_ymd_opt(2026, 9, 10).unwrap());
        let mut bundle = ArtifactBundle::default();
        let mut characters = json!([
            {"slug":"latest", "upcomingVersion":"4.9", "upcoming":false},
            {"slug":"new", "upcomingVersion":"4.10", "upcoming":false, "isNew":true},
            {"slug":"same-patch", "upcomingVersion":"4.9", "upcoming":false},
            {"slug":"old-rerun", "upcomingVersion":"1.0", "upcoming":false},
            {"slug":"future", "upcomingVersion":"5.x", "upcoming":true},
            {"slug":"unknown", "upcomingVersion":"$undefined"}
        ]);
        let original = vec![
            json!({"character_slug":"latest","catalog_release_order":0}),
            json!({"character_slug":"legacy","catalog_release_order":5,"banner_statuses":"next"}),
            json!({"character_slug":"new","release_order":9999}),
            json!({"character_slug":"same-patch","source":"banner_plan","banner_statuses":"previous"}),
            json!({"character_slug":"old-rerun","banner_statuses":"next"}),
            json!({"character_slug":"future"}),
            json!({"character_slug":"unknown"}),
        ];
        let mut result = vec![];
        for new_badge in [true, false] {
            characters[1]["isNew"] = new_badge.into();
            bundle
                .add_text(
                    "raw/prydwen_tier/tier-list_latest.html",
                    json!({"characters":characters}).to_string(),
                )
                .unwrap();
            let mut roster = original.clone();
            complete_release_order(
                &mut roster,
                &bundle,
                &context,
                crate::normalize::character_slug,
            )
            .unwrap();
            assert_eq!(
                roster
                    .iter()
                    .map(|row| text(row, "character_slug"))
                    .collect::<Vec<_>>(),
                [
                    "future",
                    "new",
                    "latest",
                    "same-patch",
                    "legacy",
                    "old-rerun",
                    "unknown"
                ]
            );
            if !result.is_empty() {
                assert_eq!(roster, result);
            }
            result = roster;
        }
        let before = result.clone();
        complete_release_order(
            &mut result,
            &bundle,
            &context,
            crate::normalize::character_slug,
        )
        .unwrap();
        assert_eq!(before, result);
        // Official catalog catches up; old catalog rows retain their order.
        result[1]["catalog_release_order"] = 0.into();
        result[2]["catalog_release_order"] = 1.into();
        complete_release_order(
            &mut result,
            &bundle,
            &context,
            crate::normalize::character_slug,
        )
        .unwrap();
        assert_eq!(result[1]["character_slug"], "new");
        assert_eq!(result[1]["release_order_source"], "official_catalog");
        assert!(version("4.x").is_none());
        assert!(version("4..1").is_none());
    }
}
