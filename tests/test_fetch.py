"""Offline tests for the fetch parsers and the fallback logic.

The samples are trimmed copies of what each source really returned on 2026-11-20, inline
or saved in tests/samples/ (files the parsers read as they would a download). bubor.xls holds
real rows rewritten with xlwt, used once outside the project: nothing here can write old .xls.
Run: python -m unittest
"""
import unittest
from pathlib import Path
from unittest import mock

from pipeline import fetch

SAMPLES = Path(__file__).parent / "samples"


def sample(name):
    return (SAMPLES / name).read_bytes()


class Parsers(unittest.TestCase):
    def test_mnb_xml_inside_xml(self):
        reply = (b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                 b'<GetCurrentExchangeRatesResponse xmlns="http://www.mnb.hu/webservices/">'
                 b'<GetCurrentExchangeRatesResult>&lt;MNBCurrentExchangeRates&gt;&lt;Day date="2026-11-20"&gt;'
                 b'&lt;Rate unit="1" curr="EUR"&gt;373,55000&lt;/Rate&gt;'
                 b'&lt;Rate unit="100" curr="JPY"&gt;214,10000&lt;/Rate&gt;'
                 b'&lt;/Day&gt;&lt;/MNBCurrentExchangeRates&gt;</GetCurrentExchangeRatesResult>'
                 b'</GetCurrentExchangeRatesResponse></s:Body></s:Envelope>')
        self.assertEqual(fetch.parse_mnb(reply, "EUR"), (373.55, "2026-11-20"))
        # JPY is quoted per 100 yen: 214.10 / 100 = 2.141 HUF per yen
        self.assertAlmostEqual(fetch.parse_mnb(reply, "JPY")[0], 2.141)
        with self.assertRaises(ValueError):
            fetch.parse_mnb(reply, "PLN")

    def test_stoxx_every_line(self):
        text = "Date;Symbol;Indexvalue\n18.11.2026;V2TX;22.1821\n19.11.2026;V2TX;22.5282\n"
        self.assertEqual(fetch.parse_stoxx(text), [("2026-11-18", 22.1821), ("2026-11-19", 22.5282)])
        self.assertEqual(fetch.last(fetch.parse_stoxx(text)), (22.5282, "2026-11-19"))

    def test_fred_skips_missing_days(self):
        text = "observation_date,DGS2\n2026-11-17,4.81\n2026-11-18,.\n2026-11-19,4.80\n"
        self.assertEqual(fetch.parse_fred(text), [("2026-11-17", 4.81), ("2026-11-19", 4.80)])

    def test_bundesbank_skips_header_lines(self):
        text = ('"",BBSSY.D.REN.EUR.A630.000000WT1010.A,FLAGS\n"",Daily yield of the current 10 year federal bond,\n'
                "2026-11-18,3.30,\n2026-11-19,.,No value available\n2026-11-20,3.32,\n")
        self.assertEqual(fetch.parse_bundesbank(text), [("2026-11-18", 3.30), ("2026-11-20", 3.32)])


class Readers(unittest.TestCase):
    """The Excel and JSON readers, on saved sample files."""

    def test_boe_excel_spot_curve(self):
        rows = fetch.parse_boe(sample("boe_spot_curve.xlsx"), "2")
        # 4 days with data; the "#VALUE!" row and a day with blank cells are skipped
        self.assertEqual([d for d, _ in rows], ["2026-11-02", "2026-11-17", "2026-11-18", "2026-11-19"])
        self.assertAlmostEqual(rows[-1][1], 4.734728709320078)
        self.assertAlmostEqual(fetch.parse_boe(sample("boe_spot_curve.xlsx"), "10")[-1][1], 5.303469252170214)
        with self.assertRaises(ValueError):  # the sample stops at 10 years
            fetch.parse_boe(sample("boe_spot_curve.xlsx"), "25")

    def test_bubor_old_excel(self):
        rows = fetch.parse_bubor(sample("bubor.xls"), "3months")
        # Only the 2026 sheet: the 2022 sheet's column names in row 1 are in Hungarian.
        # Excel day 46027 is 2026-01-05 (days counted from 1899-12-30).
        self.assertEqual(rows, [("2026-01-05", 6.47), ("2026-01-06", 6.46),
                                ("2026-11-19", 5.5), ("2026-11-20", 5.5)])
        with self.assertRaises(ValueError):  # the "4months" column only holds "-"
            fetch.parse_bubor(sample("bubor.xls"), "4months")

    def test_akk_json_history(self):
        self.assertEqual(fetch.parse_akk(sample("akk_benchmark.json"), "10Y"),
                         [("2026-11-18", 5.49), ("2026-11-19", 5.51), ("2026-11-20", 5.5)])
        self.assertEqual(fetch.parse_akk(sample("akk_benchmark.json"), "3Y")[-1], ("2026-11-20", 5.48))
        with self.assertRaises(ValueError):
            fetch.parse_akk(sample("akk_benchmark.json"), "2Y")

    def test_akk_json_last(self):
        self.assertEqual(fetch.last(fetch.parse_akk(sample("akk_benchmark_last.json"), "10Y")), (5.5, "2026-11-20"))

    def test_bse_embedded_json(self):
        self.assertEqual(fetch.parse_bse(sample("bse_home.html").decode())[0], 137648.73)
        with self.assertRaises(ValueError):
            fetch.parse_bse("<html>no data</html>")

    def test_pse_value_and_prague_time(self):
        page = ('<div class="detail-chart-info-item-content-title">Date &amp; Time</div> '
                '<div class="detail-chart-info-item-content-value">20.11.2026 | 16:35:00</div> '
                '<div class="detail-chart-info-item-content-title">Current value</div> '
                '<div class="detail-chart-info-item-content-value"> <td>2,568.10</td> </div>')
        # Prague is UTC+1 in November, so 16:35 local is 15:35 UTC.
        self.assertEqual(fetch.parse_pse(page), (2568.10, "2026-11-20T15:35:00+00:00"))


class Fallback(unittest.TestCase):
    inst = {"id": "eurhuf", "name": "EUR/HUF", "group": "FX", "source": "yahoo",
            "symbol": "EURHUF=X", "fallback_source": "mnb", "fallback_symbol": "EUR"}

    def test_uses_fallback_and_says_why(self):
        with mock.patch.object(fetch, "fetch_yahoo", return_value={}), \
             mock.patch.dict(fetch.SOURCES, {"mnb": lambda s: (373.55, "2026-11-20")}):
            [r] = fetch.fetch_all([self.inst])
        self.assertEqual((r["value"], r["source"]), (373.55, "mnb:EUR"))
        self.assertIn("Yahoo returned no data", r["fallback_because"])

    def test_both_fail_is_missing_not_guessed(self):
        def broken(symbol):
            raise ConnectionError("down")
        with mock.patch.object(fetch, "fetch_yahoo", return_value={}), \
             mock.patch.dict(fetch.SOURCES, {"mnb": broken}):
            [r] = fetch.fetch_all([self.inst])
        self.assertIsNone(r["value"])
        self.assertIn("mnb: ConnectionError: down", r["missing_reason"])

    def test_nan_is_rejected(self):
        with mock.patch.object(fetch, "fetch_yahoo", return_value={"EURHUF=X": (float("nan"), "t")}), \
             mock.patch.dict(fetch.SOURCES, {"mnb": lambda s: (373.55, "2026-11-20")}):
            [r] = fetch.fetch_all([self.inst])
        self.assertEqual(r["source"], "mnb:EUR")

    def test_spread_needs_both_legs_from_the_same_day(self):
        legs = [{"id": "hu10y", "name": "10y", "group": "G", "source": "akk", "symbol": "10Y"},
                {"id": "hu3y", "name": "3y", "group": "G", "source": "akk", "symbol": "3Y"},
                {"id": "hu3s10s", "name": "3s10s", "group": "G", "source": "spread", "symbol": "hu10y-hu3y"}]
        values = {"10Y": (5.50, "2026-11-20"), "3Y": (5.48, "2026-11-20")}
        with mock.patch.object(fetch, "fetch_yahoo", return_value={}), \
             mock.patch.dict(fetch.SOURCES, {"akk": values.get}):
            r = fetch.fetch_all(legs)[2]
        self.assertAlmostEqual(r["value"], 0.02)  # 5.50 - 5.48
        self.assertEqual(r["source"], "spread:hu10y-hu3y")
        values["3Y"] = (5.47, "2026-11-19")
        with mock.patch.object(fetch, "fetch_yahoo", return_value={}), \
             mock.patch.dict(fetch.SOURCES, {"akk": values.get}):
            r = fetch.fetch_all(legs)[2]
        self.assertIsNone(r["value"])
        self.assertIn("from 2026-11-19", r["missing_reason"])

    def test_unavailable_keeps_its_note(self):
        [r] = fetch.fetch_all([{"id": "x", "name": "X", "group": "G", "available": False, "note": "no free source"}])
        self.assertEqual(r["missing_reason"], "no free source")


if __name__ == "__main__":
    unittest.main()
