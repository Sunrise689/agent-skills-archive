"""QTE 量化新解 · 完整后端 API 模块（可直接挂载到现有 FastAPI 服务）"

放置位置：backend_v10/wechat-miniprogram/backend/qte_api.py
挂载方式（在 app.py 中加两行）：

    from qte_api import router as qte_router
    app.include_router(qte_router)

依赖：qte 包（factor_engine / plain_report / report_image / retrieval / factor_registry
等全部已建成），以及 app.py 现有 market_data 行情通道

接口清单：
    GET /api/v1/qte/discover        因子归因总入口（结构化数据 + 热力图格子 + 大白话报告）
    GET /api/v1/qte/report-image    热力图报告图片（PNG，可直接给 image 组件用）
    GET /api/v1/qte/factor-explain  单因子解释（热力图格子点击 → 知识库大白话 + 证据）
    GET /api/v1/qte/search          知识库检索（前端展示口径，CN 资料 display_policy 过滤）

合规：全部输出为历史统计描述，附"不预示未来、不构成投资建议"；LLM 不参与计算
"""
from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

# ---------------- 路径装配（与 app.py 一致） ----------------
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parents[1]
for _p in (str(PROJECT_ROOT), str(BACKEND_DIR), str(PROJECT_ROOT / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from qte.factor_engine import run_attribution  # noqa: E402
from qte.plain_report import build_plain_report  # noqa: E402
from qte.report_image import build_heatmap_cells, render_heatmap_report, REPORT_DIR  # noqa: E402
from qte import retrieval  # noqa: E402
import json  # noqa: E402

router = APIRouter(prefix="/api/v1/qte", tags=["qte"])

REGISTRY_PATH = PROJECT_ROOT / "qte" / "factor_registry.json"
LEXICON_PATH = PROJECT_ROOT / "qte" / "translation_lexicon.json"
EVIDENCE_PATH = PROJECT_ROOT / "qte" / "evidence" / "compiled_quant_evidence.jsonl"

# R² 解释力分档（行业通行经验阈值，已同步登记进 quant_rules.json）
R2_WEAK, R2_MODERATE = 0.15, 0.5


def _r2_level(r2: float | None) -> dict[str, Any]:
    if r2 is None:
        return {"level": "unknown", "message": "模型解释力未知"}
    if r2 < R2_WEAK:
        return {"level": "weak", "message": f"R²={r2:.2f}，模型基本没有解释力，这次涨跌大部分解释不了，结论仅供参考"}
    if r2 < R2_MODERATE:
        return {"level": "moderate", "message": f"R²={r2:.2f}，模型能解释一部分涨跌，剩下的仍是未知"}
    return {"level": "strong", "message": f"R²={r2:.2f}，模型对这次涨跌的解释力较强"}


# 因子全集（继续学习用）：只收录有实际意义的核心因子，主观/难测量/无实证的已剔除
CORE_FACTORS = [
    "market_beta", "industry_beta", "size", "value_pe", "value_pb",
    "momentum_12_1", "short_term_reversal", "residual_momentum",
    "volatility_realized", "maximum_drawdown", "trend_strength",
    "quality_roe", "quality_gross_margin", "growth_earnings",
    "leverage", "dividend_yield",
]

# ---------------- 轻量限流（与 app.py 同策略：60 秒 / 30 次 / 用户----------------
_RATE_WINDOW = 60.0
_RATE_MAX = 30
_RATE_LOCK = threading.Lock()
_RATE_BUCKETS: dict[str, list[float]] = {}


def _request_identity(request: Request, explicit_openid: str = "") -> str:
    gateway_openid = (
        request.headers.get("X-WX-OPENID")
        or request.headers.get("x-wx-openid")
        or ""
    ).strip()
    if gateway_openid:
        return f"wx:{gateway_openid[:128]}"
    if explicit_openid and explicit_openid != "anonymous":
        return f"wx:{explicit_openid[:128]}"
    host = request.client.host if request.client else "anonymous"
    return f"ip:{host}"


def _check_rate(request: Request, explicit_openid: str = "") -> None:
    now = time.time()
    identity = _request_identity(request, explicit_openid)
    with _RATE_LOCK:
        hits = [t for t in _RATE_BUCKETS.get(identity, []) if now - t < _RATE_WINDOW]
        if len(hits) >= _RATE_MAX:
            wait = max(5, int(_RATE_WINDOW - (now - hits[0])) + 1)
            raise HTTPException(status_code=429, detail=f"请求太频繁，请约 {wait} 秒后再试")
        hits.append(now)
        _RATE_BUCKETS[identity] = hits
        if len(_RATE_BUCKETS) > 5000:
            stale_before = now - _RATE_WINDOW
            stale = [
                key
                for key, values in _RATE_BUCKETS.items()
                if not values or values[-1] < stale_before
            ]
            for key in stale:
                _RATE_BUCKETS.pop(key, None)


def _normalize_symbol(value: str) -> str:
    raw = "".join(str(value or "").lower().split())
    if raw.startswith(("sh", "sz", "bj")) and len(raw) == 8 and raw[2:].isdigit():
        return raw
    if len(raw) == 6 and raw.isdigit():
        return ("sh" if raw[0] in "5689" else "sz") + raw
    # 港股：hk + 5 位数字
    if raw.startswith("hk") and len(raw) == 7 and raw[2:].isdigit():
        return raw
    # 美股：us + ticker（指数 ^ 开头除外，市场数据层自行路由）
    if raw.startswith("us"):
        ticker = raw[2:]
        if re.fullmatch(r"[a-z][a-z0-9.\-]{0,10}", ticker):
            return raw
    raise HTTPException(status_code=400, detail="当前量化归因支持 A股/港股/美股代码，例如 sz000858、hk00700、usaapl")


def _load_registry() -> dict[str, Any]:
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _registry_entries(registry: dict[str, Any]) -> list[dict[str, Any]]:
    """正典因子与运行时代理分层保存，但解释接口应能覆盖两者。"""
    canonical = registry.get("factors") or []
    runtime = registry.get("runtime_style_factors") or []
    return [
        item
        for item in [*canonical, *runtime]
        if isinstance(item, dict) and item.get("factor_id")
    ]


def _stat_terms_payload(attribution: dict[str, Any]) -> list[dict[str, Any]]:
    """深入学习区：把本次计算涉及的统计术语与大白话解释、实际数值一起返回。"""
    exposures = attribution.get("exposures", {})
    wanted = {
        "模型解释力": attribution.get("r_squared_full_sample"),
        "贝塔联动系数": exposures.get("market_beta"),
        "波动": exposures.get("volatility_realized"),
        "回撤": exposures.get("maximum_drawdown"),
    }
    skew = exposures.get("skewness")
    kurt = exposures.get("kurtosis")
    if skew is not None:
        wanted["偏度"] = skew
    if kurt is not None:
        wanted["峰度"] = kurt
    out: list[dict[str, Any]] = []
    try:
        with open(LEXICON_PATH, "r", encoding="utf-8") as f:
            lexicon = json.load(f)
        for term in lexicon.get("terms", []):
            name = term.get("term")
            if name in wanted and wanted[name] is not None:
                out.append({
                    "term": name,
                    "value": wanted[name],
                    "plain": term.get("plain"),
                    "usage_note": term.get("usage_note"),
                })
    except Exception:
        pass
    return out


# ---------------- 1. 因子归因总入口 ------------------------------

@router.get("/discover")
def discover(
    request: Request,
    symbol: str = Query(..., min_length=3, max_length=10),
    days: int = Query(63, ge=21, le=1500),
    openid: str = Query("anonymous", max_length=64),
) -> dict[str, Any]:
    """因子归因：结构化数据 + 热力图格子 + 大白话报告，一次返回结果

    前端推荐渲染方式：heatmap_cells 画统一热力图，格子点击 → /factor-explain
    plain_report 直接按分节展示，detail 放默认折叠的统计层
    """
    _check_rate(request, openid)
    normalized = _normalize_symbol(symbol)
    try:
        attribution = run_attribution(normalized, attribution_days=days)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        print("[qte_api] discover failed:", repr(exc))
        raise HTTPException(status_code=502, detail="归因服务暂时繁忙，请稍后再试") from exc

    # 生成热力图图片并编码为 base64（供前端 image 组件直接显示）
    today_b64 = time.strftime("%Y%m%d")
    img_cache = REPORT_DIR / f"{normalized}_heatmap_{today_b64}_d{days}.png"
    if not img_cache.exists():
        try:
            render_heatmap_report(attribution, img_cache)
        except Exception:
            pass
    img_b64 = ""
    if img_cache.exists():
        try:
            import base64 as _b64
            img_b64 = _b64.b64encode(img_cache.read_bytes()).decode("ascii")
        except Exception:
            pass

    plain = build_plain_report(attribution)
    return {
        "source": "qte_factor_engine",
        "symbol": normalized,
        "name": (attribution.get("fundamentals") or {}).get("name"),
        "window": attribution.get("window"),
        "period_return": attribution.get("period_return"),
        "r_squared": attribution.get("r_squared_full_sample"),
        "heatmap_cells": build_heatmap_cells(attribution),
        "plain_report": plain,
        "detail": {
            "contributions": attribution.get("contributions"),
            "residual": attribution.get("residual"),
            "exposures": attribution.get("exposures"),
            "industry": attribution.get("industry"),
            "fundamentals": attribution.get("fundamentals"),
            "pending": attribution.get("pending"),
            "note": "统计口径层：偏度、峰度、特质波动等数值在 exposures 中，小程序默认折叠",
        },
        "report_image_url": f"/api/v1/qte/report-image?symbol={normalized}&days={days}",
        "stat_terms": _stat_terms_payload(attribution),
        "r2_assessment": _r2_level(attribution.get("r_squared_full_sample")),
        "qualifier": attribution.get("qualifier"),
        "image_base64": img_b64,
    }


# ---------------- 2. 热力图报告图片 ----------------

@router.get("/report-image")
def report_image(
    request: Request,
    symbol: str = Query(..., min_length=6, max_length=10),
    days: int = Query(63, ge=21, le=1500),
    openid: str = Query("anonymous", max_length=64),
) -> FileResponse:
    _check_rate(request, openid)
    normalized = _normalize_symbol(symbol)
    # 同一标的+天数当日只生成一次，复用磁盘结果
    today = time.strftime("%Y%m%d")
    cached = REPORT_DIR / f"{normalized}_heatmap_{today}_d{days}.png"
    if not cached.exists():
        try:
            attribution = run_attribution(normalized, attribution_days=days)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            print("[qte_api] report-image failed:", repr(exc))
            raise HTTPException(status_code=502, detail="报告图生成繁忙，请稍后再试") from exc
        render_heatmap_report(attribution, cached)
    return FileResponse(cached, media_type="image/png")


# ---------------- 3. 单因子解释（热力图格子点击） ----------------

@router.get("/factor-explain")
def factor_explain(factor_id: str = Query(..., min_length=2, max_length=48)) -> dict[str, Any]:
    """QTE 知识库取因子的大白话定义、风险提示与证据。不产生任何计算结论"""
    registry = _load_registry()
    entry = None
    for item in _registry_entries(registry):
        if item.get("factor_id") == factor_id:
            entry = item
            break
    if entry is None:
        raise HTTPException(status_code=404, detail="该因子暂未收录")

    # 翻译词条
    lexicon_hit = None
    try:
        with open(LEXICON_PATH, "r", encoding="utf-8") as f:
            lexicon = json.load(f)
        for term in lexicon.get("terms", []):
            aliases = [term.get("term", "")] + list(term.get("alias", []))
            if factor_id in " ".join(aliases).lower() or term.get("term") == entry.get("name_zh"):
                lexicon_hit = {"plain": term.get("plain"), "usage_note": term.get("usage_note")}
                break
    except Exception:
        pass

    # 证据（只取已编译证据，evidence_pending 如实标注。）
    evidence: list[dict[str, Any]] = []
    try:
        with open(EVIDENCE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("factor_id") == factor_id:
                    evidence.append({
                        "evidence_type": record.get("evidence_type"),
                        "claim_plain": record.get("claim_plain"),
                        "caveat": record.get("caveat"),
                        "source_title": record.get("source_title"),
                        "market": record.get("market"),
                        "period": record.get("period"),
                    })
    except Exception:
        pass

    availability = entry.get("data_availability", {})
    return {
        "factor_id": factor_id,
        "name_zh": entry.get("name_zh"),
        "name_en": entry.get("name_en"),
        "plain_definition": entry.get("plain_definition"),
        "academic_definition": entry.get("academic_definition"),
        "computation": entry.get("computation"),
        "lexicon": lexicon_hit,
        "failure_scenarios": entry.get("failure_scenarios", []),
        "evidence": evidence,
        "data_availability": availability,
        "qualifier": "因子是观察工具，不是赚钱配方；历史描述不预示未来，不构成投资建议",
    }


# ---------------- 3.5 因子全集（继续学习，只含有意义的核心因子）----------------

@router.get("/factor-catalog")
def factor_catalog() -> dict[str, Any]:
    """继续学习用因子全集：只收录有实际意义的核心因子，附大白话+数学定义。

    筛选口径：主观类（分析师情绪）、无法精确测量类（拥挤度）、无实证支撑类已剔除。
    单因子解释力 R²<0.15 视为基本无解释力，不单独作为结论依据。
    """
    registry = _load_registry()
    entries = {item.get("factor_id"): item for item in registry.get("factors", [])}
    groups: dict[str, list[dict[str, Any]]] = {}
    for fid in CORE_FACTORS:
        entry = entries.get(fid)
        if not entry:
            continue
        item = {
            "factor_id": fid,
            "name_zh": entry.get("name_zh"),
            "plain_definition": entry.get("plain_definition"),
            "computation": entry.get("computation"),
            "failure_scenarios": entry.get("failure_scenarios", []),
        }
        groups.setdefault(str(entry.get("category", "other")), []).append(item)
    return {
        "groups": groups,
        "count": sum(len(v) for v in groups.values()),
        "note": "以上为核心因子全集（已剔除主观与难测量项）。单因子解释R² 低于 0.15 视为基本无解释力",
    }


# ---------------- 4. 知识库检索（前端展示口径）----------------

@router.get("/search")
def search_knowledge(
    request: Request,
    q: str = Query(..., min_length=1, max_length=60),
    top_k: int = Query(5, ge=1, le=12),
    openid: str = Query("anonymous", max_length=64),
) -> dict[str, Any]:
    """BM25 检"QTE 知识库。frontend_visible=True：CN 资料 display_policy 过滤"""
    _check_rate(request, openid)
    hits = retrieval.search(q, top_k=top_k, filters={"frontend_visible": True})
    results = []
    for hit in hits:
        meta = hit.get("metadata", {})
        results.append({
            "record_type": meta.get("record_type"),
            "title": meta.get("title") or meta.get("term") or meta.get("factor_id"),
            "summary": meta.get("plain_summary") or meta.get("plain") or meta.get("claim_plain"),
            "caveat": meta.get("caveat"),
            "source_id": meta.get("source_id"),
            "score": round(hit.get("score", 0.0), 4),
        })
    return {
        "query": q,
        "results": results,
        "qualifier": "检索结果均为历史资料与定义，不构成投资建议",
    }


# ---------------- 本地自测 ----------------
