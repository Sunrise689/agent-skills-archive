---
name: o-doc-composer
description: 格式写作编排——跨格式写作域编排节点（O型）：内容跨格式转换、翻译本地化、多语言多平台版本适配及转换后一致性核对时激活。
mto: O
permalink: basic-memory/记忆库/kira/smi/o-skills/o-doc-composer/skill
---

# 格式写作编排（o-doc-composer）

## 用途与触发场景

当用户提出“把这份内容转成另一种格式”“翻译或本地化这份文档”“做一份适配多个语言或平台的版本”等要求时，激活本 O。

当任务涉及文档格式转换、出版载体适配、排版整理或转换后的内容一致性核对时，也由本 O 统一规划路径。先确认源内容、目标格式或语言、目标读者、交付平台和保真要求，再决定调用哪些成员。

## 编排流程

1. **确认交付目标**：厘清源文件与目标格式、语言、读者和平台；识别需要保留的结构、术语、版式及内容。
2. **选择编排路径**：需要格式转换时调用「格式转换编排」；需要翻译、本地化或多端适配时调用「本地化与多端适配编排」。目标不明确时，先用 `sn-report-format-discovery` 协助识别合适的格式路径。
3. **执行转换与适配**：由对应 M 选择并调度所需 T，按任务需要完成格式转换、翻译、平台适配、排版或清理。只调用与交付要求相关的成员。
4. **核对并收口**：由对应 M 汇总转换结果；需要双语核对时调用 `hd2-bilingual-doc-verify`。确认内容、结构与交付目标一致后，由本 O 收口并交付。

## 下辖M

- **格式转换编排**：当任务需要在文档格式或出版载体之间转换时调用；产出转换路径、所需 T、格式保真要求及整理后的结果。
- **本地化与多端适配编排**：当任务需要翻译、本地化、双语处理或为多个平台制作版本时调用；产出语言与平台适配路径、适用 T 及经过核对的版本。

## 核心T成员

- `sn-report-format-discovery` —— 判断报告内容与目标用途适合采用的格式及转换路径
- `baoyu-translate` —— 执行内容翻译
- `latex-translation-guide` —— 为 LaTeX 文档翻译提供处理指引
- `azure-ai-translation-document-py@lingxling__awesome-skills-cn` —— 处理文档翻译
- `latex-paper-conversion@lingxling__awesome-skills-cn` —— 执行论文相关的 LaTeX 格式转换
- `latex-to-quarto` —— 将 LaTeX 内容转换为 Quarto 格式
- `latex-to-typst` —— 将 LaTeX 内容转换为 Typst 格式
- `huashu-md-html` —— 处理 Markdown 与 HTML 之间的转换
- `quarto-clean` —— 清理和整理 Quarto 文档
- `pdf-creator` —— 创建 PDF 交付文件
- `platform-format-adapt@bangwozuo__coldstart-growth-zh` —— 按目标平台调整内容格式
- `hd2-bilingual-doc-verify` —— 核对双语文档内容

## 四类边

- **O→T**：`sn-report-format-discovery`、`baoyu-translate`、`huashu-md-html`
- **O→M**：格式转换编排；本地化与多端适配编排
- **M→T**：
  - 格式转换编排 → `latex-to-quarto`、`latex-to-typst`、`huashu-md-html`、`pdf-creator`、`quarto-clean`、`sn-report-format-discovery`、`latex-paper-conversion@lingxling__awesome-skills-cn`
  - 本地化与多端适配编排 → `baoyu-translate`、`azure-ai-translation-document-py@lingxling__awesome-skills-cn`、`platform-format-adapt@bangwozuo__coldstart-growth-zh`、`hd2-bilingual-doc-verify`、`latex-translation-guide`
- **T↔T**：
  - `latex-to-quarto` ↔ `quarto-clean`
  - `huashu-md-html` ↔ `pdf-creator`
  - `baoyu-translate` ↔ `hd2-bilingual-doc-verify`
  - `latex-paper-conversion@lingxling__awesome-skills-cn` ↔ `latex-translation-guide`

## 边界与升级

本 O 负责规划格式转换、翻译和平台适配的协作路径，不负责创作与交付目标无关的新内容，也不替代专业审校、学术判断或事实核查。超出成员能力范围的版式、格式或语言要求，应明确说明限制，并请用户补充可用的源文件、目标规范或处理要求。

成员缺失、调用失败或转换结果无法满足保真要求时，停止依赖该成员的后续步骤；汇总已完成内容、失败环节和可行替代路径，再交由用户决定如何继续。涉及付费、登录或对外发布动作时，先停下来询问用户。

## 值守红线

不替主人执行付费、登录或对外发布动作；任务涉及这些操作时，先停下来问。
