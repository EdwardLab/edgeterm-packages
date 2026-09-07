#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "rust_singlethread_overlay",
    ROOT / "scripts" / "prepare-rust-singlethread-overlay.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RustSinglethreadOverlayTests(unittest.TestCase):
    def test_prepares_runtime_overlays(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "sys/thread").mkdir(parents=True)
            (source / "sys/sync/thread_parking").mkdir(parents=True)
            (source / "sys/thread/mod.rs").write_text("cfg_select! {\n    _ => {}\n}\n", encoding="utf-8")
            (source / "sys/sync/thread_parking/mod.rs").write_text(
                "cfg_select! {\n    _ => {}\n}\n",
                encoding="utf-8",
            )
            (source / "sys/thread/unsupported.rs").write_text(
                MODULE.UNKNOWN_PARALLELISM + "\n" + MODULE.PANIC_SLEEP,
                encoding="utf-8",
            )
            (source / "sys/exit.rs").write_text(
                MODULE.EXIT_FUNCTION + "        _ => { loop {} }\n    }\n}\n",
                encoding="utf-8",
            )
            output = root / "output"

            manifest = MODULE.prepare_overlay(source, output)

            self.assertIn("single-thread-runtime", manifest["contracts"])
            self.assertIn("edgeterm_singlethread =>", (output / "thread-mod.rs").read_text())
            unsupported = (output / "thread-unsupported.rs").read_text()
            self.assertIn("Ok(NonZero::new(1).unwrap())", unsupported)
            self.assertIn("libc::nanosleep", unsupported)
            self.assertIn("edgeterm_singlethread =>", (output / "thread-parking-mod.rs").read_text())
            exit_body = (output / "exit.rs").read_text()
            self.assertIn('wasm_import_module = "wasi_snapshot_preview1"', exit_body)
            self.assertIn("edgeterm_proc_exit(code as u32)", exit_body)


if __name__ == "__main__":
    unittest.main()
