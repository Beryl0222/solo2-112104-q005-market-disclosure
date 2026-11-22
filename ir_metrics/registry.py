"""指标注册：按顺序应用披露记录、正式更正与答复引用。

核心约束：
- 正式更正只替换匹配口径（期间、指标、范围、单位、期间类型）的现行观测，
  不能因为较新的数字出现就覆盖其他口径；
- 已被审核答复引用的观测不会被改写或删除，答复转为待核并记录变更来源。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from .extraction import Mention, extract_mentions
from .models import (
    DEFAULT_SPEAKER,
    RECORD_EVIDENCE,
    Answer,
    EvidenceLevel,
    Observation,
    ObsStatus,
    PeriodType,
    ReviewTask,
)
from .queries import resolve_mention


class Registry:
    """指标观测与答复引用的登记处。"""

    def __init__(self) -> None:
        self.observations: dict[str, Observation] = {}
        self.answers: dict[str, Answer] = {}
        self.tasks: list[ReviewTask] = []
        self.audit: list[str] = []
        self._obs_seq: dict[str, int] = defaultdict(int)
        self._task_seq = 0

    @classmethod
    def from_records(cls, records, answers=()) -> "Registry":
        reg = cls()
        reg.ingest(records, answers)
        return reg

    def ingest(self, records, answers=()) -> None:
        """按记录顺序处理；答复可用 after 指定在某条记录之后登记。"""
        by_after: dict[str, list] = defaultdict(list)
        deferred: list = []
        for spec in answers:
            if spec.get("after"):
                by_after[spec["after"]].append(spec)
            else:
                deferred.append(spec)
        for record in records:
            self.ingest_record(record)
            for spec in by_after.get(record.get("id"), []):
                self.register_answer(
                    spec["text"],
                    approved=spec.get("approved", True),
                    answer_id=spec.get("id"),
                )
        for spec in deferred:
            self.register_answer(
                spec["text"],
                approved=spec.get("approved", True),
                answer_id=spec.get("id"),
            )

    def ingest_record(self, record) -> None:
        mentions = extract_mentions(record)
        if record.get("kind") == "correction":
            self._apply_correction(record, mentions)
            return
        for mention in mentions:
            self._add_observation(record, mention)

    def register_answer(self, text, approved=True, answer_id=None) -> Answer:
        """登记一条答复：解析其中数值的引用依据，无法核实的转为待核。"""
        answer_id = answer_id or f"ans-{len(self.answers) + 1}"
        record = {"id": answer_id, "kind": "draft", "period": None, "text": text}
        citations: list[str] = []
        problems: list[str] = []
        for mention in extract_mentions(record):
            result = resolve_mention(self, mention)
            if result.observation_id and result.observation_id not in citations:
                citations.append(result.observation_id)
            if result.status != "有效依据":
                problems.append(f"“{mention.span}”{result.status}：{result.detail}")
        status = "有效" if approved and not problems else "待核"
        answer = Answer(
            id=answer_id,
            text=text,
            citation_ids=citations,
            approved=approved,
            status=status,
            problems=problems,
        )
        self.answers[answer_id] = answer
        self.audit.append(
            f"{answer_id}: 登记答复（状态 {status}，引用 {len(citations)} 项）"
        )
        for problem in problems:
            self._add_task("答复引用待核", answer_id, answer_id, problem)
        return answer

    # ---- 内部 ----

    def _add_observation(
        self,
        record,
        mention: Mention,
        supersedes=(),
        inherited=(),
        status=ObsStatus.CURRENT,
    ) -> Observation:
        kind = record.get("kind", "announcement")
        self._obs_seq[record["id"]] += 1
        obs = Observation(
            id=f"obs-{record['id']}-{self._obs_seq[record['id']]}",
            record_id=record["id"],
            record_kind=kind,
            evidence=RECORD_EVIDENCE.get(kind, EvidenceLevel.MANAGEMENT_ORAL),
            speaker=record.get("speaker") or DEFAULT_SPEAKER.get(kind, "未注明主体"),
            metric=mention.metric,
            value=mention.value,
            unit=mention.unit,
            period=mention.period,
            period_type=mention.period_type,
            scope=mention.scope,
            approx=mention.approx,
            source_text=mention.source_text,
            span=mention.span,
            status=status,
            supersedes=list(supersedes),
            inherited=tuple(inherited),
            notes=tuple(mention.notes),
        )
        self.observations[obs.id] = obs
        self.audit.append(
            f"{record['id']}: 登记 {obs.id}"
            f"（{obs.caliber()}，值 {obs.value:g}{obs.unit or ''}，{obs.speaker}）"
        )
        for note in mention.notes:
            self._add_task("期间线索不一致", record["id"], obs.id, note)
        return obs

    def _apply_correction(self, record, mentions) -> None:
        if not mentions:
            self._add_task(
                "更正未提取到数值", record["id"], record["id"], record.get("text", "")
            )
            return
        for mention in mentions:
            candidates = self._match_current(mention)
            if not candidates:
                obs = self._add_observation(record, mention, status=ObsStatus.PENDING)
                self._add_task(
                    "更正未匹配到既有口径",
                    record["id"],
                    obs.id,
                    "未找到可替换的现行数值，需人工确认归属口径",
                )
                continue
            free_metric = mention.metric is None
            free_scope = mention.scope is None
            ambiguous = (
                free_metric and len({c.metric for c in candidates}) > 1
            ) or (
                free_scope and len({c.scope for c in candidates}) > 1
            )
            if ambiguous:
                obs = self._add_observation(record, mention, status=ObsStatus.PENDING)
                self._add_task(
                    "更正口径不唯一",
                    record["id"],
                    obs.id,
                    f"匹配到 {len(candidates)} 个候选口径，需人工指定，未执行替换",
                )
                continue
            base = candidates[0]
            inherited: list[str] = []
            if free_metric:
                mention = replace(mention, metric=base.metric)
                inherited.append("指标")
            if free_scope:
                mention = replace(mention, scope=base.scope)
                inherited.append("组织范围")
            if mention.period_type is PeriodType.UNKNOWN:
                mention = replace(mention, period_type=base.period_type)
                inherited.append("期间口径")
            new_obs = self._add_observation(
                record,
                mention,
                supersedes=[c.id for c in candidates],
                inherited=inherited,
            )
            for old in candidates:
                old.status = ObsStatus.SUPERSEDED
                old.superseded_by = new_obs.id
                self.audit.append(
                    f"{record['id']}: {old.id}（{old.value:g}{old.unit or ''}）被更正，"
                    f"现行 {new_obs.id}（{new_obs.value:g}{new_obs.unit or ''}）"
                )
                self._flag_impacted_answers(old, record["id"], new_obs)

    def _match_current(self, mention: Mention) -> list[Observation]:
        """更正匹配：仅按更正确认的口径要素筛选现行观测。"""
        out = []
        for obs in self.observations.values():
            if obs.status is not ObsStatus.CURRENT:
                continue
            if mention.period and obs.period != mention.period:
                continue
            if mention.metric and obs.metric != mention.metric:
                continue
            if mention.scope and obs.scope != mention.scope:
                continue
            if mention.unit and obs.unit != mention.unit:
                continue
            if (
                mention.period_type is not PeriodType.UNKNOWN
                and obs.period_type != mention.period_type
            ):
                continue
            out.append(obs)
        return out

    def _flag_impacted_answers(self, old: Observation, change_source: str, new_obs: Observation) -> None:
        """引用被更正观测的已审核答复：转待核、记来源，原文与引用不改写。"""
        for answer in self.answers.values():
            if old.id not in answer.citation_ids or answer.status != "有效":
                continue
            answer.status = "待核"
            answer.change_source = change_source
            answer.problems.append(
                f"引用 {old.id} 已被 {new_obs.id} 更正"
                f"（现行值 {new_obs.value:g}{new_obs.unit or ''}）"
            )
            self._add_task(
                "已审核答复的引用被更正",
                change_source,
                answer.id,
                f"答复原文与引用保持不变；引用 {old.id} 的现行依据为 {new_obs.id}",
            )

    def _add_task(self, reason: str, change_source: str, subject: str, detail: str) -> None:
        self._task_seq += 1
        self.tasks.append(
            ReviewTask(
                id=f"task-{self._task_seq}",
                reason=reason,
                change_source=change_source,
                subject=subject,
                detail=detail,
            )
        )
