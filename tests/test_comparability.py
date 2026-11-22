import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from ir_metrics.comparability import assess
from ir_metrics.models import EvidenceLevel, Observation, PeriodType


def make_obs(
    obs_id="obs-x-1",
    metric="服务量",
    value=1.0,
    unit="万人次",
    period="2026H1",
    period_type=PeriodType.CUMULATIVE,
    scope="直营网点",
    evidence=EvidenceLevel.FORMAL_DISCLOSURE,
):
    return Observation(
        id=obs_id,
        record_id=obs_id,
        record_kind="announcement",
        evidence=evidence,
        speaker="测试主体",
        metric=metric,
        value=value,
        unit=unit,
        period=period,
        period_type=period_type,
        scope=scope,
    )


class ComparabilityTests(unittest.TestCase):
    def test_cumulative_vs_single_quarter_not_comparable(self):
        a = make_obs("obs-a", value=18.0)
        b = make_obs("obs-b", value=7.0, period="2026Q2",
                     period_type=PeriodType.SINGLE_QUARTER)
        report = assess(a, b)
        self.assertFalse(report.comparable)
        self.assertTrue(any("期间口径" in r for r in report.reasons))
        self.assertIsNone(report.delta)  # 不自动计算涨跌

    def test_missing_unit_blocks_comparison(self):
        a = make_obs("obs-a", unit=None)
        b = make_obs("obs-b")
        report = assess(a, b)
        self.assertFalse(report.comparable)
        self.assertTrue(any("缺少单位" in r for r in report.reasons))
        self.assertIsNone(report.delta)

    def test_missing_scope_blocks_comparison(self):
        a = make_obs("obs-a", scope=None)
        b = make_obs("obs-b")
        report = assess(a, b)
        self.assertFalse(report.comparable)
        self.assertTrue(any("组织范围" in r for r in report.reasons))

    def test_same_value_different_scope_not_consistent(self):
        # 数值相同也不能据此认定口径一致
        a = make_obs("obs-a", value=5.0)
        b = make_obs("obs-b", value=5.0, scope="线上业务")
        report = assess(a, b)
        self.assertFalse(report.comparable)
        self.assertTrue(any("数值相同" in w for w in report.warnings))

    def test_unknown_period_type_blocks_comparison(self):
        a = make_obs("obs-a", period_type=PeriodType.UNKNOWN)
        b = make_obs("obs-b")
        report = assess(a, b)
        self.assertFalse(report.comparable)
        self.assertTrue(any("未明" in r for r in report.reasons))

    def test_comparable_pair_reports_delta(self):
        a = make_obs("obs-a", value=5.0, period="2026H1")
        b = make_obs("obs-b", value=8.0, period="2026H2")
        report = assess(a, b)
        self.assertTrue(report.comparable)
        self.assertEqual(report.delta, 3.0)
        self.assertEqual(report.reasons, [])

    def test_evidence_gap_warns_but_does_not_block(self):
        a = make_obs("obs-a", value=5.0)
        b = make_obs("obs-b", value=5.0, evidence=EvidenceLevel.ANALYST_INFERENCE)
        report = assess(a, b)
        self.assertTrue(report.comparable)
        self.assertTrue(any("证据级别" in w for w in report.warnings))
        self.assertTrue(any("数值相同" in w for w in report.warnings))


if __name__ == "__main__":
    unittest.main()
