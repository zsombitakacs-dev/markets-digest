"""The email's number tables: formatting, unusual moves and the weekly change. Offline."""
import math
import unittest
from datetime import datetime, timezone

from pipeline import email_tables as et

NOW = datetime(2026, 11, 23, 14, 35, tzinfo=timezone.utc)  # Monday, 14:35 UK (GMT in November)


def row(**kw):
    base = {"id": "x", "name": "Test", "group": "FX", "kind": "price", "value": 100.0, "time": "2026-11-23T14:30:00+00:00",
            "source": "yahoo:X", "market_state": "open", "suspect": False, "change": 0.5, "change_unit": "%",
            "vol_20d": 15.87, "above_sma50": True, "crossed_sma50": None, "above_sma200": True, "crossed_sma200": None}
    return {**base, **kw}


class Formatting(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(et.level(1.09745, "price"), "1.0975")      # FX: 4 dp
        self.assertEqual(et.level(372.79, "price"), "372.79")
        self.assertEqual(et.level(137648.73, "price"), "137,649")   # 10,000 and up: 0 dp
        self.assertEqual(et.level(4.912, "rate"), "4.91%")

    def test_moves_carry_an_arrow_not_only_a_colour(self):
        self.assertEqual(et.move(-3.59, "%"), ("▼ 3.59%", "dn"))
        self.assertEqual(et.move(1.4, "bp"), ("▲ 1.4 bp", "up"))
        self.assertEqual(et.move(0.0, "bp"), ("0.0 bp", None))
        self.assertEqual(et.move(0.03, "bp"), ("0.0 bp", None))   # rounds to zero: no arrow
        self.assertEqual(et.move(-0.004, "%"), ("0.00%", None))
        self.assertEqual(et.move(None, "%"), ("–", None))

    def test_state_label(self):
        self.assertEqual(et.state(row(), NOW), "● Open · 14:30")                     # today: time only
        self.assertEqual(et.state(row(market_state="closed", time="2026-11-20T21:00:00+00:00"), NOW), "○ Closed · 20 Nov")
        self.assertEqual(et.state(row(market_state="closed", time="2026-11-20"), NOW), "○ Closed · 20 Nov")  # a daily figure


class UnusualMoves(unittest.TestCase):
    def test_sigmas(self):
        # 20-day vol of √252 % a year is exactly 1% a day, so a 2.5% move is 2.5 usual days.
        self.assertAlmostEqual(et.sigmas(row(change=-2.5, vol_20d=math.sqrt(252))), 2.5)
        # Yields: vol and change are both in bp. 31.75 bp a year ≈ 2 bp a day, so 6 bp ≈ 3×.
        self.assertAlmostEqual(et.sigmas(row(kind="rate", change=6.0, vol_20d=31.749)), 3.0, places=2)
        self.assertIsNone(et.sigmas(row(change=None)))
        self.assertIsNone(et.sigmas(row(vol_20d=None)))

    def test_notable_reasons(self):
        self.assertEqual(et.why_notable(row(change=1.9, vol_20d=math.sqrt(252))), [])  # under 2×
        self.assertEqual(et.why_notable(row(change=2.0, vol_20d=math.sqrt(252))), ["2.0× its usual daily move"])
        self.assertEqual(et.why_notable(row(crossed_sma200="below")), ["crossed below its 200-day average"])

    def test_only_non_headline_usable_rows_biggest_first(self):
        v = math.sqrt(252)
        latest = {"instruments": {
            "a": row(id="a", change=3.0, vol_20d=v), "b": row(id="b", change=5.0, vol_20d=v),
            "c": row(id="c", change=9.0, vol_20d=v),                 # headline row: already in Table 1
            "d": row(id="d", change=9.0, vol_20d=v, suspect=True),   # suspect: never shown as a move
            "e": row(id="e", value=None, change=None)}}
        instruments = [{"id": "a"}, {"id": "b"}, {"id": "c", "email": True}, {"id": "d"}, {"id": "e"}]
        self.assertEqual([r["id"] for r, _ in et.notable(latest, instruments)], ["b", "a"])


class Week(unittest.TestCase):
    def test_week_change_against_the_close_7_days_earlier(self):
        rows = [("2026-11-12", 98.0), ("2026-11-13", 100.0), ("2026-11-16", 104.0), ("2026-11-20", 110.0)]
        self.assertEqual(et.week_change(rows), (110.0, "2026-11-20", 100.0))  # +10% on the week
        self.assertIsNone(et.week_change(rows[2:]))  # no close a week before
        self.assertIsNone(et.week_change([]))


class Html(unittest.TestCase):
    def test_range_bar_fill(self):
        # 75 is three quarters of the way from 0 to 100: 45 of 60 px filled.
        self.assertIn('width="45"', et.range_bar(row(value=75.0, low_52w=0.0, high_52w=100.0)))
        self.assertIn('width="2"', et.range_bar(row(value=0.0, low_52w=0.0, high_52w=100.0)))  # never zero-width
        self.assertIn("–", et.range_bar(row(low_52w=None, high_52w=None)))

    def test_outside_text_is_escaped(self):
        html, _ = et.render({"run_at": NOW.isoformat(), "instruments": {"x": row(name="<b>X</b>")}, "options": {}},
                            [{"id": "x", "group": "FX", "email": True}], {}, NOW)
        self.assertIn("&lt;b&gt;X&lt;/b&gt;", html)
        self.assertNotIn("<b>X</b>", html)

    def test_suspect_value_is_unavailable_not_shown(self):
        html, text = et.render({"run_at": NOW.isoformat(), "instruments": {"x": row(value=123.45, suspect=True)}, "options": {}},
                               [{"id": "x", "group": "FX", "email": True}], {}, NOW)
        self.assertIn("Unavailable", html)
        self.assertNotIn("123.45", html)
        self.assertIn("Test: unavailable (flagged as suspect)", text)


if __name__ == "__main__":
    unittest.main()
