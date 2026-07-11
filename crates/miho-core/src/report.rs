use std::collections::{BTreeMap, BTreeSet};

use chrono::SecondsFormat;

use crate::{
    contract::{
        Diagnostic, DiagnosticSeverity, ExportContext, ExportRequestV1, ExportStats, Game, GameMode,
    },
    output::ArtifactBundle,
    Result,
};

pub fn finalize_export_bundle(
    bundle: &mut ArtifactBundle,
    request: &ExportRequestV1,
    context: &ExportContext,
    diagnostics: &[Diagnostic],
) -> Result<ExportStats> {
    let tables = ExportTables::read(bundle);
    let stats = tables.stats();
    let report = match request.game {
        Game::Hsr => render_hsr_report(request, context, diagnostics, &stats),
        Game::Zzz => render_zzz_report(request, context, diagnostics, &stats),
    };
    bundle.add_text("export_report.md", report)?;
    bundle.refresh_manifest("artifact_manifest.json")?;
    Ok(stats)
}

#[derive(Default)]
struct ExportTables {
    rows: BTreeMap<String, Vec<BTreeMap<String, String>>>,
}

impl ExportTables {
    fn read(bundle: &ArtifactBundle) -> Self {
        let paths = [
            "phase_index.csv",
            "character_usage_long.csv",
            "team_rank_raw.csv",
            "team_rank_dedup_ordered.csv",
            "team_rank_dedup_unordered.csv",
            "name_map.csv",
            "name_map_unresolved.csv",
            "prydwen_tier_current.csv",
            "prydwen_tier_history.csv",
            "prydwen_tier_changelog.csv",
            "prydwen_tier_usage_trend.csv",
            "prydwen_tier_charts.csv",
        ];
        let rows = paths
            .into_iter()
            .map(|path| (path.to_owned(), read_csv(bundle, path)))
            .collect();
        Self { rows }
    }

    fn table(&self, path: &str) -> &[BTreeMap<String, String>] {
        self.rows.get(path).map(Vec::as_slice).unwrap_or_default()
    }

    fn stats(&self) -> ExportStats {
        let phases = self.table("phase_index.csv");
        let characters = self.table("character_usage_long.csv");
        let names = self.table("name_map.csv");
        let mut snapshots = BTreeSet::new();
        let mut phases_by_mode = BTreeMap::new();
        for row in phases {
            if let Some(snapshot) = row.get("snapshot_id").filter(|value| !value.is_empty()) {
                snapshots.insert(snapshot.clone());
            }
            if let Some(mode) = row
                .get("mode")
                .and_then(|value| parse_mode_without_game(value))
            {
                *phases_by_mode.entry(mode).or_default() += 1;
            }
        }
        ExportStats {
            snapshots: snapshots.len(),
            phases: phases.len(),
            phases_by_mode,
            character_rows: characters.len(),
            team_rows: self.table("team_rank_raw.csv").len(),
            ordered_team_rows: self.table("team_rank_dedup_ordered.csv").len(),
            unordered_team_rows: self.table("team_rank_dedup_unordered.csv").len(),
            name_rows: names.len(),
            unresolved_names: self.table("name_map_unresolved.csv").len(),
            resolved_name_rows: names
                .iter()
                .filter(|row| {
                    row.get("needs_manual_check")
                        .is_some_and(|value| value == "0")
                })
                .count(),
            tier_rows: self.table("prydwen_tier_current.csv").len(),
            tier_history_rows: self.table("prydwen_tier_history.csv").len(),
            changelog_rows: self.table("prydwen_tier_changelog.csv").len(),
            trend_rows: self.table("prydwen_tier_usage_trend.csv").len(),
            chart_rows: self.table("prydwen_tier_charts.csv").len(),
            aa_split: characters.iter().any(|row| {
                row.get("mode").is_some_and(|value| value == "aa")
                    && row
                        .get("sub_mode")
                        .is_some_and(|value| matches!(value.as_str(), "knights" | "king_piece"))
            }),
        }
    }
}

fn read_csv(bundle: &ArtifactBundle, path: &str) -> Vec<BTreeMap<String, String>> {
    let Some(bytes) = bundle.get(path) else {
        return vec![];
    };
    let bytes = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(bytes);
    let mut reader = csv::ReaderBuilder::new().from_reader(bytes);
    let Ok(headers) = reader.headers().cloned() else {
        return vec![];
    };
    reader
        .records()
        .filter_map(std::result::Result::ok)
        .map(|record| {
            headers
                .iter()
                .zip(record.iter())
                .map(|(key, value)| (key.to_owned(), value.to_owned()))
                .collect()
        })
        .collect()
}

fn parse_mode_without_game(value: &str) -> Option<GameMode> {
    [Game::Hsr, Game::Zzz]
        .into_iter()
        .find_map(|game| GameMode::parse(game, value).ok())
}

fn render_hsr_report(
    request: &ExportRequestV1,
    context: &ExportContext,
    diagnostics: &[Diagnostic],
    stats: &ExportStats,
) -> String {
    let mut lines = vec![
        "# HSR Endgame Export Report".to_owned(),
        String::new(),
        format!("- 导出时间: {}", export_time(context)),
        format!(
            "- from_date / to_date: {} / {}",
            from_date(request),
            to_date(request)
        ),
        format!(
            "- 数据源: Hugging Face dataset `{}`; Prydwen visible page data when available",
            request.dataset.repo_id
        ),
        format!("- 成功读取的 snapshot 数: {}", stats.snapshots),
        String::new(),
        "## 各模式 snapshot 覆盖情况".to_owned(),
        String::new(),
    ];
    for mode in &request.modes {
        lines.push(format!(
            "- {} ({}): {}",
            hsr_mode_name(*mode),
            mode.code(),
            stats.phases_by_mode.get(mode).copied().unwrap_or_default()
        ));
    }
    lines.extend([
        String::new(),
        "## 表行数".to_owned(),
        String::new(),
        format!("- 角色表行数: {}", stats.character_rows),
        format!("- 队伍 raw 行数: {}", stats.team_rows),
        format!("- 队伍有序去重后行数: {}", stats.ordered_team_rows),
        format!("- 队伍无序去重后行数: {}", stats.unordered_team_rows),
        format!(
            "- raw -> 无序去重移除重复行数: {}",
            stats.team_rows.saturating_sub(stats.unordered_team_rows)
        ),
        format!("- 未解析角色数量: {}", stats.unresolved_names),
        format!("- 官方中文名补全数量: {}", stats.resolved_name_rows),
        "- 简洁视图: `overview.csv`, `latest_usage_cn.csv`, `top_teams_latest.csv`（四人无序去重，每模式 Top 100），Excel 同名 sheet".to_owned(),
        format!("- Prydwen 当前 T 榜行数: {}", stats.tier_rows),
        format!("- Prydwen T 榜本地历史行数: {}", stats.tier_history_rows),
        format!("- Prydwen changelog 日期段数: {}", stats.changelog_rows),
        format!("- T0-T2 出场率趋势行数: {}", stats.trend_rows),
        format!("- T0-T2 趋势图数量: {}", stats.chart_rows),
        "- 交互可视化入口: `visualizer/index.html`（含异相仲裁本地趋势与本地 Box 维护页）".to_owned(),
        String::new(),
        "## 异相仲裁拆分情况".to_owned(),
        String::new(),
    ]);
    if stats.aa_split {
        lines.push("- 已取得可识别的骑士关卡 / 王棋关卡拆分数据。".into());
    } else {
        lines.push("- 本次未取得骑士关卡 / 王棋关卡角色出场率拆分数据。".into());
        if request.modes.contains(&GameMode::HsrAa) {
            lines.push("- AA 数据已按 `all_bosses` / `全 Boss / 未拆分` 标记。".into());
        }
    }
    append_diagnostics(&mut lines, diagnostics);
    lines.push(String::new());
    lines.join("\n")
}

fn render_zzz_report(
    request: &ExportRequestV1,
    context: &ExportContext,
    diagnostics: &[Diagnostic],
    stats: &ExportStats,
) -> String {
    let mut lines = vec![
        "# 绝区零高难数据导出报告".to_owned(),
        String::new(),
        format!("- 导出时间：{}", export_time(context)),
        format!(
            "- from_date / to_date：{} / {}",
            from_date(request),
            to_date(request)
        ),
        format!(
            "- 数据源：Hugging Face dataset `{}` + Prydwen ZZZ + HoYoWiki 官方代理人/邦布列表",
            request.dataset.repo_id
        ),
        format!(
            "- 模式：{}",
            request
                .modes
                .iter()
                .map(|mode| mode.code())
                .collect::<Vec<_>>()
                .join(", ")
        ),
        format!("- 期数行数：{}", stats.phases),
        format!("- 成功读取 snapshot 数：{}", stats.snapshots),
        format!("- 角色出场率行数：{}", stats.character_rows),
        format!("- 队伍 raw 行数：{}", stats.team_rows),
        format!("- 队伍无序去重后行数：{}", stats.unordered_team_rows),
        format!("- 待人工确认名称：{}", stats.unresolved_names),
        format!("- Prydwen 当前 T 榜行数：{}", stats.tier_rows),
        format!("- Prydwen T 榜本地历史行数：{}", stats.tier_history_rows),
        format!("- Prydwen changelog 行数：{}", stats.changelog_rows),
        format!("- T 榜角色出场趋势行数：{}", stats.trend_rows),
        "- 可视化入口：`visualizer/index.html`".to_owned(),
    ];
    append_diagnostics(&mut lines, diagnostics);
    lines.push(String::new());
    lines.join("\n")
}

fn append_diagnostics(lines: &mut Vec<String>, diagnostics: &[Diagnostic]) {
    for (title, severity) in [
        ("Warning", DiagnosticSeverity::Warning),
        ("Error", DiagnosticSeverity::RecoverableError),
    ] {
        lines.extend([String::new(), format!("## {title} 列表"), String::new()]);
        let messages = diagnostics
            .iter()
            .filter(|item| item.severity == severity)
            .map(|item| format!("- {}", item.message))
            .collect::<Vec<_>>();
        if messages.is_empty() {
            lines.push("- 无".into());
        } else {
            lines.extend(messages);
        }
    }
}

fn from_date(request: &ExportRequestV1) -> String {
    request
        .date_range
        .from
        .map(|value| value.to_string())
        .unwrap_or_else(|| "-".into())
}

fn to_date(request: &ExportRequestV1) -> String {
    request
        .date_range
        .to
        .map(|value| value.to_string())
        .unwrap_or_else(|| "-".into())
}

fn export_time(context: &ExportContext) -> String {
    context
        .fetched_at
        .to_rfc3339_opts(SecondsFormat::Secs, true)
}

fn hsr_mode_name(mode: GameMode) -> &'static str {
    match mode {
        GameMode::HsrMoc => "混沌回忆",
        GameMode::HsrPf => "虚构叙事",
        GameMode::HsrAs => "末日幻影",
        GameMode::HsrAa => "异相仲裁",
        GameMode::ZzzSd | GameMode::ZzzDa => mode.code(),
    }
}

#[cfg(test)]
mod tests {
    use chrono::{TimeZone, Utc};

    use super::*;
    use crate::contract::{
        DatasetRef, DateRange, DiagnosticSource, FeatureFlags, FetchPolicy, HistoryPolicy,
        WorkbookPolicy, EXPORT_REQUEST_SCHEMA_VERSION,
    };

    #[test]
    fn final_report_uses_context_diagnostics_and_refreshes_manifest() {
        let mut bundle = ArtifactBundle::default();
        bundle
            .add_csv(
                "phase_index.csv",
                &["snapshot_id", "mode"],
                [["1.0.0", "moc"]],
            )
            .unwrap();
        bundle
            .add_csv(
                "character_usage_long.csv",
                &["mode", "sub_mode"],
                [["moc", "all"]],
            )
            .unwrap();
        bundle.add_text("export_report.md", "stale").unwrap();
        bundle.refresh_manifest("artifact_manifest.json").unwrap();
        let request = ExportRequestV1 {
            schema_version: EXPORT_REQUEST_SCHEMA_VERSION,
            game: Game::Hsr,
            modes: vec![GameMode::HsrMoc],
            date_range: DateRange {
                from: chrono::NaiveDate::from_ymd_opt(2026, 1, 1),
                to: chrono::NaiveDate::from_ymd_opt(2026, 1, 31),
            },
            dataset: DatasetRef {
                repo_id: "owner/repo".into(),
                revision: "main".into(),
            },
            features: FeatureFlags::default(),
            prydwen_top_n: 100,
            name_map_seed: None,
            history: HistoryPolicy::MergeExisting,
            workbook: WorkbookPolicy::Disabled,
        };
        let context = ExportContext {
            fetched_at: Utc.with_ymd_and_hms(2026, 7, 12, 1, 2, 3).unwrap(),
            fetch_policy: FetchPolicy::Fixture,
            cache_root: "cache".into(),
            existing_output_root: None,
        };
        let diagnostic = Diagnostic {
            severity: DiagnosticSeverity::Warning,
            code: "fixture.warning".into(),
            source: DiagnosticSource::Pipeline,
            game: Game::Hsr,
            snapshot: None,
            mode: None,
            path: None,
            message: "fixture warning".into(),
        };

        let stats = finalize_export_bundle(&mut bundle, &request, &context, &[diagnostic]).unwrap();
        assert_eq!(stats.snapshots, 1);
        assert_eq!(stats.phases_by_mode[&GameMode::HsrMoc], 1);
        let report = std::str::from_utf8(bundle.get("export_report.md").unwrap()).unwrap();
        assert!(report.contains("2026-07-12T01:02:03Z"));
        assert!(report.contains("2026-01-01 / 2026-01-31"));
        assert!(report.contains("fixture warning"));

        let manifest: Vec<crate::output::ArtifactManifestEntry> =
            serde_json::from_slice(bundle.get("artifact_manifest.json").unwrap()).unwrap();
        let report_entry = manifest
            .iter()
            .find(|entry| entry.path == "export_report.md")
            .unwrap();
        assert_eq!(
            report_entry.bytes,
            bundle.get("export_report.md").unwrap().len()
        );
    }
}
