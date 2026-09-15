import hashlib
import hmac
import secrets
from datetime import datetime, timezone

UNKNOWN_MARK = "[?? НЕИЗВЕСТНО]"
FP_LEN = 16

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def normalize(value):
    return " ".join(str(value).replace("\xa0", " ").split()).strip().lower()


def fingerprint(value, salt):
    msg = normalize(value).encode("utf-8")
    return hmac.new(salt, msg, hashlib.sha256).hexdigest()[:FP_LEN]


def default_prefix(column_name, used_prefixes):
    translit = "".join(_TRANSLIT.get(ch, ch) for ch in column_name.lower())
    letters = "".join(ch for ch in translit if ("a" <= ch <= "z") or ch.isdigit())
    base = letters[:3].upper() or "COL"
    prefix = base + "_"
    n = 2
    while prefix in used_prefixes:
        prefix = f"{base}{n}_"
        n += 1
    return prefix


class ColumnNotFoundError(KeyError):
    pass


class AnonymizerEngine:

    def __init__(self):
        pass

    def anonymize(self, headers, rows, selected, source_file=""):
        col_pos = {h: i for i, h in enumerate(headers)}
        used_prefixes = set()
        columns_meta = {}
        entries = []
        new_rows = [list(r) for r in rows]

        for col, custom_prefix in selected.items():
            i = col_pos.get(col)
            if i is None:
                raise ColumnNotFoundError(col)
            salt = secrets.token_bytes(16)
            prefix = (custom_prefix or "").strip() or default_prefix(col, used_prefixes)
            used_prefixes.add(prefix)
            meta = {"prefix": prefix, "salt_hex": salt.hex(), "next_counter": 1}
            seen = {}
            replaced_cells = skipped_cells = 0
            for row in new_rows:
                raw = row[i]
                if not str(raw).strip():
                    row[i] = ""
                    skipped_cells += 1
                    continue
                fp = fingerprint(raw, salt)
                idx = seen.get(fp)
                if idx is None:
                    counter = meta["next_counter"]
                    meta["next_counter"] = counter + 1
                    idx = f"{prefix}{counter:04d}"
                    seen[fp] = idx
                    entries.append({"col": col, "fp": fp, "idx": idx, "val": str(raw)})
                row[i] = idx
                replaced_cells += 1
            columns_meta[col] = meta

        vault = {
            "format": "kvault-1",
            "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source_file": source_file,
            "columns": columns_meta,
            "entries": entries,
        }
        report = {}
        skipped_by_col = {
            col: sum(1 for r in rows if not str(r[col_pos[col]]).strip())
            for col in columns_meta
        }
        for col, meta in columns_meta.items():
            i = col_pos[col]
            unique_ids = {e["idx"] for e in entries if e["col"] == col}
            replaced = sum(1 for r in new_rows if str(r[i]).startswith(meta["prefix"]))
            report[col] = {
                "unique": len(unique_ids),
                "replaced_cells": replaced,
                "skipped": skipped_by_col[col],
            }
        return new_rows, vault, report

    def restore(self, headers, rows, vault):
        cols_meta = vault.get("columns", {})
        reverse = {(e["col"], e["idx"]): e for e in vault.get("entries", [])}
        col_pos = {h: i for i, h in enumerate(headers)}
        new_rows = [list(r) for r in rows]
        warnings = []
        stats = {"restored_cells": 0, "unknown_cells": 0, "fp_mismatch": 0}

        for col, meta in cols_meta.items():
            i = col_pos.get(col)
            if i is None:
                warnings.append(f"Столбец из файла-ключа отсутствует в таблице: «{col}»")
                continue
            salt = bytes.fromhex(meta["salt_hex"])
            missing = set()
            fp_bad = set()
            for row in new_rows:
                v = row[i]
                if not str(v).strip():
                    continue
                entry = reverse.get((col, str(v)))
                if entry is None:
                    missing.add(str(v))
                    row[i] = UNKNOWN_MARK
                    stats["unknown_cells"] += 1
                    continue
                val = entry["val"]
                if fingerprint(val, salt) != entry["fp"]:
                    fp_bad.add(entry["idx"])
                row[i] = val
                stats["restored_cells"] += 1
            for m in sorted(missing):
                warnings.append(f"Неизвестный индекс в столбце «{col}»: {m}")
            for m in sorted(fp_bad):
                warnings.append(f"Расхождение контрольного отпечатка: «{col}» {m}")
                stats["fp_mismatch"] += 1
        return new_rows, warnings, stats
