#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rustc_posix_wrapper",
    ROOT / "scripts" / "rustc-posix-wrapper.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RustcPosixWrapperTests(unittest.TestCase):
    def test_detects_workspace_sources_and_configured_crates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            source = workspace / "src" / "main.rs"
            source.parent.mkdir()
            source.write_text("fn main() {}\n", encoding="utf-8")

            self.assertTrue(MODULE.source_belongs_to_workspace([str(source)], workspace))
            self.assertEqual(MODULE.crate_name(["--crate-name", "terminal_size"]), "terminal_size")
            self.assertIn("uzers", MODULE.configured_unix_crates())
