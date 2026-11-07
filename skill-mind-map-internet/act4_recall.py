# -*- coding: utf-8 -*-
"""联想触达层：挂载任意 skill -> 按标签召回库内相关 skill（"能想到"的能力）。
双轨：专标签 IDF 召回（精度优先）；无专标签时泛标签兜底（粗召回，标注模式）。
同域 ×1.15 加成。超泛标签=df > 全库8%（11个：代码/AI/数据/软件架构等）。

2026-10-20 收官：数据源改指 SMI 正本（registry_networked.jsonl，19,502 条 =
19,172 skill + 131 cli + 199 repo）；IDF/泛词仍只用旧 skill 全集计算，
旧 skill 召回行为不变；新增 --search 走关键词检索命中 CLI/repo。

用法：
  python act4_recall.py <skill名> [k]        # 单条召回
  python act4_recall.py --demo               # 模拟"挂1O+1M+4T"场景
  python act4_recall.py --search "转换视频" [--k 8] [--kinds cli,repo]
"""
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
NET = HERE / "registry_networked.jsonl"

CJK = re.compile(r"[一-鿿]+")
ASCII = re.compile(r"[A-Za-z0-9_.+-]+")
# 检索打分权重：字段命中强度
FIELD_W = {
    "name": 3.0,
    "aliases": 2.5,
    "tags": 2.0,
    "desc": 1.5,
    "free": 1.5,
    "domains": 1.5,
    "category_raw": 1.2,
    "example": 0.8,
}
# repo 的 tags 由 OJ 自动分类拼出（长串噪声），权重下调；cli 的 tags/desc 是人工维护的
FIELD_W_BY_KIND = {"cli": dict(FIELD_W, desc=2.0), "repo": dict(FIELD_W, tags=1.2)}
# 单字 CJK 兜底（覆盖"转码/转换"这类同义差异），权重低于二元词
CHAR_W = 0.35
# 极小同义扩展词典（查询词 -> 近义词，权重低于原词）
SYN = {
    "转换": ["转码", "转格式"],
    "转码": ["转换"],
    "视频": ["媒体"],
    "量化": ["回测"],
    "回测": ["量化"],
    "游戏": ["引擎"],
    "端口": ["占用"],
}
SYN_W = 0.6


class Recall:
    def __init__(self, net=None):
        net = Path(net) if net else NET
        self.rows = [json.loads(l) for l in open(net, encoding="utf-8") if l.strip()]
        # 同名条目（skill 与 cli 各 8 个：docker/python/nmap/tldr/rclone/pnpm/podman/d2）：
        # 旧名解析优先给 skill，保持旧 skill 召回行为；cli 条目走 --search / by_kind 取用
        self.by_name = {}
        self.by_kind = {}
        for e in self.rows:
            kind = e.get("kind") or "skill"
            self.by_kind[(kind, e["name"])] = e
            if kind == "skill" or e["name"] not in self.by_name:
                self.by_name[e["name"]] = e
        # 旧 skill 全集 = IDF/泛词的计算口径（保持旧 skill 召回行为）
        skills = [e for e in self.rows if (e.get("kind") or "skill") == "skill"]
        n = len(skills)
        df = defaultdict(int)
        for e in skills:
            for t in set(e.get("tags") or []):
                df[t] += 1
        self.idf = {t: math.log(n / d) for t, d in df.items()}
        self.generic = {t for t, d in df.items() if d > n * 0.08}
        # 倒排索引覆盖全部条目（含 cli/repo），旧 skill 也能召回新条目
        self.inv_p, self.inv_g = defaultdict(list), defaultdict(list)
        for e in self.rows:
            for t in set(e.get("tags") or []):
                (self.inv_g if t in self.generic else self.inv_p)[t].append(e["name"])

    def recall(self, name, k=10):
        e = self.by_name.get(name)
        if e is None:
            return None, []
        tags, doms = set(e.get("tags") or []), set(e.get("domains") or [])
        score = defaultdict(float)
        for t in tags - self.generic:
            for nm in self.inv_p[t]:
                if nm != name:
                    score[nm] += self.idf.get(t, 0.5)
        mode = "专标签"
        if not score:
            mode = "泛标签兜底"
            for t in tags & self.generic:
                for nm in self.inv_g[t]:
                    if nm != name:
                        score[nm] += 1.0
        for nm in score:
            if doms & set(self.by_name[nm].get("domains") or []):
                score[nm] *= 1.15
        top = sorted(score.items(), key=lambda x: -x[1])[:k]
        return mode, [(nm, round(s, 1)) for nm, s in top]

    def demo_mount(self, mounted, k=10):
        """模拟挂载场景：每个挂载T触达k个，合并去重成视野网。"""
        seen = {}
        detail = []
        for m in mounted:
            mode, top = self.recall(m, k)
            detail.append((m, mode, top))
            for nm, s in top:
                seen[nm] = max(seen.get(nm, 0), s)
        return detail, seen

    # ---------- 关键词检索（自然语言 -> CLI/repo） ----------
    @staticmethod
    def tokenize(q):
        q = q.strip()
        toks = []
        for w in ASCII.findall(q):
            toks.append((w.lower(), 1.2))
        for seg in CJK.findall(q):
            if len(seg) == 1:
                toks.append((seg, 1.0))
            else:
                toks.append((seg, 0.8))          # 整段（低权）
                for i in range(len(seg) - 1):
                    toks.append((seg[i:i + 2], 1.0))  # 二元切分
                for ch in set(seg):
                    toks.append((ch, CHAR_W))   # 单字兜底
        for tok, wtok in list(toks):
            for syn in SYN.get(tok, []):
                toks.append((syn, wtok * SYN_W))
        return toks

    def search(self, query, k=10, kinds=("cli", "repo"), min_cover=0.5):
        """关键词检索：name/aliases/tags/desc/free/domains/category_raw 全字段打分。
        覆盖度门槛（查询字符命中比例 >= min_cover）过滤弱相关，无命中如实返回空。"""
        qchars = set(re.sub(r"[\s,，。、/]+", "", query))
        toks = self.tokenize(query)
        out = []
        for e in self.rows:
            kind = e.get("kind") or "skill"
            if kind not in kinds:
                continue
            fw = FIELD_W_BY_KIND.get(kind, FIELD_W)
            fields = {f: e.get(f) for f in fw}
            fields["tags"] = " ".join(e.get("tags") or [])
            fields["aliases"] = " ".join(e.get("aliases") or [])
            fields["free"] = " ".join(e.get("free") or [])
            fields["domains"] = " ".join(e.get("domains") or [])
            fields["desc"] = e.get("desc") or ""
            blob = " ".join(str(v) for v in fields.values() if v).lower()
            if not blob:
                continue
            score = 0.0
            hits = []
            for tok, wtok in toks:
                tl = tok.lower()
                matched = False
                for fname, wf in fw.items():
                    val = fields.get(fname)
                    if not val:
                        continue
                    if tl in str(val).lower():
                        score += wtok * wf
                        matched = True
                if matched:
                    hits.append(tok)
            if score <= 0:
                continue
            covered = {c for c in qchars if c in blob}
            cover = len(covered) / len(qchars) if qchars else 0.0
            if cover < min_cover:
                continue
            out.append({
                "kind": kind,
                "name": e["name"],
                "score": round(score, 2),
                "cover": round(cover, 2),
                "desc": (e.get("desc") or "").split(" | ")[0][:80],
                "tags": e.get("tags") or [],
                "path": e.get("path"),
                "install_state": e.get("install_state"),
                "example": e.get("example"),
                "hits": hits,
            })
        out.sort(key=lambda x: (-x["score"], -x["cover"], x["name"]))
        return out[:k]


def main():
    r = Recall()
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return
    if args[0] == "--demo":
        mounted = args[1:] or [
            "code-refactoring-refactor-clean@diegosouzapw__awesome-omni-skills",
            "deprecation-and-migration",
            "git-workflow-and-versioning",
            "dependency-injection-patterns",
        ]
        detail, seen = r.demo_mount(mounted)
        for m, mode, top in detail:
            print(f"\n挂载T「{m}」[{mode}] 触达 top{len(top)}:")
            for nm, s in top:
                print(f"   {s:>6.1f}  {nm}")
        print(f"\n=== {len(mounted)} 个挂载T 联想去重后视野网：{len(seen)} 个新T ===")
    elif args[0] == "--search":
        rest = args[1:]
        k = 8
        kinds = ("cli", "repo")
        if "--k" in rest:
            i = rest.index("--k")
            k = int(rest[i + 1])
            rest = rest[:i] + rest[i + 2:]
        if "--kinds" in rest:
            i = rest.index("--kinds")
            kinds = tuple(rest[i + 1].split(","))
            rest = rest[:i] + rest[i + 2:]
        query = " ".join(rest).strip()
        if not query:
            print("用法: python act4_recall.py --search \"关键词\" [--k 8] [--kinds cli,repo]")
            return
        hits = r.search(query, k=k, kinds=kinds)
        if not hits:
            print(f"SMI 检索「{query}」→ 未找到匹配项。")
            return
        print(f"SMI 检索「{query}」→ {len(hits)} 命中:")
        for h in hits:
            print(f"  [{h['kind']}] {h['name']}  score={h['score']} 覆盖={h['cover']}")
            if h["desc"]:
                print(f"        用途: {h['desc']}")
            if h["tags"]:
                print(f"        标签: {'/'.join(h['tags'][:6])}")
            if h["path"]:
                print(f"        路径: {h['path']}")
            if h["install_state"]:
                print(f"        安装状态: {h['install_state']}")
            if h["example"]:
                print(f"        用例: {h['example']}")
    else:
        name, k = args[0], int(args[1]) if len(args) > 1 else 10
        mode, top = r.recall(name, k)
        if mode is None:
            print(f"「{name}」不在库")
            return
        print(f"「{name}」[{mode}] 触达 top{len(top)}:")
        for nm, s in top:
            print(f"   {s:>6.1f}  {nm}")


if __name__ == "__main__":
    main()
