"""Indicator maths, checked against numbers worked out by hand. Run: python -m unittest"""
import math
import unittest
from datetime import date, datetime, timedelta, timezone

from pipeline import indicators as ind

NEW_YORK = {"tz": "America/New_York", "pre": "04:00", "open": "09:30", "close": "16:00", "post": "20:00"}
CME = {"tz": "America/Chicago", "open": "17:00", "close": "16:00"}
FX = {"tz": "America/New_York", "open": "17:00", "close": "17:00"}
LONDON = {"tz": "Europe/London", "open": "08:00", "close": "16:30"}
BUDAPEST = {"tz": "Europe/Budapest", "open": "09:00", "close": "17:00"}


def utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class Maths(unittest.TestCase):
    def test_change_in_percent_and_basis_points(self):
        self.assertAlmostEqual(ind.change(102, 100, "price"), 2.0)  # 102/100 - 1 = 2%
        self.assertAlmostEqual(ind.change(4.95, 4.80, "rate"), 15.0)  # 0.15 points = 15 bp
        self.assertAlmostEqual(ind.change(-0.10, 0.05, "rate"), -15.0)  # a spread crossing zero

    def test_moving_average(self):
        self.assertEqual(ind.sma([1, 2, 3, 4, 5], 3), 4)  # (3 + 4 + 5) / 3
        self.assertIsNone(ind.sma([1, 2, 3, 4, 5], 6))  # not enough days: no guess

    def test_52_week_range_uses_365_days(self):
        rows = [("2025-11-19", 999.0),  # 366 days before the last row: left out
                ("2025-11-20", 50.0),   # exactly 365 days: counts
                ("2026-06-01", 120.0), ("2026-11-20", 100.0)]
        self.assertEqual(ind.high_low_52w(rows), (120.0, 50.0))

    def test_realised_volatility(self):
        # 21 closes that go up 1, down 1, up 1...: 20 moves of +1 and -1, mean 0.
        # Sample standard deviation = sqrt(20 * 1^2 / 19) = 1.02598; times sqrt(252) = 16.287.
        rates = [1.00 if i % 2 == 0 else 1.01 for i in range(21)]  # moves of 1 bp
        self.assertAlmostEqual(ind.realised_vol(rates, "rate"), 16.287, places=3)
        prices = [100 if i % 2 == 0 else 100 * math.exp(0.01) for i in range(21)]  # log moves of 1%
        self.assertAlmostEqual(ind.realised_vol(prices, "price"), 16.287, places=3)
        self.assertIsNone(ind.realised_vol(prices[:20], "price"))  # 20 closes = only 19 moves

    def test_crossing_a_moving_average(self):
        self.assertEqual(ind.crossed(False, True), "above")
        self.assertEqual(ind.crossed(True, False), "below")
        self.assertIsNone(ind.crossed(True, True))
        self.assertIsNone(ind.crossed(None, True))  # first run: nothing to compare with


class Suspect(unittest.TestCase):
    def test_flags(self):
        self.assertEqual(ind.suspect(0, 100, "price", "US equities"), "zero or negative price")
        self.assertIsNone(ind.suspect(115, 100, "price", "US equities"))  # 15% < 20% for an index
        self.assertIn("12.6%", ind.suspect(420, 373, "price", "FX"))  # 420/373 - 1 = 12.6% > 10%
        self.assertIsNone(ind.suspect(54, 30, "price", "Volatility"))  # VIX +80% does happen
        self.assertIn("110.0bp", ind.suspect(5.90, 4.80, "rate", "Government bonds"))  # > 100 bp
        self.assertIsNone(ind.suspect(-0.30, 0.28, "rate", "Government bonds"))  # a negative spread is fine
        self.assertIsNone(ind.suspect(100, None, "price", "FX"))  # nothing to compare with


    def test_two_runs_agree(self):
        self.assertTrue(ind.agrees(31400, 31330, "price"))  # 0.22% apart, within 1%
        self.assertFalse(ind.agrees(33740, 31330, "price"))  # 7.7% apart
        self.assertTrue(ind.agrees(5.94, 5.90, "rate"))  # 4 bp apart, within 5 bp
        self.assertFalse(ind.agrees(6.00, 5.90, "rate"))  # 10 bp


class MarketHours(unittest.TestCase):
    def test_new_york_states(self):
        # Friday 20 Nov 2026; New York is UTC-5 in November.
        self.assertEqual(ind.market_state(NEW_YORK, utc(2026, 11, 20, 14, 45)), "open")  # 09:45
        self.assertEqual(ind.market_state(NEW_YORK, utc(2026, 11, 20, 13, 0)), "pre-market")  # 08:00
        self.assertEqual(ind.market_state(NEW_YORK, utc(2026, 11, 20, 22, 0)), "after-hours")  # 17:00
        self.assertEqual(ind.market_state(NEW_YORK, utc(2026, 11, 21, 15, 0)), "closed")  # Saturday

    def test_overnight_futures_session(self):
        # Chicago is UTC-6 in November. CME opens Sunday 17:00, breaks 16:00-17:00 each day.
        self.assertEqual(ind.market_state(CME, utc(2026, 11, 22, 23, 30)), "open")  # Sun 17:30
        self.assertEqual(ind.market_state(CME, utc(2026, 11, 25, 21, 30)), "open")  # Wed 15:30
        self.assertEqual(ind.market_state(CME, utc(2026, 11, 25, 22, 30)), "closed")  # Wed 16:30, break
        self.assertEqual(ind.market_state(CME, utc(2026, 11, 20, 23, 30)), "closed")  # Fri 17:30
        self.assertEqual(ind.market_state(FX, utc(2026, 11, 20, 21, 59)), "open")  # Fri 16:59 New York
        self.assertEqual(ind.market_state(FX, utc(2026, 11, 20, 22, 1)), "closed")  # Fri 17:01

    def test_fx_open_equals_close(self):
        # FX opens and closes at 17:00 New York: open from Sunday 17:00 to Friday 17:00, without a break.
        self.assertEqual(ind.market_state(FX, utc(2026, 11, 22, 21, 59)), "closed")  # Sun 16:59
        self.assertEqual(ind.market_state(FX, utc(2026, 11, 22, 22, 1)), "open")  # Sun 17:01
        self.assertEqual(ind.market_state(FX, utc(2026, 11, 24, 22, 0)), "open")  # Tue 17:00, no daily break
        self.assertEqual(ind.market_state(FX, utc(2026, 11, 27, 21, 59)), "open")  # Fri 16:59
        self.assertEqual(ind.market_state(FX, utc(2026, 11, 27, 22, 0)), "closed")  # Fri 17:00
        self.assertEqual(ind.market_state(FX, utc(2026, 11, 28, 15, 0)), "closed")  # Saturday

    def test_holiday_shows_as_stale_price(self):
        # US Thanksgiving, Thu 26 Nov 2026, 10:00 New York: the timetable says open, but the last
        # S&P 500 price is Wednesday's close, 17 hours old.
        now = utc(2026, 11, 26, 15, 0)
        self.assertEqual(ind.market_state(NEW_YORK, now), "open")
        self.assertEqual(ind.holiday_check("open", "2026-11-25T21:00:00+00:00", now), "closed (holiday?)")
        self.assertEqual(ind.holiday_check("open", "2026-11-26T14:29:00+00:00", now), "closed (holiday?)")  # 31 min
        self.assertEqual(ind.holiday_check("open", "2026-11-26T14:30:00+00:00", now), "open")  # exactly 30 min
        self.assertEqual(ind.holiday_check("open", "2026-11-26T14:45:00+00:00", now), "open")  # a normal day
        self.assertEqual(ind.holiday_check("closed", "2026-11-25T21:00:00+00:00", now), "closed")
        self.assertEqual(ind.holiday_check("open", "2026-11-25", now), "open")  # a daily figure: date only
        self.assertEqual(ind.holiday_check("open", None, now), "open")  # value missing

    def test_summer_time_and_daily_figures(self):
        # 1 July: London is UTC+1, so 07:30 UTC is 08:30 local, after the open.
        self.assertEqual(ind.market_state(LONDON, utc(2026, 7, 1, 7, 30)), "open")
        self.assertEqual(ind.market_state(LONDON, utc(2026, 11, 20, 7, 30)), "closed")  # 07:30 in winter
        self.assertEqual(ind.market_state(None, utc(2026, 11, 20, 14, 45)), "closed")  # a daily figure
        self.assertEqual(ind.market_state({"always_open": True}, utc(2026, 11, 21, 3, 0)), "open")

    def test_last_close(self):
        # Budapest closes 17:00 local = 16:00 UTC in winter.
        friday_close = utc(2026, 11, 20, 16, 0)
        self.assertEqual(ind.last_close(BUDAPEST, utc(2026, 11, 21, 10, 0)), friday_close)  # Saturday
        self.assertEqual(ind.last_close(BUDAPEST, utc(2026, 11, 23, 7, 0)), friday_close)  # Monday, pre-open
        self.assertEqual(ind.last_close(BUDAPEST, utc(2026, 11, 20, 16, 30)), friday_close)


class Summary(unittest.TestCase):
    def test_full_history(self):
        # 210 closes with values 1, 2, ..., 210, one every 2 days (so 418 days in all).
        start = date(2025, 9, 28)
        rows = [((start + timedelta(days=2 * i)).isoformat(), float(i + 1)) for i in range(210)]
        s = ind.summarise(rows, "price", previous={"above_sma50": False})
        self.assertAlmostEqual(s["change"], 0.48)  # 210/209 - 1 = 0.478%
        self.assertEqual(s["sma50"], 185.5)  # mean of 161..210
        self.assertAlmostEqual(s["dist_sma50"], 13.21)  # 210/185.5 - 1
        self.assertEqual(s["sma200"], 110.5)  # mean of 11..210
        self.assertAlmostEqual(s["dist_sma200"], 90.05)  # 210/110.5 - 1
        self.assertEqual(s["crossed_sma50"], "above")  # was below last run, above now
        self.assertIsNone(s["crossed_sma200"])  # no previous flag to compare with
        # The last 365 days hold the closes from day 54 on (i = 27): values 28..210.
        self.assertEqual((s["high_52w"], s["low_52w"]), (210.0, 28.0))
        self.assertAlmostEqual(s["dist_low_52w"], 650.0)  # 210/28 - 1
        self.assertNotIn("indicator_gaps", s)

    def test_short_history_says_what_is_missing(self):
        s = ind.summarise([("2026-11-19", 4.80), ("2026-11-20", 4.95)], "rate")
        self.assertEqual((s["change"], s["change_unit"]), (15.0, "bp"))
        self.assertIsNone(s["sma200"])
        self.assertIsNone(s["high_52w"])  # 2 days of data is not a 52-week range
        self.assertIn("sma200: needs 200 daily closes, has 2", s["indicator_gaps"])

    def test_first_ever_value(self):
        s = ind.summarise([("2026-11-20", 2568.1)], "price")
        self.assertIsNone(s["change"])
        self.assertIn("change: no previous close yet", s["indicator_gaps"])


if __name__ == "__main__":
    unittest.main()
