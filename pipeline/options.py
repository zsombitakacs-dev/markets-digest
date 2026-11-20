"""Options data for the watchlist in config/instruments.toml ([options] watchlist).

Run from the repo root:  python -m pipeline.options
For each symbol, from the nearest monthly expiry: at-the-money implied volatility, the put/call
ratio by volume and by open interest, the 3 strikes with the most open interest for calls and
for puts, and the next monthly and quarterly expiry dates.

The source is Yahoo Finance (via yfinance). Its US option quotes are delayed about 15 minutes,
so `time` is the newest trade in the chain, not the time of the run. Checked 2026-11-20.
"""
import json
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import yfinance as yf

from pipeline import fetch, indicators

NEW_YORK = ZoneInfo("America/New_York")


def third_friday(year, month):
    first = date(year, month, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)  # Friday = weekday 4


def monthly_expiries(listed):
    """The standard monthly expiries among the listed dates (ISO strings): the third Friday,
    or the Thursday before it when the Friday is a market holiday (e.g. 2027-06-17)."""
    out = []
    for month in sorted({d[:7] for d in listed}):
        f = third_friday(int(month[:4]), int(month[5:]))
        for d in (f, f - timedelta(days=1)):
            if d.isoformat() in listed:
                out.append(d.isoformat())
                break
    return out


def atm_iv(calls, puts, price):
    """(strike, implied vol in %) at the strike nearest the price, or (strike, None).

    The mean of the call's and the put's IV at that strike: Yahoo's own IV figures for the two
    differ by a few points (rough rate and dividend inputs), and the mean cancels most of that.
    Only contracts with a live bid and ask count: after hours Yahoo's IV can be junk.
    """
    both = sorted(set(calls.strike) & set(puts.strike), key=lambda k: abs(k - price))
    if not both:
        return None, None
    k = both[0]
    ivs = [df[df.strike == k].iloc[0] for df in (calls, puts)]
    ivs = [r.impliedVolatility for r in ivs if r.bid > 0 and r.ask > 0]
    if len(ivs) < 2 or not all(0.01 < v < 3 for v in ivs):  # 1% to 300%: anything else is junk
        return float(k), None
    return float(k), round(sum(ivs) / 2 * 100, 2)


def put_call(calls, puts, column):
    """Total puts / total calls for a column ('volume' or 'openInterest'). None if no calls."""
    c, p = calls[column].fillna(0).sum(), puts[column].fillna(0).sum()
    return round(float(p / c), 2) if c > 0 else None


def top_strikes(df, n=3):
    """The n strikes with the largest open interest, largest first."""
    top = df.fillna({"openInterest": 0}).nlargest(n, "openInterest")
    return [{"strike": float(r.strike), "open_interest": int(r.openInterest)} for r in top.itertuples()]


def summarise(calls, puts, price):
    strike, iv = atm_iv(calls, puts, price)
    return {"atm_strike": strike, "atm_iv": iv,
            "put_call_volume": put_call(calls, puts, "volume"),
            "put_call_oi": put_call(calls, puts, "openInterest"),
            "call_volume": int(calls.volume.fillna(0).sum()), "put_volume": int(puts.volume.fillna(0).sum()),
            "call_oi": int(calls.openInterest.fillna(0).sum()), "put_oi": int(puts.openInterest.fillna(0).sum()),
            "top_call_oi": top_strikes(calls), "top_put_oi": top_strikes(puts)}


def fetch_one(symbol, today):
    """The options block for one symbol. `today` is New York's date (an ISO string)."""
    t = yf.Ticker(symbol)
    listed = set(t.options)
    monthly = [d for d in monthly_expiries(listed) if d > today]  # on expiry day it has hours left
    if not monthly:
        raise ValueError("no monthly expiry listed")
    expiry = monthly[0]
    chain = t.option_chain(expiry)
    price = chain.underlying.get("regularMarketPrice")
    if not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        raise ValueError(f"no underlying price: {price!r}")
    traded = max(chain.calls.lastTradeDate.max(), chain.puts.lastTradeDate.max())
    out = {"expiry": expiry, "days_to_expiry": (date.fromisoformat(expiry) - date.fromisoformat(today)).days,
           "time": traded.astimezone(timezone.utc).isoformat(),
           "underlying_price": price,
           "underlying_time": datetime.fromtimestamp(chain.underlying["regularMarketTime"], timezone.utc).isoformat(),
           **summarise(chain.calls, chain.puts, price),
           "upcoming_monthly": monthly[:3],
           "upcoming_quarterly": [d for d in monthly if d[5:7] in ("03", "06", "09", "12")][:2],
           "source": f"yahoo:{symbol}"}
    if out["atm_iv"] is None:
        out["missing_reason"] = "atm_iv: no live bid and ask at the money"
    return out


def fetch_all(config, now):
    """{symbol: block} for the watchlist. A failed symbol gets value None fields and its reason."""
    opts = config["options"]
    state = indicators.market_state(config["market"][opts["market"]], now)
    today = now.astimezone(NEW_YORK).date().isoformat()
    out = {}
    for s in opts["watchlist"]:
        try:
            out[s] = {**fetch_one(s, today), "market_state": state}
        except Exception as e:  # recorded, not fatal: the prices still get written
            out[s] = {"expiry": None, "time": None, "source": None, "market_state": state,
                      "missing_reason": f"{type(e).__name__}: {str(e)[:120]}"}
    return out


if __name__ == "__main__":
    print(json.dumps(fetch_all(fetch.load_config(), datetime.now(timezone.utc)), indent=1))
