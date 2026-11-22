# 投资者说明文本中的指标口径与更正追踪

本项目整理投资者关系团队要从公告和问答记录整理可引用的经营指标。相同简称可能代表累计量或单季量，管理层更正常只针对某个期间；只摘取数字而不保存口径和说话主体，会让后续答复把不同范围的指标当成趋势变化。

演练资料位于 `data/market.json`，内容为合成记录，保留不同来源的原始表述和修订关系。项目环境使用 Python 3.11 标准库。

## 能力概览

- **数值抽取**（`ir_metrics/extraction.py`）：从公告、业绩问答、正式更正、分析记录中抽取数值。每个数值关联指标、单位、期间（累计/单季）、组织范围（含业务板块）、发言主体与来源段落。
- **更正血缘**（`ir_metrics/registry.py`）：正式更正只替换匹配口径的现行数值，其他期间、其他范围不受影响；未匹配或口径不唯一的更正转为待核，不做猜测。已被审核答复引用的数值不会被改写或删除，答复转为待核并记录变更来源。
- **证据级别**（`ir_metrics/models.py`）：公告披露 > 管理层口头解释 > 分析人员推断。分析人员推断保留在册但不进入可引用项；数值相同也不据此认定口径一致。
- **可比性判断**（`ir_metrics/comparability.py`）：缺少单位或组织范围、期间口径不一致时给出不可比原因，不自动计算涨跌；口径完全一致时才给出差值。
- **答复查询**（`ir_metrics/queries.py`）：当前可引用项、待核项及其变更来源、拟引用文本校验。

## 命令行用法

```bash
python3 -m ir_metrics extract                                   # 全部数值观测及口径
python3 -m ir_metrics citable                                   # 当前可引用项
python3 -m ir_metrics pending --answers data/answers.json       # 待核项与变更来源
python3 -m ir_metrics answers --answers data/answers.json       # 已登记答复状态
python3 -m ir_metrics verify --text "上半年直营网点累计服务量为 18 万人次。"
python3 -m ir_metrics compare obs-market-3-1 obs-market-2-1     # 可比性判断
python3 -m ir_metrics audit                                     # 处理日志
```

`--data` 指定披露记录（默认 `data/market.json`）。`--answers` 指定已审核答复清单，其中 `after` 字段表示该答复在某条记录处理完成后登记，用于复现“先引用、后更正”的时间线：`data/answers.json` 中的答复在 `market-1` 之后审核通过，`market-3` 更正到达后即转为待核，原文与引用保持不变。

## 本地检查

```bash
python3 -m unittest discover -s tests -v
```

本项目仅使用合成披露文本演示口径管理方法，不构成投资建议。
