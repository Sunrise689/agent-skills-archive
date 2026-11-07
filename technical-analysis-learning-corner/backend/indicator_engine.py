from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Any, Callable

import numpy as np
import pandas as pd


def _round(value: Any, digits: int = 2) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(number if math.isfinite(number) else 0.0, digits)


def _clean(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["Date"] = pd.to_datetime(data["Date"], errors="coerce")
    for column in ["Open", "High", "Low", "Close", "Volume"]:
        if column not in data:
            data[column] = 0.0
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.dropna(subset=["Date", "High", "Low", "Close"]).sort_values("Date").reset_index(drop=True)


def _metrics(close: np.ndarray, signal: np.ndarray, min_trades: int = 5) -> dict[str, Any]:
    valid = np.isfinite(close) & np.isfinite(signal)
    close = close[valid]
    signal = signal[valid]
    if len(close) < 30:
        return {"score": -1e9, "profitFactor": 0.0, "winRate": 0.0, "trades": 0, "returnPct": 0.0, "maxDrawdownPct": 0.0}
    returns = np.zeros(len(close))
    returns[1:] = close[1:] / np.maximum(close[:-1], 1e-12) - 1.0
    strategy = returns * np.roll(signal, 1)
    strategy[0] = 0.0
    gains = float(strategy[strategy > 0].sum())
    losses = abs(float(strategy[strategy < 0].sum()))
    profit_factor = gains / max(losses, 1e-9)
    equity = np.cumprod(1 + np.clip(strategy, -0.99, None))
    peaks = np.maximum.accumulate(equity)
    drawdown = float(np.min(equity / np.maximum(peaks, 1e-12) - 1.0) * 100)
    entries = np.where((signal[1:] > 0) & (signal[:-1] <= 0))[0] + 1
    exits = np.where((signal[1:] <= 0) & (signal[:-1] > 0))[0] + 1
    trade_returns: list[float] = []
    for entry in entries:
        following = exits[exits > entry]
        exit_index = int(following[0]) if len(following) else len(close) - 1
        trade_returns.append(close[exit_index] / max(close[entry], 1e-12) - 1)
    trades = len(trade_returns)
    win_rate = sum(item > 0 for item in trade_returns) / trades if trades else 0.0
    total_return = float((equity[-1] - 1.0) * 100)
    penalty = min(1.0, trades / max(min_trades, 1))
    score = (min(profit_factor, 8.0) * 0.5 + win_rate * 2.0 + max(total_return, -80) / 100 + drawdown / 180) * penalty
    return {
        "score": score,
        "profitFactor": _round(profit_factor),
        "winRate": _round(win_rate * 100),
        "trades": trades,
        "returnPct": _round(total_return),
        "maxDrawdownPct": _round(drawdown),
    }


def _best(search: Iterable[tuple[dict[str, Any], np.ndarray]], close: np.ndarray) -> tuple[dict[str, Any], np.ndarray]:
    best_params: dict[str, Any] | None = None
    best_signal: np.ndarray | None = None
    best_metrics: dict[str, Any] | None = None
    for params, signal in search:
        metrics = _metrics(close, signal)
        if best_metrics is None or metrics["score"] > best_metrics["score"]:
            best_params, best_signal, best_metrics = params, signal.copy(), metrics
    if best_params is None or best_signal is None or best_metrics is None:
        raise ValueError("没有可用的指标候选参数")
    public_metrics = {key: value for key, value in best_metrics.items() if key != "score"}
    return {**best_params, **public_metrics}, best_signal


def _macd(data: pd.DataFrame) -> tuple[dict[str, Any], np.ndarray, dict[str, Any]]:
    close_series = data["Close"]
    close = close_series.to_numpy(float)
    ema_cache = {period: close_series.ewm(span=period, adjust=False).mean().to_numpy(float) for period in range(5, 101)}

    def candidates() -> Iterable[tuple[dict[str, Any], np.ndarray]]:
        for fast in range(5, 41):
            for slow in range(fast + 5, 101):
                dif = ema_cache[fast] - ema_cache[slow]
                for signal_period in range(3, 19):
                    dea = pd.Series(dif).ewm(span=signal_period, adjust=False).mean().to_numpy(float)
                    yield {"fast": fast, "slow": slow, "signal": signal_period}, np.where(dif >= dea, 1.0, 0.0)

    best, signal = _best(candidates(), close)
    fast, slow, signal_period = best["fast"], best["slow"], best["signal"]
    dif = ema_cache[fast] - ema_cache[slow]
    dea = pd.Series(dif).ewm(span=signal_period, adjust=False).mean().to_numpy(float)
    state = "DIF在信号线上方，当前动量偏强。" if dif[-1] >= dea[-1] else "DIF在信号线下方，当前动量偏弱。"
    return best, signal, {"state": state, "value": _round(dif[-1]), "signalValue": _round(dea[-1])}


def _kdj(data: pd.DataFrame) -> tuple[dict[str, Any], np.ndarray, dict[str, Any]]:
    close = data["Close"].to_numpy(float)
    rsv_cache: dict[int, np.ndarray] = {}

    def candidates() -> Iterable[tuple[dict[str, Any], np.ndarray]]:
        for period in range(5, 46):
            low = data["Low"].rolling(period).min()
            high = data["High"].rolling(period).max()
            rsv = ((data["Close"] - low) / (high - low).replace(0, np.nan) * 100).fillna(50).to_numpy(float)
            rsv_cache[period] = rsv
            for k_smooth in range(2, 7):
                k = pd.Series(rsv).ewm(alpha=1 / k_smooth, adjust=False).mean().to_numpy(float)
                for d_smooth in range(2, 7):
                    d = pd.Series(k).ewm(alpha=1 / d_smooth, adjust=False).mean().to_numpy(float)
                    yield {"period": period, "kSmooth": k_smooth, "dSmooth": d_smooth}, np.where(k >= d, 1.0, 0.0)

    best, signal = _best(candidates(), close)
    rsv = rsv_cache[best["period"]]
    k = pd.Series(rsv).ewm(alpha=1 / best["kSmooth"], adjust=False).mean().to_numpy(float)
    d = pd.Series(k).ewm(alpha=1 / best["dSmooth"], adjust=False).mean().to_numpy(float)
    j = 3 * k - 2 * d
    zone = "高位敏感区" if j[-1] >= 80 else "低位敏感区" if j[-1] <= 20 else "中性区"
    return best, signal, {"state": f"J值位于{zone}，只作为风险提示，不等同于立即买卖。", "k": _round(k[-1]), "d": _round(d[-1]), "j": _round(j[-1])}


def _rsi_values(close: pd.Series, period: int) -> np.ndarray:
    change = close.diff()
    gain = change.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-change.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    relative_strength = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + relative_strength)).fillna(50).to_numpy(float)


def _rsi(data: pd.DataFrame) -> tuple[dict[str, Any], np.ndarray, dict[str, Any]]:
    close = data["Close"].to_numpy(float)
    values: dict[int, np.ndarray] = {period: _rsi_values(data["Close"], period) for period in range(5, 61)}
    search = (({"period": period}, np.where(value >= 50, 1.0, 0.0)) for period, value in values.items())
    best, signal = _best(search, close)
    value = values[best["period"]][-1]
    zone = "偏热区" if value >= 70 else "偏冷区" if value <= 30 else "强势区" if value >= 50 else "弱势区"
    return best, signal, {"state": f"RSI处于{zone}。上穿30是反弹候选，从70回落是风险候选，不能单独作为交易指令。", "value": _round(value)}


def _supertrend_values(data: pd.DataFrame, period: int, multiplier: float) -> tuple[np.ndarray, np.ndarray]:
    high = data["High"].to_numpy(float)
    low = data["Low"].to_numpy(float)
    close = data["Close"].to_numpy(float)
    previous = np.roll(close, 1)
    previous[0] = close[0]
    true_range = np.maximum(high - low, np.maximum(abs(high - previous), abs(low - previous)))
    atr = pd.Series(true_range).ewm(alpha=1 / period, adjust=False).mean().to_numpy(float)
    middle = (high + low) / 2
    upper = middle + multiplier * atr
    lower = middle - multiplier * atr
    final_upper = upper.copy()
    final_lower = lower.copy()
    trend = np.ones(len(close), dtype=float)
    line = np.full(len(close), np.nan)
    for index in range(1, len(close)):
        final_upper[index] = upper[index] if upper[index] < final_upper[index - 1] or close[index - 1] > final_upper[index - 1] else final_upper[index - 1]
        final_lower[index] = lower[index] if lower[index] > final_lower[index - 1] or close[index - 1] < final_lower[index - 1] else final_lower[index - 1]
        if close[index] > final_upper[index - 1]:
            trend[index] = 1
        elif close[index] < final_lower[index - 1]:
            trend[index] = 0
        else:
            trend[index] = trend[index - 1]
        line[index] = final_lower[index] if trend[index] > 0 else final_upper[index]
    return trend, line


def _supertrend(data: pd.DataFrame) -> tuple[dict[str, Any], np.ndarray, dict[str, Any]]:
    close = data["Close"].to_numpy(float)

    def candidates() -> Iterable[tuple[dict[str, Any], np.ndarray]]:
        for period in range(5, 31):
            for quarter in range(4, 21):
                multiplier = quarter / 4
                trend, _ = _supertrend_values(data, period, multiplier)
                yield {"atrPeriod": period, "multiplier": multiplier}, trend

    best, signal = _best(candidates(), close)
    _, line = _supertrend_values(data, best["atrPeriod"], best["multiplier"])
    state = "价格位于自适应趋势线上方，结构偏强。" if signal[-1] > 0 else "价格位于自适应趋势线下方，结构偏弱。"
    return best, signal, {"state": state, "lineValue": _round(line[-1])}


def _information_discreteness(data: pd.DataFrame, window: int = 60) -> dict[str, Any]:
    returns = data["Close"].pct_change().dropna().tail(window)
    if len(returns) < 20:
        return {"available": False, "reason": "有效日收益数量不足"}
    positive_share = float((returns > 0).mean())
    negative_share = float((returns < 0).mean())
    period_return = float((1 + returns).prod() - 1)
    direction = 1.0 if period_return >= 0 else -1.0
    value = direction * (negative_share - positive_share)
    largest_share = float(returns.abs().nlargest(min(5, len(returns))).sum() / max(returns.abs().sum(), 1e-12))
    if largest_share >= 0.55:
        character = "少数交易日集中"
        interpretation = "本观察期的涨跌幅有较大比例集中在少数交易日完成，历史价格变化较集中；阅读单日涨跌时，需要同时查看完整区间。"
    elif abs(value) >= 0.28:
        character = "多日连续累积"
        interpretation = "本观察期的价格变化更多由较多同方向交易日逐步累积，历史涨跌路径相对连续。"
    else:
        character = "涨跌交错分散"
        interpretation = "本观察期的上涨日和下跌日较为交错，价格变化分散在较多交易日，并非主要由少数交易日完成。"
    return {
        "available": True,
        "window": int(len(returns)),
        "value": _round(value, 3),
        "character": character,
        "interpretation": interpretation,
        "largestFiveDaySharePct": _round(largest_share * 100),
        "sourceNote": "信息离散度（Information Discreteness）用于描述历史涨跌在时间上的集中或分散程度；本项不评价资产优劣，不提供未来预测。",
    }


def _public_values(values: np.ndarray, start: int) -> list[float | None]:
    output: list[float | None] = []
    for value in values[start:]:
        output.append(_round(value, 4) if math.isfinite(float(value)) else None)
    return output


def _smooth_close(close: pd.Series, window: int) -> np.ndarray:
    """Low-pass the close series for long-horizon visual reading."""
    return close.rolling(window=max(3, int(window)), min_periods=1).mean().to_numpy(float)


def _ohlc_rows(data: pd.DataFrame, start: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(start, len(data)):
        row = data.iloc[index]
        rows.append({
            "date": row["Date"].strftime("%Y-%m-%d"),
            "open": _round(row["Open"], 4),
            "high": _round(row["High"], 4),
            "low": _round(row["Low"], 4),
            "close": _round(row["Close"], 4),
        })
    return rows


def _id_history(data: pd.DataFrame, window: int = 60) -> tuple[np.ndarray, np.ndarray]:
    close = data["Close"].to_numpy(float)
    returns = pd.Series(close).pct_change().to_numpy(float)
    id_values = np.full(len(close), np.nan)
    concentration = np.full(len(close), np.nan)
    for index in range(window, len(close)):
        sample = returns[index - window + 1:index + 1]
        sample = sample[np.isfinite(sample)]
        if len(sample) < 20:
            continue
        positive_share = float((sample > 0).mean())
        negative_share = float((sample < 0).mean())
        period_return = float(np.prod(1 + sample) - 1)
        direction = 1.0 if period_return >= 0 else -1.0
        id_values[index] = direction * (negative_share - positive_share)
        count = min(5, len(sample))
        concentration[index] = np.sort(np.abs(sample))[-count:].sum() / max(np.abs(sample).sum(), 1e-12) * 100
    return id_values, concentration


def _indicator_chart(data: pd.DataFrame, key: str, best: dict[str, Any] | None = None) -> dict[str, Any]:
    limit = 220
    start = max(0, len(data) - limit)
    close_series = data["Close"]
    close = close_series.to_numpy(float)
    display_mode = "trend" if len(data) >= 500 else "candles"
    smooth_window = max(5, min(24, round(len(data) / 80)))
    smooth_close = _smooth_close(close_series, smooth_window)
    chart: dict[str, Any] = {
        "dates": [value.strftime("%Y-%m-%d") for value in data["Date"].iloc[start:]],
        "candles": _ohlc_rows(data, start),
        "mainSeries": [],
        "subSeries": [],
        "levels": [],
        "signals": [],
        "displayMode": display_mode,
        "smoothWindow": smooth_window,
    }
    if display_mode == "trend":
        chart["mainSeries"].append({
            "label": "平滑趋势",
            "color": "#2962ff",
            "values": _public_values(smooth_close, start),
        })
    signal: np.ndarray | None = None
    if key == "macd" and best:
        fast = close_series.ewm(span=int(best["fast"]), adjust=False).mean().to_numpy(float)
        slow = close_series.ewm(span=int(best["slow"]), adjust=False).mean().to_numpy(float)
        dif = fast - slow
        dea = pd.Series(dif).ewm(span=int(best["signal"]), adjust=False).mean().to_numpy(float)
        signal = np.where(dif >= dea, 1.0, 0.0)
        chart["subSeries"] = [
            {"label": "DIF", "color": "#2962ff", "values": _public_values(dif, start)},
            {"label": "DEA", "color": "#f0a044", "values": _public_values(dea, start)},
        ]
        chart["levels"] = [{"value": 0, "label": "零轴", "color": "#a8adb7"}]
    elif key == "kdj" and best:
        period = int(best["period"])
        low = data["Low"].rolling(period).min()
        high = data["High"].rolling(period).max()
        rsv = ((data["Close"] - low) / (high - low).replace(0, np.nan) * 100).fillna(50).to_numpy(float)
        k = pd.Series(rsv).ewm(alpha=1 / int(best["kSmooth"]), adjust=False).mean().to_numpy(float)
        d = pd.Series(k).ewm(alpha=1 / int(best["dSmooth"]), adjust=False).mean().to_numpy(float)
        j = 3 * k - 2 * d
        signal = np.where(k >= d, 1.0, 0.0)
        chart["subSeries"] = [
            {"label": "K", "color": "#2962ff", "values": _public_values(k, start)},
            {"label": "D", "color": "#f0a044", "values": _public_values(d, start)},
            {"label": "J", "color": "#8b5cf6", "values": _public_values(j, start)},
        ]
        chart["levels"] = [
            {"value": 20, "label": "低位参考", "color": "#26a69a"},
            {"value": 80, "label": "高位参考", "color": "#ef5350"},
        ]
    elif key == "rsi" and best:
        rsi = _rsi_values(close_series, int(best["period"]))
        signal = np.where(rsi >= 50, 1.0, 0.0)
        chart["subSeries"] = [{"label": "RSI", "color": "#8b5cf6", "values": _public_values(rsi, start)}]
        chart["levels"] = [
            {"value": 30, "label": "低位参考", "color": "#26a69a"},
            {"value": 50, "label": "强弱分界", "color": "#a8adb7"},
            {"value": 70, "label": "高位参考", "color": "#ef5350"},
        ]
    elif key == "supertrend" and best:
        signal, line = _supertrend_values(data, int(best["atrPeriod"]), float(best["multiplier"]))
        chart["mainSeries"] = [{"label": "SuperTrend", "color": "#2962ff", "values": _public_values(line, start)}]
    elif key == "id":
        id_values, concentration = _id_history(data)
        chart["subSeries"] = [
            {"label": "信息离散度", "color": "#2962ff", "values": _public_values(id_values, start)},
            {"label": "少数交易日贡献(%)", "color": "#f0a044", "values": _public_values(concentration, start)},
        ]
        chart["levels"] = [{"value": 0, "label": "分散度中线", "color": "#a8adb7", "series": 0}]
    if signal is not None:
        transitions = np.where(signal[1:] != signal[:-1])[0] + 1
        max_visible = 5 if display_mode == "trend" else 8
        visible = [int(index) for index in transitions if index >= start][-max_visible:]
        for index in visible:
            stronger = signal[index] > signal[index - 1]
            chart["signals"].append({
                "index": index - start,
                "date": data["Date"].iloc[index].strftime("%Y-%m-%d"),
                "price": _round(close[index], 4),
                "type": "referenceUp" if stronger else "referenceDown",
                "label": "转强参考" if stronger else "转弱参考",
            })
    return chart


INDICATORS: dict[str, Callable[[pd.DataFrame], tuple[dict[str, Any], np.ndarray, dict[str, Any]]]] = {
    "macd": _macd,
    "kdj": _kdj,
    "rsi": _rsi,
    "supertrend": _supertrend,
}


def analyze_indicator(frame: pd.DataFrame, indicator: str = "macd", years: int = 3) -> dict[str, Any]:
    data = _clean(frame)
    key = str(indicator or "macd").lower()
    if key == "id":
        if len(data) < 20:
            raise ValueError("信息离散度至少需要约20个交易日")
        return {
            "indicator": "id",
            "years": years,
            "special": _information_discreteness(data),
            "chart": _indicator_chart(data, "id"),
            "methodNote": "信息离散度只回顾历史价格变化在时间上的集中或分散程度，不评价资产优劣，也不提供未来预测。",
        }
    if key not in INDICATORS:
        raise ValueError("暂支持 MACD、KDJ、RSI、SuperTrend 和信息离散度")
    if len(data) < 30:
        raise ValueError("可用行情不足，至少需要约30个交易日")
    best, signal, status = INDICATORS[key](data)
    recent = []
    for index in range(max(1, len(signal) - 80), len(signal)):
        if signal[index] != signal[index - 1]:
            recent.append({
                "date": data["Date"].iloc[index].strftime("%Y-%m-%d"),
                "type": "buy" if signal[index] > 0 else "risk",
                "price": _round(data["Close"].iloc[index]),
                "label": "转强" if signal[index] > 0 else "转弱",
            })
    return {
        "indicator": key,
        "years": years,
        "best": best,
        "status": status,
        "signals": recent[-8:],
        "chart": _indicator_chart(data, key, best),
        "special": _information_discreteness(data),
        "methodNote": "参数按1个单位逐项搜索，信号在下一交易日执行；高分代表历史适配度，不代表未来收益。",
    }
