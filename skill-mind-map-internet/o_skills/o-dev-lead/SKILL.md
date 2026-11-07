---
name: o-dev-lead
description: 开发统筹——软件工程域编排节点（O型）：功能新建或架构设计、代码重构与质量演进、依赖与数据层变更、版本控制与评审留痕等软件工程任务编排时激活，先调M定方案、按边调T、M收口O汇总。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-dev-lead/skill
---

# 开发统筹（o-dev-lead）

## 用途与触发场景

当用户提出以下需求，或任务处在相应局面时，激活本 O：

- 功能从零新建或改动面较大，需要先定模块划分、接口契约与技术选型，再动手实现。
- 代码库出现技术债：重复逻辑、坏味道堆积、依赖待升级、旧框架需要迁移，需要一条有回归底线的演进路径。
- 数据层变更：库表设计、查询优化、存储结构调整，需要与代码改动联动推进。
- 变更需要收口：走版本控制工作流、完成评审、留下可追溯的变更记录。
- 不激活的情形：单点小修（直接改即可）、部署发布与事故响应（归运维域 O）、测试专项（归测试域 O）、安全审计与授权攻防（归安全域 O）。

## 编排流程

1. **判定任务型并选 M。** 架构与设计问题（模块划分、接口契约、选型取舍）召 `architecture-patterns@diegosouzapw__awesome-omni-skills`；质量演进问题（重构、依赖升级、迁移）召 `refactor-advisor@AtulPurohit__Antigravity-Awesome-Skills`。两类交织时两个 M 都召入，先架构后演进，两个 M 共享同一份代码库现状描述，立场相互冲突时回到本步重新裁定。
2. **建立代码库基线。** 先调 `lint-and-validate@diegosouzapw__awesome-omni-skills` 摸清风格、类型与明显缺陷的现状；涉及数据层时调 `database-architect@diegosouzapw__awesome-omni-skills` 评估库表与查询现状。基线结果作为 M 制定方案的输入，基线未建立不进入下一步。
3. **由 M 按基线定方案并调 T 执行。** 架构 M 依基线产出架构方案与设计约束，按方案调 `api-design-principles`、`clean-code@diegosouzapw__awesome-omni-skills`、`dependency-injection-patterns`、`error-handling-patterns@diegosouzapw__awesome-omni-skills`；并发与异步场景按所用技术栈在 `go-concurrency-patterns@diegosouzapw__awesome-omni-skills` 与 `async-python-patterns@diegosouzapw__awesome-omni-skills` 中选对应者（语言不同、模式相通）；演进 M 依基线产出重构路径与回归底线，按路径调 `code-refactoring-refactor-clean@diegosouzapw__awesome-omni-skills`、`deprecation-and-migration`、`sql-optimization-patterns@diegosouzapw__awesome-omni-skills`。
4. **收口与留痕。** 变更经 `git-workflow-and-versioning` 与 `git-pr-review@diegosouzapw__awesome-omni-skills` 完成评审、合入与变更留痕；由对应 M 核对方案落实情况与回归底线是否守住，O 汇总为可执行结论并列出未决项交用户决定。

## 下辖M

- **architecture-patterns@diegosouzapw__awesome-omni-skills** —— 何时调用：模块划分、接口契约、技术选型、架构取舍类问题。产出：架构方案、设计约束与实现路径清单。
- **refactor-advisor@AtulPurohit__Antigravity-Awesome-Skills** —— 何时调用：重构、依赖升级、旧框架迁移、技术债治理。产出：重构路径、风险点与回归底线。

## 核心T成员

- lint-and-validate@diegosouzapw__awesome-omni-skills —— 进场基线：风格、类型与明显缺陷的现状检查
- database-architect@diegosouzapw__awesome-omni-skills —— 库表设计与数据层现状评估
- api-design-principles —— 接口契约与 API 设计原则
- clean-code@diegosouzapw__awesome-omni-skills —— 整洁代码规范落地
- dependency-injection-patterns —— 依赖注入与模块解耦
- error-handling-patterns@diegosouzapw__awesome-omni-skills —— 错误处理与异常路径设计
- go-concurrency-patterns@diegosouzapw__awesome-omni-skills —— 并发模式（Go 栈代表，模式跨栈相通）
- async-python-patterns@diegosouzapw__awesome-omni-skills —— 异步模式（Python 栈代表，模式跨栈相通）
- sql-optimization-patterns@diegosouzapw__awesome-omni-skills —— 查询与数据访问优化
- code-refactoring-refactor-clean@diegosouzapw__awesome-omni-skills —— 重构执行与坏味道清理
- deprecation-and-migration —— 弃用流程与迁移路径执行
- git-workflow-and-versioning —— 分支策略、版本管理与变更留痕
- git-pr-review@diegosouzapw__awesome-omni-skills —— 评审协作与合入把关

## 四类边

- **O→T**：`lint-and-validate@diegosouzapw__awesome-omni-skills`（进场基线，不经 M 直调）；`git-workflow-and-versioning`（收口留痕，不经 M 直调）
- **O→M**：架构与设计问题 → `architecture-patterns@diegosouzapw__awesome-omni-skills`；质量演进问题 → `refactor-advisor@AtulPurohit__Antigravity-Awesome-Skills`
- **M→T**：
  - `architecture-patterns@diegosouzapw__awesome-omni-skills` → `api-design-principles`、`clean-code@diegosouzapw__awesome-omni-skills`、`dependency-injection-patterns`、`error-handling-patterns@diegosouzapw__awesome-omni-skills`、`go-concurrency-patterns@diegosouzapw__awesome-omni-skills`、`async-python-patterns@diegosouzapw__awesome-omni-skills`、`database-architect@diegosouzapw__awesome-omni-skills`
  - `refactor-advisor@AtulPurohit__Antigravity-Awesome-Skills` → `code-refactoring-refactor-clean@diegosouzapw__awesome-omni-skills`、`deprecation-and-migration`、`sql-optimization-patterns@diegosouzapw__awesome-omni-skills`、`lint-and-validate@diegosouzapw__awesome-omni-skills`、`git-pr-review@diegosouzapw__awesome-omni-skills`
- **T↔T**：
  - `api-design-principles` ↔ `dependency-injection-patterns`
  - `error-handling-patterns@diegosouzapw__awesome-omni-skills` ↔ `clean-code@diegosouzapw__awesome-omni-skills`
  - `go-concurrency-patterns@diegosouzapw__awesome-omni-skills` ↔ `async-python-patterns@diegosouzapw__awesome-omni-skills`
  - `database-architect@diegosouzapw__awesome-omni-skills` ↔ `sql-optimization-patterns@diegosouzapw__awesome-omni-skills`
  - `code-refactoring-refactor-clean@diegosouzapw__awesome-omni-skills` ↔ `deprecation-and-migration`
  - `git-workflow-and-versioning` ↔ `git-pr-review@diegosouzapw__awesome-omni-skills`

## 边界与升级

本 O 负责软件工程任务的编排：定方案、建基线、调度执行、评审收口。不替代用户作出产品决策或验收业务正确性，不处理部署发布、测试专项与安全审计（分别归对应域 O）。成员按所用技术栈选择：并发、异步等跨栈模式类成员以实际栈为准取用，未覆盖的栈沿用同名模式能力并说明局限。

成员缺失或卡住时，按缺失成员记录降级与缺口，不声称同功能互替：`database-architect@diegosouzapw__awesome-omni-skills` 缺失时，`sql-optimization-patterns@diegosouzapw__awesome-omni-skills` 仅可临时承接查询与数据访问侧执行，库表设计与存储选型部分为缺口，停止该部分并上报；`git-pr-review@diegosouzapw__awesome-omni-skills` 缺失时，`git-workflow-and-versioning` 仅可完成合入与留痕，评审环节缺位须补做并记录降级；并发模式成员缺失按所用栈在对端（`go-concurrency-patterns@diegosouzapw__awesome-omni-skills` 与 `async-python-patterns@diegosouzapw__awesome-omni-skills`）取用；其余成员缺失无顶位，停止该环节并上报。架构方案与演进路径相互矛盾时暂停执行，整理矛盾点上报，不自行合并两套方案；基线无法建立（构建失败、依赖不可用）时停止后续步骤，报告阻塞点与所需输入。

## 值守红线

- 不替主人做付费动作：引入付费依赖、升级付费服务、消耗付费额度，一律先停下来问。
- 不替主人做登录动作：OAuth 授权、账号密码输入、验证码处理，一律先停下来问。
- 不替主人做对外发布动作：推送公共仓库、发布包、公开部署，一律先停下来问。
- 仓库内的本地提交、本地分支与本地重构在授权范围内可直接执行，执行后留痕。
