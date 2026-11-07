from __future__ import annotations

import json
import logging
import math
import re
import sys
import time
import threading
import urllib.request
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import quote

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kline_pattern_report import (  # noqa: E402
    _guide_definition,
    calculate_pivots,
    fetch_tencent_daily,
    harmonize_directions,
    resample_monthly,
    resample_weekly,
    trend_direction,
)
from pattern_core_v7 import detect_all  # noqa: E402
from fae.judgment import (  # noqa: E402
    JudgmentEngine,
    Timeframe,
    canonicalize_pattern_id,
    from_v7_events,
    get_pattern,
)
try:
    from .chan_engine import analyze_chan
    from .indicator_engine import analyze_indicator
    from .ma_engine import analyze_moving_average
    from .market_data import fetch_daily
    from .qte_api import router as qte_router
    from .report_engine import ask as ai_ask
    from .report_engine import interpret as ai_interpret
    from .valuation_data import build_valuation
except ImportError:  # Allow the documented backend-directory local command.
    from chan_engine import analyze_chan
    from indicator_engine import analyze_indicator
    from ma_engine import analyze_moving_average
    from market_data import fetch_daily
    from qte_api import router as qte_router
    from report_engine import ask as ai_ask
    from report_engine import interpret as ai_interpret
    from valuation_data import build_valuation

app = FastAPI(
    title="Kline Pattern Master API",
    version="2.0.0",
    docs_url="/docs",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(qte_router)


SYMBOL_NAMES = {
    "sh000001": "上证指数",
    "sh518880": "黄金ETF",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sz000001": "平安银行",
    "hk00700": "腾讯控股",
    "hk09988": "阿里巴巴-SW",
    "us^gspc": "标普500",
    "us^ixic": "纳斯达克综合指数",
    "us^dji": "道琼斯工业指数",
    "usspy": "标普500 ETF",
    "usqqq": "纳斯达克100 ETF",
    "usgld": "黄金 ETF",
    "usgc=f": "国际金价",
    "uscl=f": "国际油价",
    "comgold": "国际金价",
    "comoil": "国际油价",
    "comsilver": "国际银价",
    "usndx": "纳斯达克100",
    "hkhsi": "恒生指数",
    "fxusdcnh": "美元兑离岸人民币",
    "fxusdjpy": "美元兑日元",
    "fxeurusd": "欧元兑美元",
    "fxgbpusd": "英镑兑美元",
    "usaapl": "苹果",
    "usmsft": "微软",
    "usnvda": "英伟达",
    "ustsla": "特斯拉",
    "usamzn": "亚马逊",
    "usgoogl": "谷歌-A",
    "usmeta": "Meta平台",
}

CATEGORY_LABELS = {
    "simple": "simple",
    "composite": "composite",
    "trend": "trend",
    "chart": "chart",
    "gap": "gap",
}

CHART_PATTERN_NAMES = {
    "上升趋势线",
    "下降趋势线",
    "双顶",
    "双底",
    "三重顶",
    "三重底",
    "头肩顶",
    "头肩底",
    "上升三角形",
    "下降三角形",
    "对称三角形",
    "收敛三角形",
    "矩形整理",
    "上升楔形",
    "下降楔形",
    "旗形",
    "三角旗形",
    "圆顶",
    "圆底",
    "V形顶",
    "V形底",
}

IMPORTANT_PATTERN_NAMES = {
    "看涨吞没",
    "看跌吞没",
    "早晨之星",
    "黄昏之星",
    "早晨十字星",
    "黄昏十字星",
    "红三兵",
    "三个白色武士",
    "三只乌鸦",
    "黑三兵",
    "上升三法",
    "下降三法",
    "塔形顶",
    "塔形底",
    "岛形顶",
    "岛形底",
    "加速上升",
    "加速下跌",
    "绵绵阴跌",
} | CHART_PATTERN_NAMES

DIRECTION_MAP = {
    "bull": "bull",
    "bear": "bear",
    "neutral": "neutral",
    "bullish": "bull",
    "bearish": "bear",
    "up": "bull",
    "down": "bear",
}

CANONICAL_STATES = {"candidate", "confirmed", "degraded", "invalidated"}

LOGGER = logging.getLogger("technical_analysis_api")
FAE_CONTRACT_VERSION = "2.0.0"
_FAE_ENGINE = JudgmentEngine()

# 行情数据内存缓存：同一标的+年限短时间内重复请求直接命中，避免反复拉取外部行情
_FRAME_CACHE: dict[tuple[str, int], tuple[float, "pd.DataFrame"]] = {}
_FRAME_CACHE_LOCK = threading.Lock()
_FRAME_CACHE_TTL = 600

# 免费行情与 AI 接口的进程内保护。优先采用网关传入的微信 OPENID；
# 本地/非微信调用按客户端 IP 隔离，避免所有匿名用户共用同一个桶。
_RATE_WINDOW = 60.0
_RATE_MAX = 30
_RATE_BUCKETS: dict[str, list[float]] = {}


def _request_identity(request: Request) -> str:
    openid = (
        request.headers.get("X-WX-OPENID")
        or request.headers.get("x-wx-openid")
        or ""
    ).strip()
    if openid:
        return f"wx:{openid[:128]}"
    host = request.client.host if request.client else "anonymous"
    return f"ip:{host}"


def _check_rate(request: Request) -> None:
    identity = _request_identity(request)
    now = time.time()
    with _FRAME_CACHE_LOCK:
        hits = [
            stamp
            for stamp in _RATE_BUCKETS.get(identity, [])
            if now - stamp < _RATE_WINDOW
        ]
        if len(hits) >= _RATE_MAX:
            wait = max(5, int(_RATE_WINDOW - (now - hits[0])) + 1)
            raise HTTPException(
                status_code=429,
                detail=f"请求太频繁，请约 {wait} 秒后再试。",
            )
        hits.append(now)
        _RATE_BUCKETS[identity] = hits
        if len(_RATE_BUCKETS) > 5000:
            # 清理过期桶而不是整体清空，避免并发高峰突然解除所有限流。
            stale_before = now - _RATE_WINDOW
            stale = [
                key
                for key, values in _RATE_BUCKETS.items()
                if not values or values[-1] < stale_before
            ]
            for key in stale:
                _RATE_BUCKETS.pop(key, None)


def _cached_daily(normalized: str, years: int) -> pd.DataFrame:
    key = (normalized, int(years))
    now = time.time()
    with _FRAME_CACHE_LOCK:
        entry = _FRAME_CACHE.get(key)
        if entry and now - entry[0] < _FRAME_CACHE_TTL:
            return entry[1].copy()
    frame = fetch_daily(normalized, years=max(1, int(years)))
    with _FRAME_CACHE_LOCK:
        if len(_FRAME_CACHE) >= 64:
            oldest = min(_FRAME_CACHE.items(), key=lambda item: item[1][0])[0]
            _FRAME_CACHE.pop(oldest, None)
        _FRAME_CACHE[key] = (now, frame)
    return frame.copy()


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _round(value: Any) -> float:
    return round(_finite(value), 2)


def _normalize_symbol(value: str) -> str:
    raw = "".join(str(value or "").lower().split())
    if raw.startswith(("sh", "sz", "bj")) and len(raw) == 8 and raw[2:].isdigit():
        return raw
    if raw.startswith("hk") and len(raw) == 7 and raw[2:].isdigit():
        return raw
    if len(raw) == 6 and raw.isdigit():
        return ("sh" if raw[0] in "5689" else "sz") + raw
    if len(raw) == 5 and raw.isdigit():
        return "hk" + raw
    if raw.startswith("us") and 3 <= len(raw) <= 26 and re.fullmatch(r"us[a-z0-9^=._-]+", raw):
        return raw
    if raw in {"comgold", "comoil", "comsilver"}:
        return raw
    if raw == "hkhsi":
        return raw
    if re.fullmatch(r"fx[a-z]{6}", raw):
        return raw
    if re.fullmatch(r"[a-z][a-z0-9._-]{0,10}", raw):
        return "us" + raw
    raise ValueError("请输入有效代码，例如 sh000001、hk00700、usAAPL、comgold 或 fxusdcnh")


def _long_ma(daily: pd.DataFrame, symbol: str) -> pd.DataFrame:
    frame = daily.copy()
    period = 250 if symbol.startswith(("sh", "sz", "bj")) else 200
    frame["LongMA"] = frame["Close"].rolling(period, min_periods=period).mean()
    return frame


def _period_frames(daily: pd.DataFrame) -> dict[str, pd.DataFrame]:
    daily_ma = daily.set_index("Date")["LongMA"].sort_index()
    weekly = resample_weekly(daily)
    monthly = resample_monthly(daily)
    weekly["LongMA"] = [daily_ma.asof(date) for date in weekly["Date"]]
    monthly["LongMA"] = [daily_ma.asof(date) for date in monthly["Date"]]
    return {
        "M": monthly.tail(72).reset_index(drop=True),
        "W": weekly.tail(96).reset_index(drop=True),
        "D": daily.tail(120).reset_index(drop=True),
    }


def _validated_pivots(
    frame: pd.DataFrame,
    *,
    max_labels: int,
) -> list[dict[str, Any]]:
    """Return finite, ordered, alternating pivots inside the visible frame."""
    if frame.empty or len(frame) < 7:
        return []
    # The visible mobile windows are 72/96/120 bars.  A very small radius
    # overreacts to candle noise and may still miss broad swings because the
    # prominence window is too narrow.  Roughly one tenth of the window keeps
    # the pivots structural while preserving several recent turns.
    radius = max(3, min(15, len(frame) // 10))
    raw = calculate_pivots(frame, length=radius, max_labels=max_labels)
    result: list[dict[str, Any]] = []
    for item in raw:
        try:
            index = int(item["idx"])
            price = float(item["price"])
            kind = str(item["kind"])
        except (KeyError, TypeError, ValueError):
            continue
        if kind not in {"high", "low"} or not math.isfinite(price):
            continue
        if not 0 <= index < len(frame):
            continue
        candidate = {**item, "idx": index, "price": price, "kind": kind}
        if result and result[-1]["kind"] == kind:
            more_extreme = (
                price > float(result[-1]["price"])
                if kind == "high"
                else price < float(result[-1]["price"])
            )
            if more_extreme:
                result[-1] = candidate
        elif not result or index > int(result[-1]["idx"]):
            result.append(candidate)
    return result[-max_labels:]


def _levels(frame: pd.DataFrame) -> tuple[float, float]:
    recent = frame.tail(min(90, len(frame))).reset_index(drop=True)
    current = _finite(recent["Close"].iloc[-1])
    pivots = _validated_pivots(recent, max_labels=16)
    supports = [_finite(item["price"]) for item in pivots if item["kind"] == "low" and item["price"] < current]
    resistances = [_finite(item["price"]) for item in pivots if item["kind"] == "high" and item["price"] > current]
    tail = recent.tail(min(20, len(recent)))
    support = max(supports) if supports else _finite(tail["Low"].min(), current)
    resistance = min(resistances) if resistances else _finite(tail["High"].max(), current)
    typical_range = max(
        _finite((tail["High"] - tail["Low"]).mean(), 0.0),
        abs(current) * 0.002,
        1e-8,
    )
    if not math.isfinite(support) or support >= current:
        support = min(_finite(tail["Low"].min(), current - typical_range), current - typical_range)
    if not math.isfinite(resistance) or resistance <= current:
        resistance = max(_finite(tail["High"].max(), current + typical_range), current + typical_range)
    if support >= resistance:
        support = current - typical_range
        resistance = current + typical_range
    return support, resistance


def _confidence_label(value: Any) -> str:
    score = _finite(value, 0.5)
    if score >= 0.82:
        return "高"
    if score >= 0.67:
        return "中"
    return "低"


def _state_text(item: dict[str, Any]) -> str:
    name = str(item.get("name", "形态"))
    direction = DIRECTION_MAP.get(str(item.get("direction", "neutral")), "neutral")
    state = str(item.get("state", item.get("engine_state", "candidate")))
    if state == "confirmed":
        return "已满足当前确认条件，仍需结合大周期复核"
    if state == "degraded":
        return "背景削弱，保留为低强度候选"
    if state == "invalidated":
        return "条件失效，默认不作为主图信号"
    if name in {"十字星", "射击之星", "锤头线", "吊颈线", "岛形顶", "岛形底"}:
        return "反转线索，等待后续确认"
    if item.get("filled"):
        return "缺口已回补，观察回补后的方向"
    if item.get("category") == "gap":
        return "缺口未回补，观察支撑或压力"
    if direction == "bull":
        return "多方结构线索"
    if direction == "bear":
        return "空方结构线索"
    return "方向中性，结合位置确认"


def _event_payload(item: dict[str, Any], index: int, period: str) -> dict[str, Any]:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    raw_pattern_id = str(item.get("pattern_id") or item.get("pattern") or item.get("name") or "unknown_pattern")
    pattern_id = canonicalize_pattern_id(raw_pattern_id)
    record = get_pattern(pattern_id) or {}
    source_labels = metadata.get("source_labels", [])
    source_name = source_labels[0] if isinstance(source_labels, list) and source_labels else None
    name = str(
        item.get("name")
        or metadata.get("display_name_override")
        or record.get("name_zh")
        or source_name
        or pattern_id
    )
    raw_category = str(item.get("category", item.get("kind", "simple"))).lower()
    category = (
        "chart"
        if name in CHART_PATTERN_NAMES or raw_category == "chart"
        else CATEGORY_LABELS.get(raw_category, "composite" if raw_category == "combination" else "simple")
    )
    direction = DIRECTION_MAP.get(str(item.get("direction", "neutral")), "neutral")
    score = _finite(item.get("match_score", item.get("confidence", 0.5)), 0.5)
    raw_state = str(item.get("state", item.get("engine_state", "candidate")))
    state = raw_state if raw_state in CANONICAL_STATES else "candidate"
    trade_point = item.get("trade_point", metadata.get("trade_point"))
    suppressed = item.get("suppressed", metadata.get("suppressed", []))
    definition = str(record.get("definition") or _guide_definition(name))
    meaning = (
        "偏多线索，但必须服从大周期方向并观察后续是否守住形态低点。"
        if direction == "bull"
        else "偏空线索，但必须结合前置上涨、关键价位和后续下破确认。"
        if direction == "bear"
        else "表示多空暂时平衡，不能单独作为反转结论。"
    )
    confirmation = (
        "技术图形需等待价格有效突破支撑、阻力或颈线，并观察突破后能否站稳。"
        if category == "chart"
        else "反转形态需等待后续K线向预期方向突破；延续形态需确认关键边界未被反向破坏。"
    )
    important = (
        score >= 0.75
        or name in IMPORTANT_PATTERN_NAMES
        or (category in {"trend", "gap"} and score >= 0.6)
    )
    filled = bool(
        item.get(
            "filled",
            metadata.get("filled", metadata.get("gap_filled", False)),
        )
    )
    return {
        "id": f"{period}-{index}-{int(item.get('start', 0))}-{int(item.get('end', 0))}",
        "name": name,
        "category": category,
        "direction": direction,
        "start": max(0, int(item.get("start", item.get("idx", 0)))),
        "end": max(0, int(item.get("end", item.get("idx", 0)))),
        "confidenceLabel": _confidence_label(item.get("match_score", item.get("confidence", 0.5))),
        "important": important,
        "state": state,
        "stateText": _state_text({**item, "name": name, "category": category, "filled": filled}),
        "pattern_id": pattern_id,
        "variant": item.get("variant"),
        "confidence": round(max(0.0, min(1.0, score)), 4),
        "geometry": item.get("geometry") or {"lines": [], "arcs": [], "pivots": []},
        "trade_point": trade_point if state == "confirmed" else None,
        "suppressed": suppressed if isinstance(suppressed, list) else [],
        "definition": definition,
        "meaning": meaning,
        "confirmation": confirmation,
        "filled": filled,
    }


def _enrich_fae_signal(item: dict[str, Any], period: str) -> dict[str, Any]:
    """Attach stable display metadata without changing FAE canonical fields."""
    enriched = deepcopy(item)
    pattern_id = canonicalize_pattern_id(
        str(item.get("pattern_id") or item.get("pattern") or "unknown_pattern")
    )
    record = get_pattern(pattern_id) or {}
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    source_labels = metadata.get("source_labels", [])
    source_name = source_labels[0] if isinstance(source_labels, list) and source_labels else None
    enriched["pattern_id"] = pattern_id
    enriched["name"] = str(
        metadata.get("display_name_override")
        or record.get("name_zh")
        or source_name
        or pattern_id
    )
    enriched["name_en"] = str(record.get("name_en") or "")
    enriched["definition"] = str(record.get("definition") or "")
    enriched["registry_category"] = str(record.get("category") or "")
    enriched["period"] = period
    enriched["direction_short"] = DIRECTION_MAP.get(
        str(item.get("direction", "neutral")), "neutral"
    )
    return enriched


def _public_fae_payload(
    result: dict[str, Any],
    *,
    period: str,
    diagnostics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return the deployment API contract with one non-duplicated signal tree."""
    display = deepcopy(result.get("display", {}))
    for key in (
        "primary",
        "supporting",
        "candidates",
        "suppressed",
        "timeframe_deemphasized",
        "recent",
        "default",
        "all",
    ):
        values = display.get(key, [])
        if isinstance(values, list):
            display[key] = [
                _enrich_fae_signal(item, period)
                for item in values
                if isinstance(item, dict)
            ]
    manual_layers = display.get("manual_layers", {})
    if isinstance(manual_layers, dict):
        display["manual_layers"] = {
            str(kind): [
                _enrich_fae_signal(item, period)
                for item in values
                if isinstance(item, dict)
            ]
            for kind, values in manual_layers.items()
            if isinstance(values, list)
        }

    resolution = deepcopy(result.get("resolution", {}))
    if isinstance(resolution, dict):
        if isinstance(resolution.get("winner"), dict):
            resolution["winner"] = _enrich_fae_signal(resolution["winner"], period)
        if isinstance(resolution.get("losers"), list):
            resolution["losers"] = [
                _enrich_fae_signal(item, period)
                for item in resolution["losers"]
                if isinstance(item, dict)
            ]

    evidence = result.get("evidence", {})
    evidence_keys = (
        "trend",
        "position_pct",
        "atr",
        "volume_ratio",
        "shadow_frequency",
        "upper_shadow_frequency",
        "lower_shadow_frequency",
        "shadow_interpretation",
        "breakout_confirmed",
        "false_break",
        "gap_pair_confirmed",
    )
    evidence_summary = {
        key: evidence.get(key)
        for key in evidence_keys
        if isinstance(evidence, dict) and key in evidence
    }
    return {
        "contractVersion": FAE_CONTRACT_VERSION,
        "timeframe": result.get("timeframe"),
        "timeframePolicy": result.get("timeframe_policy", {}),
        "display": display,
        "resolution": resolution,
        "evidenceSummary": evidence_summary,
        "quantitativeFilter": result.get("quantitative_filter", {}),
        "matchedRules": result.get("matched_rules", []),
        "lifecycleReasons": result.get("lifecycle_reasons", []),
        "interpretations": result.get("interpretations", []),
        "caseConsensus": result.get("case_consensus", {}),
        "humanCalibration": result.get("human_calibration", {}),
        "diagnostics": diagnostics,
    }


def _service_error(label: str, exc: Exception) -> HTTPException:
    """Log internal details while returning a non-sensitive public error."""
    error_id = uuid.uuid4().hex[:12]
    LOGGER.exception("%s failed; error_id=%s", label, error_id, exc_info=exc)
    return HTTPException(
        status_code=502,
        detail=f"{label}暂时不可用，请稍后重试（错误编号：{error_id}）",
    )


def _bar_payload(frame: pd.DataFrame) -> list[dict[str, Any]]:
    result = []
    for row in frame.itertuples(index=False):
        long_ma = getattr(row, "LongMA", np.nan)
        result.append(
            {
                "date": pd.Timestamp(row.Date).strftime("%Y-%m-%d"),
                "open": _round(row.Open),
                "high": _round(row.High),
                "low": _round(row.Low),
                "close": _round(row.Close),
                "ma": None if pd.isna(long_ma) else _round(long_ma),
            }
        )
    return result


def _graphics(frame: pd.DataFrame, direction: str, support: float, resistance: float, period: str) -> list[dict[str, Any]]:
    pivots = _validated_pivots(frame, max_labels=14)
    typical_range = max(
        _finite((frame["High"] - frame["Low"]).tail(min(60, len(frame))).mean(), 0.0),
        abs(_finite(frame["Close"].iloc[-1])) * 0.002,
        1e-8,
    )
    # Suppress tiny alternating turns that are statistically valid pivots but
    # visually become noise on a phone-sized chart.
    wave_pivots: list[dict[str, Any]] = []
    for pivot in pivots:
        if not wave_pivots:
            wave_pivots.append(pivot)
            continue
        previous = wave_pivots[-1]
        if pivot["kind"] == previous["kind"]:
            more_extreme = (
                pivot["price"] > previous["price"]
                if pivot["kind"] == "high"
                else pivot["price"] < previous["price"]
            )
            if more_extreme:
                wave_pivots[-1] = pivot
            continue
        if abs(float(pivot["price"]) - float(previous["price"])) >= typical_range * 0.8:
            wave_pivots.append(pivot)
    wave_pivots = wave_pivots[-10:]
    points = [
        {"index": int(item["idx"]), "price": _round(item["price"]), "kind": item["kind"]}
        for item in wave_pivots
    ]

    graphics: list[dict[str, Any]] = []
    if len(points) >= 2:
        graphics.append(
            {
                "id": f"{period}-zigzag",
                "type": "zigzag",
                "name": "主要波段",
                "points": points,
            }
        )
    graphics.extend([
        {
            "id": f"{period}-support",
            "type": "support",
            "name": "支撑位",
            "price": _round(support),
        },
        {
            "id": f"{period}-resistance",
            "type": "resistance",
            "name": "阻力位",
            "price": _round(resistance),
        },
    ])

    line_kind = (
        "low"
        if direction == "上升趋势"
        else "high"
        if direction == "下降趋势"
        else ""
    )
    anchors = [point for point in points if point["kind"] == line_kind][-3:]
    if len(anchors) >= 2:
        x = np.asarray([point["index"] for point in anchors], dtype=float)
        y = np.asarray([point["price"] for point in anchors], dtype=float)
        slope, intercept = np.polyfit(x, y, 1)
        fitted = slope * x + intercept
        residual = float(np.sum((y - fitted) ** 2))
        total = float(np.sum((y - np.mean(y)) ** 2))
        fit_r2 = 1.0 if total <= 1e-12 else max(0.0, 1.0 - residual / total)
        expected_slope = slope > 0 if line_kind == "low" else slope < 0
        meaningful_move = abs(float(fitted[-1] - fitted[0])) >= typical_range * 0.25
    else:
        x = np.asarray([], dtype=float)
        fitted = np.asarray([], dtype=float)
        fit_r2 = 0.0
        expected_slope = False
        meaningful_move = False
    if len(anchors) >= 2 and expected_slope and meaningful_move and fit_r2 >= 0.45:
        line_points = [
            {"index": int(x[0]), "price": _round(fitted[0]), "kind": line_kind},
            {"index": int(x[-1]), "price": _round(fitted[-1]), "kind": line_kind},
        ]
        graphics.append(
            {
                "id": f"{period}-trendline",
                "type": "trendline",
                "name": "上升趋势线" if line_kind == "low" else "下降趋势线",
                "direction": "bull" if line_kind == "low" else "bear",
                "points": line_points,
                "anchorCount": len(anchors),
                "fitR2": round(fit_r2, 4),
            }
        )
    return graphics


def _period_payload(
    period: str,
    frame: pd.DataFrame,
    requested_years: int = 5,
    *,
    symbol: str = "",
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    raw = detect_all(
        frame,
        max_trend_per_direction=3,
        diagnostics=diagnostics,
    )
    timeframe = {
        "M": Timeframe.MONTHLY,
        "W": Timeframe.WEEKLY,
        "D": Timeframe.DAILY,
    }[period]
    candlestick_signals = from_v7_events(raw, timeframe=timeframe)
    direction = trend_direction(frame)
    support, resistance = _levels(frame)
    trend_context = {
        "上升趋势": "up",
        "下降趋势": "down",
        "震荡整理": "range",
    }.get(direction, "range")
    fae_result = _FAE_ENGINE.evaluate(
        frame,
        candlestick_signals,
        reference_levels={"support": support, "resistance": resistance},
        context={
            "symbol": symbol,
            "period": period,
            "requested_years": int(requested_years),
            "trend": trend_context,
        },
        timeframe=timeframe,
        display_mode="adaptive",
    )
    fae_payload = _public_fae_payload(
        fae_result,
        period=period,
        diagnostics=diagnostics,
    )
    patterns = [
        _event_payload(item, index, period)
        for index, item in enumerate(fae_payload["display"].get("default", []))
    ]
    horizon = {"M": "长期", "W": "中期", "D": "短期"}[period]
    stage = {
        "上升趋势": f"{horizon}价格重心正在抬高",
        "下降趋势": f"{horizon}价格重心正在下移",
        "震荡整理": f"{horizon}价格在区间内整理",
    }.get(direction, "当前结构需要更多数据")
    objective = (
        f"当前{direction}。最近支撑 {_round(support)}，最近阻力 {_round(resistance)}；"
        "先观察价格在关键价位的实际反应。"
    )
    rule_summary = {
        "M": "月线决定主要方向。单个反转形态必须处在趋势末端，并获得后续K线确认。",
        "W": "周线用于判断中期力度。组合形态需结构完整，冲突形态只保留位置合理的一项。",
        "D": "日线用于寻找执行位置。趋势形态、缺口和突破要服从月线与周线背景。",
    }[period]
    bars = _bar_payload(frame)
    smooth_window = max(3, min(18, round(len(frame) / 24)))
    smooth = frame["Close"].rolling(smooth_window, min_periods=1).mean().to_numpy(float)
    for index, bar in enumerate(bars):
        bar["smooth"] = _round(smooth[index])
    # 三周期统一显示真实K线；平滑曲线仅作为可选参考数据保留在 bars[].smooth
    display_mode = "candles"
    return {
        "direction": direction,
        "stage": stage,
        "support": _round(support),
        "resistance": _round(resistance),
        "latest": _round(frame["Close"].iloc[-1]),
        "objectiveSummary": objective,
        "ruleSummary": rule_summary,
        "bars": bars,
        "displayMode": display_mode,
        "smoothWindow": smooth_window,
        "patterns": patterns,
        "graphics": _graphics(frame, direction, support, resistance, period),
        "fae": fae_payload,
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "technical-analysis-api", "status": "ok"}


@app.get("/api/v1/analyze")
def analyze(
    symbol: str = Query(..., min_length=3, max_length=26),
    years: int = Query(12, ge=3, le=20),
) -> dict[str, Any]:
    try:
        normalized = _normalize_symbol(symbol)
        daily = _long_ma(_cached_daily(normalized, years), normalized)
        if len(daily) < 30:
            raise ValueError("可用K线数量不足，至少需要约30个交易日")
        frames = _period_frames(daily)
        periods = {
            key: _period_payload(
                key,
                frames[key],
                requested_years=years,
                symbol=normalized,
            )
            for key in frames
        }
        latest = daily.iloc[-1]
        previous = daily.iloc[-2]
        change_pct = (_finite(latest["Close"]) / max(abs(_finite(previous["Close"])), 1e-9) - 1) * 100
        monthly, weekly, daily_direction = (
            periods["M"]["direction"],
            periods["W"]["direction"],
            periods["D"]["direction"],
        )
        harmonized = harmonize_directions(monthly, weekly, daily_direction)
        overview = (
            f"月线为{monthly}，决定当前主要方向；"
            f"周线表现为{harmonized['W']}，日线表现为{harmonized['D']}。"
            "先服从大周期，再观察小周期是否在关键价位出现经过确认的转折。"
        )
        return {
            "source": "python",
            "faeContractVersion": FAE_CONTRACT_VERSION,
            "symbol": normalized.upper(),
            "name": SYMBOL_NAMES.get(normalized, normalized.upper()),
            "updatedAt": pd.Timestamp(latest["Date"]).strftime("%Y-%m-%d"),
            **_coverage_payload(years, daily),
            "latest": _round(latest["Close"]),
            "changePct": _round(change_pct),
            "overview": overview,
            "periods": periods,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _service_error("分析服务", exc) from exc


def _feature_frame(symbol: str, years: int, minimum: int = 120) -> tuple[str, pd.DataFrame]:
    normalized = _normalize_symbol(symbol)
    frame = _cached_daily(normalized, years)
    if len(frame) < minimum:
        raise ValueError(f"可用行情不足，至少需要{minimum}根K线")
    return normalized, frame.reset_index(drop=True)


def _coverage_payload(requested_years: int, frame: pd.DataFrame) -> dict[str, Any]:
    days = len(frame)
    available_years = days / 252.0
    if days < 252:
        note = f"上市历史不足1年，按实际 {days} 个交易日计算。"
    elif available_years + 0.25 < requested_years:
        note = f"可用历史约 {available_years:.1f} 年，短于请求的 {requested_years} 年，已按实际历史计算。"
    else:
        note = f"按请求的 {requested_years} 年回看。"
    return {"availableDays": days, "availableYears": round(available_years, 1), "coverageNote": note}


@app.get("/api/v1/moving-average")
def moving_average(
    symbol: str = Query(..., min_length=3, max_length=26),
    years: int = Query(5, ge=1, le=20),
    min_trades: int = Query(5, ge=2, le=30),
    method: str = Query("single", pattern="^(single|cross|triple|midline)$"),
    mode: str = Query("basic", pattern="^(basic|adaptive)$"),
) -> dict[str, Any]:
    try:
        normalized, frame = _feature_frame(symbol, years, minimum=10)
        return {
            "source": "python",
            "symbol": normalized.upper(),
            "name": SYMBOL_NAMES.get(normalized, normalized.upper()),
            "updatedAt": pd.Timestamp(frame["Date"].iloc[-1]).strftime("%Y-%m-%d"),
            **analyze_moving_average(
                frame,
                years=years,
                min_trades=min_trades,
                method=method,
                mode=mode,
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _service_error("均线分析", exc) from exc


@app.get("/api/v1/indicators")
def indicators(
    symbol: str = Query(..., min_length=3, max_length=26),
    indicator: str = Query("macd", min_length=2, max_length=20),
    years: int = Query(3, ge=1, le=20),
) -> dict[str, Any]:
    try:
        normalized, frame = _feature_frame(symbol, years, minimum=20)
        return {
            "source": "python",
            "symbol": normalized.upper(),
            "name": SYMBOL_NAMES.get(normalized, normalized.upper()),
            "updatedAt": pd.Timestamp(frame["Date"].iloc[-1]).strftime("%Y-%m-%d"),
            **_coverage_payload(years, frame),
            **analyze_indicator(frame, indicator=indicator, years=years),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _service_error("指标分析", exc) from exc


# ---------------- 联想搜索：本地目录 + 东方财富 suggest ----------------

SEARCH_TOKEN = "D43BF722C8E33BDC906FB84D85E326E8"
_INDEX_CODE_MAP = {
    "SPX": ("us^GSPC", "标普500"),
    "IXIC": ("us^IXIC", "纳斯达克综合"),
    "NDX": ("us^NDX", "纳斯达克100"),
    "DJIA": ("us^DJI", "道琼斯"),
    "DJI": ("us^DJI", "道琼斯"),
    "HSI": ("hkHSI", "恒生指数"),
    "UDI": (None, "美元指数"),
}


def _suggest_symbol(mkt: str, code: str, name: str) -> dict[str, Any] | None:
    """把东财联想结果映射为小程序内部代码；不支持的返回 supported=False。"""
    mkt = str(mkt)
    if mkt == "1":
        return {"symbol": "sh" + code, "name": name, "market": "中国 · A股", "supported": True}
    if mkt == "0":
        return {"symbol": "sz" + code, "name": name, "market": "中国 · A股", "supported": True}
    if mkt == "116" and re.fullmatch(r"\d{5}", code):
        return {"symbol": "hk" + code, "name": name, "market": "港股", "supported": True}
    if mkt in {"105", "106", "107"} and re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,10}", code):
        return {"symbol": "us" + code.lower(), "name": name, "market": "美股", "supported": True}
    if mkt == "100":
        mapped = _INDEX_CODE_MAP.get(code.upper())
        if mapped and mapped[0]:
            return {"symbol": mapped[0], "name": name or mapped[1], "market": "全球 · 指数", "supported": True}
        return {"symbol": "", "name": name, "market": "全球 · 指数", "supported": False,
                "note": "该指数暂未接入历史数据"}
    if mkt in {"101", "102", "112", "118"}:
        return {"symbol": "", "name": name, "market": "商品 · 期货", "supported": False,
                "note": "该商品合约暂未接入；已支持 comgold/comoil/comsilver"}
    if mkt in {"119", "133"}:
        return {"symbol": "", "name": name, "market": "外汇", "supported": False,
                "note": "该外汇对暂未接入；已支持 fxusdcnh/fxusdjpy/fxeurusd/fxgbpusd"}
    return None


@app.get("/api/v1/search")
def search(q: str = Query(..., min_length=1, max_length=24)) -> dict[str, Any]:
    query = "".join(str(q or "").split())
    if not query:
        return {"query": q, "results": []}
    results: list[dict[str, Any]] = []
    # 本地目录匹配（含指数/商品/外汇等东财不直接映射的资产）
    lowered = query.lower()
    for symbol, name in SYMBOL_NAMES.items():
        if lowered in symbol or lowered in name.lower():
            market = "外汇" if symbol.startswith("fx") else "商品" if symbol.startswith("com") else "全球 · 指数" if symbol.startswith("us^") or symbol in {"usndx", "hkhsi"} else "股票/ETF"
            results.append({"symbol": symbol, "name": name, "market": market, "supported": True})
        if len(results) >= 4:
            break
    # 东财联想接口（自然语言/名称/代码模糊搜索）
    try:
        url = (f"https://searchapi.eastmoney.com/api/suggest/get?input={quote(query, safe='')}"
               f"&type=14&token={SEARCH_TOKEN}&count=10")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        items = ((payload.get("QuotationCodeTable") or {}).get("Data")) or []
        for item in items:
            mapped = _suggest_symbol(item.get("MktNum"), str(item.get("Code") or ""), str(item.get("Name") or ""))
            if mapped and mapped.get("symbol"):
                if all(r["symbol"] != mapped["symbol"] for r in results):
                    results.append(mapped)
            elif mapped:
                results.append(mapped)
            if len(results) >= 10:
                break
    except Exception:
        pass
    return {"query": q, "results": results[:10]}


@app.get("/api/v1/chan")
def chan(
    symbol: str = Query(..., min_length=3, max_length=26),
    years: int = Query(5, ge=1, le=20),
) -> dict[str, Any]:
    try:
        normalized, frame = _feature_frame(symbol, years, minimum=30)
        return {
            "source": "python",
            "symbol": normalized.upper(),
            "name": SYMBOL_NAMES.get(normalized, normalized.upper()),
            "updatedAt": pd.Timestamp(frame["Date"].iloc[-1]).strftime("%Y-%m-%d"),
            **_coverage_payload(years, frame),
            **analyze_chan(frame, years=years),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _service_error("缠论分析", exc) from exc


# ---------------- AI 大白话、页面问答与估值研究 ----------------

_INTERPRET_CACHE: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}
_INTERPRET_TTL = 1800
_KIND_LABELS = {
    "chart": "图表分析",
    "sma": "均线分析",
    "indicator": "指标分析",
    "chan": "缠论结构分析",
}


def _analysis_payload(
    kind: str,
    normalized: str,
    years: int,
    method: str,
    mode: str,
    indicator: str,
) -> dict[str, Any]:
    """复用确定性引擎结果；AI 只解释已有结构化数据，不参与计算。"""
    if kind == "sma":
        _, frame = _feature_frame(normalized, years, minimum=10)
        return analyze_moving_average(
            frame,
            years=years,
            min_trades=5,
            method=method,
            mode=mode,
        )
    if kind == "indicator":
        _, frame = _feature_frame(normalized, years, minimum=20)
        return analyze_indicator(frame, indicator=indicator, years=years)
    if kind == "chan":
        _, frame = _feature_frame(normalized, years, minimum=30)
        return analyze_chan(frame, years=years)

    daily = _long_ma(_cached_daily(normalized, years), normalized)
    if len(daily) < 30:
        raise ValueError("可用K线数量不足，无法解读")
    frames = _period_frames(daily)
    brief: dict[str, Any] = {}
    objective_summary = ""
    for key in ("M", "W", "D"):
        payload = _period_payload(
            key,
            frames[key],
            requested_years=years,
            symbol=normalized,
        )
        brief[key] = {
            "direction": payload["direction"],
            "stage": payload["stage"],
            "support": payload["support"],
            "resistance": payload["resistance"],
            "latest": payload["latest"],
            "patterns": [item["name"] for item in payload["patterns"][:6]],
        }
        if key == "D":
            objective_summary = str(payload.get("objectiveSummary") or "")
    brief["objectiveSummary"] = objective_summary
    return brief


@app.get("/api/v1/interpret")
def interpret_endpoint(
    request: Request,
    kind: str = Query("chart", pattern="^(chart|sma|indicator|chan)$"),
    symbol: str = Query(..., min_length=3, max_length=26),
    years: int = Query(5, ge=1, le=20),
    method: str = Query("single", pattern="^(single|cross|triple|midline)$"),
    mode: str = Query("basic", pattern="^(basic|adaptive)$"),
    indicator: str = Query("macd", min_length=2, max_length=20),
) -> dict[str, Any]:
    _check_rate(request)
    try:
        normalized = _normalize_symbol(symbol)
        cache_key = (kind, normalized, years, method, mode, indicator)
        now = time.time()
        with _FRAME_CACHE_LOCK:
            hit = _INTERPRET_CACHE.get(cache_key)
            if hit and now - hit[0] < _INTERPRET_TTL:
                return {**deepcopy(hit[1]), "cached": True}
        payload = _analysis_payload(
            kind,
            normalized,
            years,
            method,
            mode,
            indicator,
        )
        result = ai_interpret(
            _KIND_LABELS.get(kind, kind),
            SYMBOL_NAMES.get(normalized, normalized.upper()),
            normalized.upper(),
            payload,
        )
        response = {
            "source": "python",
            "kind": kind,
            "symbol": normalized.upper(),
            "name": SYMBOL_NAMES.get(normalized, normalized.upper()),
            **result,
        }
        with _FRAME_CACHE_LOCK:
            if len(_INTERPRET_CACHE) >= 128:
                oldest = min(
                    _INTERPRET_CACHE.items(),
                    key=lambda item: item[1][0],
                )[0]
                _INTERPRET_CACHE.pop(oldest, None)
            _INTERPRET_CACHE[cache_key] = (now, deepcopy(response))
        return {**response, "cached": False}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _service_error("AI解读", exc) from exc


@app.post("/api/v1/ask")
async def ask_endpoint(request: Request) -> dict[str, Any]:
    """基于当前页面资料回答；历史由前端携带，后端保持无状态。"""
    _check_rate(request)
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="请求格式不正确") from exc
    try:
        question = str(payload.get("question") or "").strip()[:200]
        context = str(payload.get("context") or "")[:3000]
        page = str(payload.get("page") or "")[:32]
        history = payload.get("history") or []
        if not isinstance(history, list):
            history = []
        history = history[-8:]
        if not question:
            raise ValueError("请先输入问题")
        result = ai_ask(
            page=page,
            context=context,
            question=question,
            history=history,
        )
        return {"source": "python", "page": page, **result}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _service_error("AI问答", exc) from exc


@app.get("/api/v1/valuation")
def valuation_endpoint(
    request: Request,
    symbol: str = Query(..., min_length=1, max_length=24),
    metrics: str = Query("pe", min_length=1, max_length=120),
    years: int = Query(10, ge=5, le=10),
) -> dict[str, Any]:
    _check_rate(request)
    try:
        return {"source": "python", **build_valuation(symbol, metrics, years)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise _service_error("估值研究", exc) from exc
