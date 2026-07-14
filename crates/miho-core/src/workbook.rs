use rust_xlsxwriter::{Format, FormatAlign, FormatBorder, Workbook, Worksheet, XlsxError};

use crate::{
    contract::{
        diagnostic_code, Diagnostic, DiagnosticSeverity, DiagnosticSource, Game, WorkbookPolicy,
    },
    output::ArtifactBundle,
    MihoError, Result,
};

const HSR_WORKBOOK: &str = "hsr_endgame_dataset.xlsx";
const ZZZ_WORKBOOK: &str = "zzz_endgame_dataset.xlsx";

const HSR_SHEETS: &[(&str, &str)] = &[
    ("overview", "overview.csv"),
    ("latest_usage_cn", "latest_usage_cn.csv"),
    ("top_teams_latest", "top_teams_latest.csv"),
    ("phase_index", "phase_index.csv"),
    ("character_usage_long", "character_usage_long.csv"),
    (
        "character_usage_phase_latest",
        "character_usage_phase_latest.csv",
    ),
    ("histograph_usage_long", "histograph_usage_long.csv"),
    ("team_rank_raw", "team_rank_raw.csv"),
    ("team_rank_dedup_ordered", "team_rank_dedup_ordered.csv"),
    ("team_rank_dedup_unordered", "team_rank_dedup_unordered.csv"),
    ("name_map", "name_map.csv"),
    ("name_map_unresolved", "name_map_unresolved.csv"),
    ("prydwen_tier_current", "prydwen_tier_current.csv"),
    ("prydwen_tier_history", "prydwen_tier_history.csv"),
    ("prydwen_tier_changelog", "prydwen_tier_changelog.csv"),
    (
        "prydwen_tier_changelog_history",
        "prydwen_tier_changelog_history.csv",
    ),
    ("prydwen_tier_usage_trend", "prydwen_tier_usage_trend.csv"),
    ("prydwen_tier_charts", "prydwen_tier_charts.csv"),
];

const ZZZ_SHEETS: &[(&str, &str)] = &[
    ("phase_index", "phase_index.csv"),
    ("character_usage_long", "character_usage_long.csv"),
    (
        "character_usage_phase_latest",
        "character_usage_phase_latest.csv",
    ),
    ("team_rank_raw", "team_rank_raw.csv"),
    ("team_rank_dedup_unordered", "team_rank_dedup_unordered.csv"),
    ("name_map", "name_map.csv"),
    ("name_map_unresolved", "name_map_unresolved.csv"),
    ("prydwen_tier_current", "prydwen_tier_current.csv"),
    ("prydwen_tier_history", "prydwen_tier_history.csv"),
    ("prydwen_tier_changelog", "prydwen_tier_changelog.csv"),
    (
        "prydwen_tier_changelog_history",
        "prydwen_tier_changelog_history.csv",
    ),
    ("prydwen_tier_usage_trend", "prydwen_tier_usage_trend.csv"),
];

#[derive(Debug)]
struct CsvTable {
    headers: Vec<String>,
    rows: Vec<Vec<String>>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum CellKind {
    Text,
    Integer,
    IntegerOrText,
    Number,
    NumberOrText,
    Boolean,
}

pub fn workbook_file_name(game: Game) -> &'static str {
    match game {
        Game::Hsr => HSR_WORKBOOK,
        Game::Zzz => ZZZ_WORKBOOK,
    }
}

pub fn workbook_source_paths(game: Game) -> impl Iterator<Item = &'static str> {
    sheet_specs(game).iter().map(|(_, path)| *path)
}

pub fn build_workbook_bytes(game: Game, bundle: &ArtifactBundle) -> Result<Vec<u8>> {
    let header_standard = Format::new()
        .set_bold()
        .set_font_color("FFFFFF")
        .set_background_color("263238")
        .set_border(FormatBorder::Thin)
        .set_align(FormatAlign::Center)
        .set_align(FormatAlign::VerticalCenter);
    let header_soft = Format::new()
        .set_bold()
        .set_font_color("1F2933")
        .set_background_color("E8F3F1")
        .set_border(FormatBorder::Thin)
        .set_align(FormatAlign::Center)
        .set_align(FormatAlign::VerticalCenter);
    let header_pandas = Format::new()
        .set_bold()
        .set_border(FormatBorder::Thin)
        .set_align(FormatAlign::Center)
        .set_align(FormatAlign::Top);
    let two_decimals = Format::new().set_num_format("0.00");

    let mut workbook = Workbook::new();
    for (index, (sheet_name, csv_path)) in sheet_specs(game).iter().enumerate() {
        let table = read_table(bundle, csv_path)?;
        let worksheet = workbook.add_worksheet();
        xlsx(worksheet.set_name(*sheet_name))?;
        if index == 0 {
            worksheet.set_active(true);
        }

        let header_format = match game {
            Game::Hsr if is_soft_hsr_sheet(sheet_name) => &header_soft,
            Game::Hsr => &header_standard,
            Game::Zzz => &header_pandas,
        };
        write_table(
            worksheet,
            game,
            sheet_name,
            &table,
            header_format,
            &two_decimals,
        )?;

        if game == Game::Hsr {
            configure_hsr_sheet(worksheet, index, &table)?;
        }
    }
    workbook
        .save_to_buffer()
        .map_err(|error| MihoError::Workbook(error.to_string()))
}

pub fn apply_workbook_policy(
    bundle: &mut ArtifactBundle,
    game: Game,
    policy: WorkbookPolicy,
    diagnostics: &mut Vec<Diagnostic>,
) {
    if policy == WorkbookPolicy::Disabled {
        return;
    }

    let path = workbook_file_name(game);
    let result = build_workbook_bytes(game, bundle).and_then(|bytes| bundle.add_bytes(path, bytes));
    if let Err(error) = result {
        diagnostics.push(Diagnostic {
            severity: DiagnosticSeverity::Warning,
            code: diagnostic_code::WORKBOOK_GENERATION_FAILED.into(),
            source: DiagnosticSource::Workbook,
            game,
            snapshot: None,
            mode: None,
            path: Some(path.into()),
            message: error.to_string(),
        });
    }
}

fn sheet_specs(game: Game) -> &'static [(&'static str, &'static str)] {
    match game {
        Game::Hsr => HSR_SHEETS,
        Game::Zzz => ZZZ_SHEETS,
    }
}

fn read_table(bundle: &ArtifactBundle, path: &str) -> Result<CsvTable> {
    let bytes = bundle
        .get(path)
        .ok_or_else(|| MihoError::Workbook(format!("required CSV artifact is missing: {path}")))?;
    let bytes = bytes.strip_prefix(&[0xEF, 0xBB, 0xBF]).unwrap_or(bytes);
    let mut reader = csv::ReaderBuilder::new().from_reader(bytes);
    let headers = reader
        .headers()?
        .iter()
        .map(str::to_owned)
        .collect::<Vec<_>>();
    let mut rows = Vec::new();
    for record in reader.records() {
        let record = record?;
        if record.len() != headers.len() {
            return Err(MihoError::CsvWidth {
                expected: headers.len(),
                actual: record.len(),
            });
        }
        rows.push(record.iter().map(str::to_owned).collect());
    }
    Ok(CsvTable { headers, rows })
}

fn write_table(
    worksheet: &mut Worksheet,
    game: Game,
    sheet: &str,
    table: &CsvTable,
    header_format: &Format,
    two_decimals: &Format,
) -> Result<()> {
    for (column, header) in table.headers.iter().enumerate() {
        let column = column_number(column)?;
        xlsx(worksheet.write_string_with_format(0, column, header, header_format))?;
    }

    for (row_index, row) in table.rows.iter().enumerate() {
        let excel_row = row_number(row_index + 1)?;
        let mut wrote_cell = false;
        for (column_index, (header, value)) in table.headers.iter().zip(row).enumerate() {
            let column = column_number(column_index)?;
            let kind = cell_kind(game, sheet, header, row, &table.headers);
            let number_format = if game == Game::Hsr && hsr_two_decimal_header(header) {
                Some(two_decimals)
            } else {
                None
            };
            if value.is_empty() {
                if let Some(format) = number_format {
                    xlsx(worksheet.write_blank(excel_row, column, format))?;
                    wrote_cell = true;
                }
                continue;
            }

            match kind {
                CellKind::Text => match number_format {
                    Some(format) => {
                        xlsx(worksheet.write_string_with_format(excel_row, column, value, format))?;
                    }
                    None => {
                        xlsx(worksheet.write_string(excel_row, column, value))?;
                    }
                },
                CellKind::Integer => {
                    let number = parse_integer(sheet, header, value)? as f64;
                    match number_format {
                        Some(format) => {
                            xlsx(
                                worksheet
                                    .write_number_with_format(excel_row, column, number, format),
                            )?;
                        }
                        None => {
                            xlsx(worksheet.write_number(excel_row, column, number))?;
                        }
                    }
                }
                CellKind::IntegerOrText => {
                    if let Ok(number) = value.parse::<i64>() {
                        match number_format {
                            Some(format) => {
                                xlsx(worksheet.write_number_with_format(
                                    excel_row,
                                    column,
                                    number as f64,
                                    format,
                                ))?;
                            }
                            None => {
                                xlsx(worksheet.write_number(excel_row, column, number as f64))?;
                            }
                        }
                    } else {
                        match number_format {
                            Some(format) => {
                                xlsx(
                                    worksheet
                                        .write_string_with_format(excel_row, column, value, format),
                                )?;
                            }
                            None => {
                                xlsx(worksheet.write_string(excel_row, column, value))?;
                            }
                        }
                    }
                }
                CellKind::Number => {
                    let number = parse_number(sheet, header, value)?;
                    match number_format {
                        Some(format) => {
                            xlsx(
                                worksheet
                                    .write_number_with_format(excel_row, column, number, format),
                            )?;
                        }
                        None => {
                            xlsx(worksheet.write_number(excel_row, column, number))?;
                        }
                    }
                }
                CellKind::NumberOrText => {
                    if let Ok(number) = value.parse::<f64>() {
                        if !number.is_finite() {
                            return Err(MihoError::Workbook(format!(
                                "{sheet}.{header} contains a non-finite number: {value:?}"
                            )));
                        }
                        match number_format {
                            Some(format) => {
                                xlsx(
                                    worksheet.write_number_with_format(
                                        excel_row, column, number, format,
                                    ),
                                )?;
                            }
                            None => {
                                xlsx(worksheet.write_number(excel_row, column, number))?;
                            }
                        }
                    } else {
                        match number_format {
                            Some(format) => {
                                xlsx(
                                    worksheet
                                        .write_string_with_format(excel_row, column, value, format),
                                )?;
                            }
                            None => {
                                xlsx(worksheet.write_string(excel_row, column, value))?;
                            }
                        }
                    }
                }
                CellKind::Boolean => {
                    let value = parse_boolean(sheet, header, value)?;
                    match number_format {
                        Some(format) => {
                            xlsx(
                                worksheet
                                    .write_boolean_with_format(excel_row, column, value, format),
                            )?;
                        }
                        None => {
                            xlsx(worksheet.write_boolean(excel_row, column, value))?;
                        }
                    }
                }
            }
            wrote_cell = true;
        }
        if !wrote_cell && !table.headers.is_empty() {
            xlsx(worksheet.write_blank(excel_row, 0, &Format::new()))?;
        }
    }
    Ok(())
}

fn configure_hsr_sheet(worksheet: &mut Worksheet, index: usize, table: &CsvTable) -> Result<()> {
    worksheet.set_screen_gridlines(false);
    if index > 0 {
        xlsx(worksheet.set_freeze_panes(1, 0))?;
    }
    let last_row = u32::try_from(table.rows.len())
        .map_err(|_| MihoError::Workbook("worksheet row count exceeds Excel limits".into()))?;
    let last_column = if table.headers.is_empty() {
        0
    } else {
        column_number(table.headers.len() - 1)?
    };
    xlsx(worksheet.autofilter(0, 0, last_row, last_column))?;

    for (column_index, header) in table.headers.iter().enumerate() {
        let width = hsr_column_width(header, column_index, table);
        let pixels = u32::try_from(width * 7)
            .map_err(|_| MihoError::Workbook("column width exceeds Excel limits".into()))?;
        xlsx(worksheet.set_column_width_pixels(column_number(column_index)?, pixels))?;
    }
    Ok(())
}

fn hsr_column_width(header: &str, column: usize, table: &CsvTable) -> usize {
    let override_width = match header {
        "raw_json" => Some(18),
        "source_url" => Some(24),
        "source_file" | "merged_source_files" | "ordered_signature_examples" => Some(28),
        "team_cn" => Some(42),
        _ => None,
    };
    if let Some(width) = override_width {
        return width;
    }

    let mut width = header.chars().count();
    for row in table.rows.iter().take(249) {
        if let Some(value) = row.get(column).filter(|value| !value.is_empty()) {
            width = width.max(value.chars().count());
        }
    }
    (width + 2).clamp(8, 36)
}

fn cell_kind(
    game: Game,
    sheet: &str,
    header: &str,
    row: &[String],
    headers: &[String],
) -> CellKind {
    if sheet == "overview" && header == "value" {
        let section = field(row, headers, "section");
        return if matches!(
            section,
            "rows" | "dedup" | "names" | "prydwen_tier" | "quality" | "coverage"
        ) || (section == "summary" && field(row, headers, "metric") == "snapshots")
        {
            CellKind::Integer
        } else {
            CellKind::Text
        };
    }

    match game {
        Game::Hsr => hsr_cell_kind(header),
        Game::Zzz => zzz_cell_kind(header),
    }
}

fn hsr_cell_kind(header: &str) -> CellKind {
    if matches!(
        header,
        "has_chars" | "has_comps" | "has_histograph" | "is_new"
    ) {
        return CellKind::Boolean;
    }
    if header == "rarity" {
        return CellKind::IntegerOrText;
    }
    if header == "special_rating" {
        return CellKind::NumberOrText;
    }
    if matches!(
        header,
        "raw_index" | "duplicate_count" | "series_count" | "point_count"
    ) {
        return CellKind::Integer;
    }
    if header.contains("app_rate")
        || header.contains("avg_round")
        || matches!(
            header,
            "std_dev_round"
                | "q1_round"
                | "cons_avg"
                | "usage_value"
                | "rank"
                | "rating"
                | "sample"
                | "sample_app_flat"
                | "whale_count"
                | "app_flat"
                | "uses"
        )
    {
        return CellKind::Number;
    }
    CellKind::Text
}

fn zzz_cell_kind(header: &str) -> CellKind {
    if matches!(header, "has_chars" | "has_comps" | "is_new") {
        return CellKind::Boolean;
    }
    if header == "rarity" {
        return CellKind::IntegerOrText;
    }
    if matches!(header, "sample" | "sample_players" | "raw_index") {
        return CellKind::Integer;
    }
    if matches!(
        header,
        "app_rate"
            | "avg_score"
            | "avg_score_m1"
            | "cons_avg"
            | "char_level"
            | "w_engine_level"
            | "core_skill"
            | "rank"
            | "rating"
    ) {
        return CellKind::Number;
    }
    CellKind::Text
}

fn hsr_two_decimal_header(header: &str) -> bool {
    header.contains("app_rate")
        || header == "max_app_rate"
        || header.contains("avg_round")
        || header.contains("sample")
        || header == "rank"
}

fn is_soft_hsr_sheet(sheet: &str) -> bool {
    matches!(sheet, "overview" | "latest_usage_cn" | "top_teams_latest")
}

fn field<'a>(row: &'a [String], headers: &[String], key: &str) -> &'a str {
    headers
        .iter()
        .position(|header| header == key)
        .and_then(|index| row.get(index))
        .map(String::as_str)
        .unwrap_or_default()
}

fn parse_integer(sheet: &str, header: &str, value: &str) -> Result<i64> {
    value.parse::<i64>().map_err(|_| {
        MihoError::Workbook(format!(
            "{sheet}.{header} expected an integer but received {value:?}"
        ))
    })
}

fn parse_number(sheet: &str, header: &str, value: &str) -> Result<f64> {
    let number = value.parse::<f64>().map_err(|_| {
        MihoError::Workbook(format!(
            "{sheet}.{header} expected a number but received {value:?}"
        ))
    })?;
    if !number.is_finite() {
        return Err(MihoError::Workbook(format!(
            "{sheet}.{header} contains a non-finite number: {value:?}"
        )));
    }
    Ok(number)
}

fn parse_boolean(sheet: &str, header: &str, value: &str) -> Result<bool> {
    match value.to_ascii_lowercase().as_str() {
        "true" | "1" => Ok(true),
        "false" | "0" => Ok(false),
        _ => Err(MihoError::Workbook(format!(
            "{sheet}.{header} expected a boolean but received {value:?}"
        ))),
    }
}

fn row_number(value: usize) -> Result<u32> {
    u32::try_from(value)
        .map_err(|_| MihoError::Workbook("worksheet row count exceeds Excel limits".into()))
}

fn column_number(value: usize) -> Result<u16> {
    u16::try_from(value)
        .map_err(|_| MihoError::Workbook("worksheet column count exceeds Excel limits".into()))
}

fn xlsx<T>(result: std::result::Result<T, XlsxError>) -> Result<T> {
    result.map_err(|error| MihoError::Workbook(error.to_string()))
}

#[cfg(test)]
mod tests {
    use std::io::{Cursor, Read};

    use zip::ZipArchive;

    use super::*;

    fn minimal_source_bundle(game: Game, value: &str) -> ArtifactBundle {
        let mut bundle = ArtifactBundle::default();
        for path in workbook_source_paths(game) {
            bundle.add_csv(path, &["text"], [[value]]).unwrap();
        }
        bundle
    }

    #[test]
    fn both_workbooks_keep_external_formula_text_literal() {
        for game in [Game::Hsr, Game::Zzz] {
            let bundle = minimal_source_bundle(game, "=HYPERLINK(\"https://invalid\",\"text\")");
            let bytes = build_workbook_bytes(game, &bundle).unwrap();
            assert!(bytes.starts_with(&[0x50, 0x4b, 0x03, 0x04]));

            let mut archive = ZipArchive::new(Cursor::new(bytes)).unwrap();
            for index in 0..archive.len() {
                let mut file = archive.by_index(index).unwrap();
                if file.name().starts_with("xl/worksheets/sheet") && file.name().ends_with(".xml") {
                    let mut xml = String::new();
                    file.read_to_string(&mut xml).unwrap();
                    assert!(!xml.contains("<f>"), "{} contained a formula", file.name());
                }
            }
        }
    }

    #[test]
    fn best_effort_failure_is_a_warning_without_a_partial_artifact() {
        let mut bundle = ArtifactBundle::default();
        let mut diagnostics = vec![];
        apply_workbook_policy(
            &mut bundle,
            Game::Hsr,
            WorkbookPolicy::BestEffort,
            &mut diagnostics,
        );

        assert!(bundle.get(HSR_WORKBOOK).is_none());
        assert_eq!(diagnostics.len(), 1);
        assert_eq!(diagnostics[0].source, DiagnosticSource::Workbook);
        assert_eq!(
            diagnostics[0].code,
            diagnostic_code::WORKBOOK_GENERATION_FAILED
        );
        assert_eq!(diagnostics[0].path.as_deref(), Some(HSR_WORKBOOK));
    }

    #[test]
    fn disabled_policy_is_a_noop() {
        let mut bundle = ArtifactBundle::default();
        let mut diagnostics = vec![];
        apply_workbook_policy(
            &mut bundle,
            Game::Zzz,
            WorkbookPolicy::Disabled,
            &mut diagnostics,
        );
        assert!(bundle.get(ZZZ_WORKBOOK).is_none());
        assert!(diagnostics.is_empty());
    }

    #[test]
    fn fractional_integer_cell_fails_before_artifact_insertion() {
        let mut bundle = minimal_source_bundle(Game::Zzz, "text");
        bundle
            .add_csv("character_usage_long.csv", &["sample"], [["59.5"]])
            .unwrap();
        let mut diagnostics = vec![];
        apply_workbook_policy(
            &mut bundle,
            Game::Zzz,
            WorkbookPolicy::BestEffort,
            &mut diagnostics,
        );
        assert!(bundle.get(ZZZ_WORKBOOK).is_none());
        assert_eq!(diagnostics.len(), 1);
        assert!(diagnostics[0].message.contains("expected an integer"));
    }

    #[test]
    fn workbook_numeric_fields_accept_real_source_shapes() {
        let mut hsr = minimal_source_bundle(Game::Hsr, "text");
        hsr.add_csv(
            "character_usage_long.csv",
            &["sample", "sample_app_flat"],
            [["0.0", "20.0"]],
        )
        .unwrap();
        hsr.add_csv(
            "histograph_usage_long.csv",
            &["whale_count", "app_flat", "uses"],
            [["1.0", "2.0", "3.0"]],
        )
        .unwrap();
        assert!(build_workbook_bytes(Game::Hsr, &hsr).is_ok());

        let mut zzz = minimal_source_bundle(Game::Zzz, "text");
        zzz.add_csv(
            "character_usage_long.csv",
            &[
                "sample",
                "sample_players",
                "char_level",
                "w_engine_level",
                "core_skill",
            ],
            [["59", "24", "59.85", "58.98", "6.91"]],
        )
        .unwrap();
        assert!(build_workbook_bytes(Game::Zzz, &zzz).is_ok());
    }

    #[test]
    fn hsr_width_uses_unicode_codepoints_and_python_sample_limit() {
        let table = CsvTable {
            headers: vec!["name".into()],
            rows: vec![vec!["代理甲".into()]],
        };
        assert_eq!(hsr_column_width("name", 0, &table), 8);
        assert_eq!(
            hsr_column_width(
                "name",
                0,
                &CsvTable {
                    headers: vec!["name".into()],
                    rows: vec![vec!["x".repeat(50)]],
                }
            ),
            36
        );
        assert_eq!(hsr_column_width("team_cn", 0, &table), 42);
    }
}
