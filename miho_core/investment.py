from __future__ import annotations

from typing import Any

from .box import OwnedAgent


DEFAULT_THRESHOLDS = {
    "level": 60,
    "w_engine_level": 60,
    "core_skill": 6,
}


DEFAULT_STAGE_LADDER = [
    {"stage": "0+0", "label": "0+0 本体", "pull_cost": 1},
    {"stage": "0+1", "label": "0+1 本体+专武", "pull_cost": 2},
    {"stage": "1+1", "label": "1+1 一影+专武", "pull_cost": 3},
    {"stage": "2+1", "label": "2+1 二影+专武", "pull_cost": 4},
]


def evaluate_investment(agent: OwnedAgent | None, rules: dict[str, Any]) -> dict[str, Any]:
    if not agent or not agent.owned:
        return {
            "status": "未拥有",
            "score": 0,
            "warnings": ["未拥有，练度不可评估"],
            "ready": False,
        }
    thresholds = {**DEFAULT_THRESHOLDS, **dict(rules.get("investment_thresholds") or {})}
    checks = [
        _check("等级", agent.level, thresholds["level"]),
        _check("音擎等级", agent.w_engine_level, thresholds["w_engine_level"]),
        _check("核心技", agent.core_skill, thresholds["core_skill"]),
    ]
    passed = sum(1 for item in checks if item["ok"])
    warnings = [item["warning"] for item in checks if item["warning"]]
    if agent.drive_discs and str(agent.drive_discs).lower() in {"missing", "none", "未刷", "未成型"}:
        warnings.append("驱动盘未成型")
    status = "已满练" if passed == len(checks) and not warnings else "需补练度"
    return {
        "status": status,
        "score": round(passed / len(checks), 3),
        "warnings": warnings,
        "ready": status == "已满练",
    }


def compare_stages(
    *,
    agent: OwnedAgent | None,
    decision: str,
    max_recommended_stage: str,
    rules: dict[str, Any],
) -> list[dict[str, Any]]:
    ladder = rules.get("stage_ladder") if isinstance(rules.get("stage_ladder"), list) else DEFAULT_STAGE_LADDER
    current = _stage_tuple(agent.stage if agent and agent.owned else "-1+0")
    max_stage = _stage_tuple(max_recommended_stage or rules.get("default_max_recommended_stage") or "0+1")
    rows: list[dict[str, Any]] = []
    for item in ladder:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage") or "")
        stage_tuple = _stage_tuple(stage)
        reached = current >= stage_tuple
        beyond = stage_tuple > max_stage
        if reached:
            value = "已达成"
            advice = "不用再投入"
        elif beyond:
            value = "低"
            advice = "第一版不建议加仓"
        elif decision == "抽" and stage == "0+0":
            value = "高"
            advice = "优先看本体"
        elif decision == "等实测":
            value = "未知"
            advice = "等实测后再判断"
        elif decision == "不抽":
            value = "低"
            advice = "本期不作为抽取目标"
        else:
            value = "中"
            advice = "仅作占位比较"
        rows.append(
            {
                "stage": stage,
                "label": item.get("label") or stage,
                "pull_cost": item.get("pull_cost", ""),
                "value": value,
                "advice": advice,
                "reached": reached,
                "placeholder": True,
            }
        )
    return rows


def _check(label: str, value: int | None, target: Any) -> dict[str, Any]:
    try:
        target_int = int(float(target))
    except (TypeError, ValueError):
        target_int = 0
    ok = value is not None and value >= target_int
    warning = "" if ok else f"{label}未达标：{value if value is not None else '未录入'} / {target_int}"
    return {"label": label, "value": value, "target": target_int, "ok": ok, "warning": warning}


def _stage_tuple(value: str) -> tuple[int, int]:
    try:
        left, right = str(value).split("+", 1)
        return int(left), int(right)
    except (TypeError, ValueError):
        return -1, 0

