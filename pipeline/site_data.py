"""Build the dashboard folder that is deployed to Cloudflare Pages.

Run from the repo root, after pipeline.run:
  python -m pipeline.site_data     writes _site/: site/ plus latest.json and history.json

_site/ holds private data, so it is in .gitignore and only ever goes to Cloudflare, where it
sits behind Cloudflare Access. history.json is the last year of daily closes per instrument,
with the 50- and 200-day moving averages at each day, for the charts.
"""
import json
import shutil
from datetime import date, timedelta

from pipeline import indicators
from pipeline.run import DATA_DIR, ROOT, load_history

OUT = ROOT / "_site"


def chart_series(rows, days=365):
    """The last `days` of (date, close) rows, with the 50- and 200-day averages at each date.

    The averages use the full history, so they start on the chart's first day when there is a
    year of closes before it. A day with too few closes before it gets null (no line yet).
    """
    if not rows:
        return None
    start = (date.fromisoformat(rows[-1][0]) - timedelta(days=days)).isoformat()
    closes = [v for _, v in rows]
    out = {"d": [], "c": [], "m50": [], "m200": []}
    for k, (d, v) in enumerate(rows):
        if d < start:
            continue
        out["d"].append(d)
        out["c"].append(round(v, 6))
        for n in (50, 200):
            m = indicators.sma(closes[: k + 1], n)
            out[f"m{n}"].append(None if m is None else round(m, 6))
    return out


def with_latest(rows, r):
    """Past closes plus the latest value as its own day's point (not when missing or suspect)."""
    if r["value"] is None or r["suspect"]:
        return rows
    day = r["time"][:10]
    return [x for x in rows if x[0] < day] + [(day, r["value"])]


def main():
    latest_path = DATA_DIR / "data" / "latest.json"
    latest = json.loads(latest_path.read_text())
    hist, _ = load_history(DATA_DIR / "data" / "history" / "prices.csv")
    charts = {i: chart_series(with_latest(hist.get(i, []), r)) for i, r in latest["instruments"].items()}

    shutil.rmtree(OUT, ignore_errors=True)
    shutil.copytree(ROOT / "site", OUT)
    shutil.copy(latest_path, OUT / "latest.json")
    (OUT / "history.json").write_text(json.dumps({i: s for i, s in charts.items() if s}, separators=(",", ":")))
    print(f"wrote {OUT} with {sum(bool(s) for s in charts.values())} charts")


if __name__ == "__main__":
    main()
