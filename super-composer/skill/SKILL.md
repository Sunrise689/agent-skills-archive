---
name: super-composer
description: >-
  super composer / 超级创作 的操作指南。只有主人点名这两个词才用。
  入口是一个同名 MCP，按顺序调它的动作，不另建 MCP。
---

# Super Composer

只有主人说 **super composer** 或 **超级创作** 才用。普通的写、改、审，不走这里。

入口只有一个 MCP：`super-composer`。下面是它里面的动作，按这个顺序调。

1. `create_project`：给一个项目目录和 style_brief。
2. `save_draft`：调用方自己写初稿，存进去。稿子一旦存下就不再改，改了就存新版本。
3. `launch_role_cards`：需要时才派卡。C 只收集材料，A 只审计一项职责，P 只改已点名的段落。验收只派一张。传 `lanes` 就按通道组发卡，每张卡用自己的 profile、model、effort。不传 `lanes` 走 `policy.json` 的单个 profile。两组通道：`minimax` 用 `CC-U` / `MiniMax-M3.1-Flash`，8 到 10 张；`openrouter` 用 `openrouter/` 前缀的模型，最多 20 张。`CC-U-OR-free` 和 `CC-U-OR-free-nemotron` 只接受它们钉死的免费模型。CX 档、`MINIMAX-U`、`MINIMAX-L`、超限张数和错配模型直接拒绝，不截断、不换通道。
4. `run_decision_audit`：本地逐项判断。它只标风险，不判定事实真假。
5. `get_status`：看 `open_issues`。大于 0 就要先处理，或者明确确认后再往下。
6. `collect_results`：从 `cards/<id>/work/report.md` 收回报告。
7. `finalize`：还有未关闭问题时必须带 `confirm=true`。

卡没派出去就看 `cards/<id>/launch.log`，状态会是 `launch_failed`，不要当成已发出。
