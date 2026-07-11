use std::{future::Future, pin::Pin};

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

use crate::{contract::GameMode, Result};

pub type SupplementalFuture<'a> =
    Pin<Box<dyn Future<Output = Result<SupplementalDocument>> + Send + 'a>>;

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "kebab-case")]
pub enum Locale {
    EnUs,
    ZhCn,
}

impl Locale {
    pub const fn code(self) -> &'static str {
        match self {
            Self::EnUs => "en-us",
            Self::ZhCn => "zh-cn",
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum HsrMode {
    Moc,
    Pf,
    As,
    Aa,
}

impl HsrMode {
    pub const fn code(self) -> &'static str {
        match self {
            Self::Moc => "moc",
            Self::Pf => "pf",
            Self::As => "as",
            Self::Aa => "aa",
        }
    }
}

impl TryFrom<GameMode> for HsrMode {
    type Error = GameMode;

    fn try_from(value: GameMode) -> std::result::Result<Self, Self::Error> {
        match value {
            GameMode::HsrMoc => Ok(Self::Moc),
            GameMode::HsrPf => Ok(Self::Pf),
            GameMode::HsrAs => Ok(Self::As),
            GameMode::HsrAa => Ok(Self::Aa),
            GameMode::ZzzSd | GameMode::ZzzDa => Err(value),
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ZzzMode {
    Sd,
    Da,
}

impl ZzzMode {
    pub const fn code(self) -> &'static str {
        match self {
            Self::Sd => "sd",
            Self::Da => "da",
        }
    }
}

impl TryFrom<GameMode> for ZzzMode {
    type Error = GameMode;

    fn try_from(value: GameMode) -> std::result::Result<Self, Self::Error> {
        match value {
            GameMode::ZzzSd => Ok(Self::Sd),
            GameMode::ZzzDa => Ok(Self::Da),
            GameMode::HsrMoc | GameMode::HsrPf | GameMode::HsrAs | GameMode::HsrAa => Err(value),
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum HoyowikiEntryKind {
    Character,
    Agent,
    Bangboo,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum HsrSupplementalResource {
    PrydwenTeams { mode: HsrMode },
    PrydwenTier,
    HoyowikiCharacters { locale: Locale, page: u32 },
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum ZzzSupplementalResource {
    PrydwenTeams {
        mode: ZzzMode,
    },
    PrydwenTier,
    HoyowikiEntries {
        entry_kind: HoyowikiEntryKind,
        locale: Locale,
        page: u32,
    },
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SupplementalOrigin {
    Network,
    Cache,
    Fixture,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct SupplementalDocument {
    pub body: String,
    pub source_url: String,
    pub fetched_at: DateTime<Utc>,
    pub origin: SupplementalOrigin,
    pub fallback_reason: Option<String>,
}

pub trait HsrSupplementalSource: Send + Sync {
    fn fetch<'a>(&'a self, resource: HsrSupplementalResource) -> SupplementalFuture<'a>;
}

pub trait ZzzSupplementalSource: Send + Sync {
    fn fetch<'a>(&'a self, resource: ZzzSupplementalResource) -> SupplementalFuture<'a>;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resource_requests_are_game_specific_and_serializable() {
        let hsr = HsrSupplementalResource::PrydwenTeams { mode: HsrMode::Moc };
        let zzz = ZzzSupplementalResource::HoyowikiEntries {
            entry_kind: HoyowikiEntryKind::Bangboo,
            locale: Locale::ZhCn,
            page: 2,
        };
        assert_eq!(
            serde_json::to_value(hsr).unwrap(),
            serde_json::json!({"kind":"prydwen_teams","mode":"moc"})
        );
        assert_eq!(
            serde_json::to_value(zzz).unwrap(),
            serde_json::json!({
                "kind":"hoyowiki_entries",
                "entry_kind":"bangboo",
                "locale":"zh-cn",
                "page":2
            })
        );
        assert_eq!(HsrMode::try_from(GameMode::ZzzSd), Err(GameMode::ZzzSd));
        assert_eq!(ZzzMode::try_from(GameMode::HsrMoc), Err(GameMode::HsrMoc));
    }
}
