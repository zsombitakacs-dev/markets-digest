"""Fetch the latest value of every instrument in config/instruments.toml.

Run from the repo root:  python -m pipeline.fetch
It prints one line per instrument: value, the time the value is from (UTC), and its source.

Each source has one small function that returns (value, time). `time` is an ISO 8601
string: a full UTC timestamp for live prices, or just a date (YYYY-MM-DD) for sources
that publish one number per day. If a source fails, the instrument's fallback is tried;
if that fails too, the value is recorded as missing with the reason. Nothing is estimated.
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
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import openpyxl
import requests
import xlrd
import yfinance as yf

CONFIG = Path(__file__).resolve().parent.parent / "config" / "instruments.toml"


def load_instruments():
    with open(CONFIG, "rb") as f:
        return tomllib.load(f)["instrument"]


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


# ---------- One function per other source: fetch(symbol) -> (value, time) ----------

def fetch_fred(series):
    # FRED's CSV download needs no key. Missing days are written as "." or empty.
    text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}").decode()
    rows = [r for r in csv.reader(io.StringIO(text))][1:]
    date, value = [r for r in rows if r[1] not in ("", ".")][-1]
    return float(value), date


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


def fetch_boe(years):
    # Bank of England daily nominal spot curve: a zip holding an Excel file. Sheet
    # "4. spot curve" has one row per day and one column per maturity (0.5y steps).
    z = zipfile.ZipFile(io.BytesIO(get(
        "https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/latest-yield-curve-data.zip")))
    wb = openpyxl.load_workbook(io.BytesIO(z.read("GLC Nominal daily data current month.xlsx")),
                                read_only=True, data_only=True)
    rows = list(wb["4. spot curve"].iter_rows(values_only=True))
    col = next(r for r in rows if r[0] == "years:").index(float(years))
    day = [r for r in rows if isinstance(r[0], datetime) and isinstance(r[col], (int, float))][-1]
    return float(day[col]), day[0].date().isoformat()


def fetch_bundesbank(key):
    # Bundesbank statistics API, CSV: two header lines of metadata, then "date,value,".
    text = get(f"https://api.statistiken.bundesbank.de/rest/data/{key}"
               "?format=csv&lang=en&lastNObservations=5").decode()
    rows = [r for r in csv.reader(io.StringIO(text)) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[0] if r else "")]
    date, value = [r[:2] for r in rows if r[1] not in ("", ".")][-1]
    return float(value), date


def fetch_akk(tenor):
    # ÁKK (Hungarian debt agency) benchmark yields: the JSON behind its own website.
    data = json.loads(get("https://www.akk.hu/api/data/xpose3-dwh/data?query=getBenchmarkLast"))["data"]
    row = next(r for r in data if r["tenor"] == tenor)
    return float(row["yield"]), row["date"]


def fetch_mnb_bubor(column):
    # MNB's BUBOR file: an old-format .xls with one sheet per year; row 1 holds the
    # English column names, then one row per fixing day (date as an Excel day number).
    book = xlrd.open_workbook(file_contents=get("https://www.mnb.hu/letoltes/bubor2.xls"))
    for name in sorted((n for n in book.sheet_names() if n.isdigit()), reverse=True):
        sheet = book.sheet_by_name(name)
        if sheet.nrows < 3:
            continue  # e.g. a new year's sheet before its first fixing
        col = sheet.row_values(1).index(column)
        for r in range(sheet.nrows - 1, 1, -1):
            day, value = sheet.cell_value(r, 0), sheet.cell_value(r, col)
            if isinstance(day, float) and isinstance(value, float):
                return value, xlrd.xldate_as_datetime(day, book.datemode).date().isoformat()
    raise ValueError("no BUBOR fixing found")


def parse_stoxx(text):
    # Lines look like "19.11.2026;V2TX;22.5282" (day.month.year).
    day, _, value = text.strip().splitlines()[-1].split(";")[:3]
    return float(value), datetime.strptime(day, "%d.%m.%Y").date().isoformat()


def fetch_stoxx(symbol):
    return parse_stoxx(get(f"https://www.stoxx.com/document/Indices/Current/HistoricalData/h_{symbol.lower()}.txt").decode())


def parse_bse(page):
    # The home page embeds the BUX panel's data as JSON. It carries no timestamp.
    # shortcut: time = when we read it, so after the close it looks fresher than it is;
    # cap it at the Budapest close once phase 2 knows market hours.
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
    return results


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
