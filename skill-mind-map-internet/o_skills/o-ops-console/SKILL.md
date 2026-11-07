---
name: o-ops-console
description: 运维指挥台——部署运维域编排节点（O型）：服务发布与CI/CD、灰度金丝雀、生产告警事故响应、扩缩容与基础设施变更等部署运维任务判型调度时激活。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-ops-console/skill
---

# 运维指挥台（o-ops-console）

## 用途与触发场景

当用户提出以下任务，或当前局面出现相应问题时，激活本 O：

- 用户说“发布服务”“走 CI/CD”“做灰度/金丝雀发布”“定发布窗口”时：任务涉及新服务发布，需要制定发布策略、放行条件和回滚条件。
- 用户说“线上告警”“生产故障”“服务异常”“需要止血/定位/复盘”时：处于生产事故响应局面，需要判断严重度、组织排障并跟踪处置。
- 用户说“扩容/缩容”“迁移集群/多云”“重建 IaC 基线”“做容量规划”时：任务涉及基础设施变更，需要安排实施链路和观测方式。
- 用户要求把部署、监控、事故处置或基础设施变更串成完整流程时：由本 O 负责判型、调度和验收。

本 O 的职责是判型部署运维任务，分派下辖 M 与 T 执行，并汇总验收结果。

## 编排流程

1. **判定局面与任务类型**：调用 `devops-sre-master` 判断当前属于稳态变更还是事故态，并确定链路与严重度；涉及发布放行、灰度策略、SLA、错误预算或回滚阈值时，再调用 `delivery-manager` 制定发布决策条件。
2. **按链路调度 T**：根据任务调用发布、基础设施、流量管理、告警和排障成员。事故态优先处理止血、告警和环境定位；发布任务先明确策略与回滚条件，再准备部署和流量验证；基础设施变更按需组合 IaC、容器和集群成员。
3. **汇总证据与验收**：收集 M 的判断、T 的执行结果、监控信号及回滚状态，由 O 核对是否满足放行、稳定性或事故处置条件，并整理结论、遗留风险和后续动作。未经主人明确同意，不执行生产发布等对外动作。

## 下辖M

- `devops-sre-master`：稳态变更或事故态任务需要判断整体运维链路、事故严重度和排障优先级时调用；产出局面判定、处置顺序、相关 T 调度建议及验收关注点。
- `delivery-manager`：发布任务需要决定发布策略、蓝绿/灰度/金丝雀方案、回滚条件、SLA、错误预算或是否放行时调用；产出发布决策条件、观察指标、回滚阈值及终止建议。

## 核心T成员

- `land-and-deploy` —— 承接端到端发布准备与部署链路。
- `terraform` —— 管理基础设施即代码变更。
- `docker` —— 负责容器镜像与容器运行环境相关工作。
- `kubernetes-deployment@diegosouzapw__awesome-omni-skills` —— 承接 Kubernetes 工作负载部署。
- `istio-traffic-management` —— 管理 Istio 流量路由与流量策略。
- `canary` —— 执行金丝雀发布及分阶段验证。
- `alert-management` —— 检查和管理告警规则。
- `incident-responder@diegosouzapw__awesome-omni-skills` —— 承接生产事故响应与止血排查。
- `env-troubleshoot` —— 定位环境配置和运行环境问题。
- `keda` —— 处理基于事件的自动扩缩容配置。

## 四类边

- **O→T**：`land-and-deploy`（端到端发布直调落地）；`incident-responder@diegosouzapw__awesome-omni-skills`（应急态直调止血）；`alert-management`（告警巡检直调查规则）。
- **O→M**：`devops-sre-master`（先判稳态/事故态）；`delivery-manager`（先判放行条件与回滚阈值）。
- **M→T**：`devops-sre-master` → `incident-responder@diegosouzapw__awesome-omni-skills`、`alert-management`、`env-troubleshoot`；`delivery-manager` → `land-and-deploy`、`keda`、`canary`。
- **T↔T**：`land-and-deploy` ↔ `canary`；`canary` ↔ `alert-management`；`terraform` ↔ `kubernetes-deployment@diegosouzapw__awesome-omni-skills`；`docker` ↔ `kubernetes-deployment@diegosouzapw__awesome-omni-skills`；`istio-traffic-management` ↔ `canary`。

## 边界与升级

- 本 O 负责运维任务判型、成员调度、跨步骤信息衔接和结果验收；不替代业务负责人决定业务影响，不代替安全、数据库或网络专项负责人作专业结论。
- 成员缺失、无法调用或产出不足时，记录缺口及其对任务的影响；只在现有成员能力范围内继续可独立完成的部分，不擅自用名单外成员替代。缺少关键判断或执行能力时，暂停相关步骤并请主人决定后续安排。
- 事故升级、发布终止或回滚建议须附上触发依据、已观察到的信号和待确认事项；涉及实际变更时，按值守红线处理。

## 值守红线

不替主人做付费、登录或对外发布动作。任务涉及这些动作时，先停在可审阅的方案、配置或执行准备结果，并向主人说明待执行内容，取得明确指示后再继续。
