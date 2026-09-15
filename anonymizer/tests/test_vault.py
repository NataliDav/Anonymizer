import json
import tempfile
import unittest
from pathlib import Path

from anonymizer.core.vault import VaultError, load_vault, save_vault


def sample_data():
    return {
        "format": "kvault-1",
        "created": "2026-08-24T19:00:00+00:00",
        "source_file": "test.xlsx",
        "columns": {
            "ФИО": {"prefix": "FIO_", "salt_hex": "ab" * 16, "next_counter": 2}
        },
        "entries": [
            {"col": "ФИО", "fp": "0123456789abcdef",
             "idx": "FIO_0001", "val": "Иван Царевич"}
        ],
    }


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "key.kvault"
        self.data = sample_data()
        self.addCleanup(self.tmp.cleanup)

    def test_roundtrip(self):
        save_vault(self.path, self.data, "пароль-123")
        loaded = load_vault(self.path, "пароль-123")
        self.assertEqual(loaded, self.data)

    def test_wrong_password_rejected(self):
        save_vault(self.path, self.data, "правильный-пароль")
        with self.assertRaises(VaultError):
            load_vault(self.path, "неверный-пароль")

    def test_short_password_rejected_on_save(self):
        with self.assertRaises(VaultError):
            save_vault(self.path, self.data, "коротко")

    def test_tampered_token_rejected(self):
        save_vault(self.path, self.data, "надёжный-пароль")
        blob = json.loads(self.path.read_text(encoding="utf-8"))
        tok = bytearray(blob["token"].encode("ascii"))
        tok[-3] ^= 0x20
        blob["token"] = tok.decode("ascii", errors="ignore")
        self.path.write_text(json.dumps(blob), encoding="utf-8")
        with self.assertRaises(VaultError):
            load_vault(self.path, "надёжный-пароль")

    def test_foreign_file_rejected(self):
        other = Path(self.tmp.name) / "other.json"
        other.write_text(json.dumps({"hello": "world"}), encoding="utf-8")
        with self.assertRaises(VaultError):
            load_vault(other, "любой-пароль")

    def test_plaintext_absent_on_disk(self):
        save_vault(self.path, self.data, "секретный-пароль")
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn("Иван Царевич", raw)
        self.assertNotIn("секретный-пароль", raw)


if __name__ == "__main__":
    unittest.main()
