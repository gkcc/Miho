use chrono::NaiveDate;

#[derive(Debug, Eq, Ord, PartialEq, PartialOrd)]
enum NaturalVersionToken {
    Text(String),
    Number(usize, String),
}

pub fn parse_percent(value: &str) -> Option<f64> {
    let trimmed = value.trim();
    if matches!(trimmed, "" | "-") {
        return None;
    }
    let is_percent = trimmed.ends_with('%');
    let number = trimmed.trim_end_matches('%').trim().parse::<f64>().ok()?;
    let _ = is_percent;
    Some(number)
}

pub fn character_slug(value: &str) -> String {
    let expanded = value
        .trim()
        .to_lowercase()
        .replace('&', " and ")
        .replace('+', " plus ")
        .replace('•', " ")
        .replace(['.', '\'', '’', '`'], "");
    let slug = expanded
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '-' })
        .collect::<String>()
        .split('-')
        .filter(|v| !v.is_empty())
        .collect::<Vec<_>>()
        .join("-");
    match slug.as_str() {
        "topaz-numby" => "topaz-and-numby".to_owned(),
        _ => slug,
    }
}

pub fn character_slug_to_english(value: &str) -> String {
    character_slug(value)
        .split('-')
        .map(|part| match part {
            "and" | "of" | "the" => part.to_owned(),
            _ if part.chars().all(|c| c.is_ascii_digit()) => part.to_owned(),
            _ => {
                let mut chars = part.chars();
                chars
                    .next()
                    .map(|head| head.to_uppercase().chain(chars).collect())
                    .unwrap_or_default()
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

pub fn parse_number(value: &str) -> Option<f64> {
    let trimmed = value.trim();
    if matches!(trimmed, "" | "-") {
        None
    } else {
        trimmed.parse().ok()
    }
}

pub fn parse_date(value: &str) -> String {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return String::new();
    }
    for format in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"] {
        if let Ok(date) = NaiveDate::parse_from_str(trimmed, format) {
            return date.format("%Y-%m-%d").to_string();
        }
    }
    trimmed.to_owned()
}

pub(crate) fn natural_version_cmp(left: &str, right: &str) -> std::cmp::Ordering {
    natural_version_tokens(left)
        .cmp(&natural_version_tokens(right))
        .then_with(|| left.cmp(right))
}

fn natural_version_tokens(value: &str) -> Vec<NaturalVersionToken> {
    let mut tokens = Vec::new();
    let mut start = 0;
    let mut digits = None;
    for (index, character) in value.char_indices() {
        let current_digits = character.is_ascii_digit();
        match digits {
            None => digits = Some(current_digits),
            Some(previous_digits) if previous_digits != current_digits => {
                tokens.push(natural_version_token(&value[start..index], previous_digits));
                start = index;
                digits = Some(current_digits);
            }
            Some(_) => {}
        }
    }
    if let Some(digits) = digits {
        tokens.push(natural_version_token(&value[start..], digits));
    }
    tokens
}

fn natural_version_token(value: &str, digits: bool) -> NaturalVersionToken {
    if !digits {
        return NaturalVersionToken::Text(value.to_lowercase());
    }
    let significant = value.trim_start_matches('0');
    let significant = if significant.is_empty() {
        "0"
    } else {
        significant
    };
    NaturalVersionToken::Number(significant.len(), significant.to_owned())
}

#[allow(clippy::too_many_arguments)]
pub fn ordered_signature(
    snapshot_id: &str,
    collect_date: &str,
    mode: &str,
    sub_mode: &str,
    scope: &str,
    phase_ver: &str,
    phase_name: &str,
    chars: &[String],
) -> String {
    let chars = chars
        .iter()
        .map(|value| character_slug(value))
        .collect::<Vec<_>>()
        .join(">");
    format!(
        "{snapshot_id}|{collect_date}|{mode}|{sub_mode}|{scope}|{phase_ver}|{phase_name}|{chars}"
    )
}

#[allow(clippy::too_many_arguments)]
pub fn unordered_signature(
    snapshot_id: &str,
    collect_date: &str,
    mode: &str,
    sub_mode: &str,
    scope: &str,
    phase_ver: &str,
    phase_name: &str,
    chars: &[String],
) -> String {
    let mut chars = chars
        .iter()
        .map(|value| character_slug(value))
        .collect::<Vec<_>>();
    chars.sort();
    format!(
        "{snapshot_id}|{collect_date}|{mode}|{sub_mode}|{scope}|{phase_ver}|{phase_name}|{}",
        chars.join(">")
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn percentages() {
        assert_eq!(parse_percent("12.5%"), Some(12.5));
        assert_eq!(parse_percent("1,234%"), None);
    }
    #[test]
    fn slugs() {
        assert_eq!(character_slug("  Ye Shunguang "), "ye-shunguang");
        assert_eq!(character_slug("Topaz & Numby"), "topaz-and-numby");
        assert_eq!(character_slug("A+B"), "a-plus-b");
        assert_eq!(character_slug("O'Brien"), "obrien");
    }

    #[test]
    fn natural_versions_compare_numeric_runs() {
        assert!(natural_version_cmp("4.3.10", "4.3.9").is_gt());
        assert!(natural_version_cmp("4.10", "4.9").is_gt());
        assert!(natural_version_cmp("fixture-10", "fixture-9").is_gt());
    }

    #[test]
    fn golden_cases_match_python_fixture() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../../tests/fixtures/normalize_cases.json"))
                .unwrap();
        for case in fixture["slugs"].as_array().unwrap() {
            assert_eq!(
                character_slug(case["input"].as_str().unwrap()),
                case["expected"].as_str().unwrap()
            );
        }
        for case in fixture["percents"].as_array().unwrap() {
            let expected = case["expected"].as_f64();
            assert_eq!(parse_percent(case["input"].as_str().unwrap()), expected);
        }
        for case in fixture["dates"].as_array().unwrap() {
            assert_eq!(
                parse_date(case["input"].as_str().unwrap()),
                case["expected"].as_str().unwrap()
            );
        }
    }
}
