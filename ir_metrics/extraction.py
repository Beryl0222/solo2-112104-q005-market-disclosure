"""从披露文本中抽取指标数值及其口径要素。

抽取基于词典与分句规则，针对合成披露文本设计；每条数值保留原文片段，
便于答复人员回溯来源段落。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import PeriodType

#: 指标词典：长词在前，避免“营收”截断“营业收入”
METRIC_LEXICON = (
    "营业收入",
    "活跃用户",
    "服务量",
    "净利润",
    "订单量",
    "门店数",
    "客单价",
    "用户数",
    "毛利率",
    "营收",
    "毛利",
)

#: 组织范围 / 业务板块词典：长词在前，避免“直营”截断“直营网点”
SCOPE_LEXICON = (
    "直营网点",
    "线上业务",
    "线下业务",
    "集团整体",
    "加盟店",
    "全渠道",
    "直营",
    "加盟",
    "线上",
    "线下",
    "整体",
    "集团",
)

#: 单位模式：长单位在前
UNIT_PATTERN = "万人次|个百分点|万人|人次|亿元|万元|元|家|%"

VALUE_RE = re.compile(
    rf"(?P<approx>约|近|超过|不足|超)?\s*(?P<num>\d+(?:\.\d+)?)\s*(?P<unit>{UNIT_PATTERN})"
)

CUMULATIVE_MARK = "累计"
SINGLE_QUARTER_MARKS = ("单季", "当季", "本季度")
POINT_IN_TIME_MARK = "截至"

#: 文本期间线索 → 期间后缀
PERIOD_HINTS = (
    ("上半年", "H1"),
    ("下半年", "H2"),
    ("一季度", "Q1"),
    ("二季度", "Q2"),
    ("三季度", "Q3"),
    ("四季度", "Q4"),
    ("全年", "FY"),
)

# 注意：不含英文句点，避免拆散小数（如 17.8）
CLAUSE_SPLIT_RE = re.compile(r"[，。；！？,;!?]")


@dataclass
class Mention:
    """文本中识别到的一处数值及其口径线索。"""

    metric: str | None
    value: float
    unit: str | None
    period: str | None  # 记录层面的期间（如 2026H1）
    period_hint: str | None  # 文本内的期间线索（如 H1）
    period_type: PeriodType
    scope: str | None
    approx: bool
    span: str
    source_text: str
    notes: list[str] = field(default_factory=list)


def _clauses(text: str) -> list[str]:
    return [c for c in CLAUSE_SPLIT_RE.split(text) if c.strip()]


def _find_lexicon(clause: str, lexicon: tuple[str, ...]) -> str | None:
    for word in lexicon:
        if word in clause:
            return word
    return None


def _period_hint(clause: str) -> str | None:
    for word, suffix in PERIOD_HINTS:
        if word in clause:
            return suffix
    return None


def _period_type(clause: str, hint: str | None) -> PeriodType:
    if CUMULATIVE_MARK in clause:
        return PeriodType.CUMULATIVE
    if any(mark in clause for mark in SINGLE_QUARTER_MARKS):
        return PeriodType.SINGLE_QUARTER
    if hint is not None:
        if hint.startswith("Q"):
            return PeriodType.SINGLE_QUARTER
        return PeriodType.CUMULATIVE  # 上半年 / 下半年 / 全年
    if POINT_IN_TIME_MARK in clause:
        return PeriodType.POINT_IN_TIME
    return PeriodType.UNKNOWN


def extract_mentions(record: dict) -> list[Mention]:
    """从一条披露记录中抽取数值及其口径要素。

    更正类记录允许出现未点名指标的数值（如“上半年累计口径为 17.8 万人次”），
    其指标与范围留空，由注册环节匹配既有口径后继承。
    """
    text = record.get("text", "")
    kind = record.get("kind", "")
    record_period = record.get("period") or None
    if record_period == "unknown":
        record_period = None
    mentions: list[Mention] = []
    for clause in _clauses(text):
        hint = _period_hint(clause)
        period_type = _period_type(clause, hint)
        scope = _find_lexicon(clause, SCOPE_LEXICON)
        metric = _find_lexicon(clause, METRIC_LEXICON)
        for match in VALUE_RE.finditer(clause):
            if metric is None and kind != "correction":
                # 无指标名的数值不归属任何指标（更正除外）
                continue
            notes: list[str] = []
            if hint and record_period and not record_period.endswith(hint):
                notes.append(
                    f"文本期间线索({hint})与记录期间({record_period})不一致"
                )
            mentions.append(
                Mention(
                    metric=metric,
                    value=float(match.group("num")),
                    unit=match.group("unit"),
                    period=record_period,
                    period_hint=hint,
                    period_type=period_type,
                    scope=scope,
                    approx=bool(match.group("approx")),
                    span=match.group(0).strip(),
                    source_text=text,
                    notes=notes,
                )
            )
    return mentions
