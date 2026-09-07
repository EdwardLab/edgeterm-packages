#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


PATCH_SUFFIXES = {".patch", ".diff"}
SOURCE_SUFFIXES = {".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".go"}
PREPARATION_SUFFIXES = {".py", ".sh"}


def audit(ports_root: Path) -> dict:
    packages: list[dict] = []
    totals = {
        "packages": 0,
        "patch_files": 0,
        "source_fragments": 0,
        "preparation_scripts": 0,
        "patch_lines": 0,
    }

    for manifest in sorted(ports_root.glob("*/port.toml")):
        files = [path for path in manifest.parent.iterdir() if path.is_file()]
        patches = [path for path in files if path.suffix in PATCH_SUFFIXES]
        fragments = [path for path in files if path.suffix in SOURCE_SUFFIXES]
        preparation = [path for path in files if path.suffix in PREPARATION_SUFFIXES]
        patch_lines = sum(
            len(path.read_text(encoding="utf-8", errors="replace").splitlines())
            for path in patches
        )
        totals["packages"] += 1
        totals["patch_files"] += len(patches)
        totals["source_fragments"] += len(fragments)
        totals["preparation_scripts"] += len(preparation)
        totals["patch_lines"] += patch_lines
        if patches or fragments or preparation:
            packages.append({
                "package": manifest.parent.name,
                "patches": [path.name for path in patches],
                "source_fragments": [path.name for path in fragments],
                "preparation_scripts": [path.name for path in preparation],
                "patch_lines": patch_lines,
            })

    return {
        "schema": "org.edgeterm.posix-port-audit.v1",
        "totals": totals,
        "packages_with_local_overrides": packages,
    }


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: audit-ports.py PORTS_DIRECTORY", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    if not root.is_dir():
        print(f"ports directory not found: {root}", file=sys.stderr)
        return 2
    print(json.dumps(audit(root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
