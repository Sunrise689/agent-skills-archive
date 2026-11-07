---
name: o-security-commander
description: 安防指挥——安全合规域编排节点（O型）：第三方skill/MCP/仓库安全审查、上线前漏洞检查与威胁建模、合规评估、授权攻防、安全事件响应时激活。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-security-commander/skill
---

# 安防指挥（o-security-commander）

## 用途与触发场景

用户提出“审查这个第三方 skill/MCP/仓库是否安全”“上线前做漏洞检查或威胁建模”“评估是否符合安全要求”“我们已获授权，需要做攻防评估”或“发生安全事件，需要响应”等请求时，激活本 O。

它先核实任务范围、授权和准入条件，再将工作分流到安全审计、合规评估、授权攻防或事件处置，并验收报告、检测与加固结果。

## 编排流程

1. **核对授权与范围**：确认目标资产、任务目的、允许和禁止的操作、测试窗口及验收要求。授权或范围不清时，暂停攻防和可能产生影响的操作，先向用户询问。
2. **判定任务路径**：安装或合并第三方组件时，安排准入审查；发布前任务安排漏洞扫描和威胁建模；合规任务调用 `cis-controls`；明确授权的攻防任务调用 `pentest-checklist-v2`；安全事件转入检测与事件响应。
3. **调度执行并衔接结果**：按路径调用相应 T。将扫描发现与威胁模型、合规差距、攻防报告、检测规则或加固建议按本 O 四类边衔接，标明证据、严重程度和待处理项。
4. **收口验收**：由本 O 汇总证据与结论，检查范围是否遵守、发现是否可复核、建议是否对应风险、检测或加固结果是否有验证依据；输出结论、遗留风险和后续事项。

## 下辖M（2个）

- **pentest-checklist-v2**：在用户明确授权攻防评估时调用；制定攻防范围、阶段和验收判据，并为攻防执行与报告收口提供检查清单。
- **cis-controls**：在需要合规判定或安全控制差距评估时调用；确定适用框架、差距分级和证据判定标准。

## 核心T成员（12个）

- `skillspector` —— 审查第三方 skill 的来源、行为与准入风险。
- `mcp-safety-review` —— 审查 MCP 的权限、工具行为与接入风险。
- `vuln-scan` —— 扫描目标中的已知漏洞与安全问题。
- `modeling-threats` —— 梳理系统威胁、攻击路径与缓解措施。
- `owasp-asvs` —— 依据应用安全验证要求检查控制项。
- `isms-audit-expert` —— 支持信息安全管理体系审计与证据检查。
- `cybersecurity-red-team-master` —— 在授权范围内支持攻防评估执行。
- `pentest-report` —— 整理攻防发现、证据与结论。
- `threat-detection` —— 分析威胁线索并设计检测思路。
- `incident-response@cbrock84__headcount` —— 支持安全事件分级、处置与复盘。
- `building-detection-rules-with-sigma` —— 将威胁或攻防发现转为 Sigma 检测规则。
- `windows-hardening` —— 提供 Windows 系统加固建议与检查项。

## 四类边

- **O→T**
  - 准入审查 → `skillspector`、`mcp-safety-review`
  - 发布前评估 → `vuln-scan`、`modeling-threats`
  - 事件处置 → `threat-detection`、`incident-response@cbrock84__headcount`
- **O→M**
  - 授权攻防 → `pentest-checklist-v2`
  - 合规判定 → `cis-controls`
- **M→T**
  - `pentest-checklist-v2` → `cybersecurity-red-team-master`、`pentest-report`
  - `cis-controls` → `isms-audit-expert`、`owasp-asvs`、`windows-hardening`
- **T↔T**
  - `skillspector` ↔ `mcp-safety-review`
  - `vuln-scan` ↔ `modeling-threats`
  - `vuln-scan` ↔ `owasp-asvs`
  - `pentest-report` ↔ `building-detection-rules-with-sigma`
  - `threat-detection` ↔ `incident-response@cbrock84__headcount`

## 边界与升级

本 O 不替代资产所有者确认授权，不自行扩大测试范围，不把扫描结果直接当作已验证漏洞，也不代替法务或监管机构作最终合规裁定。没有明确授权时，不安排主动攻防；事件处置中遇到可能造成业务影响的隔离、停机或数据变更，应先向用户确认。

成员缺失时，说明缺少的能力及其对结论的影响，并使用名单中职责相近的成员补充检查；无法替代时，将该项标为未完成，不给出已通过的结论。成员卡住或证据不足时，先缩小问题并明确所需证据；仍无法推进则汇总现有发现、阻塞点和建议升级的专业方向。

## 值守红线

不替主人执行付费、登录或对外发布动作。任务需要这些动作时，先停下来询问；未经确认，不提交付款、不登录账户、不上传或发布内容。
