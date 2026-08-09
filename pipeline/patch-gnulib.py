#!/usr/bin/env python3
from pathlib import Path
import sys


root = Path(sys.argv[1])
patterns = {
    "open.c": ("orig_open", "#undef __need_system_fcntl_h", "#undef open", "open", "rpl_open"),
    "openat.c": ("orig_openat", "#undef __need_system_fcntl_h", "#undef openat", "openat", "rpl_openat"),
    "stat.c": ("orig_stat", "#undef __need_system_sys_stat_h", "#undef stat", None, None),
    "lstat.c": ("orig_lstat", "# undef __need_system_sys_stat_h", "# undef lstat", None, None),
    "fstat.c": ("orig_fstat", "#undef __need_system_sys_stat_h", "#undef fstat", None, None),
    "fstatat.c": ("orig_fstatat", "#undef __need_system_sys_stat_h", "#undef fstatat", None, None),
}

for path in root.rglob("*.c"):
    rule = patterns.get(path.name)
    if not rule:
        continue
    marker, anchor, directive, original, replacement = rule
    text = path.read_text(errors="surrogateescape")
    if marker not in text or anchor not in text:
        continue
    if directive not in text:
        text = text.replace(anchor, f"{anchor}\n{directive}", 1)
    if original is not None:
        signature = f"\nint\n{original} ("
        replacement_signature = f"\nint\n{replacement} ("
        if replacement_signature not in text:
            if signature not in text:
                raise SystemExit(f"gnulib replacement signature was not found: {path}")
            text = text.replace(signature, replacement_signature, 1)
    path.write_text(text, errors="surrogateescape")
