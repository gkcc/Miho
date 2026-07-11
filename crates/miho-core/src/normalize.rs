pub fn parse_percent(value: &str) -> Option<f64> {
    let trimmed = value.trim().replace(',', "");
    if trimmed.is_empty() || matches!(trimmed.as_str(), "-" | "--" | "N/A" | "n/a") {
        return None;
    }
    let is_percent = trimmed.ends_with('%');
    let number = trimmed.trim_end_matches('%').trim().parse::<f64>().ok()?;
    Some(if is_percent { number / 100.0 } else { number })
}

pub fn character_slug(value: &str) -> String {
    value
        .trim()
        .to_lowercase()
        .chars()
        .map(|c| if c.is_ascii_alphanumeric() { c } else { '-' })
        .collect::<String>()
        .split('-')
        .filter(|v| !v.is_empty())
        .collect::<Vec<_>>()
        .join("-")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn percentages() {
        assert_eq!(parse_percent("12.5%"), Some(0.125));
        assert_eq!(parse_percent("--"), None);
    }
    #[test]
    fn slugs() {
        assert_eq!(character_slug("  Ye Shunguang "), "ye-shunguang");
    }
}
