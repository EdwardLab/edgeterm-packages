#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "normalize-source.py"
SPEC = importlib.util.spec_from_file_location("normalize_source", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class NormalizeSourceTests(unittest.TestCase):
    def test_locale_module_is_normalized_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / MODULE.LOCALE_FILE
            path.write_text(
                "#elif defined __ANDROID__\nreturn android_value;\n",
                encoding="utf-8",
            )
            self.assertTrue(MODULE.normalize_locale_name(path))
            normalized = path.read_text(encoding="utf-8")
            self.assertIn(MODULE.TARGET_BRANCH, normalized)
            self.assertFalse(MODULE.normalize_locale_name(path))
            self.assertEqual(path.read_text(encoding="utf-8"), normalized)

    def test_unknown_locale_module_structure_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / MODULE.LOCALE_FILE
            path.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "unsupported locale-name"):
                MODULE.normalize_locale_name(path)


if __name__ == "__main__":
    unittest.main()
