import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from ir_metrics.extraction import extract_mentions
from ir_metrics.models import PeriodType

DATA = Path(__file__).parents[1] / "data" / "market.json"


def load_records():
    return {r["id"]: r for r in json.loads(DATA.read_text(encoding="utf-8"))}


class ExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_records()

    def test_announcement_extracts_full_caliber(self):
        mentions = extract_mentions(self.records["market-1"])
        self.assertEqual(len(mentions), 1)
        m = mentions[0]
        self.assertEqual(m.metric, "服务量")
        self.assertEqual(m.scope, "直营网点")
        self.assertEqual(m.value, 18.0)
        self.assertEqual(m.unit, "万人次")
        self.assertEqual(m.period, "2026H1")
        self.assertEqual(m.period_type, PeriodType.CUMULATIVE)
        self.assertFalse(m.approx)
        self.assertIn("18 万人次", m.source_text)

    def test_qa_single_quarter_and_approx(self):
        mentions = extract_mentions(self.records["market-2"])
        self.assertEqual(len(mentions), 1)
        m = mentions[0]
        self.assertEqual(m.period_type, PeriodType.SINGLE_QUARTER)
        self.assertEqual(m.period_hint, "Q2")
        self.assertTrue(m.approx)
        self.assertEqual(m.value, 7.0)

    def test_correction_value_without_metric_name(self):
        mentions = extract_mentions(self.records["market-3"])
        self.assertEqual(len(mentions), 1)
        m = mentions[0]
        self.assertIsNone(m.metric)  # 指标留待注册环节继承
        self.assertEqual(m.value, 17.8)
        self.assertEqual(m.unit, "万人次")
        self.assertEqual(m.period_type, PeriodType.CUMULATIVE)
        self.assertEqual(m.period_hint, "H1")

    def test_no_change_statement_yields_no_mention(self):
        # “二季度单季数据不变”不含数值，不应产生观测
        mentions = extract_mentions(self.records["market-3"])
        self.assertNotIn("不变", " ".join(m.span for m in mentions))

    def test_analyst_note_without_numbers_yields_nothing(self):
        self.assertEqual(extract_mentions(self.records["market-4"]), [])

    def test_segment_scope_extracted(self):
        mentions = extract_mentions(self.records["market-5"])
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].scope, "线上业务")
        self.assertEqual(mentions[0].value, 3.0)

    def test_analyst_numeric_estimate_extracted(self):
        mentions = extract_mentions(self.records["market-6"])
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0].value, 7.5)
        self.assertTrue(mentions[0].approx)

    def test_period_hint_mismatch_noted(self):
        record = {
            "id": "x-1",
            "kind": "qa",
            "period": "2026Q3",
            "text": "二季度直营网点服务量约 7 万人次。",
        }
        mentions = extract_mentions(record)
        self.assertEqual(len(mentions), 1)
        self.assertTrue(any("不一致" in note for note in mentions[0].notes))


if __name__ == "__main__":
    unittest.main()
