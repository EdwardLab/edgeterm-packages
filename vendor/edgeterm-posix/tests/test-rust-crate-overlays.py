#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rust_crate_overlays",
    ROOT / "scripts" / "prepare-rust-crate-overlays.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RustCrateOverlayTests(unittest.TestCase):
    def test_overlays_a_locked_registry_crate_without_changing_the_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cargo_home = root / "cargo-home"
            registry = cargo_home / "registry" / "src" / "index" / "demo-1.2.3"
            (registry / "src").mkdir(parents=True)
            (registry / "src" / "lib.rs").write_text("pub const VALUE: u8 = 1;\n")
            compatibility = root / "posix" / "rust" / "demo"
            (compatibility / "src").mkdir(parents=True)
            (compatibility / "Cargo.toml").write_text(
                '[package]\nname = "demo"\nversion = "1.2.3"\n', encoding="utf-8"
            )
            (compatibility / "src" / "lib.rs").write_text(
                "pub const VALUE: u8 = 2;\n", encoding="utf-8"
            )
            lockfile = root / "Cargo.lock"
            lockfile.write_text(
                '[[package]]\nname = "demo"\nversion = "1.2.3"\n'
                'source = "registry+https://github.com/rust-lang/crates.io-index"\n',
                encoding="utf-8",
            )
            original_lock = lockfile.read_bytes()
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {"overlays": {"demo": {"source": "rust/demo", "paths": ["src"]}}}
                ),
                encoding="utf-8",
            )

            result = MODULE.apply_overlays(
                cargo_home, lockfile, root / "posix", profile, root / "result.json"
            )

            self.assertEqual(lockfile.read_bytes(), original_lock)
            self.assertIn("VALUE: u8 = 2", (registry / "src" / "lib.rs").read_text())
            self.assertEqual(result["applied"][0]["crate"], "demo")

    def test_rejects_a_compatibility_crate_with_the_wrong_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cargo_home = root / "cargo-home"
            (cargo_home / "registry" / "src" / "index" / "demo-1.2.3").mkdir(
                parents=True
            )
            compatibility = root / "posix" / "rust" / "demo"
            compatibility.mkdir(parents=True)
            (compatibility / "Cargo.toml").write_text(
                '[package]\nname = "demo"\nversion = "9.9.9"\n', encoding="utf-8"
            )
            lockfile = root / "Cargo.lock"
            lockfile.write_text(
                '[[package]]\nname = "demo"\nversion = "1.2.3"\n'
                'source = "registry+https://github.com/rust-lang/crates.io-index"\n',
                encoding="utf-8",
            )
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {"overlays": {"demo": {"source": "rust/demo", "paths": ["src"]}}}
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit):
                MODULE.apply_overlays(
                    cargo_home, lockfile, root / "posix", profile, root / "result.json"
                )

    def test_exposes_locked_unix_dependencies_for_the_posix_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cargo_home = root / "cargo-home"
            registry = cargo_home / "registry" / "src" / "index" / "demo-1.2.3"
            registry.mkdir(parents=True)
            manifest = registry / "Cargo.toml"
            manifest.write_text(
                '[package]\nname = "demo"\nversion = "1.2.3"\n'
                '[target."cfg(unix)".dependencies.example]\nversion = "1"\n',
                encoding="utf-8",
            )
            lockfile = root / "Cargo.lock"
            lockfile.write_text(
                '[[package]]\nname = "demo"\nversion = "1.2.3"\n'
                'source = "registry+https://github.com/rust-lang/crates.io-index"\n',
                encoding="utf-8",
            )
            profile = root / "profile.json"
            profile.write_text(
                json.dumps({"overlays": {"demo": {"manifest_cfg_unix": True}}}),
                encoding="utf-8",
            )

            result = MODULE.apply_overlays(
                cargo_home, lockfile, root / "posix", profile, root / "result.json"
            )

            self.assertIn(
                'cfg(any(unix, target_os = \\"wasi\\"))',
                manifest.read_text(encoding="utf-8"),
            )
            self.assertIn("target", MODULE.tomllib.loads(manifest.read_text()))
            self.assertIn("Cargo.toml[target-cfg]", result["applied"][0]["paths"])


if __name__ == "__main__":
    unittest.main()
