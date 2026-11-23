"""Mirror the running tables into a private Google Sheet, one tab per table.

Run from the repo root, after the end-of-day run:
  python -m pipeline.sheet

Needs GOOGLE_SA_KEY (a service account's JSON key) and GOOGLE_SHEET_ID (the long id in the
sheet's address), both GitHub Actions secrets. The sheet is shared with that service account
only. Without them it prints a note and does nothing, so it is safe to run before setup.
"""
import csv
import json
import os

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

from pipeline.export import num
from pipeline.run import DATA_DIR

TABS = {
    "prices": "data/history/prices.csv",
    "data_surprises": "logs/data_surprises.csv",
    "calendar_changes": "logs/calendar_changes.csv",
}


def ok(r):
    r.raise_for_status()  # the error body names the problem (e.g. sheet not shared); never the key
    return r.json()


def main():
    key, sheet_id = os.environ.get("GOOGLE_SA_KEY"), os.environ.get("GOOGLE_SHEET_ID")
    if not key or not sheet_id:
        print("Google Sheet mirror not set up (GOOGLE_SA_KEY / GOOGLE_SHEET_ID missing): skipped")
        return
    creds = service_account.Credentials.from_service_account_info(
        json.loads(key), scopes=["https://www.googleapis.com/auth/spreadsheets"])  # sheets only, no Drive
    s = AuthorizedSession(creds)
    base = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"

    tables = {}
    for tab, path in TABS.items():
        if (DATA_DIR / path).exists():
            with open(DATA_DIR / path, newline="") as f:
                if rows := [[num(c) for c in r] for r in csv.reader(f) if r]:
                    tables[tab] = rows

    have = {t["properties"]["title"] for t in ok(s.get(base, params={"fields": "sheets.properties.title"}))["sheets"]}
    if new := [{"addSheet": {"properties": {"title": t}}} for t in tables if t not in have]:
        ok(s.post(f"{base}:batchUpdate", json={"requests": new}))
    ids = {t["properties"]["title"]: t["properties"]["sheetId"]
           for t in ok(s.get(base, params={"fields": "sheets.properties(title,sheetId)"}))["sheets"]}

    # Size each tab to its table first: writing past a tab's last row is an error, not a resize.
    ok(s.post(f"{base}:batchUpdate", json={"requests": [
        {"updateSheetProperties": {
            "properties": {"sheetId": ids[t], "gridProperties": {
                "rowCount": len(rows) + 1, "columnCount": max(map(len, rows)), "frozenRowCount": 1}},
            "fields": "gridProperties(rowCount,columnCount,frozenRowCount)"}}
        for t, rows in tables.items()]}))
    for tab, rows in tables.items():
        ok(s.post(f"{base}/values/{tab}:clear"))
        # RAW: text is stored as text, so a log cell starting with "=" can never become a formula.
        ok(s.put(f"{base}/values/{tab}!A1", params={"valueInputOption": "RAW"}, json={"values": rows}))
        print(f"sheet tab {tab}: {len(rows) - 1} rows")


if __name__ == "__main__":
    main()
