import tempfile
import unittest
from pathlib import Path

from anonymizer.core.io_tables import TableFormatError, read_table, write_table

HEADERS = ["№", "ФИО", "Адрес", "Продажи"]
ROWS = [
    ["1", "Иван Царевич", "Тридевятое царство", "15"],
    ["2", "Василиса Премудрая", "Избушка на курьих ножках", "7,5"],
]


class XlsxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_roundtrip(self):
        p = self.dir / "t.xlsx"
        write_table(p, HEADERS, ROWS)
        headers, rows = read_table(p)
        self.assertEqual(headers, HEADERS)
        self.assertEqual(rows, ROWS)


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_roundtrip_semicolon_bom(self):
        p = self.dir / "t.csv"
        write_table(p, HEADERS, ROWS)
        raw = p.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        headers, rows = read_table(p)
        self.assertEqual(headers, HEADERS)
        self.assertEqual(rows, ROWS)

    def test_read_cp1251(self):
        p = self.dir / "old.csv"
        text = "ФИО;Телефон\nИван Царевич;+7 (999) 001-11-22\n"
        p.write_bytes(text.encode("cp1251"))
        headers, rows = read_table(p)
        self.assertEqual(headers, ["ФИО", "Телефон"])
        self.assertEqual(rows[0][1], "+7 (999) 001-11-22")

    def test_ragged_rows_padded(self):
        p = self.dir / "ragged.csv"
        p.write_text("A;B;C\n1;2\n3\n", encoding="utf-8")
        _, rows = read_table(p)
        self.assertEqual(rows, [["1", "2", ""], ["3", "", ""]])

    def test_unsupported_format(self):
        with self.assertRaises(TableFormatError):
            read_table(self.dir / "t.docx")


if __name__ == "__main__":
    unittest.main()
