"""The number tables of the daily email, ready to paste, so the digest task never types a number.

Run from the repo root, after pipeline.run:
  python -m pipeline.email_tables    writes data/email_tables.html and data/email_tables.txt

Each file starts with `run_at: <the latest.json run time>` and holds four blocks, between `<!-- BLOCK name -->` and `<!-- /BLOCK name -->` lines
(in the .txt: `=== name ===` and `=== /name ===`):
  markets   the ~20 headline instruments (`email = true` in config/instruments.toml)
  notable   other instruments that moved unusually today or crossed a moving average
  options   the SPY/QQQ options block
  week      each headline instrument over the last week (used in the Sunday recap)
The HTML is inline styles only: Gmail's send tool strips <style> blocks and class names.
"""
import html
import json
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pipeline import fetch, indicators
from pipeline.run import DATA_DIR, load_history
from pipeline.site_data import with_latest

LONDON = ZoneInfo("Europe/London")
INK, TEXT, MUTED, RULE, BAND = "#1b2f4e", "#1d2430", "#586273", "#d9dee6", "#f3f5f8"
UP, DOWN, WARN_INK, WARN_WASH, ACC_INK, ACC_WASH = "#17773a", "#b8322a", "#7a4300", "#fff3d6", "#7f4a00", "#fbf1e2"
UNUSUAL = 2  # a day's move this many times the usual daily move counts as notable
NOTABLE_MAX = 8
STATES = {"open": ("●", "Open"), "just opened": ("●", "Just opened"), "pre-market": ("◐", "Pre-market"),
          "after-hours": ("◐", "After-hours"), "closed": ("○", "Closed")}
SOURCE_NAMES = {"yahoo": "Yahoo Finance", "fred": "FRED", "ecb": "ECB", "mnb": "MNB", "boe": "Bank of England",
                "bundesbank": "Bundesbank", "akk": "ÁKK", "mnb_bubor": "MNB (BUBOR)", "stoxx": "STOXX",
                "bse": "Budapest Stock Exchange", "pse": "Prague Stock Exchange"}

e = html.escape


# ---------- numbers and words ----------

def fmt(v, dp):
    return f"{v:,.{dp}f}"


def level(v, kind):
    """As the dashboard (yields 2 dp with %, small prices like FX 4 dp, the rest 2 dp), except
    0 dp from 10,000 up, so the column fits a phone."""
    return fmt(v, 2 if kind == "rate" or 10 <= abs(v) < 10_000 else 0 if abs(v) >= 10_000 else 4) + ("%" if kind == "rate" else "")


def move(ch, unit):
    """('▲ 1.29%', 'up') for a daily change; bp moves to 1 dp. None = no change known."""
    if ch is None:
        return "–", None
    dp = 1 if unit == "bp" else 2
    text = fmt(abs(ch), dp) + (" bp" if unit == "bp" else "%")
    if round(ch, dp) == 0:  # shows as zero: no arrow
        return text, None
    return ("▲ " if ch > 0 else "▼ ") + text, "up" if ch > 0 else "dn"


def sigmas(r):
    """Today's move in units of the usual daily move: 20-day realised volatility (annualised)
    divided by √252 turns it back into a typical day. None when either is unknown."""
    if r.get("change") is None or not r.get("vol_20d"):
        return None
    return abs(r["change"]) / (r["vol_20d"] / math.sqrt(indicators.TRADING_DAYS))


def uk_time(iso, with_day=True):
    """'Fri 20 Nov 16:41' in UK time; a date-only value (a daily figure) gives '20 Nov'."""
    if len(iso) == 10:
        return date.fromisoformat(iso).strftime("%-d %b")
    t = datetime.fromisoformat(iso).astimezone(LONDON)
    return t.strftime("%a %-d %b %H:%M" if with_day else "%H:%M")


def state(r, now):
    """'● Open · 14:34' or '○ Closed · Fri 20 Nov'. UK time; a value from today shows only its time."""
    dot, word = STATES.get(r.get("market_state"), ("○", "Closed"))
    t = r["time"]
    if len(t) > 10 and datetime.fromisoformat(t).astimezone(LONDON).date() == now.astimezone(LONDON).date():
        return f"{dot} {word} · {uk_time(t, with_day=False)}"
    day = t if len(t) == 10 else datetime.fromisoformat(t).astimezone(LONDON).date().isoformat()
    return f"{dot} {word} · {uk_time(day)}"


def why_notable(r):
    """The reasons an instrument is notable today, in words, or [] if it is not."""
    out = []
    s = sigmas(r)
    if s is not None and s >= UNUSUAL:
        out.append(f"{s:.1f}× its usual daily move")
    for n in (50, 200):
        if r.get(f"crossed_sma{n}"):
            out.append(f"crossed {r[f'crossed_sma{n}']} its {n}-day average")
    return out


def usable(r):
    return r.get("value") is not None and not r.get("suspect")


def week_change(rows):
    """(last close, its date, % or bp change vs the last close at least 7 days earlier) or None."""
    if not rows:
        return None
    last_day, last = rows[-1]
    before = [v for d, v in rows if d <= (date.fromisoformat(last_day) - timedelta(days=7)).isoformat()]
    return (last, last_day, before[-1]) if before else None


# ---------- HTML pieces ----------
# Gmail's send tool strips <style>, classes and roles, so everything is inline. To keep the email
# small (Gmail drops a large HTML body), padding comes from cellpadding, alignment and row
# shading from attributes, and the text style from the table: cells carry no style of their own.

F = "font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;"  # on each table: Outlook does not inherit fonts into tables


def table(top=2):
    return (f'<table width="100%" cellpadding="4" cellspacing="0" border="0" style="{F}border-collapse:collapse;'
            f'border-top:{top}px solid {INK};border-bottom:{top}px solid {INK};font-size:14px;line-height:19px;'
            f'color:{TEXT};font-variant-numeric:tabular-nums">')


def th(text, align="left"):
    """A column header: a real <th>, so screen readers announce each number with its column."""
    return f'<th align="{align}" style="font-size:12px;font-weight:600;color:{MUTED};border-bottom:1px solid {INK}">{text}</th>'


def tr(cells, banded):
    return f'<tr bgcolor="{BAND}">{cells}</tr>' if banded else f"<tr>{cells}</tr>"


def small(text):
    return f'<span style="color:{MUTED};font-size:12px">{text}</span>'


def change_cell(r):
    text, d = move(r.get("change"), r.get("change_unit", "%"))
    return f'<td align="right" nowrap style="color:{ {"up": UP, "dn": DOWN}.get(d, MUTED)}"><b>{text}</b></td>'


def ma_cell(r, n):
    above, crossed = r.get(f"above_sma{n}"), r.get(f"crossed_sma{n}")
    if above is None:
        return f'<td align="center" style="color:{MUTED}">–</td>'
    arrow = "↑" if above else "↓"
    if crossed:  # the one place the email uses the accent: a crossing since the last run
        return f'<td align="center"><b style="background:{ACC_WASH};color:{ACC_INK};padding:0 3px">{arrow}</b></td>'
    return f'<td align="center" style="color:{INK}">{arrow}</td>'


BAR = 8  # segments in the 52-week range bar


def range_bar(r):
    """Where the value sits between its 52-week low (▱▱▱) and high (▰▰▰), in characters, not images."""
    lo, hi, v = r.get("low_52w"), r.get("high_52w"), r.get("value")
    if lo is None or hi is None or hi <= lo:
        return small("–")
    n = max(0, min(BAR, round((v - lo) / (hi - lo) * BAR)))
    return f'<span style="color:{INK};font-size:9px">{"▰" * n}{"▱" * (BAR - n)}</span>'


def unavailable(r):
    why = "flagged as suspect by the sanity checks" if r.get("suspect") else (r.get("missing_reason") or "no value")
    return (f'<b style="background:{WARN_WASH};color:{WARN_INK};padding:0 5px;font-size:12px">Unavailable</b> '
            + small(e(why[:80])))


def name_html(r):
    return f'<b style="color:{INK}">{e(r["name"])}</b>'


def name_cell(r, now):
    # On a narrow phone the label may break only after the "·", never inside "20 Nov"
    under = " · ".join(x.replace(" ", "&nbsp;") for x in state(r, now).split(" · ")) if r.get("value") is not None else ""
    return f"<td>{name_html(r)}" + (f"<br>{small(under)}" if under else "") + "</td>"


def sources_line(rows):
    names = sorted({SOURCE_NAMES.get((r.get("source") or "").split(":")[0]) for r in rows} - {None})
    return ", ".join(names)


def caption(title):
    return f'<h2 style="margin:0 0 8px;font-size:18px;line-height:24px;color:{INK}">{e(title)}</h2>'


def note(text):
    return f'<p style="margin:6px 0 0;font-size:12px;line-height:17px;color:{MUTED}">{text}</p>'


def markets_html(latest, instruments, now):
    rows, group, shown, k = [], None, [], 0
    head = f'<tr>{th("Instrument")}{th("Last · 52w", "right")}{th("Day", "right")}{th("50d", "center")}{th("200d", "center")}</tr>'
    for inst in instruments:
        if not inst.get("email"):
            continue
        r = latest["instruments"][inst["id"]]
        shown.append(r)
        if inst["group"] != group:
            group = inst["group"]
            rows.append(f'<tr><td colspan="5" style="padding-top:12px;font-size:12px;font-weight:700;color:{INK};'
                        f'border-bottom:1px solid {RULE}">{e(group)}</td></tr>')
            k = 0
        k += 1
        if usable(r):
            cells = (f'<td align="right" nowrap>{level(r["value"], r["kind"])}<br>{range_bar(r)}</td>'
                     + change_cell(r) + ma_cell(r, 50) + ma_cell(r, 200))
        else:
            cells = f'<td colspan="4">{unavailable(r)}</td>'
        rows.append(tr(name_cell(r, now) + cells, k % 2 == 0))
    return (caption("Markets") + table() + head + "".join(rows) + "</table>"
            + note("Day: change since the previous close (bp = basis points, 0.01 percentage point, for yields and spreads). "
                   "50d / 200d: ↑ above or ↓ below the 50- or 200-day moving average; highlighted = crossed since the last update. "
                   "52w: where the price sits in its 52-week range, from ▱▱▱ at the low to ▰▰▰ at the high. – = not enough history yet. Times are UK time.")
            + note(f"Source: {e(sources_line(shown))}. Own calculations. Data as of {uk_time(latest['run_at'])} UK."))


def notable(latest, instruments):
    """[(row, reasons)] for instruments not in the headline table, biggest move first."""
    out = []
    for inst in instruments:
        r = latest["instruments"][inst["id"]]
        if not inst.get("email") and usable(r) and why_notable(r):
            out.append((r, why_notable(r)))
    return sorted(out, key=lambda x: -(sigmas(x[0]) or 0))[:NOTABLE_MAX]


def notable_html(items):
    if not items:
        return note("No other instrument moved unusually or crossed a moving average today.")
    rows = [tr(f'<td>{name_html(r)}<br>{small(e("; ".join(why)))}</td>'
               f'<td align="right" nowrap>{level(r["value"], r["kind"])}</td>{change_cell(r)}', k % 2)
            for k, (r, why) in enumerate(items)]
    return (f'<h3 style="margin:18px 0 6px;font-size:15px;line-height:21px;color:{INK}">Notable moves elsewhere</h3>'
            + table(1) + "".join(rows) + "</table>"
            + note(f"An unusual move is at least {UNUSUAL}× the usual daily move, which is the 20-day realised volatility divided by √252."))


def options_rows(o):
    if not o.get("expiry"):
        return None
    strikes = lambda xs: ", ".join(fmt(x["strike"], 0) for x in xs) or "–"
    n2 = lambda v: "–" if v is None else fmt(v, 2)
    return [
        ("Fund price", f'{fmt(o["underlying_price"], 2)}' if o.get("underlying_price") is not None else "–"),
        ("Expiry used", f'{date.fromisoformat(o["expiry"]).strftime("%-d %b")} ({o["days_to_expiry"]} days)'),
        ("At-the-money implied vol", "–" if o.get("atm_iv") is None else f'{fmt(o["atm_iv"], 1)}%'),
        ("Put/call, volume", n2(o.get("put_call_volume"))),
        ("Put/call, open interest", n2(o.get("put_call_oi"))),
        ("Most call open interest", strikes(o.get("top_call_oi", []))),
        ("Most put open interest", strikes(o.get("top_put_oi", []))),
    ]


def options_html(opts):
    syms = list(opts)
    rows_by = {s: options_rows(opts[s]) for s in syms}
    good = [s for s in syms if rows_by[s]]
    if not good:
        return caption("Options") + note("Options data unavailable: " + e("; ".join(f"{s}: {opts[s].get('missing_reason', 'no data')}" for s in syms)))
    head = "<tr>" + th("Measure") + "".join(th(e(s), "right") for s in good) + "</tr>"
    body = [tr(f'<td style="color:{INK}">{label}</td>' + "".join(f'<td align="right">{rows_by[s][k][1]}</td>' for s in good), k % 2)
            for k, (label, _) in enumerate(rows_by[good[0]])]
    first = opts[good[0]]
    exp = lambda ds: ", ".join(date.fromisoformat(d).strftime("%-d %b %Y") for d in ds)
    missing = [s for s in syms if not rows_by[s]]
    return (caption("Options, nearest monthly expiry") + table() + head + "".join(body) + "</table>"
            + (note("Unavailable: " + e(", ".join(missing))) if missing else "")
            + note(f"Next monthly expiries: {exp(first.get('upcoming_monthly', []))}. Quarterly: {exp(first.get('upcoming_quarterly', []))}.")
            + note(f"Source: Yahoo Finance, delayed about 15 minutes; newest trade {uk_time(first['time'])} UK. Own calculations."))


def week_rows(latest, instruments, hist):
    out = []
    for inst in instruments:
        r = latest["instruments"][inst["id"]]
        if inst.get("email"):
            w = week_change(with_latest(hist.get(inst["id"], []), r)) if r.get("value") is not None else None
            out.append((r, w))
    return out


def week_html(rows):
    body = []
    for k, (r, w) in enumerate(rows):
        if w:
            last, day, before = w
            ch = indicators.change(last, before, r["kind"])
            cells = f'<td align="right" nowrap>{level(last, r["kind"])}</td>' + change_cell({"change": ch, "change_unit": r.get("change_unit", "%")})
        else:
            cells = f'<td colspan="2" align="right">{small("Not enough history yet")}</td>'
        body.append(tr(f"<td>{name_html(r)}</td>{cells}", k % 2))
    head = f'<tr>{th("Instrument")}{th("Close", "right")}{th("Week", "right")}</tr>'
    return (caption("The week") + table() + head + "".join(body) + "</table>"
            + note("Week: last close against the last close at least 7 days earlier. Source: as the markets table. Own calculations."))


# ---------- plain text ----------

def text_line(r, now):
    if not usable(r):
        why = "flagged as suspect" if r.get("suspect") else (r.get("missing_reason") or "no value")
        return f"{r['name']}: unavailable ({why[:80]})"
    ch, _ = move(r.get("change"), r.get("change_unit", "%"))
    ma = [f"{'above' if r[f'above_sma{n}'] else 'below'} {n}d" + (" (crossed)" if r.get(f"crossed_sma{n}") else "")
          for n in (50, 200) if r.get(f"above_sma{n}") is not None]
    return f"{r['name']}: {level(r['value'], r['kind'])}, {ch} ({state(r, now)})" + (f", {', '.join(ma)}" if ma else "")


def block(name, body, kind):
    return (f"<!-- BLOCK {name} -->\n{body}\n<!-- /BLOCK {name} -->\n" if kind == "html"
            else f"=== {name} ===\n{body}\n=== /{name} ===\n")


def render(latest, instruments, hist, now):
    """(html, text): the four blocks of each file."""
    core = [latest["instruments"][i["id"]] for i in instruments if i.get("email")]
    items = notable(latest, instruments)
    weeks = week_rows(latest, instruments, hist)
    opts = latest.get("options", {})

    t_markets, group = [], None
    for i in instruments:
        if i.get("email"):
            if i["group"] != group:
                group = i["group"]
                t_markets.append(f"\n{group}")  # the name exactly as configured, e.g. "US equities"
            t_markets.append(text_line(latest["instruments"][i["id"]], now))
    t_markets.append(f"\nSource: {sources_line(core)}. Own calculations. Data as of {uk_time(latest['run_at'])} UK.")
    t_notable = [f"{r['name']}: {level(r['value'], r['kind'])}, {move(r['change'], r['change_unit'])[0]}: {'; '.join(w)}" for r, w in items] \
        or ["No other instrument moved unusually or crossed a moving average today."]
    t_opts = []
    for s, o in opts.items():
        rows = options_rows(o)
        t_opts.append(f"{s}: " + ("; ".join(f"{a.lower()} {b}" for a, b in rows) if rows else f"unavailable ({o.get('missing_reason', 'no data')})"))
    t_week = [f"{r['name']}: " + (f"{level(w[0], r['kind'])}, {move(indicators.change(w[0], w[2], r['kind']), r.get('change_unit', '%'))[0]} on the week"
                                  if w else "not enough history yet") for r, w in weeks]

    h = (block("markets", markets_html(latest, instruments, now), "html") + block("notable", notable_html(items), "html")
         + block("options", options_html(opts), "html") + block("week", week_html(weeks), "html"))
    t = (block("markets", "\n".join(t_markets).strip(), "text") + block("notable", "\n".join(t_notable), "text")
         + block("options", "\n".join(t_opts), "text") + block("week", "\n".join(t_week), "text"))
    return h, t


def main():
    latest = json.loads((DATA_DIR / "data" / "latest.json").read_text())
    hist, _ = load_history(DATA_DIR / "data" / "history" / "prices.csv")
    instruments = fetch.load_config()["instrument"]
    h, t = render(latest, instruments, hist, datetime.fromisoformat(latest["run_at"]))
    stamp = f"run_at: {latest['run_at']}"  # the digest task checks this equals latest.json's run_at
    (DATA_DIR / "data" / "email_tables.html").write_text(f"<!-- {stamp} -->\n{h}")
    (DATA_DIR / "data" / "email_tables.txt").write_text(f"{stamp}\n{t}")
    print(f"wrote email tables to {DATA_DIR / 'data'} for the run at {latest['run_at']}")


if __name__ == "__main__":
    main()
