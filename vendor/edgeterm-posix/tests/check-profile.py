#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {"native", "compat", "advisory", "unsupported"}


def main() -> int:
    profile = json.loads((ROOT / "profile/edgeterm-posix-v1.json").read_text(encoding="utf-8"))
    assert profile["profile_version"] == 1
    assert profile["abi_version"] == 1
    assert profile["release"] == (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    for name, capability in profile["capabilities"].items():
        assert name and capability["status"] in ALLOWED
        if capability["status"] == "unsupported":
            assert capability.get("errno")
        else:
            assert capability.get("tests")
    print(f"Validated {len(profile['capabilities'])} profile capabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
