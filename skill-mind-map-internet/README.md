# Skill Mind Map Internet

Skill Mind Map Internet 是一个 Skill 知识库、标签索引和联想召回工具。精选内容来自公开开源 Skill 与通用工具，经过打标、筛选、同类合并和必要切分。

## 解决的问题

任务开始时经常不知道该找什么 Skill。SMI 用索引、MTO 网络和召回脚本，把任务需求连接到可复用的 Skill。

## 使用方法

```bash
python act4_recall.py --search "video conversion"
python act4_recall.py <skill-name> 8
python act4_arm.py <skill-name-1> <skill-name-2> --k 10
```

## 内容规模与架构

当前索引包含 19,502 条记录，包含 19,172 条 Skill、131 条 CLI 和 199 条开源仓库记录。MTO 架构由 M 型判断与方法、T 型确定性工具、O 型编排组成。

## 技术架构

实现使用 Python 标准库、JSONL 索引、图结构 JSON 和 IDF 召回。`act4_recall.py` 负责检索，`act4_arm.py` 负责生成任务所需的 Skill 清单，`o_skills/` 保存 O 型 Skill。
