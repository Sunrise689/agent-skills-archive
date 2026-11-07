"""估值研究数据与计算。

数据状态：内置历史数据（基于公开资料的近似值）+ baostock 动态数据（A 股任意股票）。
支持指标：市盈率pe、远期市盈率fpe、市净率pb、市销率ps、EV/EBITDA、
ROE、自由现金流收益率fcf_yield、负债率debt_ratio、毛利率gross_margin、股息率dividend_yield。
最多叠加 3 个指标；区间支持 5 年 / 10 年（最多回溯 10 年）；分位按全部可用历史计算。
"""
from __future__ import annotations

from typing import Any

YEARS = list(range(2010, 2026))

METRIC_META = {
    "pe": {"name": "市盈率", "unit": "倍"},
    "fpe": {"name": "远期市盈率", "unit": "倍"},
    "pb": {"name": "市净率", "unit": "倍"},
    "ps": {"name": "市销率", "unit": "倍"},
    "ev_ebitda": {"name": "EV/EBITDA", "unit": "倍"},
    "roe": {"name": "ROE", "unit": "%"},
    "fcf_yield": {"name": "自由现金流收益率", "unit": "%"},
    "debt_ratio": {"name": "负债率", "unit": "%"},
    "gross_margin": {"name": "毛利率", "unit": "%"},
    "dividend_yield": {"name": "股息率", "unit": "%"},
}

VALE_LIB: dict[str, dict[str, Any]] = {
    "600519": {
        "name": "贵州茅台", "market": "A股", "currency": "元",
        "aliases": ["茅台", "贵州茅台", "600519", "sh600519"],
        "price": [135, 185, 207, 139, 215, 217, 293, 688, 509, 1183, 1998, 2020, 1727, 1737, 1480, 1400],
        "eps": [5.05, 6.55, 11.9, 14.4, 15.5, 16.4, 17.9, 21.8, 28.0, 34.8, 37.2, 41.8, 49.9, 59.5, 68.6, 72.0],
        "bps": [25, 33, 42, 52, 62, 72, 84, 100, 122, 146, 167, 190, 215, 240, 262, 285],
        "sps": [11, 14, 18, 22, 23, 24, 27, 36, 45, 53, 58, 65, 75, 88, 100, 108],
        "growth": 9, "fcf_factor": 0.85,
        "extra": {
            "ev_ebitda": [13, 18, 16, 11, 15, 15, 19, 40, 30, 50, 65, 60, 50, 45, 38, 35],
            "debt_ratio": [25, 24, 24, 23, 22, 22, 26, 27, 27, 28, 26, 25, 24, 23, 22, 21],
            "gross_margin": [91, 92, 92, 93, 93, 93, 92, 90, 91, 91, 91, 92, 92, 92, 92, 92],
            "dividend_yield": [1.2, 1.1, 1.3, 1.8, 1.2, 1.4, 1.5, 1.0, 1.5, 1.1, 0.9, 1.1, 1.4, 1.6, 2.0, 2.3],
        },
    },
    "000001": {
        "name": "平安银行", "market": "A股", "currency": "元",
        "aliases": ["平安银行", "payh", "000001", "sz000001"],
        "price": [16, 15, 20, 12, 15, 12, 9, 13, 9, 16, 19, 17, 13, 9.5, 11, 12],
        "eps": [1.9, 2.2, 2.0, 2.0, 1.7, 1.9, 1.9, 2.0, 1.9, 1.8, 1.9, 1.5, 2.6, 2.4, 2.3, 2.3],
        "bps": [10, 12, 14, 15, 16, 17, 18, 20, 21, 23, 25, 26, 28, 30, 32, 34],
        "sps": [8, 10, 11, 12, 13, 14, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23],
        "growth": 5, "fcf_factor": None,
        "naMetrics": {
            "ev_ebitda": "银行业不适用 EBITDA 口径",
            "fcf_yield": "银行现金流结构特殊，不适用自由现金流口径",
            "gross_margin": "银行无营业成本口径，不适用毛利率",
        },
        "extra": {
            "debt_ratio": [92, 92, 93, 93, 93, 94, 94, 93, 93, 93, 92, 92, 93, 93, 92, 92],
            "dividend_yield": [2.5, 3.2, 2.8, 4.5, 3.8, 4.6, 5.2, 3.9, 5.8, 4.2, 3.8, 4.3, 5.5, 6.8, 6.0, 5.6],
        },
    },
    "00700": {
        "name": "腾讯控股", "market": "港股", "currency": "港元",
        "aliases": ["腾讯", "腾讯控股", "00700", "hk00700"],
        "price": [36, 30, 49, 99, 113, 148, 188, 406, 307, 378, 578, 445, 320, 295, 415, 500],
        "eps": [2.6, 2.4, 3.1, 4.6, 5.2, 6.2, 8.3, 19.2, 15.8, 19.6, 33.0, 44.0, 24.0, 31.0, 41.0, 46.0],
        "bps": [10, 12, 16, 22, 28, 35, 45, 60, 72, 88, 110, 130, 140, 165, 195, 225],
        "sps": [15, 18, 24, 33, 40, 48, 60, 90, 105, 120, 150, 175, 185, 200, 230, 255],
        "growth": 15, "fcf_factor": 0.8,
        "extra": {
            "ev_ebitda": [28, 26, 30, 35, 32, 35, 40, 55, 48, 50, 60, 52, 42, 40, 45, 48],
            "debt_ratio": [15, 16, 18, 20, 22, 25, 30, 35, 38, 40, 42, 45, 44, 43, 42, 41],
            "gross_margin": [60, 62, 63, 60, 58, 59, 60, 57, 55, 54, 53, 52, 48, 49, 53, 55],
            "dividend_yield": [0.3, 0.3, 0.3, 0.3, 0.3, 0.4, 0.4, 0.3, 0.3, 0.3, 0.2, 0.2, 0.5, 0.6, 0.5, 0.5],
        },
    },
    "aapl": {
        "name": "苹果", "market": "美股", "currency": "美元",
        "aliases": ["苹果", "apple", "aapl", "usaapl"],
        "growthHistory": {"latestYear": 2024, "yoy1y": 5, "cagr3y": 5, "cagr5y": 17},
        "price": [11.5, 14.5, 19.0, 28.0, 27.6, 26.3, 29.0, 42.3, 39.4, 73.4, 132.7, 177.6, 129.9, 192.5, 250.0, 215.0],
        "eps": [1.6, 2.0, 2.9, 2.6, 2.8, 2.5, 2.3, 2.5, 3.0, 2.9, 3.3, 5.6, 5.9, 6.1, 6.4, 7.0],
        "bps": [5, 6, 8, 10, 11, 12, 13, 14, 13, 15, 18, 20, 16, 18, 20, 22],
        "sps": [20, 24, 30, 34, 38, 42, 43, 46, 53, 52, 56, 73, 79, 75, 80, 84],
        "growth": 8, "fcf_factor": 0.9,
        "extra": {
            "ev_ebitda": [12, 11, 12, 12, 12, 12, 13, 14, 13, 16, 22, 20, 18, 20, 21, 20],
            "debt_ratio": [45, 47, 50, 52, 55, 58, 60, 62, 65, 68, 72, 78, 82, 80, 78, 76],
            "gross_margin": [40, 40, 42, 38, 39, 40, 39, 38, 38, 38, 38, 42, 43, 44, 46, 46],
            "dividend_yield": [0, 0, 0.8, 0.8, 0.9, 1.1, 1.3, 1.4, 1.6, 1.5, 0.8, 0.6, 1.3, 1.1, 0.8, 0.8],
        },
    },
    "000300": {
        "name": "沪深300", "market": "A股指数", "currency": "点",
        "aliases": ["沪深300", "沪深三百", "hs300", "000300", "sh000300"],
        "indexOnly": True,
        "price": [3128, 2346, 2522, 2116, 3534, 3731, 3310, 4031, 3011, 4097, 5211, 4940, 3872, 3431, 3935, 4150],
        "eps": [208.5, 217.2, 240.2, 237.8, 278.3, 262.7, 258.6, 278.0, 276.2, 320.1, 321.7, 352.9, 342.7, 311.9, 314.8, 319.2],
        "growth": None,
    },
    "spx": {
        "name": "标普500", "market": "美股指数", "currency": "点",
        "aliases": ["标普500", "标普", "spx", "gspc", "s&p500", "s&p 500", "s & p 500", "us^gspc", "usgspc", "sp500", "^gspc"],
        "indexOnly": True,
        "price": [1258, 1258, 1426, 1848, 2059, 2044, 2239, 2674, 2507, 3231, 3756, 4766, 3840, 4770, 5880, 6200],
        "eps": [83.9, 91.8, 98.3, 108.7, 113.8, 105.4, 111.4, 119.9, 127.9, 131.9, 101.5, 166.6, 197.9, 196.3, 221.9, 248.0],
        "growth": None,
    },
    "ixic": {
        "name": "纳斯达克综合", "market": "美股指数", "currency": "点",
        "aliases": ["纳斯达克综合", "纳斯达克", "纳指", "ixic", "us^ixic", "^ixic", "nasdaq"],
        "indexOnly": True,
        "price": [2653, 2605, 3020, 4177, 4736, 5007, 5383, 6903, 6635, 8973, 12888, 15645, 10467, 14766, 19722, 21300],
        "eps": [55, 60, 68, 82, 92, 100, 112, 135, 148, 172, 205, 285, 252, 290, 365, 420],
        "growth": None,
    },
    "msft": {
        "name": "微软", "market": "美股", "currency": "美元",
        "aliases": ["微软", "microsoft", "msft", "usmsft"],
        "growthHistory": {"latestYear": 2024, "yoy1y": 22, "cagr3y": 14, "cagr5y": 18},
        "price": [26, 25.5, 27, 35.5, 43, 52, 62, 85.5, 99.5, 157.7, 222.4, 335.5, 240, 375, 425, 512],
        "eps": [2.0, 2.0, 2.1, 2.6, 2.9, 2.7, 2.7, 3.2, 3.9, 5.0, 5.7, 8.1, 7.6, 9.7, 11.8, 13.5],
        "bps": [8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 24, 27, 32, 38, 45],
        "sps": [25, 26, 27, 29, 31, 32, 33, 36, 43, 51, 56, 66, 74, 80, 88, 98],
        "growth": 10, "fcf_factor": 0.85,
        "extra": {
            "ev_ebitda": [10, 10, 11, 13, 14, 16, 18, 22, 22, 28, 35, 32, 25, 30, 31, 33],
            "debt_ratio": [45, 45, 47, 46, 48, 52, 58, 60, 62, 60, 58, 55, 52, 50, 48, 46],
            "gross_margin": [62, 63, 64, 65, 65, 66, 61, 62, 63, 65, 67, 68, 68, 69, 69, 69],
            "dividend_yield": [0.8, 1.0, 1.1, 1.1, 1.3, 1.5, 1.6, 1.5, 1.5, 1.1, 0.9, 0.8, 1.0, 0.8, 0.7, 0.6],
        },
    },
    "nvda": {
        "name": "英伟达", "market": "美股", "currency": "美元",
        "aliases": ["英伟达", "nvidia", "nvda", "usnvda"],
        "growthHistory": {"latestYear": 2025, "yoy1y": 70, "cagr3y": 75, "cagr5y": 55},
        "price": [0.4, 0.3, 0.25, 0.5, 0.8, 0.85, 1.6, 2.7, 2.0, 5.9, 13.1, 29.4, 14.6, 49.5, 135, 180],
        "eps": [0.08, 0.05, 0.1, 0.2, 0.4, 0.45, 0.5, 0.7, 0.8, 1.1, 1.7, 2.4, 1.2, 2.1, 3.5, 4.7],
        "bps": [0.5, 0.55, 0.6, 0.8, 1.2, 1.6, 2.0, 2.8, 3.5, 4.5, 6, 9, 11, 16, 26, 36],
        "sps": [0.5, 0.55, 0.6, 0.9, 1.4, 1.6, 1.8, 2.3, 2.9, 3.7, 5.2, 8.0, 9.5, 15.0, 35, 48],
        "growth": 25, "fcf_factor": 0.8,
        "extra": {
            "ev_ebitda": [8, 10, 9, 15, 20, 22, 30, 40, 35, 50, 70, 65, 45, 55, 40, 35],
            "debt_ratio": [30, 32, 35, 33, 35, 38, 40, 42, 45, 42, 40, 38, 35, 32, 28, 25],
            "gross_margin": [55, 52, 54, 55, 57, 58, 60, 62, 60, 62, 65, 66, 60, 70, 75, 74],
            "dividend_yield": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0.05, 0.03, 0.02, 0.02, 0.02, 0.02, 0.02],
        },
    },
}


def resolve_stock(query: str):
    q = str(query or "").strip().lower()
    if not q:
        return None
    for code, item in VALE_LIB.items():
        if q == code or q in item["aliases"]:
            return code, item
    for code, item in VALE_LIB.items():
        if item["name"].lower() in q or q in item["name"].lower():
            return code, item
    return None




# ---------------- baostock 动态数据路径（任意 A 股） ----------------

def _bs_code_for_val(symbol: str) -> str | None:
    """内部代码转 baostock 格式。"""
    s = str(symbol or "").lower()
    if s.startswith("sh") and s[2:].isdigit():
        return "sh." + s[2:]
    if s.startswith(("sz", "bj")) and s[2:].isdigit():
        return "sz." + s[2:]
    return None


def _fetch_bs_valuation_series(query: str, years: int = 10) -> dict | None:
    """用 baostock 获取任意 A 股的历史 PE/PB 序列。
    返回与 build_valuation 兼容的 dict 格式。
    """
    try:
        import baostock as bs
    except ImportError:
        return None

    code = _bs_code_for_val(query)
    if not code:
        return None

    try:
        lg = bs.login()
        if lg.error_code != "0":
            return None
        try:
            end_date = __import__("datetime").date.today().strftime("%Y-%m-%d")
            start_date = (__import__("datetime").date.today() -
                          __import__("datetime").timedelta(days=years*365)).strftime("%Y-%m-%d")
            rs = bs.query_history_k_data_plus(
                code,
                "date,close,peTTM,pbMRq,psTTM,isST",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3",
            )
            if rs.error_code != "0":
                return None
            rows = []
            while rs.next():
                rows.append(dict(zip(rs.fields, rs.get_row_data())))
            if len(rows) < 60:
                return None

            # 提取名称
            name_rs = bs.query_stock_basic(code=code)
            stock_name = code
            if name_rs.error_code == "0" and name_rs.next():
                row = dict(zip(name_rs.fields, name_rs.get_row_data()))
                stock_name = row.get("code_name", code)

            # 构建年度序列（按年采样，每年取最后一个有效值）
            import pandas as pd
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df["year"] = df["date"].dt.year

            pe_series, pb_series, ps_series, price_series = [], [], [], []
            years_list = []

            for year in sorted(df["year"].unique()):
                yr_data = df[df["year"] == year]
                years_list.append(str(year))

                # PE
                pe_vals = []
                for _, r in yr_data.iterrows():
                    try:
                        v = float(r["peTTM"])
                        if v > 0: pe_vals.append(v)
                    except: pass
                pe_series.append(round(pe_vals[-1], 2) if pe_vals else None)

                # PB
                pb_vals = []
                for _, r in yr_data.iterrows():
                    try:
                        v = float(r["pbMRq"])
                        if v > 0: pb_vals.append(v)
                    except: pass
                pb_series.append(round(pb_vals[-1], 2) if pb_vals else None)

                # PS
                ps_vals = []
                for _, r in yr_data.iterrows():
                    try:
                        v = float(r["psTTM"])
                        if v > 0: ps_vals.append(v)
                    except: pass
                ps_series.append(round(ps_vals[-1], 2) if ps_vals else None)

                # Price
                close_vals = []
                for _, r in yr_data.iterrows():
                    try:
                        close_vals.append(float(r["close"]))
                    except: pass
                price_series.append(round(close_vals[-1], 2) if close_vals else None)

            # 计算百分位
            def _calc_stats(series):
                valid = [v for v in series if v is not None]
                if not valid:
                    return None
                current = valid[-1]
                ordered = sorted(valid)
                rank = sum(1 for v in valid if v <= current)
                pct = int(round(rank / len(valid) * 100))
                if pct >= 80: zone = "历史偏高区"
                elif pct <= 20: zone = "历史偏低区"
                else: zone = "历史中间区"
                return {"current": current, "percentile": pct,
                        "p20": ordered[max(0, int(len(ordered)*0.2)-1)],
                        "p80": ordered[min(len(ordered)-1, int(len(ordered)*0.8))],
                        "zone": zone, "values": series}

            result_metrics = {}
            for key, name, unit, s in [("pe","市盈率","倍",pe_series),
                                        ("pb","市净率","倍",pb_series),
                                        ("ps","市销率","倍",ps_series)]:
                st = _calc_stats(s)
                if st:
                    result_metrics[key] = {"name": name, "unit": unit, "na": False,
                                           "values": st["values"], **{k:v for k,v in st.items() if k != "values"}}
                else:
                    result_metrics[key] = {"name": name, "unit": unit, "na": True,
                                           "reason": "baostock 未取到该指标历史数据"}

            # —— 增长历史：用 baostock 年报净利润算同比与复合增速 ——
            growth_history = None
            try:
                import datetime as _dt
                _this_year = _dt.date.today().year
                _profits = {}
                for _y in range(_this_year - 6, _this_year + 1):
                    _grs = bs.query_profit_data(code=code, year=_y, quarter=4)
                    while _grs.error_code == "0" and _grs.next():
                        _row = dict(zip(_grs.fields, _grs.get_row_data()))
                        try:
                            _np = float(_row.get("netProfit") or "")
                            if _np != 0:
                                _profits[_y] = _np
                        except Exception:
                            pass
                if _profits:
                    _ys = sorted(_profits.keys())
                    _latest = _ys[-1]

                    def _cagr(n):
                        base = _profits.get(_latest - n)
                        cur = _profits.get(_latest)
                        if base and base > 0 and cur and cur > 0:
                            return round(((cur / base) ** (1.0 / n) - 1.0) * 100.0, 1)
                        return None

                    growth_history = {
                        "latestYear": _latest,
                        "yoy1y": _cagr(1),
                        "cagr3y": _cagr(3),
                        "cagr5y": _cagr(5),
                    }
            except Exception:
                growth_history = None

            return {
                "name": stock_name, "symbol": query, "market": "A股",
                "currency": "元", "years": [int(y) for y in years_list],
                "price": price_series, "metrics": result_metrics,
                "peg": None, "growth": None,
                "growthHistory": growth_history,
                "note": "数据来自 baostock（免费开源）；PE/PB 为 TTM/MRQ 口径；分位数按全部可用历史计算；仅供学习参考，不构成投资建议。",
                "dynamic": True,
            }
        finally:
            bs.logout()
    except Exception:
        return None


def _safe_div(a, b, nd=2):
    if b in (None, 0):
        return None
    return round(a / b, nd)


def _series(item: dict[str, Any], key: str) -> list:
    price = item["price"]
    eps = item.get("eps") or []
    bps = item.get("bps") or []
    sps = item.get("sps") or []
    n = len(YEARS)
    out: list = []
    if key == "pe":
        out = [_safe_div(price[i], eps[i]) if i < len(eps) else None for i in range(n)]
    elif key == "fpe":
        for i in range(n):
            if i + 1 < len(eps) and eps[i + 1]:
                out.append(_safe_div(price[i], eps[i + 1]))
            elif i == n - 1 and item.get("growth") and eps and eps[-1]:
                out.append(_safe_div(price[-1], eps[-1] * (1 + item["growth"] / 100.0)))
            else:
                out.append(None)
    elif key == "pb":
        out = [_safe_div(price[i], bps[i]) if i < len(bps) else None for i in range(n)]
    elif key == "ps":
        out = [_safe_div(price[i], sps[i]) if i < len(sps) else None for i in range(n)]
    elif key == "roe":
        out = [round(eps[i] / bps[i] * 100, 1) if (i < len(eps) and i < len(bps) and bps[i]) else None for i in range(n)]
    elif key == "fcf_yield":
        f = item.get("fcf_factor")
        out = [round(eps[i] * f / price[i] * 100, 1) if (f and i < len(eps) and eps[i] and price[i]) else None for i in range(n)]
    else:
        raw = list((item.get("extra") or {}).get(key) or [])
        raw += [None] * (n - len(raw))
        out = raw[:n]
    return out


def _stats(series: list) -> dict[str, Any]:
    valid = [v for v in series if v is not None]
    if not valid:
        return {}
    current = valid[-1]
    ordered = sorted(valid)
    rank = sum(1 for v in valid if v <= current)
    percentile = int(round(rank / len(valid) * 100))
    p20 = ordered[max(0, int(len(ordered) * 0.2) - 1)]
    p80 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.8))]
    if percentile >= 80:
        zone = "历史偏高区"
    elif percentile <= 20:
        zone = "历史偏低区"
    else:
        zone = "历史中间区"
    return {"current": current, "percentile": percentile, "p20": p20, "p80": p80, "zone": zone}


def build_valuation(query: str, metrics: str = "pe", years: int = 10) -> dict[str, Any]:
    keys = [k for k in str(metrics or "pe").split(",") if k in METRIC_META]
    keys = keys[:3] if keys else ["pe"]
    try:
        years = int(years)
    except (TypeError, ValueError):
        years = 10
    years = 5 if years <= 5 else 10

    # 优先尝试 baostock 动态数据（任意 A 股均可获取真实历史序列）
    bs_result = _fetch_bs_valuation_series(query, years)
    if bs_result:
        return bs_result

    # baostock 未命中 → 回退到内置数据库
    found = resolve_stock(query)
    if not found:
        raise ValueError("该资产暂无估值数据。A 股任意股票均可查询，港股/美股目前支持内置库中的标的。")
    code, item = found

    start = len(YEARS) - years
    result_metrics: dict[str, Any] = {}
    for key in keys:
        meta = METRIC_META[key]
        na_reason = (item.get("naMetrics") or {}).get(key)
        if item.get("indexOnly") and key not in ("pe", "fpe"):
            na_reason = "指数不适用该指标"
        if na_reason:
            result_metrics[key] = {"name": meta["name"], "unit": meta["unit"], "na": True, "reason": na_reason}
            continue
        series = _series(item, key)
        st = _stats(series)
        if not st:
            result_metrics[key] = {"name": meta["name"], "unit": meta["unit"], "na": True, "reason": "该指标暂无历史数据"}
            continue
        result_metrics[key] = {
            "name": meta["name"], "unit": meta["unit"], "na": False,
            "values": series[start:], **st,
        }

    peg = None
    pe_series = _series(item, "pe") if not item.get("indexOnly") else []
    pe_valid = [v for v in pe_series if v is not None]
    if pe_valid and item.get("growth"):
        peg = round(pe_valid[-1] / item["growth"], 2)

    return {
        "name": item["name"], "symbol": code, "market": item["market"], "currency": item["currency"],
        "years": YEARS[start:], "price": item["price"][start:],
        "metrics": result_metrics,
        "peg": peg, "growth": item.get("growth"),
        "growthHistory": item.get("growthHistory"),
        "note": "数据为历史近似值；分位数按全部可用历史（2010年起）计算；仅用于学习估值的历史位置，不构成投资建议；分位高低不等于未来涨跌。",
    }
