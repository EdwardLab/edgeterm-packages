#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


TARGET_UNIX = "[target.'cfg(unix)'.dependencies]"
TARGET_POSIX = "[target.'cfg(any(unix, target_os = \"wasi\"))'.dependencies]"
def rewrite_manifest(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    rewritten = original.replace(TARGET_UNIX, TARGET_POSIX)
    if rewritten == original:
        return False
    path.write_text(rewritten, encoding="utf-8")
    return True


def prepare_source(root: Path) -> list[Path]:
    changed: list[Path] = []
    manifest = root / "Cargo.toml"
    if manifest.is_file() and rewrite_manifest(manifest):
        changed.append(manifest)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Expose POSIX Cargo dependencies to the WASI target"
    )
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    changed = prepare_source(args.source)
    print(f"Prepared {len(changed)} Rust source files for the POSIX target")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
