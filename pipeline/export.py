"""Monthly exports, written into the data repo's exports/ folder.

Run from the repo root:
  python -m pipeline.export            last month (the workflow runs on the 1st)
  python -m pipeline.export 2026-11    a given month

Writes exports/YYYY-MM.xlsx (price history, indicators, data surprises, calendar log and an
index of digests), and when the month has digests, exports/YYYY-MM-digests.pdf (printed from
the emailed HTML by headless Chrome) and exports/YYYY-MM-digests.docx (built from the .md files).
"""
import argparse
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from docx import Document
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Font

from pipeline import fetch
from pipeline.run import DATA_DIR

INDICATOR_COLS = ["value", "change", "change_unit", "sma50", "dist_sma50", "sma200", "dist_sma200",
                  "high_52w", "low_52w", "dist_high_52w", "dist_low_52w", "vol_20d",
                  "market_state", "suspect", "source", "missing_reason"]


def last_month(today):
    return (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def num(s):
    """A CSV cell as a number when it is one, so spreadsheets can sum and chart it."""
    try:
        x = float(s)
    except ValueError:
        return s
    return x if math.isfinite(x) and "_" not in s else s  # "nan" or "1_000" stay text


def csv_month(path, month):
    """Header and the rows whose first column (the date) is in `month`. Empty if no file yet."""
    if not path.exists():
        return [], []
    with open(path, newline="") as f:
        header, *rows = list(csv.reader(f)) or [[]]
    return header, [[num(c) for c in r] for r in rows if r and r[0].startswith(month)]


def digest_files(month, ext):
    return sorted((DATA_DIR / "digests").glob(f"{month}-??{ext}"))


def title(md):
    """The digest's first '# ' heading, for the index."""
    return next((l[2:].strip() for l in md.read_text().splitlines() if l.startswith("# ")), "")


def excel(month, out):
    names = {i["id"]: (i["name"], i["group"]) for i in fetch.load_config()["instrument"]}
    wb = Workbook()
    sheets = {}

    _, rows = csv_month(DATA_DIR / "data/history/prices.csv", month)
    sheets["Prices"] = (["date", "id", "name", "group", "close", "source"],
                        [[d, i, *names.get(i, ("", "")), c, s] for d, i, c, s in rows])

    ind = []
    for snap in sorted((DATA_DIR / "data/snapshots").glob(f"{month}-??.json")):
        for i, r in json.loads(snap.read_text())["instruments"].items():
            ind.append([snap.stem, i, r.get("name", "")] + [r.get(c) for c in INDICATOR_COLS])
    sheets["Indicators"] = (["date", "id", "name"] + INDICATOR_COLS, ind)

    sheets["Data surprises"] = csv_month(DATA_DIR / "logs/data_surprises.csv", month)
    sheets["Calendar log"] = csv_month(DATA_DIR / "logs/calendar_changes.csv", month)
    sheets["Digests"] = (["date", "title", "markdown", "html"],
                         [[md.stem, title(md), f"digests/{md.name}",
                           f"digests/{md.stem}.html" if md.with_suffix(".html").exists() else ""]
                          for md in digest_files(month, ".md")])

    wb.remove(wb.active)
    for name, (header, rows) in sheets.items():
        ws = wb.create_sheet(name)
        ws.append(header or ["(no rows yet)"])
        for r in rows:
            ws.append(r)
            for c in ws[ws.max_row]:
                if isinstance(c.value, str) and c.value.startswith("="):
                    c.data_type = "s"  # text, never a formula: the logs hold text from web pages
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.freeze_panes = "A2"
        if rows:
            ws.auto_filter.ref = ws.dimensions
        for col in ws.columns:  # rough fit: the longest value in the first 200 rows
            width = max(len(str(c.value or "")) for c in col[:200])
            ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 8), 60)
    wb.save(out)


# The digests' HTML came from web content via the digest task: block scripts and remote loads.
LOCKDOWN = ('<meta http-equiv="Content-Security-Policy" '
            'content="default-src \'none\'; style-src \'unsafe-inline\'; img-src data:">')


def find_chrome():
    for c in (os.environ.get("CHROME"), "google-chrome", "chromium", "chromium-browser",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if c and shutil.which(c):
            return shutil.which(c)
    sys.exit("Chrome not found: install it or set CHROME to its path")


def combined_html(htmls):
    """One printable page: each digest's styles and body, each starting on a new page."""
    styles, bodies = [], []
    for h in htmls:
        text = h.read_text()
        styles += [s for s in re.findall(r"<style[^>]*>.*?</style>", text, re.S | re.I) if s not in styles]
        body = re.search(r"<body[^>]*>(.*)</body>", text, re.S | re.I)
        bodies.append(f'<section style="break-before:page">{body[1] if body else text}</section>')
    return f'<!doctype html><meta charset="utf-8">{LOCKDOWN}{"".join(styles)}{"".join(bodies)}'


def pdf(htmls, out):
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "digests.html"
        page.write_text(combined_html(htmls))
        subprocess.run([find_chrome(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={tmp}/profile", f"--print-to-pdf={out}", page.as_uri()],
                       check=True, timeout=180, capture_output=True)


INLINE = re.compile(r"\*\*(.+?)\*\*|\[([^\]]+)\]\(((?:[^()\s]|\([^()\s]*\))+)\)")  # a URL may hold one (…) pair


def add_inline(p, text):
    """Plain text, **bold** and [links](url). shortcut: no italics or code spans; add them if digests use them."""
    pos = 0
    for m in INLINE.finditer(text):
        p.add_run(text[pos:m.start()])
        if m[1]:
            p.add_run(m[1]).bold = True
        elif m[3].startswith(("https://", "http://")):  # never a javascript: or file: link
            r_id = p.part.relate_to(m[3], RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
            link = OxmlElement("w:hyperlink")
            link.set(qn("r:id"), r_id)
            run = p.add_run(m[2])
            run.font.underline = True
            run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x8C)
            link.append(run._r)  # moves the run inside the link
            p._p.append(link)
        else:
            p.add_run(m[2])
        pos = m.end()
    p.add_run(text[pos:])


def add_table(doc, lines):
    rows = [[c.strip() for c in l.strip().strip("|").split("|")] for l in lines
            if not re.fullmatch(r"[\s|:-]+", l)]  # drop the |---|---| separator row
    if not rows:
        return
    t = doc.add_table(rows=len(rows), cols=max(map(len, rows)), style="Table Grid")
    for r, cells in zip(t.rows, rows):
        for cell, text in zip(r.cells, cells):
            add_inline(cell.paragraphs[0], text)
    for c in t.rows[0].cells:
        for run in c.paragraphs[0].runs:
            run.bold = True


def word(mds, out):
    doc = Document()
    doc.styles["Normal"].font.size = Pt(10.5)
    for n, md in enumerate(mds):
        if n:
            doc.add_page_break()
        table = []
        for line in md.read_text().splitlines() + [""]:
            if line.lstrip().startswith("|"):
                table.append(line)
                continue
            if table:
                add_table(doc, table)
                table = []
            s = line.strip()
            if not s or re.fullmatch(r"[-*_]{3,}", s):
                continue
            if h := re.match(r"(#{1,4})\s+(.*)", s):
                add_inline(doc.add_heading(level=len(h[1])), h[2])
            elif b := re.match(r"[-*+]\s+(.*)", s):
                add_inline(doc.add_paragraph(style="List Bullet"), b[1])
            elif re.match(r"\d+\.\s", s):  # keep the number as text: Word's numbering would not restart per digest
                p = doc.add_paragraph()
                p.paragraph_format.left_indent = Pt(18)
                add_inline(p, s)
            else:
                add_inline(doc.add_paragraph(), s)
    doc.save(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("month", nargs="?", help="YYYY-MM (default: last month)")
    month = ap.parse_args().month or last_month(date.today())
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        sys.exit("month must look like 2026-11")
    out = DATA_DIR / "exports"
    out.mkdir(exist_ok=True)

    excel(month, out / f"{month}.xlsx")
    print(f"wrote exports/{month}.xlsx")
    htmls, mds = digest_files(month, ".html"), digest_files(month, ".md")
    if htmls:
        pdf(htmls, out / f"{month}-digests.pdf")
        print(f"wrote exports/{month}-digests.pdf ({len(htmls)} digests)")
    if mds:
        word(mds, out / f"{month}-digests.docx")
        print(f"wrote exports/{month}-digests.docx ({len(mds)} digests)")
    if not (htmls or mds):
        print(f"no digests for {month} yet: PDF and Word skipped")


if __name__ == "__main__":
    main()
