import ast
import unittest
from pathlib import Path

BANNED_ROOTS = {"requests", "urllib", "http", "socket", "ftplib", "smtplib", "telnetlib"}
PKG = Path(__file__).resolve().parents[1]


class NoNetworkImportsTest(unittest.TestCase):
    def test_no_network_modules_anywhere_in_package(self):
        violations = []
        for py in PKG.rglob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
            for node in ast.walk(tree):
                roots = []
                if isinstance(node, ast.Import):
                    roots = [alias.name.split(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    roots = [node.module.split(".")[0]]
                for root in roots:
                    if root in BANNED_ROOTS:
                        violations.append(f"{py.relative_to(PKG)}: {root}")
        self.assertEqual(violations, [], f"Запрещённые сетевые импорты: {violations}")

    def test_gui_module_importable_without_display_side_effects(self):
        import importlib
        mod = importlib.import_module("anonymizer.gui.app")
        self.assertTrue(hasattr(mod, "App"))
        self.assertTrue(callable(mod.App))


if __name__ == "__main__":
    unittest.main()
