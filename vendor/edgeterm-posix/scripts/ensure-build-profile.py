#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import re


ARCHIVE_FLAGS = re.compile(r"^(?P<prefix>\s*ARFLAGS\s*=\s*)(?P<flags>\S+)(?P<suffix>.*)$")


def deterministic_archive_flags(flags: str) -> str:
    prefix = "-" if flags.startswith("-") else ""
    modes = flags.removeprefix("-").replace("U", "")
    if "D" not in modes:
        modes += "D"
    return f"{prefix}{modes}"


def update_makefile(path: Path, link_flags: str) -> bool:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    changed = False
    for index, line in enumerate(lines):
        ending = "\n" if line.endswith("\n") else ""
        body = line.removesuffix(ending)
        if body.startswith("LDFLAGS =") and "libedgeterm-posix.a" not in body:
            lines[index] = f"{body} {link_flags}{ending}"
            changed = True
            continue
        archive_match = ARCHIVE_FLAGS.match(body)
        if archive_match:
            flags = deterministic_archive_flags(archive_match.group("flags"))
            replacement = f"{archive_match.group('prefix')}{flags}{archive_match.group('suffix')}{ending}"
            if replacement != line:
                lines[index] = replacement
                changed = True
    if changed:
        path.write_text("".join(lines), encoding="utf-8")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--link-flags", required=True)
    args = parser.parse_args()
    for path in sorted(args.root.rglob("Makefile")):
        if path.is_file():
            update_makefile(path, args.link_flags)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
