"""AI 引擎：大白话解读（三遍流水线）+ 问问AI（页面接地问答）。

设计原则：
1. 模型只"翻译"不计算：所有数字来自后端已算好的分析结果/页面资料；
2. 合规硬约束：提示词红线 + 输出端违禁词过滤双保险；
3. 模型降级链：主力免费模型不可用时自动切换 openrouter/free 路由；
4. 全站每日共享池：超限后友好提示，绝不把免费额度刷爆。
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.request
from datetime import datetime
from typing import Any
from urllib.parse import quote

# ==================== 配置区 ====================
# 方案 2：Key 只放在 CloudBase 云托管环境变量 OPENROUTER_API_KEY（免费功能），
# 不进代码包。未配置时 AI 功能会提示“尚未配置”，其余功能不受影响。
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
# 模型降级链：主力不可用（下架/限流）自动切换 openrouter/free 路由。
# 可选：在云托管环境变量填 OPENROUTER_MODEL 指定其他主力模型，无需重新打包。
_env_model = os.environ.get("OPENROUTER_MODEL", "").strip()
OPENROUTER_MODELS = (
    [_env_model, "openrouter/free"] if _env_model else [
        "nvidia/nemotron-3-ultra-550b-a55b:free",
        "openrouter/free",
    ]
)
# 全站每日共享池（充值$10档为1000次/天，留200缓冲；若未充值请改为 40）
_AI_DAILY_CAP = 800
# 联网新闻辅助（OpenRouter web search 为付费功能，默认关闭；
# 开启后回答可引用相关新闻，但仍以资料区为主）
NEWS_SEARCH_ENABLED = False
# ================================================

_ai_lock = threading.Lock()
_ai_usage = {"day": "", "count": 0}

_FORBIDDEN_WORDS = [
    "建议买入", "建议卖出", "建议加仓", "建议减仓", "应该买", "应该卖",
    "赶紧买", "赶紧卖", "抄底", "逃顶", "追高", "割肉", "满仓", "清仓",
    "必涨", "必跌", "稳赚", "保本", "翻倍可期", "目标价",
]

# 最终版系统提示词（定稿；资料与问题在 user 消息中注入）
_SYSTEM_PROMPT = """你是「技术分析学习角」的AI讲解员。你的每一次回复都必须严格遵守以下规则，没有例外。

## 你的身份
你是一位耐心、克制、说话接地气的老师，面向完全不懂金融的普通用户。你从不炫耀专业，只负责把复杂的事讲简单。

## 内容红线（7条，绝对不可违反）
1. 只讲资料里有的东西。所有回答必须严格基于提供的"资料"。资料里没有的信息，一律回答兜底话术。禁止补充资料外的任何知识、推测、联想。（若提供了"联网检索"内容，你必须先自查它与用户问题的相关性：若不相关、疑似广告或来源可疑，就完全忽略这部分内容，只根据资料回答，回复中也不要提及检索内容；只有确认明显相关时才可引用作为背景补充，并用"据公开资料"表述；涉及具体数字仍以资料区为准。）
2. 绝不预测涨跌。禁止出现任何对未来价格走势的判断，包括但不限于"可能上涨""预计会跌""后市看好"等表述。
3. 绝不给买卖建议。禁止出现任何操作建议，包括但不限于买入、卖出、加仓、减仓、持有、观望。用户追问操作时，必须回答："我只负责讲懂知识，做决定要你自己来哦"。
4. 数字只能引用，不可编造。资料中出现的数字可以引用。禁止编造或推测资料以外的任何数字（包括但不限于价格、百分比、时间、点位）。
5. 术语必须先解释再使用。遇到专业术语（如"均线""MACD""KDJ""支撑位""死叉"），必须先用一句话生活化解释，然后再继续讲。例如："均线就是最近一段时间大家的平均持仓成本线"。
6. 语气平和，不煽动。禁止夸张、恐吓、煽动性表述。禁止连续使用感叹号营造气氛。可以温和鼓励，但不夸大收益或风险。
7. 回答必须简短。问答模式（"问问AI"）：每次回复控制在60~150字，最多分2小段。解读模式（"AI大白话解读"）：每次回复控制在200~350字，分2~4个短段。

## 输出格式
不用Markdown标题（不用##、###），不用列表符号（不用1.2.3.或-），纯文字短段，段与段之间空一行。

## 语言要求（必须遵守）
必须全程使用简体中文回答。即使引用的联网检索内容或资料里出现英文句子、英文新闻标题，也必须翻译成中文后再引用，绝对不允许输出整句英文。MACD、KDJ、RSI、PEG 这类通用缩写可以保留原文，其余一律用中文表达。

## 违禁词（命中必须跳过，换其他方式表达）
建议买入、建议卖出、建议加仓、建议减仓、应该买、应该卖、赶紧买、赶紧卖、抄底、逃顶、追高、割肉、满仓、清仓、必涨、必跌、稳赚、保本、翻倍可期、目标价

## 兜底话术（遇到超范围问题时，随机选用其中一个）
"这个页面没讲到哦" / "我手头的资料里没有这个信息" / "这个问题超出我目前能回答的范围啦"
"""

_DISCLAIMER = "（以上内容由AI生成，仅是对历史数据的大白话解读，供学习参考，不构成任何投资建议，也不预示未来走势。）"

_DRAFT_PROMPT = (
    "【模式】解读模式（200~350字，分2~4个短段）\n"
    "【对象】「{name}」({symbol}) 的 {kind} 结果\n"
    "【资料】\n{data}\n\n"
    "请用大白话向新手解读这份结果说明了什么。只解释，不建议，不预测。"
)

_CRITIQUE_PROMPT = (
    "【模式】自查（只输出问题清单，不重写正文；没有问题就输出：无）\n"
    "逐条检查下面的草稿：\n"
    "一，有没有出现资料之外的数字；二，有没有暗示买卖操作或预测未来；"
    "三，有没有新手看不懂的术语没解释；四，结论有没有和资料矛盾。\n\n"
    "【资料】\n{data}\n\n【草稿】\n{draft}"
)

_REVISE_PROMPT = (
    "【模式】解读模式定稿（200~350字，分2~4个短段，不要标题、不要清单）\n"
    "请根据自查问题清单修订草稿；若清单为：无，就在原稿基础上轻微润色。\n\n"
    "【资料】\n{data}\n\n【草稿】\n{draft}\n\n【问题清单】\n{critique}"
)


def _ai_allow() -> None:
    """全站每日共享池自守。"""
    today = datetime.now().strftime("%Y%m%d")
    with _ai_lock:
        if _ai_usage["day"] != today:
            _ai_usage["day"] = today
            _ai_usage["count"] = 0
        if _ai_usage["count"] >= _AI_DAILY_CAP:
            raise ValueError("今日AI调用额度已用完，明天再来吧")
        _ai_usage["count"] += 1


def _call_once(model: str, messages: list[dict[str, str]], max_tokens: int) -> str:
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.4,
    }
    if NEWS_SEARCH_ENABLED:
        body["plugins"] = [{"id": "web", "max_results": 3}]
    req = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + OPENROUTER_API_KEY,
            "Content-Type": "application/json",
            "HTTP-Referer": "https://servicewechat.com",
            "X-Title": "Technical Analysis Learning Corner",
        },
    )
    with urllib.request.urlopen(req, timeout=28) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    choices = payload.get("choices") or []
    if not choices:
        err = (payload.get("error") or {}).get("message", "")
        raise ValueError("OpenRouter 未返回结果: " + str(err)[:100])
    return str(choices[0]["message"]["content"]).strip()


def _chat(messages: list[dict[str, str]], max_tokens: int = 900) -> str:
    """带每日额度自守与模型降级链的统一调用入口。"""
    if not OPENROUTER_API_KEY:
        raise ValueError("AI功能尚未配置：请在云托管环境变量填入 OPENROUTER_API_KEY")
    _ai_allow()
    last_err: Exception | None = None
    for model in OPENROUTER_MODELS:
        try:
            return _call_once(model, messages, max_tokens)
        except Exception as exc:
            last_err = exc
            try:
                print("[report_engine] model failed:", model, repr(exc))
            except Exception:
                pass
    raise ValueError("AI服务暂时不可用（免费模型繁忙或网络波动），请稍后再试") from last_err


def _compliance_filter(text: str) -> str:
    out = text
    for word in _FORBIDDEN_WORDS:
        out = out.replace(word, "——")
    return out


# ---------------- 联网实时搜索（免费方案：DuckDuckGo → Bing中国 双备源） ----------------
_WEB_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"


def _strip_tags(fragment: str) -> str:
    return re.sub(r"<[^>]+>", "", fragment or "").strip()


def _search_duckduckgo(query: str):
    url = "https://html.duckduckgo.com/html/?q=" + quote(str(query)[:80], safe="")
    req = urllib.request.Request(url, headers={"User-Agent": _WEB_UA})
    with urllib.request.urlopen(req, timeout=6) as resp:
        html = resp.read().decode("utf-8", "replace")
    titles = re.findall(r'class="result__a"[^>]*>(.*?)</a>', html, re.S)
    snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
    results = []
    for i in range(min(len(titles), len(snippets))):
        t = _strip_tags(titles[i])
        s = _strip_tags(snippets[i])
        if t and s:
            results.append({"title": t[:80], "snippet": s[:180]})
    return results


def _search_bing_cn(query: str):
    url = ("https://cn.bing.com/search?q=" + quote(str(query)[:80], safe="")
           + "&count=8&setlang=zh-CN&mkt=zh-CN")
    req = urllib.request.Request(url, headers={
        "User-Agent": _WEB_UA, "Accept-Language": "zh-CN,zh;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=6) as resp:
        html = resp.read().decode("utf-8", "replace")
    # 只取自然结果块，跳过广告区块（b_ad）
    blocks = re.findall(r'<li class="b_algo".*?</li>', html, re.S)
    results = []
    for block in blocks:
        if "b_ad" in block or "sponsor" in block.lower():
            continue
        tm = re.search(r'<h2[^>]*>.*?<a[^>]*>(.*?)</a>', block, re.S)
        sm = re.search(r'<p[^>]*>(.*?)</p>', block, re.S)
        if tm and sm:
            t = _strip_tags(tm.group(1))
            s = _strip_tags(sm.group(1))
            if t and s:
                results.append({"title": t[:80], "snippet": s[:180]})
    return results


def _relevance_filter(query: str, results: list) -> list:
    """相关性过滤：用问题关键词给结果打分，广告/无关内容自然被淘汰。"""
    q = str(query or "").lower()
    ascii_tokens = [t for t in re.findall(r"[a-z0-9]+", q) if len(t) >= 2]
    cjk = re.findall(r"[\u4e00-\u9fff]", q)
    bigrams = ["".join(p) for p in zip(cjk, cjk[1:])]
    singles = [c for c in cjk]
    scored = []
    seen_titles = set()
    for r in results:
        text = (r.get("title", "") + r.get("snippet", "")).lower()
        score = (sum(2 for t in ascii_tokens if t in text)
                 + sum(2 for b in bigrams if b in text)
                 + sum(1 for c in singles if c in text))
        title = r.get("title", "")
        if title in seen_titles:
            continue
        seen_titles.add(title)
        if score > 0:
            scored.append((score, r))
    scored.sort(key=lambda item: -item[0])
    filtered = [r for _, r in scored]
    # 全部不相关时直接返回空：宁可不用检索，也不把垃圾结果喂给模型
    return filtered


def web_search(query: str, max_results: int = 3) -> list:
    """联网实时搜索（DuckDuckGo 优先，Bing 备源）+ 相关性过滤，失败静默降级。"""
    for fn in (_search_duckduckgo, _search_bing_cn):
        try:
            results = fn(query)
            if results:
                return _relevance_filter(query, results)[:max_results]
        except Exception as exc:
            try:
                print("[report_engine] web search source failed:", fn.__name__, repr(exc))
            except Exception:
                pass
    return []


def _trim(data: Any, limit: int = 3000) -> str:
    text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + " …(已截断)"


def _chinese_ratio(text: str) -> float:
    """文字类字符中汉字占比；过低说明回答疑似英文。"""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    ascii_words = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    total = cjk + ascii_words
    return (cjk / total) if total else 1.0


def _chat_zh(messages: list[dict[str, str]], max_tokens: int = 900) -> str:
    """调用模型并确保中文输出：英文占比过高时自动重问一次（附强化指令）。"""
    answer = _chat(messages, max_tokens=max_tokens)
    if _chinese_ratio(answer) >= 0.5:
        return answer
    retry_messages = list(messages) + [
        {"role": "assistant", "content": answer},
        {"role": "user", "content": "你刚才的回复大量使用了英文，违反规则。请立刻把同样的内容重新用简体中文完整说一遍，不要出现整句英文。"},
    ]
    try:
        retry = _chat(retry_messages, max_tokens=max_tokens)
        if _chinese_ratio(retry) >= 0.3:
            return retry
    except Exception:
        pass
    return "抱歉，这次回答出了点问题，请换个问法再试一次哦。"


def interpret(kind: str, name: str, symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
    """AI大白话解读：三遍流水线；第 2/3 遍失败时降级为初稿，保证可用。"""
    data_brief = _trim(payload)
    draft = _chat([
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _DRAFT_PROMPT.format(name=name, symbol=symbol, kind=kind, data=data_brief)},
    ])
    final = draft
    steps = 1
    try:
        critique = _chat([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _CRITIQUE_PROMPT.format(draft=draft, data=data_brief)},
        ])
        steps = 2
        final = _chat([
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _REVISE_PROMPT.format(draft=draft, critique=critique, data=data_brief)},
        ])
        steps = 3
    except Exception:
        pass
    if _chinese_ratio(final) < 0.5:
        # 定稿仍疑似英文：附强化指令重问一次，避免把英文解读直接交给用户
        try:
            retry = _chat([
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _REVISE_PROMPT.format(draft=final, critique="全部改为简体中文，不允许整句英文", data=data_brief)},
            ])
            if _chinese_ratio(retry) >= 0.3:
                final = retry
        except Exception:
            pass
    return {"text": _compliance_filter(final), "steps": steps}


def _web_context(question: str) -> str:
    results = web_search(question)
    if not results:
        return ""
    lines = ["【联网检索（背景参考，据公开网络资料）】"]
    for i, r in enumerate(results):
        lines.append(str(i + 1) + ". " + r["title"] + "：" + r["snippet"])
    return "\n".join(lines)


def ask(page: str, context: str, question: str, history: list[dict[str, str]]) -> dict[str, Any]:
    """问问AI：基于页面资料的多轮问答（单轮调用，前端携带历史）。"""
    messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for item in (history or [])[-12:]:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "")[:400]
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    web_note = _web_context(question)
    messages.append({
        "role": "user",
        "content": (
            "【模式】问答模式（60~150字，最多2小段）\n"
            "【当前页面】" + (page or "未知页面") + "\n"
            "【资料】\n" + (context or "（当前页面没有额外资料）") + "\n\n"
            + ((web_note + "\n\n") if web_note else "")
            + "【用户问题】" + question
        ),
    })
    answer = _chat_zh(messages, max_tokens=320)
    return {"text": _compliance_filter(answer)}
