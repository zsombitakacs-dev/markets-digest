"""Offline tests for the fetch parsers and the fallback logic.

The samples are trimmed copies of what each source really returned on 2026-11-20.
Run: python -m unittest
"""
import unittest
from unittest import mock

from pipeline import fetch


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

    def test_stoxx_last_line(self):
        text = "Date;Symbol;Indexvalue\n18.11.2026;V2TX;22.1821\n19.11.2026;V2TX;22.5282\n"
        self.assertEqual(fetch.parse_stoxx(text), (22.5282, "2026-11-19"))

    def test_bse_embedded_json(self):
        page = 'x,"BuxIndexPanelDataSource":{"index":137411.49,"change":-5654.17,"tradingDay":true},y'
        self.assertEqual(fetch.parse_bse(page)[0], 137411.49)
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

    def test_unavailable_keeps_its_note(self):
        [r] = fetch.fetch_all([{"id": "x", "name": "X", "group": "G", "available": False, "note": "no free source"}])
        self.assertEqual(r["missing_reason"], "no free source")


if __name__ == "__main__":
    unittest.main()
