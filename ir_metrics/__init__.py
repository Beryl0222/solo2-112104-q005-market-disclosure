"""投资者关系指标口径与引用管理。

从公告、业绩问答与正式更正中提取经营指标数值，维护口径、证据级别与
更正血缘，支持可引用项查询、待核项追踪与拟引用文本校验。

本项目仅使用合成披露文本演示口径管理方法，不构成投资建议。
"""

from .comparability import ComparabilityReport, assess
from .extraction import Mention, extract_mentions
from .models import (
    Answer,
    CheckResult,
    EvidenceLevel,
    Observation,
    ObsStatus,
    PeriodType,
    ReviewTask,
)
from .queries import citable_items, pending_items, resolve_mention, verify_draft
from .registry import Registry

__all__ = [
    "Answer",
    "CheckResult",
    "ComparabilityReport",
    "EvidenceLevel",
    "Mention",
    "Observation",
    "ObsStatus",
    "PeriodType",
    "Registry",
    "ReviewTask",
    "assess",
    "citable_items",
    "extract_mentions",
    "pending_items",
    "resolve_mention",
    "verify_draft",
]
