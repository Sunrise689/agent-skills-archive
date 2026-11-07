---
name: o-agent-orchestrator
description: 智能体编排——AI/智能体域编排节点（O型）：需要跨会话记忆、上下文管理、RAG检索问答设计调优排障或技能路由编排时激活，先调M定方案、按边调T、M收口O汇总。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-agent-orchestrator/skill
---

# 智能体编排（o-agent-orchestrator）

## 用途与触发场景

当用户提出以下需求，或任务处在相应局面时，激活本 O：

- 需要让智能体跨会话保留、检索或使用记忆，或遇到上下文过长、信息召回不准、重要内容被截断等问题。
- 需要设计、调整或排查带知识检索能力的智能体，例如用户说“帮我设计一个带 RAG 的智能体”或“检索结果不准，帮我查链路”。
- 任务同时涉及技能路由、记忆或上下文管理、检索调优、证据整理、答案依据核验，需安排技能的调用顺序并明确交付责任。

本 O 根据任务目标和现有信息选择技能与调用顺序，并把检索质量和答案依据核验纳入流程。

## 编排流程

1. **识别问题类型并确定路由。** 判断任务主要涉及跨会话记忆或上下文管理、检索问答设计或排障，还是技能路由。纯技能路由任务可直接调用 `skill-router-v2`。
2. **先调用对应的 M 定方案。** 记忆、跨会话召回或上下文问题交给“记忆与上下文策略”；检索问答设计、调优或排障交给“检索问答链路”。两类问题相互影响时，先后调用两个 M，并让它们共享问题描述、约束和已有证据。
3. **按方案调用所需 T。** 由 M 选择适用的核心 T，避免无目标地调用全部成员。根据任务需要串联记忆管理、上下文处理、检索设计、召回优化和评估；遇到关联问题时，沿四类边补充调用相关 T。
4. **由 M 收口，O 汇总交付。** 对应的 M 整理方案、依据、评估方法和未解决项；若两个 M 都参与，由检索问答链路汇总检索与评估结果，记忆与上下文策略补充上下文和记忆约束。O 汇总为可执行结论，并核对答案依据和检索质量是否有交代。

## 下辖M

- **记忆与上下文策略**：当任务涉及跨会话记忆、上下文构建、窗口管理或上下文过载时调用。产出记忆与上下文处理方案，说明适用技能、调用顺序及需要保留或压缩的信息。
- **检索问答链路**：当任务涉及知识检索问答的设计、优化、排障或质量评估时调用。产出检索链路方案，说明适用技能、关键检索环节、评估方式及答案依据核验要求。

## 核心T成员

- mesh-memory —— 为记忆策略提供网状记忆管理能力。
- openviking-context-database —— 为上下文策略提供上下文数据库相关能力。
- context-engineering@mrgoonie__claudekit-skills —— 处理上下文工程与上下文构建。
- context-engine —— 支持上下文组织与管理。
- sliding-window-chat-truncation —— 处理滑动窗口对话截断。
- skill-router-v2 —— 按任务需求路由到适用技能。
- rag-pipeline-design —— 设计 RAG 检索问答流水线。
- rag-architecture-review —— 审视 RAG 架构与设计选择。
- iterative-retrieval —— 支持迭代式检索。
- top-k-vector-pruning —— 优化向量检索的 top-k 候选筛选。
- summarized-rag-memories —— 处理摘要式 RAG 记忆。
- rag-observability-evals —— 观测和评估 RAG 链路质量。

## 四类边

- **O→T**：O 可因技能路由需求直接调用 `skill-router-v2`。
- **O→M**：跨会话记忆或上下文问题 → 记忆与上下文策略；检索问答设计或排障 → 检索问答链路。
- **M→T**：
  - 记忆与上下文策略 → `mesh-memory`、`openviking-context-database`、`context-engineering@mrgoonie__claudekit-skills`、`context-engine`、`sliding-window-chat-truncation`
  - 检索问答链路 → `rag-pipeline-design`、`rag-architecture-review`、`iterative-retrieval`、`top-k-vector-pruning`、`summarized-rag-memories`、`rag-observability-evals`、`skill-router-v2`
- **T↔T**：
  - `rag-pipeline-design` ↔ `rag-observability-evals`
  - `iterative-retrieval` ↔ `top-k-vector-pruning`
  - `context-engineering@mrgoonie__claudekit-skills` ↔ `sliding-window-chat-truncation`
  - `mesh-memory` ↔ `openviking-context-database`

## 边界与升级

本 O 负责围绕记忆、上下文、知识检索、技能路由和答案依据核验进行编排，不替代业务领域判断，也不把检索到的信息自动视为已核实事实。任务超出这些范围时，说明缺少的能力或证据，并建议转交适合的领域技能或负责人。

所需成员不存在或无法调用时，记录缺失项及其对结果的影响；由对应 M 判断能否用现有成员完成替代方案。若关键成员持续卡住、关键证据缺失，或评估无法支持结论，暂停依赖该环节的结论，向用户说明阻塞点和所需输入。

## 值守红线

不替主人执行付费、登录或对外发布动作。任务涉及这些动作时，先停下来说明具体动作及所需信息，等待主人明确指示后再继续。
