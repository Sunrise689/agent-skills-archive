---
name: o-research-hub
description: 研枢——科研流程域编排节点（O型）：系统综述、领域调研、文献筛选、论文成稿、引用校验、选刊与投稿前审查等科研流程编排时激活。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-research-hub/skill
---

# 研枢（o-research-hub）

## 用途与触发场景

当用户提出系统综述、领域调研或文献筛选任务，或需要把研究构想推进到论文成稿、投稿准备时，激活研枢。用户要求跨环节完成引用校验、选刊或投稿前审查时，也由研枢编排。

研枢负责拆解科研任务，组织检索、筛选、综合、写作与投稿检查，并检查各阶段交付是否衔接完整。

## 编排流程

1. **判定任务路径并定研究框架。** 领域侦察任务调用 `deep-research-framework`，明确研究问题、来源范围和证据组织方式；系统综述或论文出版流程调用 `slr-prisma`，明确纳排标准、筛选流程和报告要求。
2. **检索并筛选文献。** 根据框架调用 `search-lit` 开始检索，并按需组织引文追溯、全文获取、相关性评估和问题核对；系统综述按预定纳排标准执行筛选。
3. **综合证据并形成稿件。** 按任务调用文献综合、论文写作、图表制作和引用管理成员，确保稿件内容与已筛选的证据相对应。
4. **检查交付并收口。** 按需完成参考文献校验、选刊和投稿前审查；由研枢核对阶段产物与用户目标是否一致，整理交付及尚待用户决定的事项。

## 下辖M

- **deep-research-framework** —— 适用于领域侦察、研究问题尚待拆解的调研任务；产出研究问题拆分、来源范围与证据组织框架，并可进一步编排检索和筛选成员。
- **slr-prisma** —— 适用于系统综述或需要规范筛选、报告的论文出版流程；产出纳排标准、筛选流程与报告闸门，并编排综述、写作、图表、引用、选刊和审查成员。

## 核心T成员

- search-lit —— 执行文献检索，作为任务进场时的直接检索入口。
- citation-chaining-guide —— 沿引用关系追溯相关研究，扩展检索线索。
- fulltext-retrieval —— 获取候选文献全文，支持后续评估与筛选。
- Evaluating Paper Relevance —— 评估文献与研究问题的相关性。
- five-questions —— 用问题清单核对研究内容和证据。
- literature-review-builder —— 汇总筛选结果，组织文献综述内容。
- paper-write —— 按研究材料与证据撰写论文。
- figure-composer —— 根据论文内容组织图表。
- cite —— 整理稿件中的引用与参考文献。
- validate-bib@brycewang-stanford__Auto-Empirical-Research-Skills —— 校验参考文献信息。
- find-journal —— 根据论文方向查找候选期刊。
- paper-review-lite —— 在交付前进行论文审查。

## 四类边

- **O→T**
  - 任务进场时直调 `search-lit`。
  - 交付前直调 `paper-review-lite`。
- **O→M**
  - 领域侦察 → `deep-research-framework`。
  - 系统综述或论文出版流程 → `slr-prisma`。
- **M→T**
  - `deep-research-framework` → `search-lit`、`citation-chaining-guide`、`fulltext-retrieval`、`Evaluating Paper Relevance`、`five-questions`。
  - `slr-prisma` → `literature-review-builder`、`paper-write`、`figure-composer`、`cite`、`validate-bib@brycewang-stanford__Auto-Empirical-Research-Skills`、`find-journal`、`paper-review-lite`。
- **T↔T**
  - `search-lit` ↔ `citation-chaining-guide`。
  - `fulltext-retrieval` ↔ `Evaluating Paper Relevance`。
  - `literature-review-builder` ↔ `paper-write`。
  - `paper-write` ↔ `figure-composer`。
  - `cite` ↔ `validate-bib@brycewang-stanford__Auto-Empirical-Research-Skills`。

## 边界与升级

研枢负责科研流程编排和阶段交付验收，不替代研究者作出学术结论、确认事实或承担作者责任。超出检索、综述、写作与投稿检查范围的专业分析，交由相应领域工具或用户处理。

成员缺失时，说明缺失的环节及其对交付的影响，并继续完成可独立推进的部分；关键成员无法调用或连续卡住时，暂停依赖该成员的后续步骤，向用户报告阻塞点和可选的替代路径。

## 值守红线

不替主人做付费、登录或对外发布动作。任务涉及这些动作时，先停下来问；获准前不执行。
