#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


LOCALE_FILE = "getlocalename_l-unsafe.c"
TARGET_BRANCH = "#elif defined __wasi__"
NEXT_BRANCH = "#elif defined __ANDROID__"
TARGET_BODY = (
    f"{TARGET_BRANCH}\n"
    "      return (struct string_with_storage) { \"C\", STORAGE_INDEFINITE };\n"
)


def normalize_locale_name(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    if TARGET_BRANCH in text:
        return False
    if NEXT_BRANCH not in text:
        raise RuntimeError(f"unsupported locale-name source structure: {path}")
    path.write_text(
        text.replace(NEXT_BRANCH, TARGET_BODY + NEXT_BRANCH, 1),
        encoding="utf-8",
        errors="surrogateescape",
    )
    return True


def normalize_tree(root: Path) -> int:
    changed = 0
    for path in sorted(root.rglob(LOCALE_FILE)):
        changed += normalize_locale_name(path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize portable source contracts")
    parser.add_argument("source_root", type=Path)
    arguments = parser.parse_args()
    if not arguments.source_root.is_dir():
        parser.error("source_root must be a directory")
    normalize_tree(arguments.source_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
