import logging
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from ..core.engine import AnonymizerEngine, default_prefix
from ..core.io_tables import TableFormatError, read_table, write_table
from ..core.vault import load_vault, save_vault

logger = logging.getLogger("anonymizer.gui")

FILETYPES = [("Таблицы", "*.xlsx *.csv"), ("Все файлы", "*.*")]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Локальный анонимизатор таблиц — работает офлайн")
        self.geometry("1080x680")
        self.minsize(900, 560)

        self.src_path = None
        self.headers = []
        self.rows = []
        self.col_checks = {}
        self.col_prefixes = {}

        self.anon_path = None
        self.key_path = None
        self.result_rows = None
        self.result_headers = None

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_enc = ttk.Frame(notebook)
        self.tab_dec = ttk.Frame(notebook)
        notebook.add(self.tab_enc, text="  Анонимизация  ")
        notebook.add(self.tab_dec, text="  Восстановление  ")
        self._build_encode_tab()
        self._build_decode_tab()

    def _safe(self, func):
        def wrapper(*a, **kw):
            try:
                return func(*a, **kw)
            except Exception as e:
                logger.exception("Ошибка операции")
                messagebox.showerror("Ошибка", str(e), parent=self)
        return wrapper

    @staticmethod
    def _make_preview(parent):
        wrap = ttk.Frame(parent)
        tree = ttk.Treeview(wrap, show="headings", height=10)
        ys = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        xs = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        return wrap, tree

    @staticmethod
    def _fill_preview(tree, headers, rows):
        cols = list(range(len(headers)))
        tree["columns"] = cols
        for i in cols:
            tree.heading(i, text=headers[i])
            tree.column(i, width=140, stretch=(len(headers) <= 6), anchor="w")
        tree.delete(*tree.get_children())
        for row in rows:
            tree.insert("", "end", values=[str(c) for c in row])

    def _build_encode_tab(self):
        f = self.tab_enc
        top = ttk.Frame(f)
        top.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(top, text="Исходный файл:").pack(side="left")
        self.var_src = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.var_src, state="readonly")
        entry.pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(top, text="Обзор…", command=self._safe(self.pick_source)).pack(side="left")

        prev_wrap, self.tree_src = self._make_preview(f)
        prev_wrap.pack(fill="both", expand=True, padx=8, pady=4)

        cols_frame = ttk.LabelFrame(f, text="Столбцы персональных данных (отметьте нужные)")
        cols_frame.pack(fill="x", padx=8, pady=4)
        self.cols_holder = ttk.Frame(cols_frame)
        self.cols_holder.pack(fill="x", padx=4, pady=4)

        pw_frame = ttk.LabelFrame(f, text="Пароль защиты файла-ключа (минимум 8 символов)")
        pw_frame.pack(fill="x", padx=8, pady=4)
        self.var_pw1 = tk.StringVar()
        self.var_pw2 = tk.StringVar()
        ttk.Label(pw_frame, text="Пароль:").grid(row=0, column=0, sticky="e", padx=4, pady=3)
        e1 = ttk.Entry(pw_frame, textvariable=self.var_pw1, show="*", width=28)
        e1.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Label(pw_frame, text="Повтор:").grid(row=0, column=2, sticky="e", padx=4)
        e2 = ttk.Entry(pw_frame, textvariable=self.var_pw2, show="*", width=28)
        e2.grid(row=0, column=3, sticky="w", padx=4)

        btns = ttk.Frame(f)
        btns.pack(fill="x", padx=8, pady=4)
        ttk.Button(btns, text="▶ Выполнить анонимизацию",
                   command=self._safe(self.run_anonymize)).pack(side="left")

        rep = ttk.LabelFrame(f, text="Отчёт")
        rep.pack(fill="both", padx=8, pady=(4, 8))
        self.txt_report = tk.Text(rep, height=7, wrap="word", state="disabled")
        self.txt_report.pack(fill="both", expand=True, padx=4, pady=4)

    def pick_source(self):
        path = filedialog.askopenfilename(
            title="Выберите таблицу с персональными данными",
            filetypes=FILETYPES, parent=self,
        )
        if not path:
            return
        headers, rows = read_table(path)
        if not headers:
            raise TableFormatError("В файле нет заголовков")
        self.src_path = Path(path)
        self.headers = headers
        self.rows = rows
        self.var_src.set(str(path))
        self._fill_preview(self.tree_src, headers, rows[:10])
        self._build_columns_area()

    def _build_columns_area(self):
        for w in self.cols_holder.winfo_children():
            w.destroy()
        self.col_checks.clear()
        self.col_prefixes.clear()
        used = set()
        for i, h in enumerate(self.headers):
            var_on = tk.BooleanVar(value=False)
            var_pref = tk.StringVar(value=default_prefix(h, used))
            used.add(var_pref.get())
            frame = ttk.Frame(self.cols_holder)
            frame.grid(row=i // 2, column=i % 2, sticky="we", padx=6, pady=2)
            cb = ttk.Checkbutton(frame, text=h, variable=var_on)
            cb.pack(side="left")
            pe = ttk.Entry(frame, textvariable=var_pref, width=10)
            pe.pack(side="left", padx=(8, 0))
            self.col_checks[h] = var_on
            self.col_prefixes[h] = (pe, var_pref)
        for c in range(2):
            self.cols_holder.columnconfigure(c, weight=1)

    def run_anonymize(self):
        if not self.src_path:
            raise TableFormatError("Сначала выберите исходный файл")
        selected = {}
        used = set()
        for h, on_var in self.col_checks.items():
            if on_var.get():
                raw_pref = self.col_prefixes[h][0].get().strip() or default_prefix(h, used)
                used.add(raw_pref)
                selected[h] = raw_pref if raw_pref.endswith("_") else raw_pref + "_"
        if not selected:
            messagebox.showwarning(
                "Нет столбцов",
                "Отметьте хотя бы один столбец персональных данных.",
                parent=self,
            )
            return
        pw1, pw2 = self.var_pw1.get(), self.var_pw2.get()
        if len(pw1) < 8:
            messagebox.showwarning(
                "Слабый пароль",
                "Пароль должен содержать не менее 8 символов.",
                parent=self,
            )
            return
        if pw1 != pw2:
            messagebox.showerror("Пароли не совпадают",
                                 "Значения полей пароля различаются.", parent=self)
            return

        engine = AnonymizerEngine()
        new_rows, vault, report = engine.anonymize(
            self.headers, self.rows, selected,
            source_file=self.src_path.name,
        )
        out_path = self.src_path.with_name(self.src_path.stem + "_anon" + self.src_path.suffix)
        key_path = self.src_path.with_name(self.src_path.stem + "_KEY.kvault")
        write_table(out_path, self.headers, new_rows)
        save_vault(key_path, vault, pw1)
        logger.info("Анонимизация: %s, столбцов=%d, строк=%d",
                    self.src_path.name, len(selected), len(new_rows))

        lines = [
            f"Анонимная таблица: {out_path}",
            f"Файл-ключ (храните бережно!): {key_path}",
            "",
        ]
        for col, st in report.items():
            lines.append(f"«{col}»: уникальных {st['unique']}, заменено ячеек "
                         f"{st['replaced_cells']}, пропусков {st['skipped']}")
        self._show_report("\n".join(lines))
        self._fill_preview(self.tree_src, self.headers, new_rows[:10])
        messagebox.showinfo(
            "Готово",
            f"Анонимизация завершена.\n\n{out_path.name}\n{key_path.name}\n\n"
            "Файл-ключ нужен для восстановления данных — не теряйте его.",
            parent=self,
        )

    def _show_report(self, text):
        self.txt_report.configure(state="normal")
        self.txt_report.delete("1.0", "end")
        self.txt_report.insert("1.0", text)
        self.txt_report.configure(state="disabled")

    def _build_decode_tab(self):
        f = self.tab_dec
        files = ttk.LabelFrame(f, text="Исходные данные для восстановления")
        files.pack(fill="x", padx=8, pady=8)

        self.var_anon = tk.StringVar()
        self.var_keyf = tk.StringVar()
        self.var_dpw = tk.StringVar()
        rows_spec = [
            ("Анонимная таблица:", self.var_anon, self.pick_anon),
            ("Файл-ключ (.kvault):", self.var_keyf, self.pick_keyfile),
        ]
        for r, (label, var, cmd) in enumerate(rows_spec):
            ttk.Label(files, text=label).grid(row=r, column=0, sticky="e", padx=4, pady=3)
            ttk.Entry(files, textvariable=var, state="readonly").grid(
                row=r, column=1, sticky="we", padx=4)
            ttk.Button(files, text="Обзор…", command=self._safe(cmd)).grid(row=r, column=2, padx=4)
        ttk.Label(files, text="Пароль ключа:").grid(row=2, column=0, sticky="e", padx=4, pady=3)
        ttk.Entry(files, textvariable=self.var_dpw, show="*").grid(
            row=2, column=1, sticky="w", padx=4)
        files.columnconfigure(1, weight=1)

        act = ttk.Frame(f)
        act.pack(fill="x", padx=8, pady=4)
        ttk.Button(act, text="◀ Восстановить данные",
                   command=self._safe(self.run_restore)).pack(side="left")
        self.btn_save_res = ttk.Button(
            act, text="Сохранить результат…", state="disabled",
            command=self._safe(self.save_result))
        self.btn_save_res.pack(side="left", padx=8)

        res_wrap, self.tree_res = self._make_preview(f)
        res_wrap.pack(fill="both", expand=True, padx=8, pady=4)

        warn = ttk.LabelFrame(f, text="Предупреждения")
        warn.pack(fill="both", padx=8, pady=(4, 8))
        self.txt_warn = tk.Text(warn, height=6, wrap="word", state="disabled")
        self.txt_warn.pack(fill="both", expand=True, padx=4, pady=4)

    def pick_anon(self):
        path = filedialog.askopenfilename(
            title="Анонимная таблица", filetypes=FILETYPES, parent=self)
        if path:
            self.anon_path = Path(path)
            self.var_anon.set(path)

    def pick_keyfile(self):
        path = filedialog.askopenfilename(
            title="Файл-ключ",
            filetypes=[("Файл-ключ", "*.kvault"), ("Все файлы", "*.*")],
            parent=self,
        )
        if path:
            self.key_path = Path(path)
            self.var_keyf.set(path)

    def run_restore(self):
        if not self.anon_path or not self.key_path:
            raise TableFormatError("Укажите анонимную таблицу и файл-ключ")
        password = self.var_dpw.get()
        vault = load_vault(self.key_path, password)
        headers, rows = read_table(self.anon_path)
        engine = AnonymizerEngine()
        new_rows, warnings, stats = engine.restore(headers, rows, vault)
        self.result_headers = headers
        self.result_rows = new_rows
        self.btn_save_res.configure(state="normal")
        self._fill_preview(self.tree_res, headers, new_rows[:10])
        warn_text = (
            f"Восстановлено ячеек: {stats['restored_cells']}. "
            f"Не найдено индексов: {stats['unknown_cells']}.\n\n"
            + ("\n".join(warnings) if warnings else "Предупреждений нет.")
        )
        self.txt_warn.configure(state="normal")
        self.txt_warn.delete("1.0", "end")
        self.txt_warn.insert("1.0", warn_text)
        self.txt_warn.configure(state="disabled")
        logger.info("Восстановление: %s, ячеек=%d, предупреждений=%d",
                    self.anon_path.name, stats["restored_cells"], len(warnings))
        if warnings:
            messagebox.showwarning("Восстановление с замечаниями",
                                   "Часть ячеек не восстановлена — см. вкладку «Предупреждения».",
                                   parent=self)

    def save_result(self):
        if self.result_rows is None:
            return
        path = filedialog.asksaveasfilename(
            title="Куда сохранить восстановленную таблицу",
            defaultextension=".xlsx",
            initialfile="restored.xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv")],
            parent=self,
        )
        if not path:
            return
        write_table(path, self.result_headers, self.result_rows)
        logger.info("Результат сохранён: %s", Path(path).name)
        messagebox.showinfo("Готово", f"Таблица сохранена:\n{path}", parent=self)


def launch():
    logging.basicConfig(
        filename=str(Path(__file__).resolve().parents[2] / "anonymizer.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    App().mainloop()
