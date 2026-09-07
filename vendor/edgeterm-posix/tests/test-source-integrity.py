#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "source-integrity.py"
SPEC = importlib.util.spec_from_file_location("source_integrity", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class SourceIntegrityTests(unittest.TestCase):
    def test_unchanged_tree_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            (root / "file.c").write_text("int value;\n", encoding="utf-8")
            snapshot = Path(directory) / "snapshot.json"
            MODULE.snapshot(root, snapshot)
            MODULE.verify(root, snapshot)

    def test_content_change_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            source = root / "file.c"
            source.write_text("int value;\n", encoding="utf-8")
            snapshot = Path(directory) / "snapshot.json"
            MODULE.snapshot(root, snapshot)
            source.write_text("int changed;\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "file.c"):
                MODULE.verify(root, snapshot)

    def test_added_file_and_symlink_change_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            target = root / "target"
            target.write_text("value\n", encoding="utf-8")
            link = root / "link"
            link.symlink_to("target")
            snapshot = Path(directory) / "snapshot.json"
            MODULE.snapshot(root, snapshot)
            link.unlink()
            link.symlink_to("other")
            (root / "added.c").write_text("int added;\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "added"):
                MODULE.verify(root, snapshot)

    def test_build_artifacts_do_not_change_upstream_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "source"
            root.mkdir()
            (root / "file.c").write_text("int value;\n", encoding="utf-8")
            snapshot = Path(directory) / "snapshot.json"
            MODULE.snapshot(root, snapshot)
            (root / "file.o").write_bytes(b"object")
            (root / "program").write_bytes(b"binary")
            MODULE.verify(root, snapshot)


if __name__ == "__main__":
    unittest.main()
