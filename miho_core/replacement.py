from __future__ import annotations

from typing import Any

from hsr_endgame_exporter.normalize import normalize_character_id

from .box import BoxProfile


def evaluate_replacement_risk(
    candidate_slug: str,
    candidate_meta: dict[str, Any],
    box: BoxProfile,
    tier_by_slug: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    slug = normalize_character_id(candidate_slug)
    role = str(candidate_meta.get("role_group") or "")
    style = str(candidate_meta.get("style") or "")
    element = str(candidate_meta.get("element") or "")
    candidate_rating = _float(candidate_meta.get("best_rating"))
    replacements: list[dict[str, Any]] = []
    for owned_slug, owned in box.agents.items():
        if owned_slug == slug or not owned.owned:
            continue
        meta = tier_by_slug.get(owned_slug, {})
        same_role = role and meta.get("role_group") == role
        same_style = style and meta.get("style") == style
        same_element = element and meta.get("element") == element
        if not (same_role or (same_style and same_element)):
            continue
        rating = _float(meta.get("best_rating"))
        replacements.append(
            {
                "slug": owned_slug,
                "name_cn": owned.name_cn or meta.get("character_name_cn") or meta.get("character_name_en") or owned_slug,
                "tier": meta.get("best_tier", ""),
                "rating": rating,
                "same_role": same_role,
                "same_style": same_style,
                "same_element": same_element,
            }
        )
    replacements.sort(key=lambda item: (-item["rating"], item["slug"]))
    strong = [item for item in replacements if item["same_role"] and item["rating"] >= max(9.0, candidate_rating - 1)]
    if strong:
        level = "高"
        reason = "Box 内已有同定位高评级角色，新增收益可能被稀释"
    elif replacements:
        level = "中"
        reason = "Box 内已有相近定位角色，需要看当期环境是否点名"
    else:
        level = "低"
        reason = "Box 内暂无明显同定位替代"
    return {
        "level": level,
        "reason": reason,
        "replacements": replacements[:5],
    }


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

