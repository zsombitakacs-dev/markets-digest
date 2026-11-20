"""Indicators for one instrument, from its daily closes. Pure maths: no downloads, no files.

`kind` decides the unit of every change and distance:
  "price" -> percent (%), e.g. the S&P 500 is up 0.8%
  "rate"  -> basis points (bp, 0.01 percentage point), e.g. the Bund 10-year is up 3 bp
Yields and spreads use bp because a % change of a yield is hard to read (and meaningless
for a spread that can cross zero, like the 2s10s).
"""
import math
import statistics
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TRADING_DAYS = 252  # in a year; turns daily volatility into yearly ("annualised")


def unit(kind):
    return "bp" if kind == "rate" else "%"


def change(new, old, kind):
    """How far `new` is from `old`: % for prices, bp for rates."""
    if kind == "rate":
        return (new - old) * 100
    return (new / old - 1) * 100


def sma(values, n):
    """Simple moving average: the mean of the last n values. None until there are n."""
    return sum(values[-n:]) / n if len(values) >= n else None


def high_low_52w(rows):
    """Highest and lowest close in the 52 weeks up to the last row. rows: [(date, value)]."""
    cutoff = (date.fromisoformat(rows[-1][0]) - timedelta(days=365)).isoformat()
    year = [v for d, v in rows if d >= cutoff]
    return max(year), min(year)


def realised_vol(values, kind, n=20):
    """Annualised standard deviation of the last n daily moves. None until there are n moves.

    Prices: log returns, in %. Rates: daily changes, in bp.
    shortcut: always 252 trading days a year, also for Bitcoin (trades 365); fine for comparing
    one instrument with itself over time.
    """
    if len(values) < n + 1:
        return None
    v = values[-(n + 1):]
    if kind == "rate":
        moves = [(b - a) * 100 for a, b in zip(v, v[1:])]
    else:
        moves = [math.log(b / a) * 100 for a, b in zip(v, v[1:])]
    return statistics.stdev(moves) * math.sqrt(TRADING_DAYS)


def crossed(was_above, is_above):
    """'above' or 'below' if the price crossed a moving average since the last run, else None."""
    if was_above is None or is_above is None or was_above == is_above:
        return None
    return "above" if is_above else "below"


# Largest believable move since the last run, before a value is flagged `suspect`.
MAX_MOVE_PCT = {"FX": 10, "Volatility": 100}  # every other price: 20%
MAX_MOVE_BP = 100  # yields and spreads


def suspect(value, ref, kind, group):
    """A reason the value looks wrong, or None. ref = the last run's value (or the previous close)."""
    if kind == "price" and value <= 0:
        return "zero or negative price"
    if ref is None or (kind == "price" and ref <= 0):
        return None
    move = abs(change(value, ref, kind))
    limit = MAX_MOVE_BP if kind == "rate" else MAX_MOVE_PCT.get(group, 20)
    if move > limit:
        return f"moved {move:.1f}{unit(kind)} since the last run (limit {limit}{unit(kind)})"
    return None


# Two runs in a row this close together confirm a big move as real (see pipeline.run).
AGREE_PCT = 1
AGREE_BP = 5


def agrees(a, b, kind):
    """True if a and b are the same level, within 1% (prices) or 5 bp (rates)."""
    if kind == "price" and b <= 0:
        return False
    return abs(change(a, b, kind)) <= (AGREE_BP if kind == "rate" else AGREE_PCT)


def market_state(market, now):
    """'open', 'closed', 'pre-market' or 'after-hours' at `now` (an aware datetime), by the timetable.

    market: a [market.*] table from config/instruments.toml, or None for a figure published
    once a day (a bond fixing, a FRED series), which is always 'closed'.
    """
    if market is None:
        return "closed"
    if market.get("always_open"):
        return "open"
    t = now.astimezone(ZoneInfo(market["tz"]))
    hm, day = t.strftime("%H:%M"), t.weekday()  # "HH:MM" strings compare correctly; Monday = 0
    opens, closes = market["open"], market["close"]
    if opens >= closes:  # overnight session: opens Sunday-Thursday evening, closes next day
        evening = day in (6, 0, 1, 2, 3) and hm >= opens
        morning = day < 5 and hm < closes
        return "open" if evening or morning else "closed"
    if day >= 5:
        return "closed"
    if opens <= hm < closes:
        return "open"
    if market.get("pre", opens) <= hm < opens:
        return "pre-market"
    if closes <= hm < market.get("post", closes):
        return "after-hours"
    return "closed"


STALE = timedelta(minutes=30)
JUST_OPENED = timedelta(minutes=45)
OPEN = ("open", "just opened")  # the states in which a market is trading


def checked_state(market, time, now):
    """market_state, plus what the timetable can't know. `time` is the latest price's time.

    The timetables have no public holidays (e.g. US Thanksgiving); a holiday shows up as a price
    that stops updating, so an open market whose price is over 30 minutes old is
    'closed (holiday?)'. Except in the first 45 minutes of a session, 'just opened': a delayed
    source may still show the last close then. Only full timestamps count: a date-only figure
    is daily anyway.
    """
    state = market_state(market, now)
    if state != "open":
        return state
    if market_state(market, now - JUST_OPENED) != "open":  # works for overnight and FX sessions too
        return "just opened"
    if time and "T" in time and now - datetime.fromisoformat(time) > STALE:
        return "closed (holiday?)"
    return state


def last_close(market, now):
    """The most recent weekday closing time at or before `now`, for a daytime market."""
    tz = ZoneInfo(market["tz"])
    today = now.astimezone(tz).date()
    for back in range(8):
        d = today - timedelta(days=back)
        close = datetime.combine(d, time.fromisoformat(market["close"]), tz)
        if d.weekday() < 5 and close <= now:
            return close


def summarise(rows, kind, previous=None):
    """All indicators for one instrument.

    rows: daily closes [(date, value)], oldest first, the last row being the latest value.
    previous: this instrument's entry from the last run's latest.json (for crossings), or None.
    Anything that cannot be calculated yet is None, and `indicator_gaps` says why.
    """
    values = [v for _, v in rows]
    value = values[-1]
    out = {"change_unit": unit(kind), "history_days": len(rows)}
    gaps = []

    if len(rows) >= 2:
        out["prev_close"], out["prev_close_date"] = values[-2], rows[-2][0]
        out["change"] = round(change(value, values[-2], kind), 2)
    else:
        out["prev_close"] = out["prev_close_date"] = out["change"] = None
        gaps.append("change: no previous close yet")

    for n in (50, 200):
        avg = sma(values, n)
        out[f"sma{n}"] = None if avg is None else round(avg, 4)
        out[f"dist_sma{n}"] = None if avg is None else round(change(value, avg, kind), 2)
        out[f"above_sma{n}"] = None if avg is None else value > avg
        out[f"crossed_sma{n}"] = crossed((previous or {}).get(f"above_sma{n}"), out[f"above_sma{n}"])
        if avg is None:
            gaps.append(f"sma{n}: needs {n} daily closes, has {len(rows)}")

    # A "52-week high" from a few weeks of data would look real but is not, so it waits.
    if date.fromisoformat(rows[0][0]) <= date.fromisoformat(rows[-1][0]) - timedelta(days=360):
        hi, lo = high_low_52w(rows)
        out.update(high_52w=hi, low_52w=lo,
                   dist_high_52w=round(change(value, hi, kind), 2),
                   dist_low_52w=round(change(value, lo, kind), 2))
    else:
        out.update(high_52w=None, low_52w=None, dist_high_52w=None, dist_low_52w=None)
        gaps.append(f"52-week range: history only starts {rows[0][0]}")

    vol = realised_vol(values, kind)
    out["vol_20d"] = None if vol is None else round(vol, 2)
    if vol is None:
        gaps.append(f"vol_20d: needs 21 daily closes, has {len(rows)}")

    if gaps:
        out["indicator_gaps"] = gaps
    return out
