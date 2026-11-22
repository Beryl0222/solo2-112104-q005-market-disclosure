"""数据模型：数值观测、答复、复核任务与证据级别。"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class EvidenceLevel(enum.IntEnum):
    """证据级别：数值相同、级别不同，不能据此认定口径一致。"""

    ANALYST_INFERENCE = 1  # 分析人员推断
    MANAGEMENT_ORAL = 2  # 管理层口头解释
    FORMAL_DISCLOSURE = 3  # 公告披露 / 正式更正

    @property
    def label(self) -> str:
        return {
            EvidenceLevel.ANALYST_INFERENCE: "分析人员推断",
            EvidenceLevel.MANAGEMENT_ORAL: "管理层口头解释",
            EvidenceLevel.FORMAL_DISCLOSURE: "公告披露",
        }[self]


#: 记录类型 → 证据级别
RECORD_EVIDENCE = {
    "announcement": EvidenceLevel.FORMAL_DISCLOSURE,
    "correction": EvidenceLevel.FORMAL_DISCLOSURE,
    "qa": EvidenceLevel.MANAGEMENT_ORAL,
    "analyst_note": EvidenceLevel.ANALYST_INFERENCE,
}

#: 记录类型 → 默认发言主体（记录可携带 speaker 字段覆盖）
DEFAULT_SPEAKER = {
    "announcement": "公司（公告披露）",
    "correction": "公司（正式更正）",
    "qa": "管理层（业绩问答）",
    "analyst_note": "分析人员（外部推断）",
}

#: 可对外引用的最低证据级别
CITABLE_MIN = EvidenceLevel.MANAGEMENT_ORAL


class PeriodType(enum.Enum):
    """期间口径：同一简称可能是累计量或单季量。"""

    CUMULATIVE = "累计"
    SINGLE_QUARTER = "单季度"
    POINT_IN_TIME = "时点"
    UNKNOWN = "未明"


class ObsStatus(enum.Enum):
    CURRENT = "现行有效"
    SUPERSEDED = "已被更正"
    PENDING = "待核"


@dataclass
class Observation:
    """一条数值观测：数值与其完整口径、发言主体、来源段落绑定。"""

    id: str
    record_id: str
    record_kind: str
    evidence: EvidenceLevel
    speaker: str
    metric: str | None
    value: float
    unit: str | None
    period: str | None
    period_type: PeriodType
    scope: str | None
    approx: bool = False
    source_text: str = ""
    span: str = ""
    status: ObsStatus = ObsStatus.CURRENT
    superseded_by: str | None = None
    supersedes: list[str] = field(default_factory=list)
    inherited: tuple[str, ...] = ()  # 更正时从被替换观测继承的口径要素
    notes: tuple[str, ...] = ()

    @property
    def citable(self) -> bool:
        return self.status is ObsStatus.CURRENT and self.evidence >= CITABLE_MIN

    def caliber(self) -> str:
        """口径摘要：指标 / 期间 / 期间口径 / 组织范围 / 单位。"""
        parts = [
            self.metric or "指标未明",
            self.period or "期间未明",
            self.period_type.value,
            self.scope or "范围未明",
            self.unit or "单位未明",
        ]
        return " / ".join(parts)


@dataclass
class Answer:
    """已登记答复：引用不被改写，引用依据被更正时转为待核。"""

    id: str
    text: str
    citation_ids: list[str]
    approved: bool
    status: str  # "有效" / "待核"
    change_source: str | None = None
    problems: list[str] = field(default_factory=list)


@dataclass
class ReviewTask:
    """待核任务：说明原因、涉及对象与变更来源。"""

    id: str
    reason: str
    change_source: str
    subject: str
    detail: str


@dataclass
class CheckResult:
    """拟引用文本中单个数值的校验结果。"""

    span: str
    value: float
    unit: str | None
    status: str  # 有效依据 / 已被更正 / 数值与现行口径不符 / 证据级别不足 / 无对应依据
    observation_id: str | None
    detail: str
    change_source: str | None
