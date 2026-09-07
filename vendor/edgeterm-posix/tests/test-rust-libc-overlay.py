#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rust_libc_overlay",
    ROOT / "scripts" / "prepare-rust-libc-overlay.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RustLibcOverlayTests(unittest.TestCase):
    def test_extends_the_wasi_rusage_abi_without_touching_the_input(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "libc-0.2.177"
            module = source / "src" / "wasi" / "mod.rs"
            module.parent.mkdir(parents=True)
            original = (
                MODULE.RUSAGE_MINIMAL
                + "\n"
                + "pub const STDERR_FILENO: c_int = 2;\n"
            )
            module.write_text(original, encoding="utf-8")
            (source / "Cargo.toml").write_text(
                '[package]\nname = "libc"\nversion = "0.2.177"\n',
                encoding="utf-8",
            )
            output = root / "overlay"

            manifest = MODULE.prepare_overlay(source, output)

            self.assertEqual(module.read_text(encoding="utf-8"), original)
            result = (output / "src" / "wasi" / "mod.rs").read_text(encoding="utf-8")
            self.assertIn("pub ru_maxrss: c_long,", result)
            self.assertIn("pub const RUSAGE_CHILDREN: c_int = 2;", result)
            self.assertIn("pub const fn major(device: dev_t)", result)
            self.assertIn("pub const SIGPIPE: c_int = 13;", result)
            self.assertIn("pub fn signal(signum: c_int", result)
            self.assertTrue(manifest["changed"])

    def test_accepts_an_upstream_libc_that_already_has_the_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "libc-0.2.999"
            module = source / "src" / "wasi" / "mod.rs"
            module.parent.mkdir(parents=True)
            module.write_text(
                MODULE.RUSAGE_WASIX
                + "\npub const RUSAGE_CHILDREN: c_int = 2;\n"
                + MODULE.DEVICE_HELPERS
                + MODULE.SIGNAL_SUPPORT,
                encoding="utf-8",
            )
            (source / "Cargo.toml").write_text(
                '[package]\nname = "libc"\nversion = "0.2.999"\n',
                encoding="utf-8",
            )

            manifest = MODULE.prepare_overlay(source, root / "overlay")

            self.assertFalse(manifest["changed"])

    def test_exports_posix_unistd_for_the_combined_wasi_unix_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "libc-0.2.185"
            (source / "src" / "wasi").mkdir(parents=True)
            (source / "src" / "wasi" / "mod.rs").write_text(
                MODULE.RUSAGE_MINIMAL + "\npub const STDERR_FILENO: c_int = 2;\n",
                encoding="utf-8",
            )
            new_module = source / "src" / "new" / "mod.rs"
            new_module.parent.mkdir(parents=True)
            new_module.write_text(MODULE.UNISTD_EXPORT, encoding="utf-8")
            (source / "Cargo.toml").write_text(
                '[package]\nname = "libc"\nversion = "0.2.185"\n',
                encoding="utf-8",
            )

            MODULE.prepare_overlay(source, root / "overlay")

            result = (root / "overlay" / "src" / "new" / "mod.rs").read_text(
                encoding="utf-8"
            )
            self.assertIn('cfg(target_os = "wasi")', result)
            self.assertIn("common::posix::unistd::*", result)

    def test_keeps_wasi_platform_dispatch_when_unix_is_forced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "libc-0.2.185"
            (source / "src" / "wasi").mkdir(parents=True)
            (source / "src" / "wasi" / "mod.rs").write_text(
                MODULE.RUSAGE_MINIMAL + "\npub const STDERR_FILENO: c_int = 2;\n",
                encoding="utf-8",
            )
            (source / "src" / "lib.rs").write_text(
                "cfg_if::cfg_if! {\n"
                "    if #[cfg(windows)] {\n"
                "    } else if #[cfg(unix)] {\n"
                "    } else if #[cfg(target_os = \"wasi\")] {\n"
                "    }\n"
                "}\n",
                encoding="utf-8",
            )
            (source / "Cargo.toml").write_text(
                '[package]\nname = "libc"\nversion = "0.2.185"\n',
                encoding="utf-8",
            )

            manifest = MODULE.prepare_overlay(source, root / "overlay")

            result = (root / "overlay" / "src" / "lib.rs").read_text(
                encoding="utf-8"
            )
            self.assertIn(
                'not(any(target_env = "wasi", target_os = "wasi"))', result
            )
            self.assertIn(
                "wasi-platform-precedes-forced-unix", manifest["contracts"]
            )

    def test_can_apply_the_overlay_to_build_local_cargo_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cargo_home = root / "cargo-home"
            source = cargo_home / "registry" / "src" / "index" / "libc-0.2.185"
            (source / "src" / "wasi").mkdir(parents=True)
            (source / "src" / "wasi" / "mod.rs").write_text(
                MODULE.RUSAGE_MINIMAL + "\npub const STDERR_FILENO: c_int = 2;\n",
                encoding="utf-8",
            )
            (source / "Cargo.toml").write_text(
                '[package]\nname = "libc"\nversion = "0.2.185"\n',
                encoding="utf-8",
            )
            lockfile = root / "Cargo.lock"
            lockfile.write_text(
                '[[package]]\nname = "libc"\nversion = "0.2.185"\n'
                'source = "registry+https://github.com/rust-lang/crates.io-index"\n',
                encoding="utf-8",
            )

            result = MODULE.prepare_all_overlays(
                cargo_home,
                lockfile,
                root / "overlays",
                apply_in_place=True,
            )

            self.assertTrue(result["applied_in_place"])
            self.assertIn(
                "pub ru_maxrss: c_long,",
                (source / "src" / "wasi" / "mod.rs").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
