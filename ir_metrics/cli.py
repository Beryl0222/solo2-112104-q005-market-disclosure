"""命令行入口：抽取、可引用项、待核项、答复状态、校验与可比性查询。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .comparability import assess
from .queries import citable_items, pending_items, verify_draft
from .registry import Registry


def _load_json(path: str):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_registry(args) -> Registry:
    records = _load_json(args.data)
    answers = _load_json(args.answers) if args.answers else []
    return Registry.from_records(records, answers)


def _fmt_obs(obs) -> str:
    approx = "约" if obs.approx else ""
    return (
        f"{obs.id} | {obs.metric or '指标未明'} | {approx}{obs.value:g}{obs.unit or ''} | "
        f"{obs.period or '期间未明'} | {obs.period_type.value} | "
        f"{obs.scope or '范围未明'} | {obs.speaker} | {obs.evidence.label} | {obs.status.value}"
    )


def _cmd_extract(reg) -> None:
    if not reg.observations:
        print("（无数值观测）")
        return
    for obs in reg.observations.values():
        print(_fmt_obs(obs))
        print(f"    来源 {obs.record_id}：{obs.source_text}")
        for note in obs.notes:
            print(f"    备注：{note}")


def _cmd_citable(reg) -> None:
    items = citable_items(reg)
    print(f"当前可引用项（{len(items)} 项）：")
    for obs in items:
        print(_fmt_obs(obs))
        print(f"    来源 {obs.record_id}：{obs.source_text}")


def _cmd_pending(reg) -> None:
    pend = pending_items(reg)
    if not pend["tasks"] and not pend["answers"] and not pend["observations"]:
        print("无待核项。")
        return
    if pend["tasks"]:
        print("【待核任务】")
        for task in pend["tasks"]:
            print(
                f"{task.id} | {task.reason} | 对象 {task.subject} | "
                f"变更来源 {task.change_source}"
            )
            print(f"    {task.detail}")
    if pend["answers"]:
        print("【待核答复】")
        for answer in pend["answers"]:
            print(
                f"{answer.id} | 变更来源 {answer.change_source or '-'} | "
                f"引用 {', '.join(answer.citation_ids) or '无'}"
            )
            print(f"    原文：{answer.text}")
    if pend["observations"]:
        print("【待核观测】")
        for obs in pend["observations"]:
            print(_fmt_obs(obs))


def _cmd_answers(reg) -> None:
    if not reg.answers:
        print("（无已登记答复）")
        return
    for answer in reg.answers.values():
        print(
            f"{answer.id} | {answer.status} | 引用 {', '.join(answer.citation_ids) or '无'} | "
            f"变更来源 {answer.change_source or '-'}"
        )
        print(f"    原文：{answer.text}")
        for problem in answer.problems:
            print(f"    问题：{problem}")


def _cmd_audit(reg) -> None:
    for line in reg.audit:
        print(line)


def _cmd_verify(reg, text: str) -> None:
    results = verify_draft(reg, text)
    if not results:
        print("未在文本中识别到带单位的数值。")
        return
    for result in results:
        print(f"数值 {result.value:g}{result.unit or ''}（片段“{result.span}”）→ {result.status}")
        if result.observation_id:
            print(f"  依据：{result.observation_id}")
        print(f"  说明：{result.detail}")
        if result.change_source:
            print(f"  变更来源：{result.change_source}")


def _cmd_compare(reg, obs_a_id: str, obs_b_id: str) -> int:
    a = reg.observations.get(obs_a_id)
    b = reg.observations.get(obs_b_id)
    missing = [oid for oid, obs in ((obs_a_id, a), (obs_b_id, b)) if obs is None]
    if missing:
        print(f"未找到观测：{', '.join(missing)}", file=sys.stderr)
        return 2
    report = assess(a, b)
    print(f"{a.id}（{a.caliber()}，{a.speaker}）")
    print(f"{b.id}（{b.caliber()}，{b.speaker}）")
    print("可比：" + ("是" if report.comparable else "否"))
    for reason in report.reasons:
        print(f"  不可比原因：{reason}")
    for warning in report.warnings:
        print(f"  提示：{warning}")
    if report.comparable and report.delta is not None:
        print(f"  差值（后者-前者）：{report.delta:g}{b.unit or ''}")
    return 0


def main(argv=None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--data", default="data/market.json", help="披露记录 JSON 路径")
    common.add_argument("--answers", default=None, help="已审核答复 JSON 路径（可选）")

    parser = argparse.ArgumentParser(
        prog="ir_metrics",
        description="投资者关系指标口径与引用管理（合成数据，不构成投资建议）",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("extract", parents=[common], help="列出抽取到的全部数值观测")
    sub.add_parser("citable", parents=[common], help="列出当前可引用项")
    sub.add_parser("pending", parents=[common], help="列出待核项及其变更来源")
    sub.add_parser("answers", parents=[common], help="列出已登记答复及其引用状态")
    sub.add_parser("audit", parents=[common], help="列出处理日志")
    p_verify = sub.add_parser("verify", parents=[common], help="校验拟引用文本中的数值")
    p_verify.add_argument("--text", required=True, help="拟引用文本")
    p_compare = sub.add_parser("compare", parents=[common], help="判断两个观测值是否可比")
    p_compare.add_argument("obs_a")
    p_compare.add_argument("obs_b")
    args = parser.parse_args(argv)

    reg = _build_registry(args)
    if args.cmd == "extract":
        _cmd_extract(reg)
    elif args.cmd == "citable":
        _cmd_citable(reg)
    elif args.cmd == "pending":
        _cmd_pending(reg)
    elif args.cmd == "answers":
        _cmd_answers(reg)
    elif args.cmd == "audit":
        _cmd_audit(reg)
    elif args.cmd == "verify":
        _cmd_verify(reg, args.text)
    elif args.cmd == "compare":
        return _cmd_compare(reg, args.obs_a, args.obs_b)
    return 0


if __name__ == "__main__":
    sys.exit(main())
