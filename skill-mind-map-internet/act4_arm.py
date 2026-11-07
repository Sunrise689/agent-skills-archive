# -*- coding: utf-8 -*-
"""SMI 装弹器：指挥层按任务挑 3-5 个主 skill -> 产出「任务弹药单」。
弹药单两部分：
  主弹药 = 挂载 skill 的正本路径 + 用途（卡必读）
  联想弹药 = 每个主弹沿标签 IDF 召回的相关条目（名字+路径+说明），卡遇关联问题沿单现取
用法：python act4_arm.py <skill名1> <skill名2> ... [--k 10]
产出：stdout + SMI正本/armory_loadout.md（直接贴进派卡任务书）

2026-10-20 收官：数据源与产出改指 SMI 正本目录（原来指向 skills_armory/act4_out 副本）。
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARM = Path(__import__("os").environ.get("SMI_EXTERNAL_ARMORY", "")) if __import__("os").environ.get("SMI_EXTERNAL_ARMORY") else None
NET = HERE / "registry_networked.jsonl"
OUT = HERE / "armory_loadout.md"
sys.path.insert(0, str(HERE))
from act4_recall import Recall  # noqa: E402


def locate(e):
    """定位条目正本路径：先 SMI 正本 o_skills，再旧副本，最后 registry paths。"""
    name = e["name"]
    for cand in (HERE / "o_skills" / name / "SKILL.md",
                 (ARM / "act4_out" / "o_skills" / name / "SKILL.md") if ARM else HERE / "__missing__"):
        if cand.exists():
            return str(cand)
    if e.get("paths"):
        return str(e["paths"][0]) if e.get("paths") else None
    if e.get("path"):
        return e["path"]
    return None


def main():
    argv = list(sys.argv[1:])
    k = 10
    if "--k" in argv:
        i = argv.index("--k")
        k = int(argv[i + 1])
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return
    r = Recall()
    by_name = r.by_name
    mains, missing = [], []
    for n in args:
        e = by_name.get(n)
        if e:
            mains.append(e)
        else:
            missing.append(n)
    lines = ["# 任务弹药单（SMI 装弹器生成）", ""]
    lines.append("## 主弹药（挂载必读）")
    for e in mains:
        loc = locate(e)
        desc = "、".join(e.get("free") or []) or "、".join((e.get("tags") or [])[:3])
        kind = e.get("kind") or "skill"
        lines.append(f"- **{e['name']}**（{kind}）— {desc}\n  正本：`{loc}`")
    if missing:
        lines.append(f"- ⚠ 未在库中找到：{missing}")
    lines += ["", "## 联想弹药（遇关联问题沿单现取，不必预读）"]
    seen = set(mains and {e["name"] for e in mains})
    for e in mains:
        mode, top = r.recall(e["name"], k)
        for n, s in top:
            if n in seen:
                continue
            seen.add(n)
            x = by_name[n]
            desc = "、".join(x.get("free") or []) or "、".join((x.get("tags") or [])[:3])
            kind = x.get("kind") or "skill"
            if kind == "skill":
                p = locate(x) or "?"
            elif kind == "repo":
                p = x.get("path") or "?"
            else:
                p = x.get("exe_path") or x.get("example") or "?"
            lines.append(f"- `{n}`（{kind}，联想自 {e['name']}，分{s}，[{mode}]）— {desc}\n  路径：`{p}`")
    lines += ["", f"联想弹药合计 {len(seen) - len(mains)} 个。派卡时：主弹药贴任务书，联想弹药作附件随单。"]
    text = "\n".join(lines)
    OUT.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n弹药单已落盘：{OUT}")


if __name__ == "__main__":
    main()
