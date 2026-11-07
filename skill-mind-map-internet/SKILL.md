---
name: skill-mind-map-internet
description: Skill Mind Map Internet（Skill 思维库与联想网络）的使用说明。
---

# Skill Mind Map Internet

Skill Mind Map Internet 是一个面向 AI 工作流的 Skill 知识库和联想网络。精选内容来自公开开源 Skill 与通用工具，并经过打标、筛选、同类合并和必要的切分。

当前索引包含 19,502 条记录，口径为 19,172 条 Skill、131 条 CLI 和 199 条开源仓库记录。索引文件只保存通用元数据，不包含个人路径。

## MTO 架构

- M 型是判断与方法层，负责选择和解释。
- T 型是确定性工具层，负责具体执行。
- O 型是编排层，负责把 M 与 T 组合成工作流。

## 使用方法

```bash
python act4_recall.py --search "视频转换"
python act4_recall.py <skill-name> 8
python act4_arm.py <skill-name-1> <skill-name-2> --k 10
```

`act4_recall.py` 根据标签和关键词召回相关条目。`act4_arm.py` 为任务生成主 Skill 与联想 Skill 清单。外部 Skill 正本可通过 `SMI_EXTERNAL_ARMORY` 配置，默认使用本目录内的 O 型 Skill。

## 技术架构

实现使用 Python 标准库、JSONL 索引、图结构 JSON 和 IDF 召回。`edges.json` 保存 MTO 网络，`edges_cli.json` 保存 CLI 与仓库关联，`o_skills/` 保存可直接阅读的 O 型 Skill。
