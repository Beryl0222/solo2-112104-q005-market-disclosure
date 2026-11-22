import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from ir_metrics.queries import citable_items, pending_items, verify_draft
from ir_metrics.registry import Registry

DATA = Path(__file__).parents[1] / "data" / "market.json"
ANSWER_SPEC = {
    "id": "ans-1",
    "text": "截至六月末，直营网点累计服务量为 18 万人次。",
    "after": "market-1",
    "approved": True,
}


def build(answers=()):
    records = json.loads(DATA.read_text(encoding="utf-8"))
    return Registry.from_records(records, answers=answers)


class CitableItemsTests(unittest.TestCase):
    def test_citable_excludes_superseded_and_analyst(self):
        reg = build()
        ids = [o.id for o in citable_items(reg)]
        self.assertIn("obs-market-3-1", ids)  # 更正后的现行值
        self.assertIn("obs-market-2-1", ids)  # 单季口径仍有效
        self.assertIn("obs-market-5-1", ids)  # 板块口径仍有效
        self.assertNotIn("obs-market-1-1", ids)  # 已被更正
        self.assertNotIn("obs-market-6-1", ids)  # 分析人员推断

    def test_citable_items_carry_full_context(self):
        reg = build()
        for obs in citable_items(reg):
            self.assertTrue(obs.metric)
            self.assertTrue(obs.unit)
            self.assertTrue(obs.speaker)
            self.assertTrue(obs.source_text)


class PendingItemsTests(unittest.TestCase):
    def test_pending_lists_impacted_answer_with_change_source(self):
        reg = build(answers=[ANSWER_SPEC])
        pend = pending_items(reg)
        self.assertIn("ans-1", [a.id for a in pend["answers"]])
        task = next(t for t in pend["tasks"] if t.subject == "ans-1")
        self.assertEqual(task.change_source, "market-3")
        self.assertEqual(task.reason, "已审核答复的引用被更正")

    def test_no_pending_when_no_answers(self):
        reg = build()
        pend = pending_items(reg)
        self.assertEqual(pend["answers"], [])
        self.assertEqual(pend["observations"], [])


class VerifyDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = build()

    def test_current_value_ok(self):
        results = verify_draft(self.reg, "上半年直营网点累计服务量为 17.8 万人次。")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].status, "有效依据")
        self.assertEqual(results[0].observation_id, "obs-market-3-1")

    def test_stale_value_flagged_with_change_source(self):
        results = verify_draft(self.reg, "上半年直营网点累计服务量为 18 万人次。")
        self.assertEqual(results[0].status, "已被更正")
        self.assertEqual(results[0].observation_id, "obs-market-1-1")
        self.assertEqual(results[0].change_source, "market-3")
        self.assertIn("17.8", results[0].detail)

    def test_single_quarter_value_still_valid(self):
        results = verify_draft(self.reg, "二季度直营网点服务量约 7 万人次。")
        self.assertEqual(results[0].status, "有效依据")
        self.assertEqual(results[0].observation_id, "obs-market-2-1")

    def test_segment_value_valid_under_own_scope(self):
        results = verify_draft(self.reg, "二季度线上业务服务量约 3 万人次。")
        self.assertEqual(results[0].status, "有效依据")
        self.assertEqual(results[0].observation_id, "obs-market-5-1")

    def test_analyst_value_low_evidence(self):
        results = verify_draft(self.reg, "三季度直营网点服务量约 7.5 万人次。")
        self.assertEqual(results[0].status, "证据级别不足")
        self.assertEqual(results[0].observation_id, "obs-market-6-1")

    def test_unknown_metric_unverified(self):
        results = verify_draft(self.reg, "上半年直营网点累计客单价为 200 元。")
        self.assertEqual(results[0].status, "无对应依据")
        self.assertIsNone(results[0].observation_id)

    def test_value_mismatch_reports_current_value(self):
        results = verify_draft(self.reg, "二季度直营网点服务量约 8 万人次。")
        self.assertEqual(results[0].status, "数值与现行口径不符")
        self.assertIn("7", results[0].detail)

    def test_multiple_values_checked_independently(self):
        results = verify_draft(
            self.reg,
            "上半年直营网点累计服务量为 17.8 万人次，二季度直营网点服务量约 8 万人次。",
        )
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].status, "有效依据")
        self.assertEqual(results[1].status, "数值与现行口径不符")


if __name__ == "__main__":
    unittest.main()
