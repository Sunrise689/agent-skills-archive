from __future__ import annotations

import math
from typing import Any

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
    for column in ["Open", "High", "Low", "Close"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.dropna(subset=["Date", "High", "Low", "Close"]).sort_values("Date").reset_index(drop=True)


def _compress(data: pd.DataFrame) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    direction = 0
    for index, row in data.iterrows():
        current = {"source": int(index), "date": row["Date"], "high": float(row["High"]), "low": float(row["Low"]), "close": float(row["Close"])}
        if not bars:
            bars.append(current)
            continue
        previous = bars[-1]
        included = (current["high"] <= previous["high"] and current["low"] >= previous["low"]) or (current["high"] >= previous["high"] and current["low"] <= previous["low"])
        if not included:
            direction = 1 if current["high"] > previous["high"] else -1
            bars.append(current)
            continue
        if direction >= 0:
            previous["high"] = max(previous["high"], current["high"])
            previous["low"] = max(previous["low"], current["low"])
        else:
            previous["high"] = min(previous["high"], current["high"])
            previous["low"] = min(previous["low"], current["low"])
        previous["source"] = current["source"]
        previous["date"] = current["date"]
        previous["close"] = current["close"]
    return bars


def _fractals(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for index in range(1, len(bars) - 1):
        left, current, right = bars[index - 1], bars[index], bars[index + 1]
        if current["high"] > left["high"] and current["high"] >= right["high"] and current["low"] > left["low"] and current["low"] >= right["low"]:
            result.append({"kind": "top", "index": current["source"], "date": current["date"], "price": current["high"]})
        elif current["low"] < left["low"] and current["low"] <= right["low"] and current["high"] < left["high"] and current["high"] <= right["high"]:
            result.append({"kind": "bottom", "index": current["source"], "date": current["date"], "price": current["low"]})
    return result


def _strokes(fractals: list[dict[str, Any]], atr: float) -> list[dict[str, Any]]:
    pivots: list[dict[str, Any]] = []
    for item in fractals:
        if not pivots:
            pivots.append(item)
            continue
        previous = pivots[-1]
        if item["kind"] == previous["kind"]:
            more_extreme = item["price"] > previous["price"] if item["kind"] == "top" else item["price"] < previous["price"]
            if more_extreme:
                pivots[-1] = item
            continue
        if item["index"] - previous["index"] < 4:
            continue
        if abs(item["price"] - previous["price"]) < atr * 0.7:
            continue
        pivots.append(item)
    return pivots


def _centers(pivots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    centers: list[dict[str, Any]] = []
    for index in range(len(pivots) - 3):
        segments = []
        for offset in range(3):
            first, second = pivots[index + offset], pivots[index + offset + 1]
            segments.append((min(first["price"], second["price"]), max(first["price"], second["price"])))
        low = max(item[0] for item in segments)
        high = min(item[1] for item in segments)
        if low < high:
            candidate = {"startIndex": pivots[index]["index"], "endIndex": pivots[index + 3]["index"], "low": low, "high": high}
            if centers and candidate["startIndex"] <= centers[-1]["endIndex"] and max(candidate["low"], centers[-1]["low"]) < min(candidate["high"], centers[-1]["high"]):
                centers[-1]["endIndex"] = candidate["endIndex"]
                centers[-1]["low"] = max(centers[-1]["low"], candidate["low"])
                centers[-1]["high"] = min(centers[-1]["high"], candidate["high"])
            else:
                centers.append(candidate)
    return centers


def _signals(pivots: list[dict[str, Any]], centers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for center in centers:
        after = [item for item in pivots if item["index"] > center["endIndex"]]
        if len(after) < 2:
            continue
        for index in range(1, len(after)):
            previous, current = after[index - 1], after[index]
            if previous["kind"] == "top" and previous["price"] > center["high"] and current["kind"] == "bottom" and current["price"] > center["high"]:
                signals.append({"index": current["index"], "date": current["date"], "price": current["price"], "type": "buy", "label": "三买候选", "reason": "离开中枢后回踩未进入中枢上沿"})
                break
            if previous["kind"] == "bottom" and previous["price"] < center["low"] and current["kind"] == "top" and current["price"] < center["low"]:
                signals.append({"index": current["index"], "date": current["date"], "price": current["price"], "type": "sell", "label": "三卖候选", "reason": "离开中枢后反抽未进入中枢下沿"})
                break
    for index in range(3, len(pivots)):
        older, previous, current = pivots[index - 2], pivots[index - 1], pivots[index]
        if current["kind"] == "bottom" and older["kind"] == "bottom" and current["price"] > older["price"] and previous["kind"] == "top":
            signals.append({"index": current["index"], "date": current["date"], "price": current["price"], "type": "buy", "label": "二买候选", "reason": "回撤低点高于前低，等待突破前一笔高点"})
        elif current["kind"] == "top" and older["kind"] == "top" and current["price"] < older["price"] and previous["kind"] == "bottom":
            signals.append({"index": current["index"], "date": current["date"], "price": current["price"], "type": "sell", "label": "二卖候选", "reason": "反弹高点低于前高，等待跌破前一笔低点"})
    unique: dict[tuple[int, str], dict[str, Any]] = {}
    priority = {"三买候选": 3, "三卖候选": 3, "二买候选": 2, "二卖候选": 2}
    for item in signals:
        key = (item["index"], item["type"])
        if key not in unique or priority[item["label"]] > priority[unique[key]["label"]]:
            unique[key] = item
    return sorted(unique.values(), key=lambda item: item["index"])[-10:]


def analyze_chan(frame: pd.DataFrame, years: int = 5) -> dict[str, Any]:
    data = _clean(frame)
    if len(data) < 30:
        raise ValueError("缠论结构至少需要约30根K线")
    previous = data["Close"].shift(1)
    true_range = pd.concat([(data["High"] - data["Low"]), (data["High"] - previous).abs(), (data["Low"] - previous).abs()], axis=1).max(axis=1)
    atr = float(true_range.tail(60).median())
    compressed = _compress(data)
    fractals = _fractals(compressed)
    pivots = _strokes(fractals, atr)
    centers = _centers(pivots)
    signals = _signals(pivots, centers)
    direction = "上行笔占优" if len(pivots) >= 2 and pivots[-1]["price"] > pivots[-2]["price"] else "下行笔占优"
    return {
        "years": years,
        "summary": f"包含关系处理后得到{len(fractals)}个分型、{max(0, len(pivots)-1)}笔和{len(centers)}个中枢；当前{direction}。",
        "counts": {"compressedBars": len(compressed), "fractals": len(fractals), "strokes": max(0, len(pivots) - 1), "centers": len(centers), "signals": len(signals)},
        "pivots": [{"index": item["index"], "date": item["date"].strftime("%Y-%m-%d"), "price": _round(item["price"]), "kind": item["kind"]} for item in pivots[-36:]],
        "centers": [{"startIndex": item["startIndex"], "endIndex": item["endIndex"], "low": _round(item["low"]), "high": _round(item["high"])} for item in centers[-8:]],
        "signals": [{**item, "date": item["date"].strftime("%Y-%m-%d"), "price": _round(item["price"])} for item in signals],
        "methodNote": "Beta版按包含关系、分型、笔和三笔重叠中枢逐层构建；买卖点均标为候选，必须等待后续走势确认。暂不把简化背驰当作原著级确定结论。",
        "sourceNote": "理论来源为网络作者“缠中说禅”公开发布的《教你炒股票》系列。公开资料常将其与李彪联系，但真实身份存在争议。",
    }
