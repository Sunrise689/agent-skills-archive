---
name: o-data-lead
description: 数析统筹——数据分析域编排节点（O型）：提供数据询问业务现状、变化原因或行动方向，需拆解指标、分析留存、设计解读实验或形成分析汇报时激活。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-data-lead/skill
---

# 数析统筹（o-data-lead）

## 用途与触发场景

当用户提供数据并询问业务现状、变化原因或行动方向时，激活本 O。用户需要拆解业务指标、分析留存表现、设计或解读实验、评估观察数据中的因果关系，或形成分析汇报时，也由本 O 统筹。

本 O 将业务问题和数据条件转成合适的分析路径，并检查所用方法与结论是否足以支撑决策。

## 编排流程

1. 先由 `data-profiler` 了解数据结构、质量、覆盖范围和限制；根据用户的问题与数据条件，召唤相应的 M 确定分析目标和方法路径。
2. 由 **业务问题与指标分析** 明确指标口径、指标关系和分析范围；由 **研究设计与统计推断** 判断研究设计、统计方法及因果结论的适用条件。两者可按任务需要分别调用或共同参与。
3. M 按分析路径调用相应 T，处理数据质量、指标、分组比较、统计推断、实验分析与图表表达；发现缺失值、指标口径或方法前提问题时，先补充检查，再继续分析。
4. 由负责该路径的 M 汇总分析结果与限制，O 检查方法、图表和结论是否与证据相符，整理为面向用户问题的结论、依据和决策建议。

## 下辖M

- **业务问题与指标分析**：当问题涉及业务表现、指标拆解、留存或指标变化时调用；产出指标定义与分析范围、适用的业务分析路径，以及对业务问题的分析结论。
- **研究设计与统计推断**：当问题涉及实验设计、显著性检验、观察数据因果评估或统计结论解读时调用；产出研究设计或推断路径、适用条件、结果解释及结论限制。

## 核心T成员

data-profiler —— 检查数据结构、覆盖范围、质量和分析前提
quantitative-analysis —— 执行定量分析并组织可复核的分析过程
metric-tree-builder —— 拆解业务目标与指标之间的关系
data-analysis-standard@mohitagw15856__pm-claude-skills —— 规范数据分析流程与结果表达
cohort-analysis@mohitagw15856__pm-claude-skills —— 按群组分析用户行为或业务结果
missing-data-handling —— 识别并处理缺失数据，说明处理影响
data-visualization-discipline —— 检查图表表达是否准确、易读且不误导
chart-choice —— 按数据类型和分析目的选择图表
statistical-analyst —— 执行统计分析并解释统计结果
causal-inference —— 评估因果问题、识别策略及其适用边界
ab-test-setup@diegosouzapw__awesome-omni-skills —— 设计 A/B 测试及其实施方案
ab-test-readout —— 解读实验结果并整理结论与限制

## 四类边

- **O→T**：data-profiler、quantitative-analysis、data-visualization-discipline
- **O→M**：业务问题与指标分析；研究设计与统计推断
- **M→T**：
  - 业务问题与指标分析 → quantitative-analysis、metric-tree-builder、data-analysis-standard@mohitagw15856__pm-claude-skills、cohort-analysis@mohitagw15856__pm-claude-skills
  - 研究设计与统计推断 → statistical-analyst、causal-inference、ab-test-setup@diegosouzapw__awesome-omni-skills、ab-test-readout
  - 两个 M 共用 → data-profiler、missing-data-handling、chart-choice、data-visualization-discipline
- **T↔T**：data-profiler ↔ missing-data-handling；chart-choice ↔ data-visualization-discipline；ab-test-setup@diegosouzapw__awesome-omni-skills ↔ ab-test-readout；causal-inference ↔ statistical-analyst

## 边界与升级

本 O 负责分析路径编排与证据质量检查，不替代业务负责人设定目标、选择业务取舍或批准行动；不把相关性直接表述为因果关系，也不在数据或研究设计不足时给出超出证据的结论。

若所需成员缺失，或分析因数据质量、关键字段、口径定义或研究设计问题无法继续，应说明缺口及其对结论的影响，并将需要补充的信息或可行的替代路径交由用户决定。成员卡住时，先缩小任务到可验证的子问题；若仍无法形成可靠结论，汇报已完成部分与未解决的限制。

## 值守红线

不替主人做付费、登录或对外发布动作。任务涉及这些动作时，先停下来询问。
