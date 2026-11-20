"""Fetch every instrument, calculate its indicators and write the data files.

Run from the repo root:
  python -m pipeline.run           writes data/latest.json
  python -m pipeline.run --close   also saves today's closes to data/history/prices.csv
                                   and a copy of latest.json to data/snapshots/YYYY-MM-DD.json

The data folder is the private data repo, found through the DATA_DIR environment variable
(default: ../markets-digest-data, cloned next to this repo). Nothing is written to this repo.

Past daily closes come from data/history/prices.csv. An instrument with no rows there yet
(the first run, or a newly added one) gets about two years of history from its source.
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import fetch, indicators, options

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT.parent / "markets-digest-data"))


def load_history(path):
    """{id: [(date, close), ...]} oldest first, and {(id, date): source} from prices.csv."""
    hist, sources = {}, {}
    if path.exists():
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                hist.setdefault(row["id"], []).append((row["date"], float(row["close"])))
                sources[row["id"], row["date"]] = row["source"]
    return {k: sorted(v) for k, v in hist.items()}, sources


def save_history(path, hist, sources):
    """One row per instrument per day, sorted by date so each day's closes land at the end."""
    rows = sorted((d, i, v) for i, series in hist.items() for d, v in series)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "id", "close", "source"])
        for d, i, v in rows:
            w.writerow([d, i, repr(v), sources[i, d]])


def put(hist, sources, i, rows, source):
    """Store an instrument's history rows, each with the source it came from."""
    hist[i] = rows
    sources.update({(i, d): source for d, _ in rows})


def backfill(instruments, hist, sources):
    """Fill in past closes for every instrument that has none yet. Returns what failed, by id."""
    todo = [i for i in instruments if i.get("available", True) and not hist.get(i["id"])]
    failed = {}
    yahoo = [i for i in todo if i["source"] == "yahoo"]
    if yahoo:
        got = fetch.history_yahoo([i.get("history_symbol", i["symbol"]) for i in yahoo])
        for i in yahoo:
            sym = i.get("history_symbol", i["symbol"])
            if got.get(sym):
                put(hist, sources, i["id"], got[sym], f"yahoo:{sym}")
    for i in todo:
        if i["source"] in fetch.HISTORY:
            try:
                put(hist, sources, i["id"], fetch.HISTORY[i["source"]](i["symbol"]), f"{i['source']}:{i['symbol']}")
            except Exception as e:  # recorded, not fatal: indicators wait for history
                failed[i["id"]] = f"{type(e).__name__}: {str(e)[:120]}"
        elif i["source"] == "spread":  # e.g. 10-year minus 3-year, on days both exist
            a, b = (dict(hist.get(x, [])) for x in i["symbol"].split("-"))
            series = [(d, round(a[d] - b[d], 6)) for d in sorted(a) if d in b]
            if series:
                put(hist, sources, i["id"], series, f"spread:{i['symbol']}")
    # FRED and BUBOR send decades; two years covers every indicator. Today's row is dropped:
    # mid-session it is not a close yet (`--close` adds the real one).
    start, today = fetch.two_years_ago(), datetime.now(timezone.utc).date().isoformat()
    for i in todo:
        if hist.get(i["id"]):
            hist[i["id"]] = [r for r in hist[i["id"]] if start <= r[0] < today]
    return failed


def build(instruments, markets, results, hist, previous, now):
    """The latest.json content: run time, then one object per instrument, keyed by id."""
    out = {}
    for inst, res in zip(instruments, results):
        market = markets.get(inst.get("market"))
        kind = inst.get("kind", "price")
        res = {**res, "kind": kind, "chart": inst["chart"]}
        if "note" in inst:
            res["note"] = inst["note"]
        if not inst.get("available", True):
            out[inst["id"]] = {**res, "market_state": None, "suspect": False}
            continue
        res["market_state"] = indicators.checked_state(market, res["time"], now)
        if inst["source"] == "bse" and res["value"] is not None and res["market_state"] not in indicators.OPEN:
            res["time"] = indicators.last_close(market, now).astimezone(timezone.utc).isoformat()
        prev = previous.get(inst["id"])
        if res["value"] is None:
            out[inst["id"]] = {**res, "suspect": False}
            continue
        day = res["time"][:10]
        rows = [r for r in hist.get(inst["id"], []) if r[0] < day] + [(day, res["value"])]
        # Compare with the last value that was not suspect: the last run's, the one the last
        # run carried forward, or (first run) the previous close.
        if prev and prev.get("value") is not None and not prev.get("suspect"):
            last_good = {"value": prev["value"], "time": prev["time"]}
        elif prev and prev.get("last_good"):
            last_good = prev["last_good"]
        else:
            last_good = {"value": rows[-2][1], "time": rows[-2][0]} if len(rows) > 1 else None
        reason = indicators.suspect(res["value"], last_good and last_good["value"], kind, inst["group"])
        if reason and prev and prev.get("suspect") and indicators.agrees(res["value"], prev["value"], kind):
            # Two runs in a row at the new level: a real move, not a glitch. Accept it, and
            # keep the last run's value as its day's close if that day has none yet.
            reason = None
            res["confirmed_jump"] = f"same level as the last run ({prev['value']} at {prev['time']})"
            if prev["time"][:10] < day:
                res["confirmed_close"] = {"date": prev["time"][:10], "value": prev["value"], "source": prev["source"]}
        res["suspect"] = reason is not None
        if reason:
            res["suspect_reason"] = reason
            res["last_good"] = last_good  # so the next run compares with it, not with this value
        if not (kind == "price" and res["value"] <= 0):  # a log return needs a positive price
            res.update(indicators.summarise(rows, kind, prev))
        out[inst["id"]] = res
    return {"run_at": now.isoformat(timespec="seconds"), "instruments": out}


def add_close(hist, sources, i, day, value, source):
    hist[i] = sorted({**dict(hist.get(i, [])), day: value}.items())
    sources[i, day] = source


def save_closes(latest, hist, sources, today=True):
    """Save closes into the history: a confirmed jump's earlier day (every run, so it is not
    lost), and with today=True each latest value as the close for its own date."""
    for i, r in latest["instruments"].items():
        c = r.get("confirmed_close")
        if c and c["date"] not in dict(hist.get(i, [])):
            add_close(hist, sources, i, c["date"], c["value"], c["source"])
        if today and r["value"] is not None and not r["suspect"]:  # a suspect value never enters it
            add_close(hist, sources, i, r["time"][:10], r["value"], r["source"])


OPTIONS_EVERY = timedelta(minutes=30)  # option chains change slowly and are heavy to fetch


def options_due(prev, watchlist, open_now, now):
    """Fetch new option chains, or keep the last block (`prev`, {symbol: block})?

    Keep it while it is under 30 minutes old. While the US market is shut, also keep a block
    that was taken while it was open (e.g. Friday's, all weekend): after-hours chains can lack
    a live bid and ask, which leaves the at-the-money implied volatility empty.
    """
    blocks = [(prev or {}).get(s) or {} for s in watchlist]
    if not all(b.get("fetched_at") for b in blocks):
        return True  # first run, or a symbol newly added to the watchlist
    if not open_now and all(b.get("market_state") in indicators.OPEN and b.get("expiry") for b in blocks):
        return False
    return now - min(datetime.fromisoformat(b["fetched_at"]) for b in blocks) >= OPTIONS_EVERY


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--close", action="store_true", help="also save today's closes and a snapshot")
    args = ap.parse_args()

    config = fetch.load_config()
    instruments, markets = config["instrument"], config["market"]
    prices = DATA_DIR / "data" / "history" / "prices.csv"
    latest_path = DATA_DIR / "data" / "latest.json"

    hist, sources = load_history(prices)
    failed = backfill(instruments, hist, sources)
    for i, why in failed.items():
        print(f"history for {i} not available: {why}")
    previous = json.loads(latest_path.read_text()) if latest_path.exists() else {}

    now = datetime.now(timezone.utc)
    latest = build(instruments, markets, fetch.fetch_all(instruments), hist, previous.get("instruments", {}), now)
    opts = config["options"]
    # The S&P 500's state stands for the US options market: it is holiday-checked, the timetable isn't.
    us_state = latest["instruments"]["sp500"]["market_state"]
    if options_due(previous.get("options"), opts["watchlist"], us_state in indicators.OPEN, now):
        latest["options"] = options.fetch_all(config, now, us_state)
    else:
        latest["options"] = {s: previous["options"][s] for s in opts["watchlist"]}
        print(f"options: kept the block fetched at {min(b['fetched_at'] for b in latest['options'].values())}")
    write_json(latest_path, latest)
    save_closes(latest, hist, sources, today=args.close)
    if args.close:
        write_json(DATA_DIR / "data" / "snapshots" / f"{now.date().isoformat()}.json", latest)
    save_history(prices, hist, sources)  # also keeps a fresh backfill, so it runs only once

    rows = latest["instruments"].values()
    got = sum(r["value"] is not None for r in rows)
    print(f"wrote {latest_path} at {latest['run_at']}: {got} of "
          f"{len(rows)} values, {sum(r['suspect'] for r in rows)} suspect")
    wanted = sum(i.get("available", True) for i in instruments)
    if got < wanted / 2:  # e.g. Yahoo blocking us: the files are written, but the run fails visibly
        sys.exit(f"only {got} of {wanted} available instruments fetched")


if __name__ == "__main__":
    main()
