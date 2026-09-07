#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rust_posix_source",
    ROOT / "scripts" / "prepare-rust-posix-source.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RustPosixSourceTests(unittest.TestCase):
    def test_exposes_unix_dependencies_without_rewriting_rust_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "src").mkdir()
            (root / "Cargo.toml").write_text(
                "[package]\nname = \"sample\"\nversion = \"1.0.0\"\n"
                "[dependencies]\n"
                "[target.'cfg(unix)'.dependencies]\nuzers = \"0.12\"\n",
                encoding="utf-8",
            )
            source = root / "src" / "main.rs"
            source.write_text(
                "#[cfg(unix)]\nfn platform() {}\n"
                "#[cfg(not(unix))]\nfn fallback() {}\n"
                "fn enabled() -> bool { cfg!(unix) }\n",
                encoding="utf-8",
            )

            changed = MODULE.prepare_source(root)

            self.assertEqual(changed, [root / "Cargo.toml"])
            self.assertEqual(
                source.read_text(encoding="utf-8"),
                "#[cfg(unix)]\nfn platform() {}\n"
                "#[cfg(not(unix))]\nfn fallback() {}\n"
                "fn enabled() -> bool { cfg!(unix) }\n",
            )
            self.assertIn(
                "[target.'cfg(any(unix, target_os = \"wasi\"))'.dependencies]",
                (root / "Cargo.toml").read_text(encoding="utf-8"),
            )
            self.assertIn(
                'uzers = "0.12"',
                (root / "Cargo.toml").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
