"""统一行情数据源路由：腾讯(A股/港股) + 新浪(美股/全球指数/大宗商品) + 东财(备用) + Yahoo(兜底)。

统一输出列：Date, Open, Close, High, Low, Volume（与 kline_pattern_report 一致）。
所有外部请求均设置超时，单源失败自动切换下一数据源。
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timedelta

import pandas as pd

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0 Safari/537.36"}
EM_HOSTS = [
    "https://push2his.eastmoney.com",
    "https://92.push2his.eastmoney.com",
    "https://7.push2his.eastmoney.com",
    "https://43.push2his.eastmoney.com",
]
SINA_HEADERS = {"User-Agent": UA["User-Agent"], "Referer": "https://finance.sina.com.cn"}

_US_INDEX_TO_SINA = {"^gspc": "INX", "^ixic": "IXIC", "^dji": "DJI"}
_US_INDEX_TO_EM = {"^gspc": "100.SPX", "^ixic": "100.IXIC", "^dji": "100.DJIA", "^ndx": "100.NDX"}
_COM_TO_SINA = {"comgold": "GC", "comoil": "CL", "comsilver": "SI"}
_COM_TO_EM = {"comgold": "101.GC00Y", "comoil": "102.CL00Y", "comsilver": "112.B00Y"}
_FX_TO_EM = {"usdcnh": "133.USDCNH", "usdjpy": "119.USDJPY", "eurusd": "119.EURUSD", "gbpusd": "119.GBPUSD"}


def _http_get(url, headers=None, timeout=8):
    req = urllib.request.Request(url, headers=headers or UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _clean_frame(rows, start_dt):
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[df["date"] >= start_dt]
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.drop_duplicates(subset="date", keep="last").sort_values("date").reset_index(drop=True)
    df = df[["date", "open", "close", "high", "low", "volume"]]
    df.columns = ["Date", "Open", "Close", "High", "Low", "Volume"]
    return df


def _start_date(years):
    return datetime.now() - timedelta(days=int(365.25 * max(1, years)) + 30)


def fetch_eastmoney_daily(secid, years=3):
    """东方财富历史日K，多域名轮询重试；一次请求取全区间。"""
    start_dt = _start_date(years)
    beg = start_dt.strftime("%Y%m%d")
    url_tpl = (
        "{host}/api/qt/stock/kline/get?secid={secid}"
        "&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56"
        "&klt=101&fqt=1&beg=" + beg + "&end=20500101"
    )
    last_err = None
    for host in EM_HOSTS:
        try:
            data = json.loads(_http_get(url_tpl.format(host=host, secid=secid), timeout=6))
            block = data.get("data")
            if not isinstance(block, dict):
                continue
            klines = block.get("klines") or []
            rows = []
            for line in klines:
                parts = line.split(",")
                if len(parts) >= 6:
                    rows.append({
                        "date": parts[0], "open": parts[1], "close": parts[2],
                        "high": parts[3], "low": parts[4], "volume": parts[5],
                    })
            if rows:
                return _clean_frame(rows, start_dt)
        except Exception as exc:
            last_err = exc
    raise ValueError(f"东方财富接口未返回数据: {secid}" + (f" ({last_err})" if last_err else ""))


def fetch_sina_us_daily(ticker, years=3):
    """新浪美股日K：单次请求返回全部历史，再按年限裁剪。"""
    url = f"https://stock.finance.sina.com.cn/usstock/api/json_v2.php/US_MinKService.getDailyK?symbol={ticker.lower()}"
    data = json.loads(_http_get(url, headers=SINA_HEADERS, timeout=10))
    if not isinstance(data, list) or not data:
        raise ValueError("新浪美股接口未返回数据")
    start_dt = _start_date(years)
    rows = [{
        "date": item.get("d"), "open": item.get("o"), "close": item.get("c"),
        "high": item.get("h"), "low": item.get("l"), "volume": item.get("v") or 0,
    } for item in data if item.get("d")]
    return _clean_frame(rows, start_dt)


def _parse_sina_jsonp(body):
    match = re.search(r"=\((.*)\)\s*;?\s*$", body, re.S)
    if not match:
        return None
    return json.loads(match.group(1))


def fetch_sina_global_daily(sina_symbol, years=3):
    """新浪全球指数/外盘期货日K（HSI/GC/CL/SI/INX 等）。"""
    url = (
        "https://stock2.finance.sina.com.cn/futures/api/jsonp.php/var%20_=/"
        f"GlobalFuturesService.getGlobalFuturesDailyKLine?symbol={sina_symbol}&_=1&type=5"
    )
    data = _parse_sina_jsonp(_http_get(url, headers=SINA_HEADERS, timeout=8))
    if not isinstance(data, list) or not data:
        raise ValueError(f"新浪全球行情接口未返回数据: {sina_symbol}")
    start_dt = _start_date(years)
    rows = [{
        "date": item.get("date"), "open": item.get("open"), "close": item.get("close"),
        "high": item.get("high"), "low": item.get("low"), "volume": item.get("volume") or 0,
    } for item in data if item.get("date")]
    return _clean_frame(rows, start_dt)


def fetch_daily(symbol, years=3):
    """按市场路由到合适的数据源，失败自动降级。输出列与腾讯源一致。"""
    from kline_pattern_report import fetch_tencent_daily, fetch_yahoo_daily

    s = str(symbol or "").strip().lower()
    errors = []

    def try_source(fn, *args):
        try:
            frame = fn(*args)
            if frame is not None and len(frame) > 0:
                return frame
        except Exception as exc:
            errors.append(str(exc))
        return None

    if s == "hkhsi":
        frame = try_source(fetch_sina_global_daily, "HSI", years)
        if frame is not None:
            return frame
        frame = try_source(fetch_eastmoney_daily, "100.HSI", years)
        if frame is not None:
            return frame
        frame = try_source(fetch_yahoo_daily, "us^HSI", years)
        if frame is not None:
            return frame
        raise ValueError("；".join(errors) or "恒生指数行情暂时无法获取")

    if re.fullmatch(r"(sh|sz|bj)\d{6}", s) or re.fullmatch(r"hk\d{5}", s):
        frame = try_source(fetch_tencent_daily, s, years)
        if frame is not None:
            return frame
        secid = (("1." if s.startswith("sh") else "116." if s.startswith("hk") else "0.")
                 + re.sub(r"^(sh|sz|bj|hk)", "", s))
        frame = try_source(fetch_eastmoney_daily, secid, years)
        if frame is not None:
            return frame
        raise ValueError("；".join(errors) or "该标的行情暂时无法获取")

    if s in _COM_TO_SINA:
        frame = try_source(fetch_sina_global_daily, _COM_TO_SINA[s], years)
        if frame is not None:
            return frame
        frame = try_source(fetch_eastmoney_daily, _COM_TO_EM[s], years)
        if frame is not None:
            return frame
        frame = try_source(fetch_yahoo_daily, s, years)
        if frame is not None:
            return frame
        raise ValueError("；".join(errors) or "大宗商品行情暂时无法获取")

    if s.startswith("fx") and re.fullmatch(r"fx[a-z]{6}", s):
        pair = s[2:]
        frame = try_source(fetch_eastmoney_daily, _FX_TO_EM.get(pair, "133." + pair.upper()), years)
        if frame is not None:
            return frame
        raise ValueError("；".join(errors) or "该外汇对暂未接入历史日K数据")

    if s.startswith("us"):
        ticker = s[2:]
        if ticker.startswith("^"):
            sina_symbol = _US_INDEX_TO_SINA.get(ticker)
            if sina_symbol:
                frame = try_source(fetch_sina_global_daily, sina_symbol, years)
                if frame is not None:
                    return frame
            em_secid = _US_INDEX_TO_EM.get(ticker, "100." + ticker[1:].upper())
            frame = try_source(fetch_eastmoney_daily, em_secid, years)
            if frame is not None:
                return frame
        else:
            if re.fullmatch(r"[a-z][a-z0-9._-]{0,10}", ticker):
                frame = try_source(fetch_sina_us_daily, ticker, years)
                if frame is not None:
                    return frame
            frame = try_source(fetch_eastmoney_daily, "105." + ticker.upper(), years)
            if frame is not None:
                return frame
        frame = try_source(fetch_yahoo_daily, s, years)
        if frame is not None:
            return frame
        raise ValueError("；".join(errors) or "该国际标的行情暂时无法获取")

    raise ValueError(f"暂不支持的市场代码: {symbol}")
