import argparse
import getpass
import sys
from pathlib import Path

from .core.engine import AnonymizerEngine, ColumnNotFoundError
from .core.io_tables import TableFormatError, read_table, write_table
from .core.vault import VaultError, load_vault, save_vault


def _die(msg, code=2):
    print(f"ОШИБКА: {msg}", file=sys.stderr)
    return code


def _ask_password(cli_password):
    if cli_password is not None:
        return cli_password
    return getpass.getpass("Пароль файла-ключа: ")


def _default_outputs(input_path):
    p = Path(input_path)
    anon = p.with_name(p.stem + "_anon" + p.suffix)
    key = p.with_name(p.stem + "_KEY.kvault")
    return anon, key


def cmd_encode(args):
    try:
        headers, rows = read_table(args.input)
    except TableFormatError as e:
        return _die(str(e))

    wanted = [c.strip() for c in args.cols.split(",") if c.strip()]
    missing = [c for c in wanted if c not in headers]
    if not wanted:
        return _die("Не указаны столбцы для анонимизации (--cols)")
    if missing:
        return _die(f"Столбцы не найдены в таблице: {', '.join(missing)}")

    password = _ask_password(args.password)
    if len(password) < 8:
        return _die("Пароль должен содержать не менее 8 символов")

    prefixes = {}
    if args.prefixes:
        for pair in args.prefixes.split(","):
            name, _, pref = pair.partition("=")
            if name.strip() in wanted and pref.strip():
                prefixes[name.strip()] = pref.strip()
    selected = {c: prefixes.get(c) for c in wanted}

    engine = AnonymizerEngine()
    source_name = Path(args.input).name
    try:
        new_rows, vault, report = engine.anonymize(headers, rows, selected, source_file=source_name)
    except ColumnNotFoundError as e:
        return _die(f"Столбец не найден: {e.args[0]}")

    out_path = Path(args.out) if args.out else _default_outputs(args.input)[0]
    key_path = Path(args.key) if args.key else _default_outputs(args.input)[1]
    try:
        write_table(out_path, headers, new_rows)
        save_vault(key_path, vault, password)
    except (TableFormatError, OSError) as e:
        return _die(f"Не удалось сохранить результат: {e}")

    print(f"Анонимная таблица : {out_path}")
    print(f"Файл-ключ         : {key_path}")
    for col, stat in report.items():
        print(f"  «{col}»: уникальных индексов {stat['unique']}, "
              f"заменено ячеек {stat['replaced_cells']}, пропусков {stat['skipped']}")
    return 0


def cmd_decode(args):
    try:
        headers, rows = read_table(args.input)
    except TableFormatError as e:
        return _die(str(e))

    password = _ask_password(args.password)
    try:
        vault = load_vault(args.key, password)
    except VaultError as e:
        return _die(str(e))

    engine = AnonymizerEngine()
    new_rows, warnings, stats = engine.restore(headers, rows, vault)

    default_ext = Path(args.input).suffix or ".xlsx"
    out_path = Path(args.out) if args.out else Path(args.input).with_name(
        Path(args.input).stem + "_restored" + default_ext
    )
    try:
        write_table(out_path, headers, new_rows)
    except (TableFormatError, OSError) as e:
        return _die(f"Не удалось сохранить результат: {e}")

    print(f"Восстановленная таблица: {out_path}")
    print(f"Восстановлено ячеек: {stats['restored_cells']}; "
          f"неизвестных индексов: {stats['unknown_cells']}")
    for w in warnings:
        print(f"  ! {w}")
    if stats["unknown_cells"] or stats["fp_mismatch"]:
        return 1
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog="anonymizer",
        description="Локальный анонимизатор таблиц (без сети и нейросетей)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    enc = sub.add_parser("encode", help="заменить персональные данные индексами")
    enc.add_argument("input", help="исходный файл .xlsx/.csv")
    enc.add_argument("--cols", required=True,
                     help='столбцы ПДн через запятую, например "ФИО,Адрес,Телефон"')
    enc.add_argument("--prefixes", default="",
                     help='префиксы вида "ФИО=FIO_,Адрес=ADR_" (необязательно)')
    enc.add_argument("--out", help="путь анонимной таблицы (по умолчанию *_anon.*)")
    enc.add_argument("--key", help="путь файла-ключа (по умолчанию *_KEY.kvault)")
    enc.add_argument("--password", help="пароль файла-ключа (иначе спросит скрыто)")
    enc.set_defaults(func=cmd_encode)

    dec = sub.add_parser("decode", help="восстановить данные из анонимной таблицы")
    dec.add_argument("input", help="анонимная таблица .xlsx/.csv")
    dec.add_argument("--key", required=True, help="файл-ключ .kvault")
    dec.add_argument("--out", help="путь восстановленной таблицы (*_restored.*)")
    dec.add_argument("--password", help="пароль файла-ключа (иначе спросит скрыто)")
    dec.set_defaults(func=cmd_decode)
    return parser


def run_cli(argv=None):
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(run_cli())
