"""Fetch the latest value of every instrument in config/instruments.toml.

Run from the repo root:  python -m pipeline.fetch
It prints one line per instrument: value, the time the value is from (UTC), and its source.

Each source has one small function that returns (value, time). `time` is an ISO 8601
string: a full UTC timestamp for live prices, or just a date (YYYY-MM-DD) for sources
that publish one number per day. If a source fails, the instrument's fallback is tried;
if that fails too, the value is recorded as missing with the reason. Nothing is estimated.

Sources that can also give past daily closes have a history_<source>(symbol) function
returning [(date, value), ...] oldest first (see HISTORY). It is used once per instrument
to fill data/history/prices.csv; after that, each day's close is appended by pipeline.run.
"""
import csv
import functools
import html
import io
import json
import math
import re
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl
import requests
import xlrd
import yfinance as yf

CONFIG = Path(__file__).resolve().parent.parent / "config" / "instruments.toml"


def load_config():
    with open(CONFIG, "rb") as f:
        return tomllib.load(f)


def load_instruments():
    return load_config()["instrument"]


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Tested 2026-11-20: FRED stalls browser-like and bare-name agents, the Bank of England
# refuses Python's default one (403). This honest script name works for every source.
USER_AGENT = "markets-digest/0.1 (+https://github.com)"


@functools.cache  # one download per URL per run (e.g. two bond tenors share one file)
def get(url, method="GET", data=None, headers=None):
    headers = {"User-Agent": USER_AGENT, **dict(headers or ())}
    r = requests.request(method, url, data=data, headers=headers, timeout=30)
    r.raise_for_status()
    return r.content


def last(rows):
    """[(date, value), ...] -> (value, date) of the newest row, the shape fetch_* returns."""
    day, value = rows[-1]
    return value, day


def two_years_ago():
    return (date.today() - timedelta(days=730)).isoformat()


# ---------- Yahoo Finance (most prices), batched into one request ----------

def _yahoo_last(symbols, interval):
    df = yf.download(symbols, period="5d", interval=interval, group_by="ticker",
                     auto_adjust=False, progress=False, threads=True)
    out = {}
    for s in symbols:
        try:
            close = df[s]["Close"].dropna()
        except KeyError:
            continue
        if len(close):
            ts = close.index[-1]
            time = ts.tz_convert("UTC").isoformat(timespec="seconds") if interval != "1d" else ts.date().isoformat()
            out[s] = (float(close.iloc[-1]), time)
    return out


def fetch_yahoo(symbols):
    """Return {symbol: (value, time)} for the symbols Yahoo had data for."""
    if not symbols:
        return {}
    # 1-minute bars over 5 days: the last bar is the latest price, even for a market
    # that closed hours ago (Asia) or yesterday.
    out = _yahoo_last(symbols, "1m")
    # Some symbols (e.g. MTELEKOM.BD) break Yahoo's minute data but have daily bars.
    rest = [s for s in symbols if s not in out]
    if rest:
        out.update(_yahoo_last(rest, "1d"))
    return out


def history_yahoo(symbols):
    """Return {symbol: [(date, close), ...]}: two years of daily closes, in one request."""
    df = yf.download(symbols, period="2y", interval="1d", group_by="ticker",
                     auto_adjust=False, progress=False, threads=True)
    out = {}
    for s in symbols:
        try:
            close = df[s]["Close"].dropna()
        except KeyError:
            continue
        out[s] = [(ts.date().isoformat(), float(v)) for ts, v in close.items()]
    return out


# ---------- One function per other source: fetch(symbol) -> (value, time) ----------

def parse_fred(text):
    # FRED's CSV: "observation_date,DGS2" then one row per day. Missing days are "." or empty.
    rows = list(csv.reader(io.StringIO(text)))[1:]
    return [(d, float(v)) for d, v in rows if v not in ("", ".")]


def history_fred(series):
    # The CSV download needs no key and always holds the whole history.
    return parse_fred(get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}").decode())


def fetch_fred(series):
    return last(history_fred(series))


def fetch_ecb(currency):
    # Euro foreign exchange reference rate: units of `currency` per 1 euro.
    url = (f"https://data-api.ecb.europa.eu/service/data/EXR/D.{currency}.EUR.SP00.A"
           "?format=csvdata&lastNObservations=1")
    row = list(csv.DictReader(io.StringIO(get(url).decode())))[-1]
    return float(row["OBS_VALUE"]), row["TIME_PERIOD"]


MNB_SOAP = ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope '
            'xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            '<GetCurrentExchangeRates xmlns="http://www.mnb.hu/webservices/"/></soap:Body></soap:Envelope>')


def parse_mnb(xml_bytes, currency):
    # The answer is XML wrapped inside XML: the rates arrive as one escaped string.
    inner = ET.fromstring(xml_bytes).find(".//{http://www.mnb.hu/webservices/}GetCurrentExchangeRatesResult").text
    day = ET.fromstring(inner).find("Day")
    for rate in day.findall("Rate"):
        if rate.get("curr") == currency:
            return float(rate.text.replace(",", ".")) / int(rate.get("unit")), day.get("date")
    raise ValueError(f"MNB has no rate for {currency}")


def fetch_mnb(currency):
    # Official MNB forint rate: HUF per 1 unit of `currency`.
    # shortcut: MNB's web service only answers on plain http (https returns 404), so the
    # reply is not encrypted. Acceptable for a public fallback rate; revisit if MNB adds https.
    body = get("http://www.mnb.hu/arfolyamok.asmx", "POST", MNB_SOAP.encode(), (
        ("Content-Type", "text/xml; charset=utf-8"),
        ("SOAPAction", '"http://www.mnb.hu/webservices/MNBArfolyamServiceSoap/GetCurrentExchangeRates"'),
    ))
    return parse_mnb(body, currency)


def parse_boe(xlsx, years):
    # Bank of England nominal spot curve workbook. Sheet "4. spot curve" has a "years:" row
    # naming the maturities (0.5y steps), then one row per day; days without data are blank.
    wb = openpyxl.load_workbook(io.BytesIO(xlsx), read_only=True, data_only=True)
    rows = list(wb["4. spot curve"].iter_rows(values_only=True))
    col = next(r for r in rows if r[0] == "years:").index(float(years))
    return [(r[0].date().isoformat(), float(r[col])) for r in rows
            if isinstance(r[0], datetime) and isinstance(r[col], (int, float))]


BOE_FILES = "https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/"


def boe_current_month():
    z = zipfile.ZipFile(io.BytesIO(get(BOE_FILES + "latest-yield-curve-data.zip")))
    return z.read("GLC Nominal daily data current month.xlsx")


def fetch_boe(years):
    return last(parse_boe(boe_current_month(), years))


def history_boe(years):
    # The archive (about 40 MB, downloaded once per backfill) runs to the end of last month.
    # shortcut: the file name "2025 to present" is how BoE names it in Nov 2026; if they start
    # a new file (e.g. "2030 to present"), this raises KeyError and the backfill reports it.
    z = zipfile.ZipFile(io.BytesIO(get(BOE_FILES + "glcnominalddata.zip")))
    rows = dict(parse_boe(z.read("GLC Nominal daily data_2025 to present.xlsx"), years))
    rows.update(parse_boe(boe_current_month(), years))
    return sorted(rows.items())


def parse_bundesbank(text):
    # Bundesbank statistics API, CSV: header lines of metadata, then "date,value,flags".
    rows = [r for r in csv.reader(io.StringIO(text)) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[0] if r else "")]
    return [(r[0], float(r[1])) for r in rows if r[1] not in ("", ".")]


def history_bundesbank(key, n=800):  # counts calendar days: 800 is about two years
    return parse_bundesbank(get(f"https://api.statistiken.bundesbank.de/rest/data/{key}"
                                f"?format=csv&lang=en&lastNObservations={n}").decode())


def fetch_bundesbank(key):
    return last(history_bundesbank(key, n=5))


AKK_API = "https://www.akk.hu/api/data/xpose3-dwh/data?query="


def parse_akk(body, tenor):
    # ÁKK (Hungarian debt agency) benchmark yields: the JSON behind its own website,
    # {"data": [{"date": "2026-11-20", "tenor": "10Y", "yield": 5.5, ...}, ...]}.
    rows = [(r["date"], float(r["yield"])) for r in json.loads(body)["data"] if r["tenor"] == tenor]
    if not rows:
        raise ValueError(f"ÁKK has no {tenor} benchmark")
    return sorted(rows)


def fetch_akk(tenor):
    return last(parse_akk(get(AKK_API + "getBenchmarkLast"), tenor))


def history_akk(tenor):
    # Not linked from the website, but listed in its API schema; tested 2026-11-20.
    return parse_akk(get(AKK_API + "getBenchmark&dateStart=" + two_years_ago()), tenor)


def parse_bubor(xls, column):
    # MNB's BUBOR file: an old-format .xls with one sheet per year; row 1 holds the
    # English column names, then one row per fixing day (date as an Excel day number).
    book = xlrd.open_workbook(file_contents=xls)
    rows = []
    for name in (n for n in book.sheet_names() if n.isdigit()):
        sheet = book.sheet_by_name(name)
        # Skips a new year's sheet before its first fixing, and sheets before 2023, whose
        # row 1 is in Hungarian ("3hónap", English in row 0); two years is all we need.
        if sheet.nrows < 3 or column not in sheet.row_values(1):
            continue
        col = sheet.row_values(1).index(column)
        for r in range(2, sheet.nrows):
            day, value = sheet.cell_value(r, 0), sheet.cell_value(r, col)
            if isinstance(day, float) and isinstance(value, float):  # skips "-" and notes
                rows.append((xlrd.xldate_as_datetime(day, book.datemode).date().isoformat(), value))
    if not rows:
        raise ValueError("no BUBOR fixing found")
    return sorted(rows)


def history_mnb_bubor(column):
    return parse_bubor(get("https://www.mnb.hu/letoltes/bubor2.xls"), column)


def fetch_mnb_bubor(column):
    return last(history_mnb_bubor(column))


def parse_stoxx(text):
    # Lines look like "19.11.2026;V2TX;22.5282" (day.month.year), after a header line.
    rows = [line.split(";") for line in text.strip().splitlines()[1:]]
    return [(datetime.strptime(r[0], "%d.%m.%Y").date().isoformat(), float(r[2])) for r in rows]


def history_stoxx(symbol):
    return parse_stoxx(get(f"https://www.stoxx.com/document/Indices/Current/HistoricalData/h_{symbol.lower()}.txt").decode())


def fetch_stoxx(symbol):
    return last(history_stoxx(symbol))


def parse_bse(page):
    # The home page embeds the BUX panel's data as JSON. It carries no timestamp, so the
    # time is when we read it; pipeline.run moves it back to the last close when Budapest is shut.
    m = re.search(r'"BuxIndexPanelDataSource":(\{[^}]*\})', page)
    if not m:
        raise ValueError("BUX data not found on the BSE page (layout changed?)")
    return float(json.loads(m.group(1))["index"]), now_utc()


def fetch_bse(symbol):
    return parse_bse(get("https://www.bse.hu/").decode())


def parse_pse(page):
    # The index page shows "Date & Time 20.11.2026 | 16:35:00" (Prague time) and "Current value 2,568.10".
    when = re.search(r"Date &amp; Time</div>\s*<div[^>]*>([^<]+)</div>", page)
    value = re.search(r"Current value</div>\s*<div[^>]*>\s*<td>([^<]+)</td>", page)
    if not (when and value):
        raise ValueError("PX value not found on the PSE page (layout changed?)")
    local = datetime.strptime(html.unescape(when.group(1)).strip(), "%d.%m.%Y | %H:%M:%S")
    ts = local.replace(tzinfo=ZoneInfo("Europe/Prague")).astimezone(timezone.utc)
    return float(value.group(1).replace(",", "")), ts.isoformat(timespec="seconds")


def fetch_pse(isin):
    return parse_pse(get(f"https://www.pse.cz/en/indices/index-values/detail/{isin}").decode())


SOURCES = {
    "fred": fetch_fred, "ecb": fetch_ecb, "mnb": fetch_mnb, "boe": fetch_boe,
    "bundesbank": fetch_bundesbank, "akk": fetch_akk, "mnb_bubor": fetch_mnb_bubor,
    "stoxx": fetch_stoxx, "bse": fetch_bse, "pse": fetch_pse,
}

# Sources with past daily closes. BSE and PSE have none we can read, so BUX and PX build
# their history from our own daily closes. Yahoo is batched separately (history_yahoo).
HISTORY = {
    "fred": history_fred, "boe": history_boe, "bundesbank": history_bundesbank,
    "akk": history_akk, "mnb_bubor": history_mnb_bubor, "stoxx": history_stoxx,
}


def fetch_one(source, symbol, yahoo):
    """Return (value, time) or raise with a readable reason."""
    if source == "yahoo":
        if symbol not in yahoo:
            yahoo.update(fetch_yahoo([symbol]))  # a fallback symbol not in the first batch
        if symbol not in yahoo:
            raise ValueError("Yahoo returned no data")
        value, time = yahoo[symbol]
    else:
        value, time = SOURCES[source](symbol)
    if not math.isfinite(value):
        raise ValueError(f"not a number: {value}")
    return value, time


def fetch_all(instruments):
    """One result dict per instrument, in config order."""
    yahoo = fetch_yahoo([i["symbol"] for i in instruments
                         if i.get("available", True) and i["source"] == "yahoo"])
    results = []
    for inst in instruments:
        res = {"id": inst["id"], "name": inst["name"], "group": inst["group"],
               "value": None, "time": None, "source": None}
        if not inst.get("available", True):
            res["missing_reason"] = inst["note"]
            results.append(res)
            continue
        if inst["source"] == "spread":  # filled in below, once both legs are fetched
            results.append(res)
            continue
        tries = [(inst["source"], inst["symbol"])]
        if "fallback_source" in inst:
            tries.append((inst["fallback_source"], inst["fallback_symbol"]))
        errors = []
        for source, symbol in tries:
            try:
                res["value"], res["time"] = fetch_one(source, symbol, yahoo)
                res["source"] = f"{source}:{symbol}"
                break
            except Exception as e:  # any failure: record why, try the fallback
                errors.append(f"{source}: {type(e).__name__}: {str(e)[:120]}")
        if res["value"] is None:
            res["missing_reason"] = "; ".join(errors)
        elif errors:
            res["fallback_because"] = errors[0]
        results.append(res)
    by_id = {r["id"]: r for r in results}
    for inst in instruments:
        if inst.get("source") == "spread":
            spread(by_id[inst["id"]], *(by_id[i] for i in inst["symbol"].split("-")))
    return results


def spread(res, a, b):
    """res = a minus b (e.g. 10-year yield minus 3-year), only if both are from the same day."""
    if a["value"] is None or b["value"] is None:
        res["missing_reason"] = f"needs both {a['id']} and {b['id']}"
    elif a["time"] != b["time"]:
        res["missing_reason"] = f"{a['id']} is from {a['time']}, {b['id']} from {b['time']}"
    else:
        # round: 5.50 - 5.48 is 0.019999999999999574 in binary floating point
        res.update(value=round(a["value"] - b["value"], 6), time=a["time"], source=f"spread:{a['id']}-{b['id']}")


def main():
    results = fetch_all(load_instruments())
    group = None
    for r in results:
        if r["group"] != group:
            group = r["group"]
            print(f"\n{group}")
        if r["value"] is None:
            print(f"  {r['name']:34} MISSING  {r['missing_reason']}")
        else:
            flag = "  (fallback)" if "fallback_because" in r else ""
            print(f"  {r['name']:34} {r['value']:>14,.4f}  {r['time']:25}  {r['source']}{flag}")
    ok = sum(r["value"] is not None for r in results)
    print(f"\n{ok} of {len(results)} instruments fetched at {now_utc()}")


if __name__ == "__main__":
    main()
