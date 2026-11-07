---
name: o-collab-hub
description: 协同枢纽——办公协作域编排节点（O型）：会议产出转待办与日历、跨平台排会、团队周报聚合分发等跨工具协作流转时激活，防漏项防状态不同步。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-collab-hub/skill
---

# 协同枢纽（o-collab-hub）

## 用途与触发场景

当用户说出或处于以下局面时激活这个O：

- 「把这段会议纪要整理成待办」「会开完了，行动项同步到日历/任务板」——会议产出需要转化为可追踪任务。
- 「帮我约个会，看大家日程」「跨平台排会」——需要在多个日历/协作工具之间协调时间。
- 「出一份团队周报/项目状态报告」——需要聚合会议、任务、日程多方信息形成汇报。
- 局面特征：信息散落在纪要、日历、看板、沟通渠道多处，存在漏记、漏排、状态不同步的风险。O的核心价值是跨工具串联与防漏，不是单点纪要整理（单点已有成熟T，直接用即可，不必进本O）。

## 编排流程

1. **入口分流与统一提取**：先调 `meeting-insights` 把原始纪要/讨论记录提取成统一结构（决策、行动项、负责人、截止日期、待排日程）；行动项较多或跨平台批量分发前，调 `meeting-analyzer` 对拍复核，两源一致才放行。排会请求与周报请求同样先经此入口归一化，不直接散调下游T。
2. **召M定策**：把归一化结果交 `会议决策流转法`，决定每条决策与行动项落到哪个待办工具、哪条日历；若涉及任务优先级、依赖关系、或判断是否需要追加会议/检查点，再召 `任务依赖编排法` 编排顺序与触发条件。两个M的裁定是下游执行的唯一依据，O不自行拍板分发规则。
3. **按裁定调T执行**：流转法裁定走 `using-todo`、`notion-meeting-notes`；编排法裁定走 `kanban-board`、`trello@alivirgo__Major-AI-Skills`；档期落 `lark-calendar` 与 `google-calendar-automation@rootcastleco__rei-skills`（按对方实际使用的平台选一，跨平台时两端同步）。`secretary` 承接日程与行政类杂项执行。
4. **收口与报告**：O核对三条线一致性——纪要归档、日历档期、任务板状态互相对得上，无漏项；由 `team-update-aggregator` 汇总多方信息生成周报/状态报告，`team-communications` 负责分发与回执确认。产物不一致时回到第1步重新提取，不得带错收口。

## 下辖M

- **会议决策流转法**：何时调用——会议产出需要分发落地时。产出——每条决策/行动项的去向裁定：归属哪个待办工具、是否进日历、负责人与截止日期如何绑定，形成可直接执行的分发清单。
- **任务依赖编排法**：何时调用——任务间存在先后依赖、优先级冲突，或需要判断何时触发后续会议/检查点时。产出——任务优先级序列、依赖关系图、后续会议或检查点的触发时机表。

## 核心T成员

- meeting-insights —— 会议记录统一提取入口，全链条第一站
- meeting-analyzer —— 与 meeting-insights 对拍复核，深挖决策与行动项防止漏提
- lark-calendar —— 飞书日历侧的档期读写
- google-calendar-automation@rootcastleco__rei-skills —— Google 日历侧档期读写，与 lark-calendar 互为跨平台对端
- notion-meeting-notes —— 会议纪要结构化归档落点
- meeting-notes@alapha888__agent-skills-en —— 会议纪要结构化归档的备用落点（notion-meeting-notes 缺位时顶上）
- trello@alivirgo__Major-AI-Skills —— 看板任务落卡，任务依赖编排法的执行端之一
- using-todo —— 行动项转个人待办的执行端
- kanban-board —— 看板状态追踪，与 using-todo 互验防漏
- secretary —— 日程与行政杂务的综合执行位
- team-communications —— 团队沟通渠道的信息分发与回执确认
- action-items-todo —— 行动项直转待办的备用通道（using-todo 缺位时顶上）
- team-update-aggregator —— 聚合多方协作信息，生成周报与项目状态报告

## 四类边

- **O→T**：meeting-insights（会议记录统一提取入口）
- **O→M**：决策与行动项分发 → 会议决策流转法；优先级与依赖编排 → 任务依赖编排法
- **M→T**：会议决策流转法 → using-todo、notion-meeting-notes；任务依赖编排法 → kanban-board、trello@alivirgo__Major-AI-Skills
- **T↔T**：lark-calendar ↔ google-calendar-automation@rootcastleco__rei-skills；meeting-insights ↔ meeting-analyzer；using-todo ↔ kanban-board

## 边界与升级

不归本O管：

- 单点任务——只要求「整理一份纪要」或「设一个提醒」，不经跨工具流转，直接用对应单T，不进本O。
- 纯文档撰写、代码与工程任务、招聘/财务等非协作流转事务。
- 需要新建工具账号、配置第三方集成的初始化工作——这类涉及登录，直接停下上报。

成员缺失或卡住时：

- 单T缺失 → 用名单内同功能成员顶位（纪要归档缺位用 `meeting-notes@alapha888__agent-skills-en`，行动项待办缺位用 `action-items-todo`），并记录降级。
- 日历类T卡住 → 先切对端（lark-calendar 与 google-calendar-automation@rootcastleco__rei-skills 互顶），双端皆不通才上报。
- M缺失或裁定互相矛盾 → 暂停分发，整理矛盾点上报指挥层，不自行合并两套规则。
- 两条以上链路同时缺失 → 停手上报，不带残缺状态收口。

## 值守红线

- 不替主人做付费动作：购买/升级协作工具套餐、消耗付费额度，一律先停下来问。
- 不替主人做登录动作：OAuth 授权、账号密码输入、验证码处理，一律先停下来问。
- 不替主人做对外发布动作：向团队外分发报告、发送会议邀请给外部人员、公开任何协作内容，一律先停下来问。
- 内部分发（团队成员之间的纪要/待办同步）在授权范围内可直接执行，执行后留痕。
