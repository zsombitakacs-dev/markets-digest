"""The chart data behind the dashboard: moving-average lines and today's point. Offline."""
import unittest

from pipeline import site_data


class ChartSeries(unittest.TestCase):
    def test_averages_use_days_before_the_window(self):
        # 250 days of closes 1, 2, ..., 250. On the last day, the 50-day average is the mean of
        # 201..250 = 225.5 and the 200-day average the mean of 51..250 = 150.5.
        rows = [(f"2026-{1 + k // 28:02d}-{1 + k % 28:02d}", float(k + 1)) for k in range(250)]
        s = site_data.chart_series(rows, days=30)
        self.assertEqual(s["d"][-1], rows[-1][0])
        self.assertEqual(s["c"][-1], 250.0)
        self.assertEqual(s["m50"][-1], 225.5)
        self.assertEqual(s["m200"][-1], 150.5)
        self.assertTrue(s["d"][0] >= "2026-08-01")  # only the last 30 days are drawn

    def test_too_few_closes_give_no_line(self):
        s = site_data.chart_series([("2026-11-19", 10.0), ("2026-11-20", 12.0)])
        self.assertEqual(s["m50"], [None, None])
        self.assertIsNone(site_data.chart_series([]))

    def test_latest_value_replaces_todays_row_unless_suspect(self):
        rows = [("2026-11-19", 10.0), ("2026-11-20", 11.0)]
        r = {"value": 12.0, "time": "2026-11-20T14:35:00+00:00", "suspect": False}
        self.assertEqual(site_data.with_latest(rows, r), [("2026-11-19", 10.0), ("2026-11-20", 12.0)])
        self.assertEqual(site_data.with_latest(rows, {**r, "suspect": True}), rows)
        self.assertEqual(site_data.with_latest(rows, {**r, "value": None}), rows)


if __name__ == "__main__":
    unittest.main()
