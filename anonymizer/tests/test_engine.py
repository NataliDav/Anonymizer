import unittest

from anonymizer.core.engine import (
    UNKNOWN_MARK,
    AnonymizerEngine,
    ColumnNotFoundError,
    default_prefix,
    fingerprint,
    normalize,
)

PASSWORD_SALT = b"0123456789abcdef"


class NormalizeTests(unittest.TestCase):
    def test_nbsp_and_case(self):
        self.assertEqual(normalize("+7\xa0(999)\xa0001‑11‑22"), "+7 (999) 001‑11‑22")

    def test_collapses_whitespace(self):
        self.assertEqual(normalize("  Иван   Царевич \n"), "иван царевич")


class PrefixTests(unittest.TestCase):
    def test_transliteration(self):
        self.assertEqual(default_prefix("ФИО", set()), "FIO_")
        self.assertEqual(default_prefix("Адрес", set()), "ADR_")
        self.assertEqual(default_prefix("Телефон", set()), "TEL_")

    def test_uniqueness(self):
        used = set()
        p1 = default_prefix("ФИО", used)
        used.add(p1)
        p2 = default_prefix("филиал", used)
        self.assertNotEqual(p1, p2)
        self.assertTrue(p2.startswith("FIL"))


class AnonymizeTests(unittest.TestCase):
    def setUp(self):
        self.headers = ["№", "ФИО", "Продажи"]
        self.rows = [
            ["1", "Иван Царевич", "15"],
            ["2", "Василиса Премудрая", "23"],
            ["3", "иван   царевич", "8"],
            ["4", "", "5"],
            ["5", "   ", "7"],
        ]
        self.engine = AnonymizerEngine()

    def test_same_value_same_index_by_first_appearance(self):
        new_rows, vault, report = self.engine.anonymize(
            self.headers, self.rows, {"ФИО": None})
        col = [r[1] for r in new_rows]
        self.assertEqual(col[0], col[2])
        self.assertTrue(col[0].endswith("0001"))
        self.assertTrue(col[1].endswith("0002"))
        self.assertEqual(report["ФИО"]["unique"], 2)
        self.assertEqual(report["ФИО"]["replaced_cells"], 3)
        self.assertEqual(report["ФИО"]["skipped"], 2)

    def test_empty_cells_untouched(self):
        new_rows, _, _ = self.engine.anonymize(self.headers, self.rows, {"ФИО": None})
        self.assertEqual(new_rows[3][1], "")
        self.assertEqual(new_rows[4][1], "")

    def test_original_rows_not_mutated(self):
        snapshot = [list(r) for r in self.rows]
        self.engine.anonymize(self.headers, self.rows, {"ФИО": None})
        self.assertEqual(self.rows, snapshot)

    def test_other_columns_untouched(self):
        new_rows, _, _ = self.engine.anonymize(self.headers, self.rows, {"ФИО": None})
        for orig, anon in zip(self.rows, new_rows):
            self.assertEqual(orig[0], anon[0])
            self.assertEqual(orig[2], anon[2])

    def test_vault_structure(self):
        _, vault, _ = self.engine.anonymize(self.headers, self.rows, {"ФИО": "PERS_"})
        self.assertEqual(vault["format"], "kvault-1")
        self.assertIn("ФИО", vault["columns"])
        meta = vault["columns"]["ФИО"]
        self.assertEqual(meta["prefix"], "PERS_")
        self.assertEqual(meta["next_counter"], 3)
        entry = next(e for e in vault["entries"] if e["idx"] == "PERS_0001")
        self.assertEqual(entry["val"], "Иван Царевич")

    def test_missing_column_raises(self):
        with self.assertRaises(ColumnNotFoundError):
            self.engine.anonymize(self.headers, self.rows, {"Нет такого": None})

    def test_repeat_run_same_engine_stable_indices_per_session_salt(self):
        rows_a = [["a", "X"], ["b", "Y"]]
        r1, v1, _ = self.engine.anonymize(["Код", "ФИО"], rows_a, {"ФИО": None})
        salt = bytes.fromhex(v1["columns"]["ФИО"]["salt_hex"])
        self.assertEqual(fingerprint("X", salt), v1["entries"][0]["fp"][:16])


class RestoreTests(unittest.TestCase):
    def make_table(self):
        headers = ["ФИО", "Адрес", "Телефон", "Продажи"]
        rows = [
            ["Иван Царевич", "Тридевятое царство", "+7\xa0(999)\xa0001‑11‑22", "15"],
            ["Василиса Премудрая", "Избушка, лес", "+7\xa0(999)\xa0022‑11‑33", "23"],
            ["Иван Царевич", "Тридевятое царство", "+7\xa0(999)\xa0001‑11‑22", "8"],
        ]
        return headers, rows

    def test_full_roundtrip(self):
        headers, rows = self.make_table()
        engine = AnonymizerEngine()
        selected = {c: None for c in ("ФИО", "Адрес", "Телефон")}
        new_rows, vault, _ = engine.anonymize(headers, rows, selected)
        restored, warnings, stats = engine.restore(headers, new_rows, vault)
        self.assertEqual(restored, rows)
        self.assertEqual(warnings, [])
        self.assertEqual(stats["unknown_cells"], 0)
        self.assertEqual(stats["restored_cells"], 9)

    def test_unknown_index_marked_and_reported(self):
        headers, rows = self.make_table()
        engine = AnonymizerEngine()
        new_rows, vault, _ = engine.anonymize(headers, rows, {"ФИО": None})
        tampered = [list(r) for r in new_rows]
        tampered[0][0] = "GHOST_9999"
        restored, warnings, stats = engine.restore(headers, tampered, vault)
        self.assertEqual(restored[0][0], UNKNOWN_MARK)
        self.assertEqual(stats["unknown_cells"], 1)
        self.assertTrue(any("GHOST_9999" in w for w in warnings))

    def test_restored_cell_fingerprint_mismatch_detected(self):
        headers, rows = self.make_table()
        engine = AnonymizerEngine()
        new_rows, vault, _ = engine.anonymize(headers, rows, {"ФИО": None})
        vault["entries"][0]["val"] = "Подменённое значение"
        restored, warnings, stats = engine.restore(headers, new_rows, vault)
        self.assertGreater(stats["fp_mismatch"], 0)

    def test_restore_skips_columns_not_in_keyfile(self):
        headers, rows = self.make_table()
        engine = AnonymizerEngine()
        new_rows, vault, _ = engine.anonymize(headers, rows, {"Продажи": None})
        restored, _, _ = engine.restore(headers, new_rows, vault)
        self.assertEqual([r[0] for r in restored], [r[0] for r in rows])


if __name__ == "__main__":
    unittest.main()
