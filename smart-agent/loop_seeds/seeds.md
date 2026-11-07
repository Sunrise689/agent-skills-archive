# Smart Agent Loop Seeds v2

> 用途：给 Manager 一组来自多个 Agent 生态、但已经去重和抽象后的 Workflow/Loop 方法空间。
> 规则：种子不是脚本，不指定某题必须使用哪个；Manager 必须依据当前任务风险自主选择、组合、fork 或不使用。为满足变化次数而换方法，视为无效变化。
>
> **产品边界**：这里提炼的是方法契约，不是 Codex、Claude Code、OpenCode、pi、OpenClaw、Hermes 或 DSH 的产品复制品；不吸收 UI、Ticket Bot、Gateway、插件市场、巡航基础设施、闭源私有实现或厂商锁定。
>
> 设计引用格式：`seed_id` + 当前任务信号 + 采用/不采用理由 + 本题改动点。

## Seed 01 · RISK-DESIGN · 风险观察与可检查设计

- 来源锚点：Smart Agent 自有 Manager 设计契约；Codex 公开 Goal 的 Outcome / Constraints / Verification；OpenCode 公开的能力描述选择；Hermes 公开的依赖与任务分解契约。
- 许可证/来源边界：只吸收公开方法语义；Codex CLI 公开仓库为 Apache-2.0，OpenCode 与 Hermes 公开仓库为 MIT；不复制任何产品配置字段、提示词或界面。
- 适用场景：任务风险、边界、依赖或验收方式不清；上一题的方法可能不适用；需要在执行前明确“怎么做才算完成”。
- 步骤骨架：读取任务与现状 → 分类风险/依赖/验收 → 从 catalog 选择零个或多个方法 → 生成带 rationale 的可机读 Workflow/Loop → 由壳校验设计 → 执行。
- 适用信号：语义或边界风险、多个可能执行路径、上一题失败反馈、需要显式 Verification 的任务。
- 可组合点：可与 GATED-DELIVERY 组合，把 Verification 变成独立证据；可与 CAPABILITY-ROUTING 组合，但不得把能力选择当成 Manager 设计的替代品。
- 常见改法：低风险机械任务保留最小 Loop；高风险任务增加 review/revise；依赖复杂时只增加确有信息增益的前置判断，不机械生成任务图。
- 失败模式：把 Goal 当成 Workflow；把一次 JSON 任务图当成 Manager 智能；为了体现“用了 seed”强行加步骤；把产品名当作选择理由。

## Seed 02 · GATED-DELIVERY · 执行—验收—报告闸门

- 来源锚点：Codex 公开 hooks 的事件—判定—回灌契约与结构化输出；OpenClaw 公开 Execute-Verify-Report、完成不等于成功、失败不可静默；当前 Smart Agent 的工具步骤硬闸门。
- 许可证/来源边界：仅提炼公开事件和验收语义；不复制 Codex hooks API、OpenClaw Gateway 或任何产品运行时。
- 适用场景：模型可能自称完成；工具结果需要外部判定；产物需要独立回读、检查或报告。
- 步骤骨架：真实 Execute → 独立 Verify → 按结果放行/改写/阻断 → 只报告已验证结果 → 留存事件、判定和理由。
- 适用信号：缺少 public_check；“完成”没有独立证据；工具结果过长或可能污染上下文；失败被包装为成功。
- 可组合点：与 CLASSIFIED-RECOVERY 组合处理验收失败；与 EVIDENCE-SPIRAL 组合把验收结果带入下一题设计。
- 常见改法：规则判定先行、模型审查兜底；只验证必要子集；反馈过长时落盘并注入路径/摘要；质量类失败可有限返修，安全类失败必须阻断。
- 失败模式：同源自证；只看文件存在不看内容；阻断没有可执行反馈；判定器静默失败；把 hook 变成固定脚本而非可审计契约。

## Seed 03 · EVIDENCE-SPIRAL · 假设—行动—反馈—保留/回滚

- 来源锚点：Smart Agent 现有跨题 parent hash/公开反馈链；Codex 公开 rollout/event replay 与 resume/fork 证据语义；pi 公开生命周期事件、工具尝试终态和有界父子留痕。
- 许可证/来源边界：吸收“事件可回放、方法带版本、失败也留痕”的通用语义；不复制 Codex rollout 格式、pi 内部事件名或具体会话文件布局。
- 适用场景：连续任务重复失败、旧 Loop 可能变成大圆、需要判断一次结构变化是否真的带来收益。
- 步骤骨架：读取当前任务与公开历史 → 提出可检验风险假设 → 采取最小结构变化 → 真实执行并记录全部尝试 → 根据外部反馈保留、合并或回滚 → 将方法与理由作为下一题输入。
- 适用信号：工具被拦、检查失败、同一 Loop 被机械复制、超时恢复、出现新风险类别。
- 可组合点：与 RISK-DESIGN 连接“先设计”；与 GATED-DELIVERY 连接“什么算证据”；与 CLASSIFIED-RECOVERY 连接“失败后怎么继续”。
- 常见改法：只改变一个结构因素；保留父版本和 catalog hash；把重负载证据放路径指针；截断必须显式标记，不得静默丢失。
- 失败模式：随机换流程冒充进化；只记录成功调用；把 hidden 分数传给下一题；把 resume 当策略改进；回滚后能力仍然存在却宣称已回滚。

## Seed 04 · CAPABILITY-ROUTING · 能力描述与最小工具面

- 来源锚点：OpenCode 公开的声明式 Profile、能力描述选择、provider/model 双段寻址和兼容层优先；Hermes 公开的角色目录按能力描述匹配、失败兜底；pi 公开的最小默认工具面、分级暴露和 BYOK 多 provider。
- 许可证/来源边界：只吸收能力契约、目录和暴露语义；不复制 OpenCode agent 名单、配置格式、插件安装运行时、Hermes Kanban/子 Agent 栈或 pi 具体 API。
- 适用场景：工具、Skill、MCP、Worker 或方法选项过多；任务只需要部分能力；需要保持 BYOK 和厂商可替换。
- 步骤骨架：列出能力描述与权限边界 → Manager 根据任务信号选择最小能力面 → 只暴露/激活必要能力 → 记录选择理由与版本 → 真实执行 → 任务结束后收回或保留为可替换方法。
- 适用信号：工具噪声、能力不可见、权限过宽、不同 provider 能力差异、模型反复尝试不存在的工具。
- 可组合点：与 RISK-DESIGN 组合进行任务级选择；与 GATED-DELIVERY 组合做动态门控；与 EVIDENCE-SPIRAL 组合比较不同能力面的实际收益。
- 常见改法：先只读能力，确有信号再开放写/执行；描述不清时落默认执行体；provider 特有参数透传，不在 Core 写厂商分支。
- 失败模式：把“能力目录选择”误当 Manager 设计；全量暴露造成上下文噪声；能力拒绝只靠模型自觉；默认兜底缺失；把多 provider 变成厂商绑定。

## Seed 05 · CLASSIFIED-RECOVERY · 分类恢复与副作用保护

- 来源锚点：OpenClaw 公开的失败分类、续跑而非重放、writer fencing、幂等提交、预算/终态契约；Hermes 公开的状态机、证据过期和父子预算；Codex 公开的 resume/fork 权限继承与失败回放语义。
- 许可证/来源边界：只吸收状态和恢复契约；不复制 OpenClaw Gateway/cron/SQLite、Hermes Kanban dispatcher 或 Codex Cloud/订阅机制。
- 适用场景：超时、abort、工具错误、额度耗尽或中断后，无法立即确定副作用是否发生。
- 步骤骨架：先分类失败 → 检查副作用与已落盘证据 → 无副作用且可重试时有限退避 → 有副作用或不确定时续跑而非重放 → 旧 attempt 失去写权限 → 达到明确终态或升级人工。
- 适用信号：超时、晚到事件、重复提交、失败原因不同、预算/额度受限、任务跨多个回合。
- 可组合点：与 GATED-DELIVERY 组合避免“恢复后直接报完成”；与 EVIDENCE-SPIRAL 组合将恢复结果转成下一题方法反馈。
- 常见改法：父/子预算分离；恢复次数有界；证据编辑后失效；幂等键防重复提交；不确定就报告 Unknown/Blocked，不伪造成功。
- 失败模式：无条件重放副作用；只按重试次数处理所有错误；晚到事件污染新 attempt；额度耗尽被误标 complete；失败静默暂停。

## Manager 使用纪律

1. 先判断任务风险，再决定引用零个、一个或多个 seed。
2. 引用 seed 时，`method_refs` 必须写 seed ID、来源、版本、当前信号、采用/组合/fork/skip 理由和本题改动点；不引用时在 rationale 说明标准 Loop 足够。
3. seed 只约束可考虑的设计空间，不替 Manager 做选择，不提供任务答案。
4. 方法必须来自公开、可复核的来源锚点；闭源产品只允许引用公开行为/文档，不能破解或复制私有实现。
5. 设计变化必须能由工具回执、检查结果或跨题反馈解释；只有步骤字符串变化而无证据，不算聪明进化。
6. 固定模型、硬闸门、权限和 Worker 工具契约不由 seed 改写；seed 不能绕过 inspect、write、public_check、submit 等 Core 约束。
7. 当前 catalog 先提供 5 个跨来源方法种子；它们只是首批可组合积木，不是数量上限。未来新增方法必须先合并重复能力或说明为何仍不重叠，保持目录可发现、可组合、可回滚，不能无理由堆积。
