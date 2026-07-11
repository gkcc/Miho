use crate::hsr_sources::{ChangelogRow, TierRow};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

pub fn merge_tier_history(existing: Vec<TierRow>, current: Vec<TierRow>) -> Vec<TierRow> {
    let mut positions = BTreeMap::new();
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
    rows.sort_by_key(|r| {
        (
            r.tier_updated_date.clone(),
            r.tier_mode.clone(),
            r.role_group.clone(),
            r.tier.clone(),
            r.character_slug.clone(),
        )
    });
    rows
}
pub fn merge_changelog_history(
    existing: Vec<ChangelogRow>,
    current: Vec<ChangelogRow>,
) -> Vec<ChangelogRow> {
    let mut positions = BTreeMap::new();
    let mut rows = Vec::new();
    for row in existing.into_iter().chain(current) {
        // Python hashes the text only to form a compact key. The actual
        // compatibility rule is date + exact text, with replacement retaining
        // the first insertion position.
        let key = (row.changelog_date.clone(), row.text.clone());
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UsagePoint {
    pub mode: String,
    pub sub_mode: String,
    pub character_slug: String,
    pub collect_date: String,
    pub phase_ver: String,
    pub phase_name: String,
    pub app_rate: f64,
    pub avg_round: Option<f64>,
    pub quality_flag: String,
}
#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct TrendRow {
    pub tier_snapshot_id: String,
    pub tier_updated_date: String,
    pub tier_mode: String,
    pub tier_mode_cn: String,
    pub character_slug: String,
    pub character_name_en: String,
    pub character_name_cn: String,
    pub prydwen_role: String,
    pub role_group: String,
    pub role_group_cn: String,
    pub tier: String,
    pub rating: Option<i64>,
    pub tags: serde_json::Value,
    pub marks: serde_json::Value,
    pub collect_date: String,
    pub phase_ver: String,
    pub phase_name: String,
    pub app_rate: f64,
    pub avg_round: Option<f64>,
    pub quality_flag: String,
    pub icon_url: String,
}
pub fn build_tier_usage_trend(tiers: &[TierRow], usage: &[UsagePoint]) -> Vec<TrendRow> {
    let mut out = vec![];
    for t in tiers
        .iter()
        .filter(|t| matches!(t.tier.as_str(), "T0" | "T0.5" | "T1" | "T1.5" | "T2"))
    {
        let mut points = usage
            .iter()
            .filter(|u| {
                matches!(u.sub_mode.as_str(), "all" | "all_bosses")
                    && u.mode == t.tier_mode
                    && u.character_slug == t.character_slug
            })
            .collect::<Vec<_>>();
        points.sort_by_key(|u| &u.collect_date);
        for u in points {
            out.push(TrendRow {
                tier_snapshot_id: t.tier_snapshot_id.clone(),
                tier_updated_date: t.tier_updated_date.clone(),
                tier_mode: t.tier_mode.clone(),
                tier_mode_cn: t.tier_mode_cn.clone(),
                character_slug: t.character_slug.clone(),
                character_name_en: t.character_name_en.clone(),
                character_name_cn: t.character_name_cn.clone(),
                prydwen_role: t.prydwen_role.clone(),
                role_group: t.role_group.clone(),
                role_group_cn: t.role_group_cn.clone(),
                tier: t.tier.clone(),
                rating: t.rating,
                tags: t.tags.clone(),
                marks: t.marks.clone(),
                collect_date: u.collect_date.clone(),
                phase_ver: u.phase_ver.clone(),
                phase_name: u.phase_name.clone(),
                app_rate: u.app_rate,
                avg_round: u.avg_round,
                quality_flag: u.quality_flag.clone(),
                icon_url: t.icon_url.clone(),
            });
        }
    }
    out
}

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
pub struct TierUsageChart {
    pub tier_mode: String,
    pub tier_mode_cn: String,
    pub role_group: String,
    pub role_group_cn: String,
    pub filename: String,
    pub series_count: usize,
    pub point_count: usize,
    pub svg: String,
}

/// Render the chart payloads without performing filesystem I/O.
///
/// The export adapter owns path resolution and atomic writes. `filename`
/// matches the Python basename and `svg` is the exact file payload to write.
pub fn render_tier_usage_charts(trend_rows: &[TrendRow]) -> Vec<TierUsageChart> {
    let mut output = Vec::new();
    for (mode, mode_cn) in [("moc", "混沌回忆"), ("pf", "虚构叙事"), ("as", "末日幻影")]
    {
        for (role_group, role_group_cn) in [
            ("main_dps", "主C"),
            ("sub_dps", "副C"),
            ("support", "辅助"),
            ("sustain", "生存位"),
        ] {
            let rows = trend_rows
                .iter()
                .filter(|row| row.tier_mode == mode && row.role_group == role_group)
                .collect::<Vec<_>>();
            if rows.is_empty() {
                continue;
            }
            output.push(TierUsageChart {
                tier_mode: mode.to_owned(),
                tier_mode_cn: mode_cn.to_owned(),
                role_group: role_group.to_owned(),
                role_group_cn: role_group_cn.to_owned(),
                filename: format!("{mode}_{role_group}_t0_t2_usage.svg"),
                series_count: rows
                    .iter()
                    .map(|row| row.character_slug.as_str())
                    .collect::<BTreeSet<_>>()
                    .len(),
                point_count: rows.len(),
                svg: render_svg_chart(&rows),
            });
        }
    }
    output
}

fn render_svg_chart(rows: &[&TrendRow]) -> String {
    let dates = rows
        .iter()
        .filter_map(|row| (!row.collect_date.is_empty()).then_some(row.collect_date.as_str()))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let mut series: BTreeMap<&str, Vec<&TrendRow>> = BTreeMap::new();
    let mut meta: BTreeMap<&str, &TrendRow> = BTreeMap::new();
    for row in rows {
        series
            .entry(row.character_slug.as_str())
            .or_default()
            .push(row);
        meta.insert(row.character_slug.as_str(), row);
    }
    let mut ordered_slugs = series.keys().copied().collect::<Vec<_>>();
    ordered_slugs.sort_by(|a, b| {
        let a_rate = series[a].last().map(|row| row.app_rate).unwrap_or(0.0);
        let b_rate = series[b].last().map(|row| row.app_rate).unwrap_or(0.0);
        b_rate
            .total_cmp(&a_rate)
            .then_with(|| meta[a].tier.cmp(&meta[b].tier))
            .then_with(|| a.cmp(b))
    });

    let max_value = rows.iter().map(|row| row.app_rate).fold(10.0_f64, f64::max);
    let max_value = (max_value * 1.12).min(100.0);
    let width = 1180;
    let legend_width = 330;
    let chart_left = 74;
    let chart_top = 70;
    let chart_width = width - legend_width - chart_left - 30;
    let chart_height = 360;
    let height = 520
        .max(chart_top + chart_height + 70)
        .max(110 + 22 * ordered_slugs.len());
    let colors = [
        "#2563eb", "#dc2626", "#16a34a", "#9333ea", "#ea580c", "#0891b2", "#be123c", "#4f46e5",
        "#65a30d", "#a16207", "#0f766e", "#7c3aed",
    ];
    let mode_cn = rows[0].tier_mode_cn.as_str();
    let role_cn = rows[0].role_group_cn.as_str();
    let title = format!("Prydwen T0-T2 {role_cn} - {mode_cn} 近半年出场率");
    let x = |date: &str| {
        if dates.len() <= 1 {
            chart_left as f64 + chart_width as f64 / 2.0
        } else {
            let index = dates
                .iter()
                .position(|candidate| *candidate == date)
                .unwrap_or(0);
            chart_left as f64 + chart_width as f64 * index as f64 / (dates.len() - 1) as f64
        }
    };
    let y = |value: f64| {
        chart_top as f64 + chart_height as f64 - chart_height as f64 * value / max_value
    };

    let mut parts = vec![
        format!(
            r#"<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">"#
        ),
        r##"<rect width="100%" height="100%" fill="#ffffff"/>"##.to_owned(),
        format!(
            r##"<text x="{chart_left}" y="34" font-size="24" font-weight="700" fill="#111827">{}</text>"##,
            escape_html(&title)
        ),
        format!(
            r##"<text x="{chart_left}" y="56" font-size="13" fill="#6b7280">T档来自 Prydwen 当前榜；出场率来自本地 MocStats long table，数值单位为 %。</text>"##
        ),
    ];
    for tick in 0..6 {
        let value = max_value * tick as f64 / 5.0;
        let yy = y(value);
        parts.push(format!(
            r##"<line x1="{chart_left}" y1="{yy:.1}" x2="{}" y2="{yy:.1}" stroke="#e5e7eb"/>"##,
            chart_left + chart_width
        ));
        parts.push(format!(
            r##"<text x="{}" y="{:.1}" text-anchor="end" font-size="11" fill="#6b7280">{value:.0}</text>"##,
            chart_left - 10,
            yy + 4.0
        ));
    }
    parts.push(format!(
        r##"<line x1="{chart_left}" y1="{chart_top}" x2="{chart_left}" y2="{}" stroke="#374151"/>"##,
        chart_top + chart_height
    ));
    parts.push(format!(
        r##"<line x1="{chart_left}" y1="{}" x2="{}" y2="{}" stroke="#374151"/>"##,
        chart_top + chart_height,
        chart_left + chart_width,
        chart_top + chart_height
    ));
    for date in &dates {
        let xx = x(date);
        parts.push(format!(
            r##"<text x="{xx:.1}" y="{}" text-anchor="middle" font-size="11" fill="#374151">{}</text>"##,
            chart_top + chart_height + 22,
            escape_html(date.get(5..).unwrap_or_default())
        ));
    }

    for (index, slug) in ordered_slugs.iter().enumerate() {
        let color = colors[index % colors.len()];
        let row_by_date = series[slug]
            .iter()
            .map(|row| (row.collect_date.as_str(), *row))
            .collect::<BTreeMap<_, _>>();
        let points = dates
            .iter()
            .filter_map(|date| row_by_date.get(date).map(|row| (x(date), y(row.app_rate))))
            .collect::<Vec<_>>();
        let point_text = points
            .iter()
            .map(|(xx, yy)| format!("{xx:.1},{yy:.1}"))
            .collect::<Vec<_>>()
            .join(" ");
        parts.push(format!(
            r#"<polyline points="{point_text}" fill="none" stroke="{color}" stroke-width="2.2"/>"#
        ));
        for (xx, yy) in points {
            parts.push(format!(
                r#"<circle cx="{xx:.1}" cy="{yy:.1}" r="2.8" fill="{color}"/>"#
            ));
        }
        let legend_y = 86 + index * 22;
        let row = meta[slug];
        let name = if row.character_name_cn.is_empty() {
            *slug
        } else {
            row.character_name_cn.as_str()
        };
        let label = format!("{name} {}", row.tier);
        parts.push(format!(
            r#"<line x1="{}" y1="{}" x2="{}" y2="{}" stroke="{color}" stroke-width="3"/>"#,
            chart_left + chart_width + 36,
            legend_y - 4,
            chart_left + chart_width + 58,
            legend_y - 4
        ));
        parts.push(format!(
            r##"<text x="{}" y="{legend_y}" font-size="12" fill="#111827">{}</text>"##,
            chart_left + chart_width + 66,
            escape_html(&label)
        ));
    }
    parts.push("</svg>".to_owned());
    parts.join("\n")
}

fn escape_html(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#x27;")
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn tier(snapshot: &str, tier: &str) -> TierRow {
        TierRow {
            tier_snapshot_id: snapshot.to_owned(),
            fetched_at: "old".to_owned(),
            tier_updated_at: "06/Jan/2026".to_owned(),
            tier_updated_date: "2026-01-06".to_owned(),
            tier_mode: "moc".to_owned(),
            tier_mode_cn: "混沌回忆".to_owned(),
            character_slug: "march-7th".to_owned(),
            character_name_en: "March 7th".to_owned(),
            character_name_cn: "三月七".to_owned(),
            prydwen_category: "Specialist".to_owned(),
            prydwen_role: "Support DPS".to_owned(),
            role_group: "sub_dps".to_owned(),
            role_group_cn: "副C".to_owned(),
            tier: tier.to_owned(),
            rating: Some(10),
            special_rating: json!("E6"),
            tags: json!("FUA"),
            marks: json!(""),
            is_new: json!(""),
            default_role: String::new(),
            element: "Ice".to_owned(),
            path: "Preservation".to_owned(),
            rarity: "4".to_owned(),
            icon_url: "march.png".to_owned(),
            source_url: "fixture".to_owned(),
        }
    }

    #[test]
    fn history_merges_replace_in_place_before_stable_sort() {
        let first = tier("z-snapshot", "T0.5");
        let second = tier("a-snapshot", "T0.5");
        let mut replacement = first.clone();
        replacement.fetched_at = "new".to_owned();
        let merged = merge_tier_history(vec![first, second], vec![replacement]);
        assert_eq!(merged[0].tier_snapshot_id, "z-snapshot");
        assert_eq!(merged[0].fetched_at, "new");
        assert_eq!(merged[1].tier_snapshot_id, "a-snapshot");

        let old_a = ChangelogRow {
            changelog_date: "2026-01-06".to_owned(),
            source_url: "old".to_owned(),
            character_slugs: "a".to_owned(),
            text: "A".to_owned(),
        };
        let b = ChangelogRow {
            changelog_date: "2026-01-06".to_owned(),
            source_url: "b".to_owned(),
            character_slugs: "b".to_owned(),
            text: "B".to_owned(),
        };
        let mut new_a = old_a.clone();
        new_a.source_url = "new".to_owned();
        let merged = merge_changelog_history(vec![old_a, b], vec![new_a]);
        assert_eq!(merged[0].text, "A");
        assert_eq!(merged[0].source_url, "new");
        assert_eq!(merged[1].text, "B");
    }

    #[test]
    fn trend_keeps_t0_to_t2_all_scope_points_in_date_order() {
        let eligible = tier("snapshot", "T0.5");
        let excluded = tier("snapshot", "T3");
        let usage = vec![
            UsagePoint {
                mode: "moc".to_owned(),
                sub_mode: "all".to_owned(),
                character_slug: "march-7th".to_owned(),
                collect_date: "2026-02-01".to_owned(),
                phase_ver: "2".to_owned(),
                phase_name: "later".to_owned(),
                app_rate: 20.0,
                avg_round: Some(5.0),
                quality_flag: "ok".to_owned(),
            },
            UsagePoint {
                mode: "moc".to_owned(),
                sub_mode: "stage_1".to_owned(),
                character_slug: "march-7th".to_owned(),
                collect_date: "2026-01-15".to_owned(),
                phase_ver: "ignored".to_owned(),
                phase_name: "ignored".to_owned(),
                app_rate: 99.0,
                avg_round: None,
                quality_flag: "ok".to_owned(),
            },
            UsagePoint {
                mode: "moc".to_owned(),
                sub_mode: "all_bosses".to_owned(),
                character_slug: "march-7th".to_owned(),
                collect_date: "2026-01-01".to_owned(),
                phase_ver: "1".to_owned(),
                phase_name: "earlier".to_owned(),
                app_rate: 10.0,
                avg_round: None,
                quality_flag: "ok".to_owned(),
            },
        ];
        let rows = build_tier_usage_trend(&[eligible, excluded], &usage);
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].collect_date, "2026-01-01");
        assert_eq!(rows[1].collect_date, "2026-02-01");
    }

    #[test]
    fn chart_renderer_returns_python_compatible_metadata_and_svg() {
        let tiers = [tier("snapshot", "T0.5")];
        let usage = [UsagePoint {
            mode: "moc".to_owned(),
            sub_mode: "all".to_owned(),
            character_slug: "march-7th".to_owned(),
            collect_date: "2026-01-01".to_owned(),
            phase_ver: "1".to_owned(),
            phase_name: "phase".to_owned(),
            app_rate: 25.0,
            avg_round: Some(4.0),
            quality_flag: "ok".to_owned(),
        }];
        let trend = build_tier_usage_trend(&tiers, &usage);
        let charts = render_tier_usage_charts(&trend);
        assert_eq!(charts.len(), 1);
        let chart = &charts[0];
        assert_eq!(chart.filename, "moc_sub_dps_t0_t2_usage.svg");
        assert_eq!((chart.series_count, chart.point_count), (1, 1));
        assert!(chart
            .svg
            .contains("Prydwen T0-T2 副C - 混沌回忆 近半年出场率"));
        assert!(chart.svg.contains("三月七 T0.5"));
        assert!(chart
            .svg
            .starts_with("<svg xmlns=\"http://www.w3.org/2000/svg\""));
        assert!(chart.svg.ends_with("</svg>"));
    }
}
