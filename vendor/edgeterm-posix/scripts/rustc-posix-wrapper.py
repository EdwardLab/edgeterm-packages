#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import subprocess
import sys
from pathlib import Path


def source_belongs_to_workspace(arguments: list[str], workspace: Path) -> bool:
    for argument in arguments:
        if not argument.endswith(".rs"):
            continue
        source = Path(argument)
        try:
            source.resolve().relative_to(workspace)
        except (OSError, ValueError):
            continue
        return True
    return False


def crate_name(arguments: list[str]) -> str | None:
    for index, argument in enumerate(arguments[:-1]):
        if argument == "--crate-name":
            return arguments[index + 1]
    return None


def configured_unix_crates() -> set[str]:
    profile = Path(__file__).resolve().parents[1] / "config" / "rust-crates.json"
    data = json.loads(profile.read_text(encoding="utf-8"))
    return set(data.get("cfg_unix", []))


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("rustc wrapper requires the compiler path")
    compiler = sys.argv[1]
    arguments = sys.argv[2:]
    workspace_value = os.environ.get("EDGETERM_RUST_WORKSPACE")
    workspace_source = bool(
        workspace_value
        and source_belongs_to_workspace(arguments, Path(workspace_value).resolve())
    )
    if workspace_source or crate_name(arguments) in configured_unix_crates():
        arguments.extend((
            "--cfg",
            "unix",
            "-Aexplicit_builtin_cfgs_in_flags",
        ))
    if workspace_source:
        arguments.append("-Zcrate-attr=feature(wasi_ext)")
    return subprocess.call((compiler, *arguments))


if __name__ == "__main__":
    raise SystemExit(main())
