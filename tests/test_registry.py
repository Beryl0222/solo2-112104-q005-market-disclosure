import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from ir_metrics.models import EvidenceLevel, ObsStatus
from ir_metrics.registry import Registry

DATA = Path(__file__).parents[1] / "data" / "market.json"
ANSWER_SPEC = {
    "id": "ans-1",
    "text": "截至六月末，直营网点累计服务量为 18 万人次。",
    "after": "market-1",
    "approved": True,
}


def load_records():
    return json.loads(DATA.read_text(encoding="utf-8"))


class CorrectionScopeTests(unittest.TestCase):
    def setUp(self):
        self.reg = Registry.from_records(load_records())

    def test_correction_supersedes_only_matching_period(self):
        old = self.reg.observations["obs-market-1-1"]
        new = self.reg.observations["obs-market-3-1"]
        self.assertIs(old.status, ObsStatus.SUPERSEDED)
        self.assertEqual(old.superseded_by, new.id)
        self.assertIs(new.status, ObsStatus.CURRENT)
        self.assertEqual(new.value, 17.8)
        self.assertIn(old.id, new.supersedes)

    def test_correction_inherits_caliber_from_replaced_observation(self):
        new = self.reg.observations["obs-market-3-1"]
        self.assertEqual(new.metric, "服务量")
        self.assertEqual(new.scope, "直营网点")
        self.assertIn("指标", new.inherited)
        self.assertIn("组织范围", new.inherited)
        self.assertIs(new.evidence, EvidenceLevel.FORMAL_DISCLOSURE)
        self.assertIn("更正", new.speaker)

    def test_other_calibers_not_overwritten(self):
        # 单季度口径不受影响
        self.assertIs(self.reg.observations["obs-market-2-1"].status, ObsStatus.CURRENT)
        # 业务板块口径不受影响
        self.assertIs(self.reg.observations["obs-market-5-1"].status, ObsStatus.CURRENT)

    def test_analyst_observation_kept_but_not_citable(self):
        obs = self.reg.observations["obs-market-6-1"]
        self.assertIs(obs.status, ObsStatus.CURRENT)
        self.assertIs(obs.evidence, EvidenceLevel.ANALYST_INFERENCE)
        self.assertFalse(obs.citable)

    def test_qualitative_note_yields_no_observation(self):
        self.assertFalse(
            any(o.record_id == "market-4" for o in self.reg.observations.values())
        )


class ApprovedAnswerProtectionTests(unittest.TestCase):
    def setUp(self):
        self.reg = Registry.from_records(load_records(), answers=[ANSWER_SPEC])

    def test_answer_approved_before_correction(self):
        # 答复在 market-1 之后登记，当时依据有效
        answer = self.reg.answers["ans-1"]
        self.assertEqual(answer.citation_ids, ["obs-market-1-1"])

    def test_correction_flags_answer_without_rewriting(self):
        answer = self.reg.answers["ans-1"]
        self.assertEqual(answer.status, "待核")
        self.assertEqual(answer.change_source, "market-3")
        # 原文与引用保持不变，不被新数字覆盖
        self.assertIn("18 万人次", answer.text)
        self.assertEqual(answer.citation_ids, ["obs-market-1-1"])

    def test_task_records_change_source(self):
        tasks = [t for t in self.reg.tasks if t.subject == "ans-1"]
        self.assertTrue(tasks)
        self.assertTrue(all(t.change_source == "market-3" for t in tasks))


class CorrectionEdgeCaseTests(unittest.TestCase):
    def test_unmatched_correction_becomes_pending(self):
        reg = Registry.from_records(
            [
                {"id": "r1", "kind": "announcement", "period": "2026Q1",
                 "text": "一季度直营网点服务量约 5 万人次。"},
                {"id": "r2", "kind": "correction", "period": "2026Q4",
                 "text": "更正：四季度累计口径为 30 万人次。"},
            ]
        )
        obs = reg.observations["obs-r2-1"]
        self.assertIs(obs.status, ObsStatus.PENDING)
        self.assertTrue(any(t.reason == "更正未匹配到既有口径" for t in reg.tasks))
        # 既有观测不受影响
        self.assertIs(reg.observations["obs-r1-1"].status, ObsStatus.CURRENT)

    def test_ambiguous_correction_does_not_guess(self):
        reg = Registry.from_records(
            [
                {"id": "r1", "kind": "announcement", "period": "2026H1",
                 "text": "上半年直营网点累计服务量为 18 万人次。"},
                {"id": "r2", "kind": "qa", "period": "2026H1",
                 "text": "上半年线上业务累计服务量为 6 万人次。"},
                {"id": "r3", "kind": "correction", "period": "2026H1",
                 "text": "更正：上半年累计口径为 20 万人次。"},
            ]
        )
        obs = reg.observations["obs-r3-1"]
        self.assertIs(obs.status, ObsStatus.PENDING)
        self.assertTrue(any(t.reason == "更正口径不唯一" for t in reg.tasks))
        # 两个候选口径均不被替换
        self.assertIs(reg.observations["obs-r1-1"].status, ObsStatus.CURRENT)
        self.assertIs(reg.observations["obs-r2-1"].status, ObsStatus.CURRENT)

    def test_sequential_corrections_chain(self):
        reg = Registry.from_records(
            [
                {"id": "r1", "kind": "announcement", "period": "2026H1",
                 "text": "上半年直营网点累计服务量为 18 万人次。"},
                {"id": "r2", "kind": "correction", "period": "2026H1",
                 "text": "更正：上半年累计口径为 17.8 万人次。"},
                {"id": "r3", "kind": "correction", "period": "2026H1",
                 "text": "更正：上半年累计口径为 17.6 万人次。"},
            ]
        )
        self.assertIs(reg.observations["obs-r1-1"].status, ObsStatus.SUPERSEDED)
        self.assertIs(reg.observations["obs-r2-1"].status, ObsStatus.SUPERSEDED)
        final = reg.observations["obs-r3-1"]
        self.assertIs(final.status, ObsStatus.CURRENT)
        self.assertEqual(final.value, 17.6)
        self.assertEqual(final.supersedes, ["obs-r2-1"])

    def test_correction_without_value_creates_task(self):
        reg = Registry.from_records(
            [
                {"id": "r1", "kind": "announcement", "period": "2026H1",
                 "text": "上半年直营网点累计服务量为 18 万人次。"},
                {"id": "r2", "kind": "correction", "period": "2026H1",
                 "text": "更正：此前表述有误，详见后续公告。"},
            ]
        )
        self.assertTrue(any(t.reason == "更正未提取到数值" for t in reg.tasks))
        self.assertIs(reg.observations["obs-r1-1"].status, ObsStatus.CURRENT)


if __name__ == "__main__":
    unittest.main()
