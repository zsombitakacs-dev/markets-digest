"""The data files: history round trip, closes, backfilled spreads, and latest.json. Offline."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from pipeline import fetch, run

BUDAPEST = {"tz": "Europe/Budapest", "open": "09:00", "close": "17:00"}


class History(unittest.TestCase):
    def test_csv_round_trip(self):
        hist = {"eurhuf": [("2026-11-19", 373.2), ("2026-11-20", 373.55)], "hu10y": [("2026-11-20", 5.5)]}
        # one source per row: on 2026-11-20 EUR/HUF came from the MNB fallback
        sources = {("eurhuf", "2026-11-19"): "yahoo:EURHUF=X", ("eurhuf", "2026-11-20"): "mnb:EUR",
                   ("hu10y", "2026-11-20"): "akk:10Y"}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history" / "prices.csv"
            run.save_history(path, hist, sources)
            self.assertEqual(path.read_text().splitlines()[:2],
                             ["date,id,close,source", "2026-11-19,eurhuf,373.2,yahoo:EURHUF=X"])
            self.assertEqual(run.load_history(path), (hist, sources))

    def test_close_replaces_the_day_and_skips_gaps_and_suspects(self):
        hist = {"otp": [("2026-11-19", 40600.0), ("2026-11-20", 38000.0)]}
        sources = {("otp", "2026-11-19"): "yahoo:OTP.BD", ("otp", "2026-11-20"): "yahoo:OTP.BD"}
        latest = {"instruments": {
            "otp": {"value": 38690.0, "time": "2026-11-20T16:00:00+00:00", "source": "yahoo:OTPX.BD", "suspect": False},
            "mol": {"value": 1.0, "time": "2026-11-20", "source": "yahoo:MOL.BD", "suspect": True},
            "hu2y": {"value": None, "time": None, "source": None, "suspect": False}}}
        run.save_closes(latest, hist, sources)
        self.assertEqual(hist, {"otp": [("2026-11-19", 40600.0), ("2026-11-20", 38690.0)]})
        # the new close has its own source; the day before keeps the one it had
        self.assertEqual(sources, {("otp", "2026-11-19"): "yahoo:OTP.BD", ("otp", "2026-11-20"): "yahoo:OTPX.BD"})

    def test_backfilled_spread_only_on_days_with_both_legs(self):
        hist = {"hu10y": [("2026-11-18", 5.49), ("2026-11-19", 5.51)],
                "hu3y": [("2026-11-19", 5.48), ("2026-11-20", 5.48)]}
        sources = {}
        inst = [{"id": "hu3s10s", "source": "spread", "symbol": "hu10y-hu3y"}]
        with mock.patch.object(fetch, "two_years_ago", return_value="2024-01-01"):
            run.backfill(inst, hist, sources)
        [(day, value)] = hist["hu3s10s"]
        self.assertEqual(day, "2026-11-19")
        self.assertAlmostEqual(value, 0.03)  # 5.51 - 5.48


class Build(unittest.TestCase):
    inst = {"id": "bux", "name": "BUX", "group": "Hungary equities", "market": "budapest",
            "source": "bse", "symbol": "BUX", "chart": "https://www.bse.hu/"}

    def build(self, value, now, previous=None):
        res = {"id": "bux", "name": "BUX", "group": "Hungary equities",
               "value": value, "time": now.isoformat(timespec="seconds"), "source": "bse:BUX"}
        hist = {"bux": [("2026-11-18", 143000.0), ("2026-11-19", 143065.66)]}
        return run.build([self.inst], {"budapest": BUDAPEST}, [res], hist, previous or {}, now)["instruments"]["bux"]

    def test_after_the_close_the_time_is_the_close(self):
        # Saturday: BSE still shows Friday's level, so its time is Friday 17:00 Budapest.
        r = self.build(137648.73, datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc))
        self.assertEqual(r["market_state"], "closed")
        self.assertEqual(r["time"], "2026-11-20T16:00:00+00:00")
        self.assertAlmostEqual(r["change"], -3.79)  # 137648.73 / 143065.66 - 1
        self.assertEqual(r["prev_close_date"], "2026-11-19")
        self.assertFalse(r["suspect"])

    def test_budapest_holiday_follows_otp(self):
        # Fri 23 Oct 2026, a Hungarian national holiday, 11:00 Budapest (09:00 UTC, summer time).
        # BSE's page gives no time, but OTP's last price is Thursday's close, so both are shut.
        now = datetime(2026, 10, 23, 9, 0, tzinfo=timezone.utc)
        bux = {**self.inst, "state_from": "otp"}
        otp = {"id": "otp", "name": "OTP Bank", "group": "Hungary equities", "market": "budapest",
               "source": "yahoo", "symbol": "OTP.BD", "chart": ""}
        results = [{"id": "bux", "name": "BUX", "group": "Hungary equities", "value": 143100.0,
                    "time": "2026-10-23T09:00:00+00:00", "source": "bse:BUX"},
                   {"id": "otp", "name": "OTP Bank", "group": "Hungary equities", "value": 40600.0,
                    "time": "2026-10-22T15:00:00+00:00", "source": "yahoo:OTP.BD"}]  # Thu 17:00 Budapest
        hist = {"bux": [("2026-10-21", 143000.0)], "otp": [("2026-10-21", 40500.0)]}
        out = run.build([bux, otp], {"budapest": BUDAPEST}, results, hist, {}, now)["instruments"]
        self.assertEqual(out["otp"]["market_state"], "closed (holiday?)")
        self.assertEqual(out["bux"]["market_state"], "closed (holiday?)")
        self.assertEqual(out["bux"]["time"], "2026-10-22T15:00:00+00:00")  # moved back to Thursday's close
        # A normal day: OTP traded 5 minutes ago, so BUX is open with the time we read it.
        results[1]["time"] = "2026-10-23T08:55:00+00:00"
        out = run.build([bux, otp], {"budapest": BUDAPEST}, results, hist, {}, now)["instruments"]
        self.assertEqual((out["bux"]["market_state"], out["bux"]["time"]), ("open", "2026-10-23T09:00:00+00:00"))

    def test_a_jump_since_the_last_run_is_suspect(self):
        r = self.build(170000.0, datetime(2026, 11, 20, 14, 45, tzinfo=timezone.utc),
                       previous={"bux": {"value": 137000.0, "time": "2026-11-20T14:40:00+00:00", "suspect": False}})
        self.assertEqual(r["market_state"], "open")
        self.assertTrue(r["suspect"])
        self.assertIn("24.1%", r["suspect_reason"])  # 170000/137000 - 1
        self.assertEqual(r["last_good"]["value"], 137000.0)  # carried, for the next run


class SuspectOverRuns(unittest.TestCase):
    """Three runs in a row of one index: normal, a big move, then either back or the same again."""
    inst = {"id": "dax", "name": "DAX", "group": "UK and Europe equities", "market": "frankfurt",
            "source": "yahoo", "symbol": "^GDAXI", "chart": "https://finance.yahoo.com/quote/%5EGDAXI/"}
    frankfurt = {"tz": "Europe/Berlin", "open": "09:00", "close": "17:30"}

    def run_once(self, value, time, previous, hist):
        res = {"id": "dax", "name": "DAX", "group": "UK and Europe equities",
               "value": value, "time": time, "source": "yahoo:^GDAXI"}
        now = datetime.fromisoformat(time)
        latest = run.build([self.inst], {"frankfurt": self.frankfurt}, [res], hist, previous, now)
        return latest, latest["instruments"]

    def setUp(self):
        self.hist = {"dax": [("2026-11-19", 24000.0)]}
        self.sources = {("dax", "2026-11-19"): "yahoo:^GDAXI"}
        _, self.run1 = self.run_once(24100.0, "2026-11-20T14:00:00+00:00", {}, self.hist)
        # Run 2: 30% higher. Over the 20% limit, so suspect, and not saved.
        latest, self.run2 = self.run_once(31330.0, "2026-11-20T14:05:00+00:00", self.run1, self.hist)
        self.assertTrue(self.run2["dax"]["suspect"])
        run.save_closes(latest, self.hist, self.sources)
        self.assertEqual(self.hist["dax"], [("2026-11-19", 24000.0)])

    def test_glitch_that_reverts(self):
        # Run 3 is back near 24,100: compared with the last good value (24,100), not with 31,330.
        _, run3 = self.run_once(24120.0, "2026-11-20T14:10:00+00:00", self.run2, self.hist)
        self.assertFalse(run3["dax"]["suspect"])
        self.assertNotIn("confirmed_jump", run3["dax"])

    def test_genuine_jump_that_persists(self):
        # Run 3 is still about 30% up, 0.2% from run 2 (within the 1% tolerance): accepted as real.
        latest, run3 = self.run_once(31400.0, "2026-11-20T14:10:00+00:00", self.run2, self.hist)
        self.assertFalse(run3["dax"]["suspect"])
        self.assertIn("31330.0", run3["dax"]["confirmed_jump"])
        run.save_closes(latest, self.hist, self.sources)  # an end-of-day run now keeps it
        self.assertEqual(self.hist["dax"][-1], ("2026-11-20", 31400.0))
        # Run 4: compared with run 3, a normal move.
        _, run4 = self.run_once(31450.0, "2026-11-20T14:15:00+00:00", run3, self.hist)
        self.assertFalse(run4["dax"]["suspect"])

    def test_jump_confirmed_next_day_saves_the_earlier_close(self):
        # The suspect run was the last one of 2026-11-20; the next morning agrees with it.
        latest, run3 = self.run_once(31300.0, "2026-11-21T09:00:00+00:00", self.run2, self.hist)
        self.assertFalse(run3["dax"]["suspect"])
        run.save_closes(latest, self.hist, self.sources, today=False)  # even a run without --close
        self.assertEqual(self.hist["dax"], [("2026-11-19", 24000.0), ("2026-11-20", 31330.0)])
        self.assertEqual(self.sources["dax", "2026-11-20"], "yahoo:^GDAXI")

    def test_two_different_wrong_values_are_not_a_confirmation(self):
        # Run 3 is 40% up, far from run 2's 30%: still suspect, still compared with 24,100.
        _, run3 = self.run_once(33740.0, "2026-11-20T14:10:00+00:00", self.run2, self.hist)
        self.assertTrue(run3["dax"]["suspect"])
        self.assertEqual(run3["dax"]["last_good"]["value"], 24100.0)


if __name__ == "__main__":
    unittest.main()


class OptionsRefresh(unittest.TestCase):
    NOW = datetime(2026, 11, 20, 16, 0, tzinfo=timezone.utc)  # a Friday, 11:00 in New York

    def block(self, fetched, state="open", expiry="2026-12-18"):
        return {"fetched_at": fetched, "market_state": state, "expiry": expiry}

    def due(self, prev, open_now=True, watchlist=("SPY",)):
        return run.options_due(prev, watchlist, open_now, self.NOW)

    def test_first_run_and_new_symbol_fetch(self):
        self.assertTrue(self.due(None))
        self.assertTrue(self.due({"SPY": self.block("2026-11-20T15:55:00+00:00")}, watchlist=("SPY", "QQQ")))

    def test_every_30_minutes_while_open(self):
        self.assertFalse(self.due({"SPY": self.block("2026-11-20T15:31:00+00:00")}))  # 29 minutes old
        self.assertTrue(self.due({"SPY": self.block("2026-11-20T15:30:00+00:00")}))   # 30 minutes old

    def test_closed_market_keeps_the_last_open_block(self):
        friday = {"SPY": self.block("2026-11-20T20:55:00+00:00")}
        self.assertFalse(run.options_due(friday, ["SPY"], False, datetime(2026, 11, 22, 22, 0, tzinfo=timezone.utc)))

    def test_closed_market_refetches_a_block_not_taken_while_open(self):
        self.assertTrue(self.due({"SPY": self.block("2026-11-20T13:00:00+00:00", "pre-market")}, open_now=False))
        # a fetch that failed while open is not worth keeping all weekend
        self.assertTrue(self.due({"SPY": self.block("2026-11-20T15:00:00+00:00", expiry=None)}, open_now=False))
