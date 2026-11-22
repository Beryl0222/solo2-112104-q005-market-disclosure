"""口径可比性判断：缺少比较所需的范围或单位时给出不可比原因，
不自动计算涨跌结论；数值相同也不能据此认定口径一致。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .models import Observation, PeriodType


@dataclass
class ComparabilityReport:
    a_id: str
    b_id: str
    comparable: bool
    reasons: list[str] = field(default_factory=list)  # 不可比原因
    warnings: list[str] = field(default_factory=list)  # 提示（证据级别差异等）
    delta: float | None = None  # 仅在口径可比时给出（b - a）


def assess(a: Observation, b: Observation) -> ComparabilityReport:
    reasons: list[str] = []
    warnings: list[str] = []

    if a.metric != b.metric:
        reasons.append(f"指标定义不同：{a.metric or '未明'} ≠ {b.metric or '未明'}")

    if not a.unit or not b.unit:
        reasons.append("缺少单位，无法比较")
    elif a.unit != b.unit:
        reasons.append(f"单位不同：{a.unit} ≠ {b.unit}")

    if not a.scope or not b.scope:
        reasons.append("缺少组织范围，无法确认是否同一口径")
    elif a.scope != b.scope:
        reasons.append(f"组织范围不同：{a.scope} ≠ {b.scope}")

    if a.period_type is PeriodType.UNKNOWN or b.period_type is PeriodType.UNKNOWN:
        reasons.append("期间口径未明（累计/单季未标注）")
    elif a.period_type != b.period_type:
        reasons.append(f"期间口径不同：{a.period_type.value} ≠ {b.period_type.value}")

    if a.evidence != b.evidence:
        warnings.append(f"证据级别不同：{a.evidence.label} vs {b.evidence.label}")

    if a.value == b.value and (reasons or warnings):
        warnings.append("两数值相同，但口径或证据存在差异，不能据此认定一致")

    comparable = not reasons
    delta = round(b.value - a.value, 6) if comparable else None
    return ComparabilityReport(a.id, b.id, comparable, reasons, warnings, delta)
