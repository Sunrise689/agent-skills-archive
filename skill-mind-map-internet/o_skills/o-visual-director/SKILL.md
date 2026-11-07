---
name: o-visual-director
description: 视觉总编——设计/视觉域编排节点（O型）：审美方向未定需比选风格，或多视觉产物（品牌/界面/图像/演示/动效）需统一规范排产时激活。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-visual-director/skill
---

# 视觉总编（o-visual-director）

## 用途与触发场景

当用户提出视觉设计需求，并出现以下情况时，激活本 O：

- 用户说“帮我定个视觉方向”“这几种风格选哪个”“先出一套视觉方案”等，审美方向尚不明确，需要比较风格并确定制作路径。
- 用户要为同一项目制作品牌、界面、图像、内容视觉、演示文稿或动效中的多种产物，需要安排制作顺序并共享视觉规范。
- 用户已有明确的单项需求：Logo 需求可直调 `press-logo`；信息图需求可直调 `sn-infographic`。

本 O 负责明确视觉方向、制作路径与共享规范，并协调各项视觉产物保持一致。

## 编排流程

1. 判断方向是否明确、产物有几类、是否需要共享规范。方向未定时，先调用“视觉方向与路径决策”确定方向、参考风格和制作约束。
2. 多种产物需要协调时，调用“视觉交付编排”，根据交付物、依赖关系和复用需求安排制作顺序与规范。
3. 按决策结果调用对应 T：方向探索可用 `briefbound-visual-design`、`illustration-direction`、`visual-content`；多产物落地可用品牌、设计系统、界面、演示文稿、信息图或动效相关成员。单项 Logo 和信息图需求可按需直调对应成员。
4. 汇总各 T 的产物与规范，由“视觉交付编排”收口多产物的一致性和交付顺序；由本 O 检查是否符合用户确定的方向，并向用户交付结果。

## 下辖M

- **视觉方向与路径决策** —— 当审美方向未定、存在多种风格候选，或需要先确定视觉语言与制作方式时调用；产出方向建议、风格依据、制作路径及适用约束。
- **视觉交付编排** —— 当项目包含多种视觉产物，或多个制作环节需要共享规范与顺序时调用；产出产物清单、制作顺序、共享规范及各环节衔接安排。

## 核心T成员

- `briefbound-visual-design` —— 将视觉需求整理为明确的设计方向与执行要求。
- `brand-identity@cbrock84__headcount` —— 建立品牌视觉识别与可复用的品牌规范。
- `press-logo` —— 制作 Logo。
- `design-system-generate` —— 生成界面设计系统与共享视觉规范。
- `frontend-design-v3` —— 将视觉方向落实为前端界面设计。
- `interface-craft` —— 打磨界面视觉与交互呈现。
- `illustration-direction` —— 确定插画方向、风格与表现方式。
- `image-generation@bytedance__deer-flow` —— 按视觉方向生成图像。
- `visual-content` —— 规划和制作内容视觉素材。
- `sn-infographic` —— 制作信息图。
- `baoyu-slide-deck` —— 制作演示文稿视觉内容。
- `motion-graphics` —— 制作动态图形与动效内容。

## 四类边

- **O→T**：Logo 需求直调 `press-logo`；信息图需求直调 `sn-infographic`。
- **O→M**：方向未定时调用“视觉方向与路径决策”；多产物需要协调时调用“视觉交付编排”。
- **M→T**：“视觉方向与路径决策”→`briefbound-visual-design`、`illustration-direction`、`visual-content`；“视觉交付编排”→`brand-identity@cbrock84__headcount`、`design-system-generate`、`frontend-design-v3`、`baoyu-slide-deck`、`sn-infographic`、`motion-graphics`。
- **T↔T**：`brand-identity@cbrock84__headcount`↔`press-logo`；`design-system-generate`↔`frontend-design-v3`；`illustration-direction`↔`image-generation@bytedance__deer-flow`；`visual-content`↔`sn-infographic`；`baoyu-slide-deck`↔`motion-graphics`。

## 边界与升级

本 O 不替用户决定未说明的品牌立场、受众偏好或内容事实；不把单项视觉制作扩大为整套品牌或产品改造。纯文案、业务策略、功能开发和技术架构不归本 O 管理；如任务包含这些内容，应仅处理视觉部分，并指出需要其他专业流程承接的部分。

成员缺失时，从名单中选择职责最接近的 T，说明替代关系，并由对应 M 调整制作路径。成员卡住或产物不符合已确定方向时，先由对应 M 检查任务要求、共享规范和上下游依赖，再决定修订、替换成员或调整顺序；方向本身需要改变时，返回“视觉方向与路径决策”。

## 值守红线

不替主人进行付费、登录或对外发布动作。任务推进到这些环节时，先停下来向主人说明待执行事项并询问。
