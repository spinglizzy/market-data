"""Build market.json: sector/industry relative strength, trend and macro readings.

Runs in GitHub Actions after the US close. Output is read by the Thesis Board's
daily ideas scan and, later, the sector wall.
"""
import json
import math
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

BENCH = "SPY"

SECTORS = {
    "XLK": "Technology", "XLF": "Financials", "XLV": "Health Care", "XLE": "Energy",
    "XLI": "Industrials", "XLY": "Consumer Discretionary", "XLP": "Consumer Staples",
    "XLU": "Utilities", "XLB": "Materials", "XLRE": "Real Estate", "XLC": "Communication Services",
}

INDUSTRIES = {
    "SMH": "Semiconductors", "IGV": "Software", "CIBR": "Cybersecurity", "SKYY": "Cloud",
    "FINX": "Fintech", "ARKF": "Fintech (ARK)", "IAI": "Brokers & Exchanges",
    "KRE": "Regional Banks", "KBE": "Banks", "KIE": "Insurance",
    "ITB": "Homebuilders", "XHB": "Homebuilders & Suppliers", "PAVE": "Infrastructure",
    "XBI": "Biotech", "IHI": "Medical Devices", "PPH": "Pharma",
    "XOP": "Oil & Gas E&P", "OIH": "Oil Services", "URA": "Uranium", "TAN": "Solar",
    "GDX": "Gold Miners", "SIL": "Silver Miners", "XME": "Metals & Mining", "COPX": "Copper Miners",
    "ITA": "Aerospace & Defense", "IYT": "Transports", "JETS": "Airlines",
    "XRT": "Retail", "IBUY": "Online Retail", "BOTZ": "Robotics & AI",
}

BENCHMARKS = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "IWM": "Russell 2000", "RSP": "S&P 500 Equal Weight"}

MACRO = {
    "^TNX": "10Y Treasury yield (%)", "^IRX": "13W T-bill yield (%)", "CL=F": "WTI crude",
    "BZ=F": "Brent crude", "DX-Y.NYB": "US Dollar Index", "^VIX": "VIX", "GC=F": "Gold",
    "HG=F": "Copper", "TLT": "20Y+ Treasuries ETF", "BTC-USD": "Bitcoin",
}

RATIOS = {
    "ITB/SPY": ("ITB", "SPY", "Homebuilders vs market (homebuilder trigger)"),
    "FINX/SPY": ("FINX", "SPY", "Fintech vs market"),
    "XLF/SPY": ("XLF", "SPY", "Financials vs market"),
    "RSP/SPY": ("RSP", "SPY", "Breadth: equal weight vs cap weight"),
    "IWM/SPY": ("IWM", "SPY", "Small caps vs large caps"),
    "XLY/XLP": ("XLY", "XLP", "Risk appetite: discretionary vs staples"),
    "SMH/SPY": ("SMH", "SPY", "Semis vs market"),
}

WINDOWS = {"1d": 1, "1w": 5, "1m": 21, "3m": 63, "6m": 126}


def r(x, nd=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), nd)


def download(tickers):
    for attempt in range(3):
        try:
            df = yf.download(tickers, period="14mo", interval="1d", auto_adjust=True,
                             group_by="ticker", threads=True, progress=False)
            if not df.empty:
                return df
        except Exception as e:  # noqa: BLE001
            print(f"download attempt {attempt + 1} failed: {e}", file=sys.stderr)
        time.sleep(10 * (attempt + 1))
    raise SystemExit("Could not download price data")


def closes_for(df, t):
    try:
        s = df[t]["Close"].dropna()
    except KeyError:
        return None
    return s if len(s) > 30 else None


def ret(s, n):
    if len(s) <= n:
        return None
    return (s.iloc[-1] / s.iloc[-1 - n] - 1) * 100


def metrics(s, bench):
    last = s.iloc[-1]
    out = {"close": r(last, 4 if last < 10 else 2), "date": s.index[-1].strftime("%Y-%m-%d")}
    for k, n in WINDOWS.items():
        out[f"ret_{k}"] = r(ret(s, n))
    if bench is not None:
        for k in ("1w", "1m", "3m"):
            a, b = ret(s, WINDOWS[k]), ret(bench, WINDOWS[k])
            out[f"rs_{k}"] = r(a - b) if a is not None and b is not None else None
    sma50 = s.rolling(50).mean().iloc[-1]
    sma200 = s.rolling(200).mean().iloc[-1] if len(s) >= 200 else float("nan")
    out["vs_sma50"] = r((last / sma50 - 1) * 100)
    out["vs_sma200"] = r((last / sma200 - 1) * 100)
    yr = s.iloc[-252:]
    out["from_52w_high"] = r((last / yr.max() - 1) * 100)
    out["from_52w_low"] = r((last / yr.min() - 1) * 100)
    # Basing tightness: 10-day closing range as % of price, vs its typical level over 3 months.
    rng = (s.rolling(10).max() - s.rolling(10).min()) / s * 100
    out["range_10d"] = r(rng.iloc[-1])
    out["range_10d_avg_3m"] = r(rng.iloc[-63:].mean())
    out["tight"] = bool(rng.iloc[-1] < 0.7 * rng.iloc[-63:].mean()) if not math.isnan(rng.iloc[-1]) else None
    return out


def score(m):
    vals = [m.get("rs_1w"), m.get("rs_1m"), m.get("rs_3m")]
    if any(v is None for v in vals):
        return None
    return 0.2 * vals[0] + 0.4 * vals[1] + 0.4 * vals[2]


def ratio_block(df, a, b):
    sa, sb = closes_for(df, a), closes_for(df, b)
    if sa is None or sb is None:
        return None
    s = (sa / sb).dropna()
    last = s.iloc[-1]
    sma50 = s.rolling(50).mean().iloc[-1]
    low_recent = s.iloc[-20:].min()
    low_prior = s.iloc[-40:-20].min()
    return {
        "value": r(last, 5),
        "chg_1w": r(ret(s, 5)), "chg_1m": r(ret(s, 21)), "chg_3m": r(ret(s, 63)),
        "vs_sma50": r((last / sma50 - 1) * 100),
        "higher_low_20d": bool(low_recent > low_prior),
        "history_60d": [r(v, 5) for v in s.iloc[-60:].tolist()],
    }


COMPACT_FIELDS = ["close", "ret_1d", "ret_1w", "ret_1m", "rs_1w", "rs_1m", "rs_3m", "rs_rank",
                  "vs_sma50", "vs_sma200", "from_52w_high", "tight"]
COMPACT_RATIO = ["value", "chg_1w", "chg_1m", "chg_3m", "vs_sma50", "higher_low_20d"]


def compact(data):
    """Small snapshot the Thesis Board stores in its database (doc meta/market)."""
    m, names, group = {}, {}, {}
    for g in ("benchmarks", "sectors", "industries", "macro"):
        for t, row in data[g].items():
            if "error" in row:
                continue
            names[t] = row["name"]
            group[t] = g
            m[t] = {k: row[k] for k in COMPACT_FIELDS if row.get(k) is not None}
    ratios = {k: {f: v[f] for f in COMPACT_RATIO if v.get(f) is not None} | {"desc": v.get("desc")}
              for k, v in data["ratios"].items() if "error" not in v}
    s = data["summary"]
    return {
        "as_of": data["as_of"], "generated_at": data["generated_at"],
        "sector_rank": s["sector_rank"], "industry_rank": s["industry_rank"],
        "leaders": s["industry_leaders_near_highs"], "basing": s["industries_basing"],
        "names": names, "group": group, "m": m, "ratios": ratios,
    }


def main():
    tickers = sorted(set(SECTORS) | set(INDUSTRIES) | set(BENCHMARKS) | set(MACRO)
                     | {x for a, b, _ in RATIOS.values() for x in (a, b)})
    df = download(tickers)
    bench = closes_for(df, BENCH)
    if bench is None:
        raise SystemExit("Benchmark SPY missing")

    def block(names, with_rs=True):
        out = {}
        for t, name in names.items():
            s = closes_for(df, t)
            if s is None:
                out[t] = {"name": name, "error": "no data"}
                continue
            m = metrics(s, bench if with_rs else None)
            m["name"] = name
            out[t] = m
        return out

    sectors = block(SECTORS)
    industries = block(INDUSTRIES)
    benchmarks = block(BENCHMARKS)
    macro = block(MACRO, with_rs=False)

    def ranked(group):
        rows = [(t, score(m)) for t, m in group.items() if "error" not in m]
        rows = [x for x in rows if x[1] is not None]
        rows.sort(key=lambda x: x[1], reverse=True)
        for i, (t, sc) in enumerate(rows, 1):
            group[t]["rs_score"] = r(sc)
            group[t]["rs_rank"] = i
        return [t for t, _ in rows]

    sector_rank = ranked(sectors)
    industry_rank = ranked(industries)

    leaders = [t for t in industry_rank[:10]
               if (industries[t].get("from_52w_high") or -99) > -10 and (industries[t].get("vs_sma50") or -1) > 0]
    basing = [t for t, m in industries.items()
              if m.get("tight") and (m.get("from_52w_high") or -99) > -12 and (m.get("vs_sma50") or -1) > -2]

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "as_of": bench.index[-1].strftime("%Y-%m-%d"),
        "notes": {
            "returns": "ret_* are % price changes over 1d/1w(5d)/1m(21d)/3m(63d)/6m(126d).",
            "rs": "rs_* = ticker return minus SPY return over the window, in percentage points.",
            "rs_score": "0.2*rs_1w + 0.4*rs_1m + 0.4*rs_3m; rs_rank 1 = strongest in its group.",
            "trend": "vs_sma50/vs_sma200 and from_52w_high/low are % distances.",
            "tight": "True when the 10-day closing range is under 70% of its 3-month average (a basing sign).",
            "ratios": "higher_low_20d compares the lowest ratio of the last 20 sessions with the 20 before.",
            "macro": "^TNX and ^IRX are yields in percent; others are prices.",
        },
        "summary": {
            "sector_rank": sector_rank,
            "industry_rank": industry_rank,
            "industry_leaders_near_highs": leaders,
            "industries_basing": basing,
        },
        "benchmarks": benchmarks,
        "sectors": sectors,
        "industries": industries,
        "macro": macro,
        "ratios": {k: {"desc": d, **(ratio_block(df, a, b) or {"error": "no data"})} for k, (a, b, d) in RATIOS.items()},
    }
    with open("market.json", "w") as f:
        json.dump(data, f, indent=1)
    with open("market_compact.json", "w") as f:
        json.dump(compact(data), f, separators=(",", ":"))
    print(f"Wrote market.json as of {data['as_of']}: top sectors {sector_rank[:3]}, top industries {industry_rank[:5]}")


if __name__ == "__main__":
    main()
