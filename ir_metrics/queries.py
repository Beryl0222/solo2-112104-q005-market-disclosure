"""面向答复人员的查询：可引用项、待核项、拟引用文本校验。"""
from __future__ import annotations

from .extraction import Mention, extract_mentions
from .models import (
    CITABLE_MIN,
    CheckResult,
    Observation,
    ObsStatus,
    PeriodType,
)


def citable_items(reg) -> list[Observation]:
    """当前可引用项：现行有效且证据级别达到公司口径门槛的观测。"""
    items = [o for o in reg.observations.values() if o.citable]
    return sorted(items, key=lambda o: (o.metric or "", o.period or "", o.scope or ""))


def pending_items(reg) -> dict:
    """待核项：复核任务、待核答复与待核观测，均携带变更来源。"""
    return {
        "tasks": list(reg.tasks),
        "answers": [a for a in reg.answers.values() if a.status == "待核"],
        "observations": [
            o for o in reg.observations.values() if o.status is ObsStatus.PENDING
        ],
    }


def _caliber_match(obs: Observation, mention: Mention) -> bool:
    """观测口径是否覆盖拟引用数值声明的口径要素。"""
    if mention.metric and obs.metric != mention.metric:
        return False
    if mention.unit and obs.unit != mention.unit:
        return False
    if mention.scope and obs.scope != mention.scope:
        return False
    if mention.period_type is not PeriodType.UNKNOWN and obs.period_type != mention.period_type:
        return False
    if mention.period and obs.period != mention.period:
        return False
    if mention.period_hint and not (obs.period or "").endswith(mention.period_hint):
        return False
    return True


def resolve_mention(reg, mention: Mention) -> CheckResult:
    """把一处拟引用数值解析到登记在册的观测，并给出校验结论。"""
    candidates = [o for o in reg.observations.values() if _caliber_match(o, mention)]

    exact_current = [
        o for o in candidates if o.status is ObsStatus.CURRENT and o.value == mention.value
    ]
    if exact_current:
        obs = max(exact_current, key=lambda o: o.evidence)
        if obs.evidence < CITABLE_MIN:
            return CheckResult(
                mention.span,
                mention.value,
                mention.unit,
                "证据级别不足",
                obs.id,
                f"仅{obs.speaker}提及，{obs.evidence.label}不能作为公司口径对外引用",
                obs.record_id,
            )
        return CheckResult(
            mention.span,
            mention.value,
            mention.unit,
            "有效依据",
            obs.id,
            f"{obs.speaker}，{obs.period or '期间未明'}，原文：{obs.source_text}",
            None,
        )

    exact_stale = [
        o for o in candidates if o.status is ObsStatus.SUPERSEDED and o.value == mention.value
    ]
    if exact_stale:
        old = exact_stale[0]
        new = reg.observations.get(old.superseded_by or "")
        detail = f"该数值已被 {old.superseded_by} 更正"
        if new is not None:
            detail += f"，现行值为 {new.value:g}{new.unit or ''}"
        return CheckResult(
            mention.span,
            mention.value,
            mention.unit,
            "已被更正",
            old.id,
            detail,
            new.record_id if new is not None else None,
        )

    current = [o for o in candidates if o.status is ObsStatus.CURRENT]
    if current:
        obs = current[0]
        return CheckResult(
            mention.span,
            mention.value,
            mention.unit,
            "数值与现行口径不符",
            obs.id,
            f"同口径现行值为 {obs.value:g}{obs.unit or ''}（{obs.record_id}）",
            obs.record_id,
        )

    return CheckResult(
        mention.span,
        mention.value,
        mention.unit,
        "无对应依据",
        None,
        "未找到相同指标/单位/范围/期间的披露记录",
        None,
    )


def verify_draft(reg, text: str) -> list[CheckResult]:
    """校验一段拟引用文本：其中每个数值是否仍对应有效依据。"""
    record = {"id": "draft", "kind": "draft", "period": None, "text": text}
    return [resolve_mention(reg, m) for m in extract_mentions(record)]
