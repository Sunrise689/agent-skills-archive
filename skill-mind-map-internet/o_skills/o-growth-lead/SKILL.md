---
name: o-growth-lead
description: 增长统筹——营销增长域编排节点（O型）：增长计划、新品上市大促、投放内容私域邮件整合、增长瓶颈分析等需统一北极星目标统筹多渠道时激活。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-growth-lead/skill
---

# 增长统筹（o-growth-lead）

## 用途与触发场景

当用户提出“做一份完整增长计划”“规划新品上市或大促”“整合投放、内容、私域和邮件”“分析增长瓶颈”“重新排增长杠杆优先级”等需求时，激活本 O。

适用于需要围绕明确的北极星目标，统筹获客、转化、留存或裂变多个环节的任务；也适用于多个营销 T 分散执行、渠道之间缺少统一目标和衔接方案的局面。

## 编排流程

1. **明确目标与现状。** 收集北极星指标、目标人群、产品定位、预算范围、时间周期、现有渠道表现和约束条件。信息不足时先列出待确认项，不自行假设预算或业务承诺。
2. **先调 M 制定策略。** 调用 `cmo-advisor` 明确品牌定位、市场进入策略和预算分配；调用 `growth-engine-v2` 决定增长杠杆优先级、实验排期和渠道资源投向。根据任务重点调整调用顺序，目标或定位尚未明确时先调用 `cmo-advisor`。
3. **再调 T 形成执行链。** 调用 `marketing-campaign-planner` 将目标和 M 的策略拆为渠道计划、执行事项与衡量指标；再按获客、转化、邮件培育、广告创意、裂变等具体环节调用相关 T，并衔接需要协同的 T。
4. **由本 O 收口。** 整合为一份统一方案，写明目标与基线、优先级、渠道分工、实验安排、衡量指标、依赖关系和待确认事项。明确各 T 的输入与交付物；涉及付费、登录或对外发布时暂停相关动作并询问用户。

## 下辖M

- **growth-engine-v2** —— 需要选择增长杠杆、排序实验或决定渠道资源投向时调用；产出增长机会优先级、实验排期和资源投向建议。
- **cmo-advisor** —— 需要厘清品牌定位、市场进入策略或预算分配时调用；产出定位与市场策略建议，以及预算分配依据。

## 核心T成员

marketing-campaign-planner —— 将增长目标拆解为渠道活动、执行计划和衡量指标。
lead-capture —— 设计潜客获取与线索承接环节。
email-sequence@indranilbanerjee__digital-marketing-pro —— 将新线索转入邮件培育序列。
ads —— 制定广告投放执行内容。
ad-angle-miner —— 挖掘并整理广告创意角度。
influencer-prospecting —— 寻找与筛选潜在合作创作者。
outbound-prospecting —— 规划主动触达潜客的执行方式。
popup-cro-v2 —— 优化弹窗的转化表现。
cro@coreyhaines31__marketingskills —— 诊断并优化转化路径。
referral-programs —— 设计推荐与裂变机制。
positioning-messaging —— 将定位转化为面向目标用户的信息表达。
landing-page-audit —— 检查落地页的转化阻碍并提出改进建议。

## 四类边

- **O→T：** 增长目标 → `marketing-campaign-planner`，拆成渠道执行方案。
- **O→M：** 增长杠杆与实验排期 → `growth-engine-v2`；定位与预算 → `cmo-advisor`。
- **M→T：** `growth-engine-v2` → `ads`、`referral-programs`；`cmo-advisor` → `ad-angle-miner`。
- **T↔T：** `ads` ↔ `ad-angle-miner`；`lead-capture` ↔ `email-sequence@indranilbanerjee__digital-marketing-pro`；`popup-cro-v2` ↔ `cro@coreyhaines31__marketingskills`。

## 边界与升级

本 O 负责组织营销增长策略与执行方案，不替代产品定价、产品开发、销售交付、财务审批或法律审查；也不把未经验证的预测写成已实现的增长结果。

成员缺失时，先说明缺少的能力环节，再从可用成员中选择职责最接近者并标明替代范围；若没有合适成员，向用户列出缺口及所需输入。成员卡住、产出冲突或关键数据不足时，暂停依赖该结论的后续安排，整理具体阻塞点并升级给用户决策。

## 值守红线

不替主人做付费、登录或对外发布动作。执行过程中一旦涉及这些操作，先停下来，向用户说明待执行事项并询问；未获明确授权前不继续。
