---
name: o-test-dispatcher
description: 测试调度——测试质量域编排节点（O型）：端到端测试计划、回归测试、可视化对比、无障碍审计、flaky排查、验收矩阵落档时激活。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-test-dispatcher/skill
---

# 测试调度（o-test-dispatcher）

## 用途与触发场景

- **用户说这些话时**："帮我制定端到端测试计划"、"跑一遍回归测试/可视化对比"、"做一次无障碍（a11y/WCAG）审计"、"这些测试时过时不过（flaky），帮我查"、"验收标准都覆盖了吗"、"验收矩阵落一下"。
- **处在这些局面时**：功能改动完成待验收；上线前需要质量把关；CI 中出现随机失败的不稳定测试；需要把业务级验收用例沉淀为可维护的矩阵文件；需要可视化回归或可访问性审计结论。
- **不激活的情形**：纯文档编辑、无验收面的重构、与测试无关的代码评审。

## 编排流程

1. **定策略**：先召唤 qa-expert 制定测试策略——明确测试范围、层级与通过判据；需要成文计划时，再由 qa-test-planner 排布用例集与优先级。
2. **跑执行**：按策略调度 T 执行——playwright-pro 负责端到端执行与可视化回归；test-scenarios 设计功能场景用例，exploratory-testing 补探索盲区；accessibility-tester 做页面级可访问性检查；flake-triage 判定不稳定测试。
3. **调方法层**：与执行并行召唤下辖 M——fr-acceptance 驱动验收矩阵，将业务级验收测试回填到 docs/acceptance/matrix.yaml；a11y-audit@borghei__Claude-Skills 审计 WCAG 合规性并扫描 HTML 中的 a11y 问题。
4. **收口**：由本 O 汇总，verification-discipline 与 meta-verify 复核全部结果（证据齐全、无假绿），产出统一测试报告与缺陷清单，向主人交付结论与产物路径。

## 下辖M

- **fr-acceptance**（同名 T 升格）：**何时调用**——任务涉及业务级验收标准落地、需要维护或更新验收矩阵时。**产出**——驱动验收矩阵，将业务级验收测试回填至 `docs/acceptance/matrix.yaml`。
- **a11y-audit@borghei__Claude-Skills**（同名 T 升格）：**何时调用**——需要 WCAG 合规审计时。**产出**——WCAG 合规性审计结论，以及 HTML 中 a11y 问题清单。

## 核心T成员

- qa-expert —— 测试策略制定：确定测试范围、层级与通过判据
- verification-discipline —— 测试结论纪律复核：证据不齐不判通过
- playwright-pro —— 端到端执行与可视化的回归的主执行成员
- visual-regression-testing —— 截图基线对比，捕捉界面视觉偏差
- accessibility-tester —— 页面级可访问性检查，a11y-audit@borghei__Claude-Skills 的执行成员
- test-scenarios —— 功能场景与用例设计，fr-acceptance 的执行成员
- exploratory-testing —— 无脚本探索测试，补用例设计外的盲区
- qa-test-planner —— 测试计划与用例优先级排布，fr-acceptance 的执行成员
- meta-verify —— 对测试结果做二次验证，防假绿
- flake-triage —— 不稳定测试判定：区分真实缺陷与环境抖动
- false-green-tests —— 识别"通过但未真正覆盖改动"的假绿测试
- flaky-test-fixer —— 对判定为不稳定的用例实施修复

## 四类边

- **O→T**：qa-expert（测试策略制定）；playwright-pro（端到端执行与可视化回归）；flake-triage（不稳定测试判定）
- **O→M**：fr-acceptance（验收矩阵回填）；a11y-audit@borghei__Claude-Skills（可访问性审计）
- **M→T**：fr-acceptance→qa-test-planner、test-scenarios；a11y-audit@borghei__Claude-Skills→accessibility-tester
- **T↔T**：qa-expert↔playwright-pro；test-scenarios↔exploratory-testing；visual-regression-testing↔flake-triage；qa-test-planner↔verification-discipline

## 边界与升级

- **不归它管**：被测功能的开发与缺陷修复本身（本 O 只产出测试结论与缺陷清单，改不改、怎么改归实现侧）；性能压测等未列入入口条件的专项；上线与发布决策。
- **成员缺失时降级**：fr-acceptance 缺失，由 qa-test-planner 手工维护验收清单；a11y-audit@borghei__Claude-Skills 缺失，由 accessibility-tester 直接产出审计报告；任一 T 缺失，沿四类边找邻接成员接力顶位。
- **成员卡住时**：先在名单内换同角色备选；仍卡住则中止该分支、保留已取得的证据，上抛主人重新定编排，不自行扩权。
- **入口条件不满足**：不激活本 O，直接告知主人该任务不属于本 O 范围。

## 值守红线

- 不替主人做**付费、登录、对外发布**三类动作：购买测试云服务或额度、注册/登录第三方测试平台、将测试报告或产物发布到外部渠道——涉这些一律先停下来问。
- 不擅自修改被测系统代码，不删除或跳过失败用例来"让测试通过"；调整测试配置前先说明。
- 结论必须基于实际执行证据，不编造、不外推测试结果。
