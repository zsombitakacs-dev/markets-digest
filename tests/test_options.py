"""Options maths, with numbers worked out by hand. Offline."""
import unittest
from datetime import date, datetime, timezone
from unittest import mock

import pandas as pd

from pipeline import options

NAN = float("nan")


def chain(strikes, iv, oi, volume, bid=1.0):
    return pd.DataFrame({"strike": strikes, "impliedVolatility": iv, "openInterest": oi,
                         "volume": volume, "bid": bid, "ask": bid + 0.2})


class Expiries(unittest.TestCase):
    def test_third_friday(self):
        self.assertEqual(options.third_friday(2026, 11), date(2026, 11, 20))  # 1 Nov is a Sunday
        self.assertEqual(options.third_friday(2027, 1), date(2027, 1, 15))  # 1 Jan is a Friday

    def test_monthly_skips_weeklies_and_takes_thursday_before_a_holiday(self):
        listed = {"2026-11-20", "2026-11-27", "2026-12-11", "2026-12-18", "2026-12-31",
                  "2027-06-17", "2027-06-30"}  # 18 June 2027 is the Juneteenth holiday
        self.assertEqual(options.monthly_expiries(listed), ["2026-11-20", "2026-12-18", "2027-06-17"])


class Chain(unittest.TestCase):
    calls = chain([700.0, 703.0, 705.0], [0.30, 0.27, 0.26], [100, 40, 5000], [10, NAN, 30])
    puts = chain([700.0, 703.0, 705.0], [0.25, 0.23, 0.22], [9000, 20, 8000], [20, 60, 0])

    def test_atm_iv_is_the_mean_of_call_and_put_at_the_nearest_strike(self):
        # 702.8 is nearest 703: (27% + 23%) / 2 = 25%
        self.assertEqual(options.atm_iv(self.calls, self.puts, 702.8), (703.0, 25.0))

    def test_atm_iv_needs_live_quotes(self):
        stale = chain([703.0], [0.00001], [1], [0], bid=0.0)  # how Yahoo looks after hours
        self.assertEqual(options.atm_iv(stale, self.puts, 702.8), (703.0, None))

    def test_put_call_ratios(self):
        # volume: puts 20+60+0 = 80, calls 10+0+30 = 40 (no volume counts as 0) -> 2.0
        self.assertEqual(options.put_call(self.calls, self.puts, "volume"), 2.0)
        # open interest: puts 17,020, calls 5,140 -> 3.31
        self.assertEqual(options.put_call(self.calls, self.puts, "openInterest"), 3.31)
        none = chain([703.0], [0.2], [0], [0])
        self.assertIsNone(options.put_call(none, self.puts, "volume"))

    def test_top_strikes_by_open_interest(self):
        self.assertEqual(options.top_strikes(self.puts, 2),
                         [{"strike": 700.0, "open_interest": 9000}, {"strike": 705.0, "open_interest": 8000}])


class FetchOne(unittest.TestCase):
    def test_expiry_day_is_skipped_for_the_next_monthly(self):
        calls = chain([700.0, 703.0], [0.27, 0.27], [10, 20], [1, 2])
        puts = chain([700.0, 703.0], [0.23, 0.23], [30, 40], [3, 4])
        calls["lastTradeDate"] = puts["lastTradeDate"] = pd.Timestamp("2026-11-20 16:27", tz="UTC")
        ticker = mock.Mock(options=("2026-11-20", "2026-11-27", "2026-12-18", "2027-01-15",
                                    "2027-02-19", "2027-03-19", "2027-03-31"))
        ticker.option_chain.return_value = mock.Mock(
            calls=calls, puts=puts,
            underlying={"regularMarketPrice": 702.8, "regularMarketTime": 1795192904})
        with mock.patch.object(options.yf, "Ticker", return_value=ticker):
            out = options.fetch_one("SPY", "2026-11-20")  # itself an expiry day
        ticker.option_chain.assert_called_once_with("2026-12-18")
        self.assertEqual((out["expiry"], out["days_to_expiry"]), ("2026-12-18", 28))
        self.assertEqual(out["upcoming_monthly"], ["2026-12-18", "2027-01-15", "2027-02-19"])
        self.assertEqual(out["upcoming_quarterly"], ["2026-12-18", "2027-03-19"])
        self.assertEqual(out["time"], "2026-11-20T16:27:00+00:00")
        self.assertEqual(out["atm_iv"], 25.0)


class FetchAll(unittest.TestCase):
    config = {"options": {"watchlist": ["SPY", "NOPE"], "market": "ny"},
              "market": {"ny": {"tz": "America/New_York", "open": "09:30", "close": "16:00"}}}

    def test_a_failed_symbol_is_recorded_not_fatal(self):
        def fake(symbol, today):
            if symbol == "NOPE":
                raise ValueError("no monthly expiry listed")
            return {"expiry": "2026-12-18", "today": today}
        # 03:00 UTC on the 21st is still the 20th in New York
        now = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)
        with mock.patch.object(options, "fetch_one", fake):
            out = options.fetch_all(self.config, now)
        self.assertEqual(out["SPY"], {"expiry": "2026-12-18", "today": "2026-11-20", "market_state": "closed",
                                      "fetched_at": "2026-11-21T03:00:00+00:00"})
        self.assertIsNone(out["NOPE"]["expiry"])
        self.assertEqual(out["NOPE"]["missing_reason"], "ValueError: no monthly expiry listed")


if __name__ == "__main__":
    unittest.main()
