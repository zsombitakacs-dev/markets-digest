import tempfile
import unittest
import unittest.mock
from datetime import date
from pathlib import Path

from docx import Document

from pipeline import export


class TestExport(unittest.TestCase):
    def test_last_month(self):
        self.assertEqual(export.last_month(date(2026, 12, 1)), "2026-11")
        self.assertEqual(export.last_month(date(2027, 1, 1)), "2026-12")  # across a year end

    def test_num(self):
        self.assertEqual(export.num("3.25"), 3.25)
        self.assertEqual(export.num("-0.1"), -0.1)
        self.assertEqual(export.num("in line"), "in line")
        self.assertEqual(export.num("2026-11-23"), "2026-11-23")  # dates stay text
        self.assertEqual(export.num(""), "")
        self.assertEqual(export.num("nan"), "nan")  # would be invalid JSON for the Sheets API
        self.assertEqual(export.num("1_000"), "1_000")

    def test_excel_formula_stays_text(self):
        from openpyxl import load_workbook
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "logs").mkdir()
            (Path(tmp) / "logs/data_surprises.csv").write_text('date,release\n2026-11-02,"=HYPERLINK(""https://x"")"\n')
            with unittest.mock.patch.object(export, "DATA_DIR", Path(tmp)):
                export.excel("2026-11", Path(tmp) / "out.xlsx")
            cell = load_workbook(Path(tmp) / "out.xlsx")["Data surprises"]["B2"]
            self.assertEqual((cell.value, cell.data_type), ('=HYPERLINK("https://x")', "s"))

    def test_csv_month(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "log.csv"
            p.write_text("date,release,actual\n2026-10-31,CPI,3.1\n2026-11-02,GDP,0.4\n")
            self.assertEqual(export.csv_month(p, "2026-11"), (["date", "release", "actual"], [["2026-11-02", "GDP", 0.4]]))
            self.assertEqual(export.csv_month(Path(tmp) / "missing.csv", "2026-11"), ([], []))

    def test_word(self):
        md = ("# Markets digest, 23 Nov\n\n## Top 5\n1. **Fed** holds, [Reuters](https://www.reuters.com/x)\n"
              "- a [bad link](javascript:alert(1))\n\n| Index | Level |\n|---|---:|\n| S&P 500 | 6,918.45 |\n")
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / "2026-11-23.md", Path(tmp) / "out.docx"
            src.write_text(md)
            export.word([src, src], out)
            doc = Document(out)
            heads = [p.text for p in doc.paragraphs if p.style.name.startswith("Heading")]
            self.assertEqual(heads, ["Markets digest, 23 Nov", "Top 5"] * 2)
            texts = [p.text for p in doc.paragraphs]
            self.assertIn("1. Fed holds, Reuters", texts)
            self.assertIn("a bad link", texts)
            links = [r.target_ref for r in doc.part.rels.values() if r.is_external]
            self.assertEqual(set(links), {"https://www.reuters.com/x"})  # the javascript: link is plain text
            self.assertEqual(len(doc.tables), 2)
            self.assertEqual([c.text for c in doc.tables[0].rows[1].cells], ["S&P 500", "6,918.45"])

    def test_combined_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            h = Path(tmp) / "d.html"
            h.write_text("<html><head><style>p{color:red}</style></head><body><p>Hi</p></body></html>")
            page = export.combined_html([h, h])
            self.assertEqual(page.count("<style>p{color:red}</style>"), 1)  # shared styles once
            self.assertEqual(page.count('<section style="break-before:page"><p>Hi</p></section>'), 2)
            self.assertIn("default-src 'none'", page)


if __name__ == "__main__":
    unittest.main()
