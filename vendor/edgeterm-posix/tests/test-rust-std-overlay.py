#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rust_std_overlay",
    ROOT / "scripts" / "prepare-rust-std-overlay.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RustStdOverlayTests(unittest.TestCase):
    def test_adds_wasix_exit_status_extensions_without_touching_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "process.rs"
            original = "use crate::process;\n\npub fn existing() {}\n"
            source.write_text(original, encoding="utf-8")
            output = root / "overlay" / "process.rs"

            manifest = MODULE.prepare_overlay(source, output)

            self.assertEqual(source.read_text(encoding="utf-8"), original)
            result = output.read_text(encoding="utf-8")
            self.assertIn(MODULE.CONTRACT_MARKER, result)
            self.assertIn("JOIN_STATUS_TYPE_EXIT_NORMAL", result)
            self.assertIn("JOIN_STATUS_TYPE_EXIT_SIGNAL", result)
            self.assertTrue(manifest["changed"])

    def test_accepts_an_upstream_module_that_already_has_the_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "process.rs"
            source.write_text(
                MODULE.IMPORT_MARKER + MODULE.EXIT_STATUS_EXTENSION,
                encoding="utf-8",
            )

            manifest = MODULE.prepare_overlay(source, root / "result.rs")

            self.assertFalse(manifest["changed"])

    def test_adds_filesystem_extensions_without_touching_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "fs.rs"
            original = (
                MODULE.PERMISSIONS_MARKER
                + "pub trait MetadataExt {\n"
                + MODULE.METADATA_TRAIT_END
                + "\nimpl MetadataExt for fs::Metadata {\n"
                + MODULE.METADATA_IMPL_END
                + "\npub trait FileTypeExt {\n"
                + MODULE.FILETYPE_SOCKET
                + "\n"
            )
            source.write_text(original, encoding="utf-8")
            output = root / "overlay" / "fs.rs"

            manifest = MODULE.prepare_fs_overlay(source, output)

            self.assertEqual(source.read_text(encoding="utf-8"), original)
            result = output.read_text(encoding="utf-8")
            self.assertIn("pub trait PermissionsExt", result)
            self.assertIn("fn mode(&self) -> u32", result)
            self.assertIn("fn is_fifo(&self) -> bool", result)
            self.assertTrue(manifest["changed"])


if __name__ == "__main__":
    unittest.main()
