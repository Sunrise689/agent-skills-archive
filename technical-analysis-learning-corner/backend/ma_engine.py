from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _round(value: Any, digits: int = 2) -> float:
    return round(_finite(value), digits)


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"Date", "Open", "High", "Low", "Close"}
    if not required.issubset(frame.columns):
        raise ValueError("行情字段不完整")
    data = frame.copy()
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    for column in ["Open", "High", "Low", "Close"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.dropna(subset=["Date", "Close"]).sort_values("Date").reset_index(drop=True)


def _moving_average(values: np.ndarray, period: int) -> np.ndarray:
    output = np.full(len(values), np.nan, dtype=float)
    if period <= 0 or len(values) < period:
        return output
    cumulative = np.cumsum(np.insert(values, 0, 0.0))
    output[period - 1 :] = (cumulative[period:] - cumulative[:-period]) / period
    return output


def _max_drawdown(equity: np.ndarray) -> float:
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    drawdown = equity / np.maximum(peak, 1e-12) - 1.0
    return float(np.min(drawdown))


def _trade_returns(close: np.ndarray, signal: np.ndarray) -> list[float]:
    trades: list[float] = []
    entries = (np.where((signal[:-1] <= 0) & (signal[1:] > 0))[0] + 1).tolist()
    exits = (np.where((signal[:-1] > 0) & (signal[1:] <= 0))[0] + 1).tolist()
    exit_index = 0
    for entry_index in entries:
        while exit_index < len(exits) and exits[exit_index] <= entry_index:
            exit_index += 1
        exit_at = exits[exit_index] if exit_index < len(exits) else len(close) - 1
        if exit_at >= entry_index and close[entry_index] > 0:
            trades.append(close[exit_at] / close[entry_index] - 1.0)
        if exit_index < len(exits) and exits[exit_index] == exit_at:
            exit_index += 1
    return trades


def _metrics(close: np.ndarray, signal: np.ndarray, min_trades: int) -> dict[str, float | int]:
    valid = np.isfinite(close) & np.isfinite(signal)
    close = close[valid]
    signal = signal[valid]
    if len(close) < 5:
        return {"score": -1e9, "profitFactor": 0.0, "winRate": 0.0, "trades": 0, "returnPct": 0.0, "maxDrawdownPct": 0.0}
    returns = np.zeros(len(close), dtype=float)
    returns[1:] = close[1:] / np.maximum(close[:-1], 1e-12) - 1.0
    strategy = returns * np.roll(signal, 1)
    strategy[0] = 0.0
    gains = float(strategy[strategy > 0].sum())
    losses = abs(float(strategy[strategy < 0].sum()))
    profit_factor = gains / max(losses, 1e-9)
    equity = np.cumprod(1.0 + np.clip(strategy, -0.99, None))
    trades = _trade_returns(close, signal)
    wins = sum(1 for item in trades if item > 0)
    win_rate = wins / len(trades) if trades else 0.0
    return_pct = (equity[-1] - 1.0) * 100.0
    drawdown = _max_drawdown(equity) * 100.0
    trade_penalty = min(1.0, len(trades) / max(min_trades, 1))
    score = (min(profit_factor, 8.0) * 0.48 + win_rate * 2.0 + max(return_pct, -80.0) / 100.0 + drawdown / 180.0) * trade_penalty
    return {
        "score": float(score),
        "profitFactor": _round(profit_factor),
        "winRate": _round(win_rate * 100.0),
        "trades": len(trades),
        "returnPct": _round(return_pct),
        "maxDrawdownPct": _round(drawdown),
    }


def _selection_metrics(close: np.ndarray, signal: np.ndarray, min_trades: int, mode: str) -> dict[str, float | int]:
    full = _metrics(close, signal, min_trades)
    if mode != "adaptive" or len(close) < 180:
        return full
    recent_length = min(252, len(close))
    recent = _metrics(close[-recent_length:], signal[-recent_length:], min_trades)
    # Adaptive mode rewards candidates that remain usable in the recent
    # market regime while retaining a majority weight on the full history.
    full["score"] = float(full["score"]) * 0.55 + float(recent["score"]) * 0.45
    return full


def _single_search(close: np.ndarray, min_trades: int, mode: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    max_period = min(365, max(10, len(close) // 2))
    candidates: list[dict[str, Any]] = []
    for period in range(5, max_period + 1):
        average = _moving_average(close, period)
        signal = np.where(np.isfinite(average) & (close >= average), 1.0, 0.0)
        metrics = _selection_metrics(close, signal, min_trades, mode)
        minimum_trades = max(2, min_trades // 2) if len(close) >= 20 else 0
        if metrics["trades"] >= minimum_trades:
            candidates.append({"period": period, **metrics})
    if not candidates:
        raise ValueError("有效交易次数不足，无法筛选均线")
    candidates.sort(key=lambda item: (item["score"], item["profitFactor"], item["trades"]), reverse=True)
    return candidates[0], candidates[:18]


def _dual_search(close: np.ndarray, singles: list[dict[str, Any]], min_trades: int, mode: str) -> dict[str, Any]:
    max_period = min(365, max(20, len(close) // 2))
    anchors = sorted({int(item["period"]) for item in singles[:12]})
    fast_pool = {period for period in anchors if period < max_period}
    slow_pool = {period for period in anchors if period > 10}
    for anchor in anchors[:8]:
        for offset in range(-20, 21):
            value = anchor + offset
            if 3 <= value <= max_period:
                fast_pool.add(value)
                slow_pool.add(value)
    fast_pool.update(range(5, min(80, max_period) + 1, 5))
    slow_pool.update(range(20, max_period + 1, max(5, max_period // 80)))
    averages = {period: _moving_average(close, period) for period in fast_pool | slow_pool}
    best: dict[str, Any] | None = None
    for fast in sorted(fast_pool):
        for slow in sorted(slow_pool):
            if fast >= slow or slow < fast + 3:
                continue
            signal = np.where(np.isfinite(averages[slow]) & (averages[fast] >= averages[slow]), 1.0, 0.0)
            metrics = _selection_metrics(close, signal, min_trades, mode)
            candidate = {"fast": fast, "slow": slow, **metrics}
            if best is None or candidate["score"] > best["score"]:
                best = candidate
    if best is None:
        raise ValueError("双均线候选不足")
    return best


def _triple_search(
    close: np.ndarray,
    single: dict[str, Any],
    dual: dict[str, Any],
    singles: list[dict[str, Any]],
    min_trades: int,
    mode: str,
) -> dict[str, Any]:
    """Evaluate a bounded set of three-line candidates derived from the best searches."""
    max_period = min(240, max(30, len(close) // 2))
    anchors = {int(single["period"]), int(dual["fast"]), int(dual["slow"])}
    anchors.update(int(item["period"]) for item in singles[:10])
    pool = sorted({period for anchor in anchors for period in range(anchor - 12, anchor + 13) if 5 <= period <= max_period})
    pool = pool[:32]
    averages = {period: _moving_average(close, period) for period in pool}
    best: dict[str, Any] | None = None
    for fast_index, fast in enumerate(pool):
        for middle in pool[fast_index + 1:]:
            if middle < fast + 3:
                continue
            for slow in pool:
                if slow < middle + 3:
                    continue
                signal = np.where(
                    np.isfinite(averages[slow])
                    & np.isfinite(averages[middle])
                    & np.isfinite(averages[fast])
                    & (averages[fast] >= averages[middle])
                    & (averages[middle] >= averages[slow]),
                    1.0,
                    0.0,
                )
                metrics = _selection_metrics(close, signal, min_trades, mode)
                candidate = {"fast": fast, "middle": middle, "slow": slow, **metrics}
                if best is None or candidate["score"] > best["score"]:
                    best = candidate
    if best is None:
        raise ValueError("三均线候选不足")
    return best


def _center_moving_average(close: np.ndarray, dates=None, years: int = 3) -> tuple[int, np.ndarray, str]:
    """中间线：本质是一条真正的移动平均线，周期范围随回看年限自适应。

    - 回看 <= 5 年：直接在日线上搜索；
    - 回看 > 5 年：重采样为周线搜索；回看 >= 20 年：重采样为月线搜索；
      周线/月线结果再插值换算回日线展示，尺度越长按长周期粒度计算，
      保证中间线足够长，能充当整段历史的中枢；
    - 候选周期为回看长度的 1/8 ~ 1/2，在"价格最围绕其波动"
      （上方比例接近 50%、穿越次数多）的标准下选取。
    返回 (整数周期, 日线长度中间线序列, 粒度单位)。
    """
    n = len(close)
    use_monthly = years >= 20 and n > 2400 and dates is not None
    use_weekly = (not use_monthly) and years > 5 and n > 260 and dates is not None
    base_series = None
    if use_monthly:
        base_series = pd.Series(close, index=pd.DatetimeIndex(dates)).resample("ME").last().dropna()
        base = base_series.to_numpy(dtype=float)
        unit = "月"
    elif use_weekly:
        base_series = pd.Series(close, index=pd.DatetimeIndex(dates)).resample("W-FRI").last().dropna()
        base = base_series.to_numpy(dtype=float)
        unit = "周"
    else:
        base = close
        unit = "日"
    m = len(base)
    lo = max(20, m // 8)
    hi = max(lo, min(m - 10, m // 2))
    best = None
    for period in range(lo, hi + 1):
        ma = _moving_average(base, period)
        valid = np.isfinite(ma)
        if valid.sum() < max(30, m // 5):
            continue
        seg_close = base[valid]
        seg_ma = ma[valid]
        above = float((seg_close > seg_ma).mean())
        crossings = int(np.sum(np.diff(np.sign(seg_close - seg_ma)) != 0))
        score = (abs(above - 0.5), -crossings)
        if best is None or score < best[0]:
            best = (score, period, ma)
    if best is None:
        fallback = max(2, m // 4)
        best = ((0.0, 0), fallback, _moving_average(base, fallback))
    period = best[1]
    center_base = best[2]
    if base_series is not None:
        daily_dates = np.asarray(pd.DatetimeIndex(dates), dtype="datetime64[ns]")
        positions = np.searchsorted(daily_dates, base_series.index.to_numpy().astype("datetime64[ns]"), side="right") - 1
        positions = np.clip(positions, 0, n - 1)
        valid = np.isfinite(center_base)
        if int(valid.sum()) >= 2:
            center = np.interp(np.arange(n), positions[valid], center_base[valid])
        else:
            center = np.full(n, np.nan)
    else:
        center = center_base
    return period, center, unit


def _recovery_score(close: np.ndarray, average: np.ndarray, horizon: int = 504) -> tuple[float, float]:
    entries = np.where(np.isfinite(average) & (close <= average))[0]
    entries = entries[entries < len(close) - 10]
    if len(entries) == 0:
        return 0.0, float(horizon)
    recovered = 0
    days: list[int] = []
    for index in entries[-120:]:
        end = min(len(close), index + horizon + 1)
        future = np.where(close[index + 1 : end] >= close[index])[0]
        if len(future):
            recovered += 1
            days.append(int(future[0] + 1))
    ratio = recovered / min(len(entries), 120)
    return ratio, float(np.median(days)) if days else float(horizon)


def _safety_lines(close: np.ndarray) -> dict[str, Any]:
    max_period = min(600, len(close) - 20)
    if max_period < 200:
        return {"available": False, "reason": "至少需要约200个交易日以上的数据"}
    periods = sorted(set(range(200, max_period + 1, 5)) | {max_period})
    candidates: list[dict[str, Any]] = []
    for period in periods:
        average = _moving_average(close, period)
        valid = average[np.isfinite(average)]
        if len(valid) < 20:
            continue
        recovery, median_days = _recovery_score(close, average)
        line_returns = np.diff(valid) / np.maximum(valid[:-1], 1e-12)
        volatility = float(np.std(line_returns) * math.sqrt(252))
        slope = float(valid[-1] / max(valid[max(0, len(valid) - 60)], 1e-12) - 1.0)
        candidates.append({
            "period": period,
            "value": float(valid[-1]),
            "recovery": recovery,
            "medianDays": median_days,
            "volatility": volatility,
            "slope": slope,
            "series": average,
        })
    if not candidates:
        return {"available": False, "reason": "长期均线候选不足"}
    stable = [item for item in candidates if item["slope"] > -0.12 and item["recovery"] >= 0.58]
    if not stable:
        return {"available": False, "reason": "长期均线持续走弱或历史回到成本区的表现不足，暂不定义便宜线与无忧线"}
    cheap = max(stable, key=lambda item: (item["value"], item["recovery"] - item["volatility"]))
    worry = max(stable, key=lambda item: (item["recovery"] - item["volatility"] * 2.0, item["period"]))
    if worry["value"] > cheap["value"]:
        cheap, worry = worry, cheap
    return {
        "available": True,
        "cheap": cheap,
        "worryFree": worry,
    }


def _line_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "period": int(item["period"]),
        "value": _round(item["value"]),
        "recoveryRate": _round(item["recovery"] * 100.0),
        "medianRecoveryDays": int(round(item["medianDays"])),
    }


def _selected_periods(method: str, selected: dict[str, Any]) -> list[tuple[str, int]]:
    if method == "midline":
        return []
    if method == "cross":
        return [("快线", int(selected["fast"])), ("慢线", int(selected["slow"]))]
    if method == "triple":
        return [
            ("快线", int(selected["fast"])),
            ("中线", int(selected["middle"])),
            ("慢线", int(selected["slow"])),
        ]
    return [("单均线", int(selected["period"]))]


def _bias_distribution(bias: np.ndarray, current_bias: float) -> list[dict[str, Any]]:
    """Build a compact histogram for the deviation-rate inset chart."""
    clean = bias[np.isfinite(bias)]
    if len(clean) == 0:
        return []
    low = float(np.percentile(clean, 2))
    high = float(np.percentile(clean, 98))
    if high - low < 1e-6:
        low = float(clean.min())
        high = float(clean.max()) + 1e-6
    edges = np.linspace(low, high, 13)
    counts, _ = np.histogram(clean, bins=edges)
    active = int(np.clip(np.searchsorted(edges, current_bias, side="right") - 1, 0, len(counts) - 1))
    maximum = max(int(counts.max()), 1)
    result = []
    for index, count in enumerate(counts):
        midpoint = (edges[index] + edges[index + 1]) / 2
        result.append({
            "label": f"{_round(midpoint, 1)}%",
            "height": max(8, int(round(int(count) / maximum * 100))),
            "active": index == active,
        })
    return result


def _valley_payload(close: np.ndarray, data: pd.DataFrame, tail: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Mark the Chinese "silver valley / golden valley" triple-MA pattern.

    The common domestic teaching definition uses 5/10/30-day simple moving
    averages. This is exposed as a reference pattern, not as a guaranteed
    signal; international technical analysis treats the underlying idea as a
    triple moving-average bullish crossover.
    """
    if len(close) < 30:
        return [], []
    periods = (5, 10, 30)
    averages = {period: _moving_average(close, period) for period in periods}
    lines = []
    start = len(close) - tail
    colors = {5: "#ef5350", 10: "#f0a044", 30: "#2962ff"}
    for period in periods:
        lines.append({
            "label": f"MA {period}（山谷参考）",
            "period": period,
            "role": "valley",
            "color": colors[period],
            "values": [None if not np.isfinite(averages[period][index]) else _round(averages[period][index]) for index in range(start, len(close))],
        })
    bullish = (
        np.isfinite(averages[5]) & np.isfinite(averages[10]) & np.isfinite(averages[30])
        & (averages[5] >= averages[10]) & (averages[10] >= averages[30])
    )
    events: list[dict[str, Any]] = []
    first_index: int | None = None
    for index in range(1, len(close)):
        if not bullish[index] or bullish[index - 1]:
            continue
        if first_index is None:
            first_index = index
            label = "银山谷"
            kind = "silver"
        elif index - first_index >= 5 and close[index] >= close[first_index]:
            label = "金山谷"
            kind = "golden"
        else:
            continue
        if index < start:
            continue
        events.append({
            "index": index - start,
            "date": data["Date"].iloc[index].strftime("%Y-%m-%d"),
            "price": _round(close[index]),
            "label": label,
            "type": kind,
            "note": "5/10/30日均线先后形成向上多头排列的参考形态",
        })
    return events[-8:], lines


def analyze_moving_average(
    frame: pd.DataFrame,
    years: int = 5,
    min_trades: int = 5,
    method: str = "single",
    mode: str = "basic",
) -> dict[str, Any]:
    data = _clean(frame)
    if len(data) < 10:
        raise ValueError("可用行情不足，至少需要约10个交易日")
    close = data["Close"].to_numpy(dtype=float)
    selected_mode = mode if mode in {"basic", "adaptive"} else "basic"
    selected_method = method if method in {"single", "cross", "triple", "midline"} else "single"
    best_single: dict[str, Any] = {}
    best_dual: dict[str, Any] = {}
    best_triple: dict[str, Any] = {}
    singles: list[dict[str, Any]] = []
    if selected_method == "single":
        best_single, singles = _single_search(close, min_trades, selected_mode)
    elif selected_method == "cross":
        best_single, singles = _single_search(close, min_trades, selected_mode)
        best_dual = _dual_search(close, singles, min_trades, selected_mode)
    elif selected_method == "triple":
        best_single, singles = _single_search(close, min_trades, selected_mode)
        best_dual = _dual_search(close, singles, min_trades, selected_mode)
        best_triple = _triple_search(close, best_single, best_dual, singles, min_trades, selected_mode)
    selected = {
        "single": best_single,
        "cross": best_dual,
        "triple": best_triple,
        "midline": {},
    }[selected_method]
    center_period, center, center_unit = _center_moving_average(close, dates=data["Date"], years=years)
    if center_unit == "月":
        center_period_text = f"{center_period}月均线（约{_round(center_period / 12.0, 1)}年，相当于约{center_period * 21}日均线）"
    elif center_unit == "周":
        center_period_text = f"{center_period}周均线（约{_round(center_period / 52.0, 1)}年，相当于约{center_period * 5}日均线）"
    else:
        center_period_text = f"{center_period}日均线（约{_round(center_period / 21.0, 1)}个月）"
    bias = (close / np.maximum(center, 1e-12) - 1.0) * 100.0
    bias_valid = bias[np.isfinite(bias)]
    current_bias = float(bias[-1])
    percentile = float((bias_valid <= current_bias).mean() * 100.0) if len(bias_valid) else 50.0
    if percentile >= 85:
        zone = "偏热区"
        action = "价格明显高于中间线，向下回拉的力量正在增大；偏热区只代表历史位置偏高，不等于立即反转。"
    elif percentile <= 20:
        zone = "偏冷区"
        action = "价格明显低于中间线，向上回拉的力量正在增大；偏冷区仍需确认长期结构没有走坏。"
    else:
        zone = "常态区"
        action = "价格与长期中间线的偏离处于常见范围，重点观察趋势是否继续延续。"
    direction = "up" if current_bias > 0.05 else "down" if current_bias < -0.05 else "flat"
    direction_arrow = "↓" if direction == "up" else "↑" if direction == "down" else "→"
    direction_text = (
        f"价格高于中间线 {_round(abs(current_bias))}% ，回拉方向 ↓"
        if direction == "up"
        else f"价格低于中间线 {_round(abs(current_bias))}% ，回拉方向 ↑"
        if direction == "down"
        else "价格贴近中间线，回拉方向 →"
    )
    safety = _safety_lines(close) if selected_method != "midline" else {"available": False, "reason": "中间线模式不筛选长期安全边际线"}
    tail = min(240, len(data))
    valley_signals, valley_lines = _valley_payload(close, data, tail)
    chart = []
    selected_lines = []
    for role, period in _selected_periods(selected_method, selected):
        average = _moving_average(close, period)
        selected_lines.append({
            "label": f"MA {period}（{role}）",
            "period": period,
            "role": role,
            "values": [
                None if not np.isfinite(average[index]) else _round(average[index])
                for index in range(len(data) - tail, len(data))
            ],
        })
    cheap_series = safety.get("cheap", {}).get("series") if safety.get("available") else None
    worry_series = safety.get("worryFree", {}).get("series") if safety.get("available") else None
    for index in range(len(data) - tail, len(data)):
        chart.append({
            "date": data["Date"].iloc[index].strftime("%Y-%m-%d"),
            "close": _round(close[index]),
            "center": None if not np.isfinite(center[index]) else _round(center[index]),
            "biasPct": None if not np.isfinite(bias[index]) else _round(bias[index]),
            "cheap": None if cheap_series is None or not np.isfinite(cheap_series[index]) else _round(cheap_series[index]),
            "worryFree": None if worry_series is None or not np.isfinite(worry_series[index]) else _round(worry_series[index]),
        })
    safety_payload: dict[str, Any]
    if safety.get("available"):
        safety_payload = {
            "available": True,
            "cheap": _line_payload(safety["cheap"]),
            "worryFree": _line_payload(safety["worryFree"]),
            "note": "两条线是基于长期成本、历史修复能力和线体稳定度筛选的候选区间，不代表价格不会继续下跌。",
        }
    else:
        safety_payload = {"available": False, "reason": safety.get("reason", "当前不满足长期安全线条件")}
    coverage_years = len(data) / 252.0
    if len(data) < 252:
        coverage_note = f"上市历史不足1年，按实际 {len(data)} 个交易日计算。"
    elif coverage_years + 0.25 < years:
        coverage_note = f"可用历史约 {coverage_years:.1f} 年，短于请求的 {years} 年，已按实际历史计算。"
    else:
        coverage_note = f"按请求的 {years} 年回看。"
    midline_payload = {
        "valuePct": _round(current_bias),
        "percentile": _round(percentile),
        "zone": zone,
        "direction": direction,
        "arrow": direction_arrow,
        "force": _round(abs(current_bias)),
        "directionText": direction_text,
        "centerValue": _round(center[-1]),
        "distribution": _bias_distribution(bias, current_bias),
    }
    return {
        "years": years,
        "availableDays": len(data),
        "availableYears": _round(coverage_years, 1),
        "coverageNote": coverage_note,
        "minTrades": min_trades,
        "mode": mode if mode in {"basic", "adaptive"} else "basic",
        "selectedMethod": selected_method,
        "selectedPeriods": [period for _, period in _selected_periods(selected_method, selected)] or ([center_period_text] if selected_method == "midline" else []),
        "selected": {key: value for key, value in selected.items() if key != "score"},
        "single": {key: value for key, value in best_single.items() if key != "score"},
        "dual": {key: value for key, value in best_dual.items() if key != "score"},
        "triple": {key: value for key, value in best_triple.items() if key != "score"},
        "centerline": {"method": "中枢移动平均线", "period": center_period, "unit": center_unit, "periodText": center_period_text, "value": _round(center[-1])},
        "midline": midline_payload,
        "bias": {**midline_payload, "interpretation": action},
        "safety": safety_payload,
        "chart": chart,
        "chartLines": selected_lines,
        "valleyLines": valley_lines,
        "valleySignals": valley_signals,
        "modeNote": (
            ("中间线模式不搜索买卖参数，选取一条价格最围绕其波动的移动平均线作为中间线（回看5年以内按日线、5年以上按周线、20年以上按月线计算，并统一换算展示），并用乖离率历史分位判断偏冷、常态或偏热。"
             if selected_method == "midline" else "基础模式按全历史盈利因子、胜率和回撤筛选候选，适合做长期复盘。")
            if selected_mode == "basic"
            else ("中间线模式不受自适应参数影响，仍使用全历史搜索出的中枢均线。"
                  if selected_method == "midline" else "自适应模式在全历史结果基础上提高近252个交易日的权重，用于观察当前市场阶段是否仍然适配。")
        ),
        "methodNote": ("中间线只用于观察价格偏离与回归方向，不构成买卖信号。"
                       if selected_method == "midline" else "信号在下一交易日执行，并设置最低交易次数，减少未来函数和偶然高分。双均线采用单均线候选区间的两阶段搜索。"),
    }
