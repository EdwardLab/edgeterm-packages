#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path


SCHEMA = "org.edgeterm.posix-source-integrity.v1"
SOURCE_SUFFIXES = {
    ".ac",
    ".am",
    ".c",
    ".cc",
    ".cmake",
    ".cpp",
    ".cxx",
    ".go",
    ".h",
    ".hh",
    ".hpp",
    ".in",
    ".m4",
    ".py",
    ".rs",
    ".sh",
}


def describe(path: Path) -> dict[str, str | int]:
    metadata = path.lstat()
    mode = stat.S_IMODE(metadata.st_mode)
    if path.is_symlink():
        return {"type": "symlink", "mode": mode, "target": os.readlink(path)}
    if path.is_file():
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return {"type": "file", "mode": mode, "sha256": digest.hexdigest()}
    return {"type": "other", "mode": mode}


def inventory(root: Path) -> dict[str, dict[str, str | int]]:
    entries: dict[str, dict[str, str | int]] = {}
    for path in sorted(root.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        entries[path.relative_to(root).as_posix()] = describe(path)
    return entries


def snapshot(root: Path, destination: Path) -> None:
    payload = {"schema": SCHEMA, "entries": inventory(root)}
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def verify(root: Path, source: Path) -> None:
    expected = json.loads(source.read_text(encoding="utf-8"))
    if expected.get("schema") != SCHEMA:
        raise RuntimeError("Unsupported source-integrity snapshot schema")
    actual = inventory(root)
    wanted = expected["entries"]
    original_differences = [path for path in sorted(wanted) if actual.get(path) != wanted[path]]
    added_sources = [
        path
        for path in sorted(set(actual) - set(wanted))
        if Path(path).suffix in SOURCE_SUFFIXES or Path(path).name in {"CMakeLists.txt", "Makefile"}
    ]
    differences = original_differences + added_sources
    if not differences:
        return
    preview = "\n".join(f"  {path}" for path in differences[:20])
    suffix = "" if len(differences) <= 20 else f"\n  ... and {len(differences) - 20} more"
    raise RuntimeError(f"Upstream source tree changed before configure:\n{preview}{suffix}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a pristine upstream source tree")
    parser.add_argument("action", choices=("snapshot", "verify"))
    parser.add_argument("root", type=Path)
    parser.add_argument("snapshot", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == "snapshot":
        snapshot(root, args.snapshot)
    else:
        verify(root, args.snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
