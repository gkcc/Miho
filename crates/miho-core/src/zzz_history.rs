use std::collections::HashMap;

use serde::{Deserialize, Serialize};

pub use crate::zzz_prydwen::{ChangelogRow, TierRow as TierHistoryRow};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct UsageRow {
    pub mode: String,
    pub sub_mode: String,
    pub character_slug: String,
    pub collect_date: String,
    pub phase_ver: String,
    pub phase_name: String,
    pub app_rate: String,
    pub avg_score: String,
    pub quality_flag: String,
}

/// CSV-compatible projection of a complete Prydwen tier row joined to one
/// `sub_mode=all` usage row. Keep the tier fields flat and in Python's public
/// column order so callers cannot accidentally drop metadata while exporting.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TrendRow {
    pub tier_snapshot_id: String,
    pub fetched_at: String,
    pub tier_updated_at: String,
    pub tier_updated_date: String,
    pub tier_mode: String,
    pub tier_mode_cn: String,
    pub character_slug: String,
    pub character_name_en: String,
    pub character_name_cn: String,
    pub prydwen_category: String,
    pub prydwen_role: String,
    pub role_group: String,
    pub role_group_cn: String,
    pub tier: String,
    pub rating: String,
    pub tags: String,
    pub marks: String,
    pub is_new: String,
    pub element: String,
    pub element_cn: String,
    pub style: String,
    pub style_cn: String,
    pub faction: String,
    pub rarity: String,
    pub icon_url: String,
    pub source_url: String,
    pub collect_date: String,
    pub phase_ver: String,
    pub phase_name: String,
    pub app_rate: String,
    pub avg_score: String,
    pub quality_flag: String,
}

/// Merge using Python dict semantics: the last value for a key wins while the
/// key retains the insertion position of its first appearance. The final sort
/// is stable, so categories that share the documented sort key keep that
/// insertion order.
pub fn merge_tier_history(
    existing: Vec<TierHistoryRow>,
    current: Vec<TierHistoryRow>,
) -> Vec<TierHistoryRow> {
    let mut positions = HashMap::new();
    let mut rows = Vec::new();
    for row in existing.into_iter().chain(current) {
        let key = (
            row.tier_snapshot_id.clone(),
            row.tier_mode.clone(),
            row.character_slug.clone(),
            row.prydwen_category.clone(),
        );
        if let Some(index) = positions.get(&key).copied() {
            rows[index] = row;
        } else {
            positions.insert(key, rows.len());
            rows.push(row);
        }
    }
    rows.sort_by(|a, b| {
        a.tier_updated_date
            .cmp(&b.tier_updated_date)
            .then_with(|| a.tier_mode.cmp(&b.tier_mode))
            .then_with(|| a.character_slug.cmp(&b.character_slug))
    });
    rows
}

pub fn merge_changelog_history(
    existing: Vec<ChangelogRow>,
    current: Vec<ChangelogRow>,
) -> Vec<ChangelogRow> {
    let mut positions = HashMap::new();
    let mut rows = Vec::new();
    for row in existing.into_iter().chain(current) {
        let key = (row.changelog_date.clone(), sha1_hex(row.text.as_bytes()));
        if let Some(index) = positions.get(&key).copied() {
            rows[index] = row;
        } else {
            positions.insert(key, rows.len());
            rows.push(row);
        }
    }
    rows.sort_by(|a, b| b.changelog_date.cmp(&a.changelog_date));
    rows
}

/// Match Python's grouping order: tier rows remain the outer sequence and the
/// matching usage rows are stably ordered by collect date inside each tier.
pub fn build_usage_trend(tiers: &[TierHistoryRow], usage: &[UsageRow]) -> Vec<TrendRow> {
    let mut output = Vec::new();
    for tier in tiers {
        let mut matches = usage
            .iter()
            .filter(|row| {
                row.mode == tier.tier_mode
                    && row.character_slug == tier.character_slug
                    && row.sub_mode == "all"
            })
            .collect::<Vec<_>>();
        matches.sort_by_key(|row| &row.collect_date);
        output.extend(matches.into_iter().map(|row| trend_row(tier, row)));
    }
    output
}

fn trend_row(tier: &TierHistoryRow, usage: &UsageRow) -> TrendRow {
    TrendRow {
        tier_snapshot_id: tier.tier_snapshot_id.clone(),
        fetched_at: tier.fetched_at.clone(),
        tier_updated_at: tier.tier_updated_at.clone(),
        tier_updated_date: tier.tier_updated_date.clone(),
        tier_mode: tier.tier_mode.clone(),
        tier_mode_cn: tier.tier_mode_cn.clone(),
        character_slug: tier.character_slug.clone(),
        character_name_en: tier.character_name_en.clone(),
        character_name_cn: tier.character_name_cn.clone(),
        prydwen_category: tier.prydwen_category.clone(),
        prydwen_role: tier.prydwen_role.clone(),
        role_group: tier.role_group.clone(),
        role_group_cn: tier.role_group_cn.clone(),
        tier: tier.tier.clone(),
        rating: tier.rating.clone(),
        tags: tier.tags.clone(),
        marks: tier.marks.clone(),
        is_new: tier.is_new.clone(),
        element: tier.element.clone(),
        element_cn: tier.element_cn.clone(),
        style: tier.style.clone(),
        style_cn: tier.style_cn.clone(),
        faction: tier.faction.clone(),
        rarity: tier.rarity.clone(),
        icon_url: tier.icon_url.clone(),
        source_url: tier.source_url.clone(),
        collect_date: usage.collect_date.clone(),
        phase_ver: usage.phase_ver.clone(),
        phase_name: usage.phase_name.clone(),
        app_rate: usage.app_rate.clone(),
        avg_score: usage.avg_score.clone(),
        quality_flag: usage.quality_flag.clone(),
    }
}

fn sha1_hex(data: &[u8]) -> String {
    let mut h = [
        0x67452301u32,
        0xefcdab89,
        0x98badcfe,
        0x10325476,
        0xc3d2e1f0,
    ];
    let mut msg = data.to_vec();
    let bits = (msg.len() as u64) * 8;
    msg.push(0x80);
    while msg.len() % 64 != 56 {
        msg.push(0)
    }
    msg.extend_from_slice(&bits.to_be_bytes());
    for chunk in msg.chunks(64) {
        let mut w = [0u32; 80];
        for (i, b) in chunk.chunks(4).enumerate() {
            w[i] = u32::from_be_bytes([b[0], b[1], b[2], b[3]])
        }
        for i in 16..80 {
            w[i] = (w[i - 3] ^ w[i - 8] ^ w[i - 14] ^ w[i - 16]).rotate_left(1)
        }
        let (mut a, mut b, mut c, mut d, mut e) = (h[0], h[1], h[2], h[3], h[4]);
        for (i, &x) in w.iter().enumerate() {
            let (f, k) = match i {
                0..=19 => ((b & c) | (!b & d), 0x5a827999),
                20..=39 => (b ^ c ^ d, 0x6ed9eba1),
                40..=59 => ((b & c) | (b & d) | (c & d), 0x8f1bbcdc),
                _ => (b ^ c ^ d, 0xca62c1d6),
            };
            let t = a
                .rotate_left(5)
                .wrapping_add(f)
                .wrapping_add(e)
                .wrapping_add(k)
                .wrapping_add(x);
            e = d;
            d = c;
            c = b.rotate_left(30);
            b = a;
            a = t
        }
        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e)
    }
    h.iter().map(|value| format!("{value:08x}")).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Deserialize)]
    struct Fixture {
        existing_tier: Vec<TierHistoryRow>,
        current_tier: Vec<TierHistoryRow>,
        changelog: Vec<ChangelogRow>,
        usage: Vec<UsageRow>,
    }

    #[test]
    fn fixture_matches_python_merge_and_complete_trend_contract() {
        let fixture: Fixture = serde_json::from_str(include_str!(
            "../../../tests/fixtures/zzz_history_minimal.json"
        ))
        .unwrap();
        let tiers = merge_tier_history(fixture.existing_tier, fixture.current_tier);
        assert_eq!(tiers.len(), 2);
        assert_eq!(tiers[0].tier, "T0.5");
        assert_eq!(tiers[0].character_name_cn, "爱丽丝");
        // Python's stable sort keeps CritDPS before Support for equal sort keys.
        assert_eq!(tiers[1].prydwen_category, "Support");

        let changelog = merge_changelog_history(Vec::new(), fixture.changelog);
        assert_eq!(changelog.len(), 1);
        assert_eq!(
            sha1_hex(changelog[0].text.as_bytes()),
            "c516faa085d41bb9e6c8b0afdd8979341d56db2a"
        );
        assert_eq!(
            sha1_hex("角色增强".as_bytes()),
            "4d533a7c6b4beab8943726c11195664a4a74b951"
        );

        let trend = build_usage_trend(&tiers, &fixture.usage);
        assert_eq!(trend.len(), 4);
        assert_eq!(trend[0].collect_date, "2026-01-01");
        assert_eq!(trend[1].collect_date, "2026-02-01");
        // The second tier begins a new group instead of a global date reorder.
        assert_eq!(trend[2].prydwen_category, "Support");
        assert_eq!(trend[2].collect_date, "2026-01-01");
        assert_eq!(trend[0].fetched_at, "2026-07-12T00:00:00");
    }
}
