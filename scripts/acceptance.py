#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "acceptance"
CHECKS = (
    "reproducible_build",
    "source_checksum",
    "license",
    "apt_install",
    "version",
    "functional",
    "apt_upgrade",
    "apt_remove",
    "apt_purge",
    "chrome",
)


def evidence_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def state_path(package: str) -> Path:
    return STATE / f"{package}.json"


def read_state(package: str, version: str = "") -> dict:
    path = state_path(package)
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if version and data.get("version") != version:
            return {"schema": "edgeterm.package-acceptance.v1", "package": package, "version": version, "checks": {}}
        return data
    return {"schema": "edgeterm.package-acceptance.v1", "package": package, "version": version, "checks": {}}


def write_state(data: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    destination = state_path(data["package"])
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=STATE, delete=False) as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, destination)


def is_stable(data: dict) -> bool:
    checks = data.get("checks", {})
    return all(checks.get(name, {}).get("passed") is True for name in CHECKS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record package acceptance evidence")
    subparsers = parser.add_subparsers(dest="action", required=True)
    record = subparsers.add_parser("record")
    record.add_argument("package")
    record.add_argument("version")
    record.add_argument("check", choices=CHECKS)
    record.add_argument("evidence", type=Path)
    status = subparsers.add_parser("status")
    status.add_argument("package", nargs="?")
    args = parser.parse_args()
    if args.action == "record":
        if not args.evidence.is_file() or not args.evidence.stat().st_size:
            raise SystemExit("Acceptance evidence must be a non-empty file.")
        data = read_state(args.package, args.version)
        data["checks"][args.check] = {
            "passed": True,
            "evidence": str(args.evidence.resolve()),
            "sha256": evidence_digest(args.evidence),
        }
        data["stable"] = is_stable(data)
        write_state(data)
        print("stable" if data["stable"] else "candidate")
        return 0
    packages = [args.package] if args.package else sorted(path.stem for path in STATE.glob("*.json"))
    for package in packages:
        data = read_state(package)
        passed = sum(data.get("checks", {}).get(name, {}).get("passed") is True for name in CHECKS)
        print(f"{package}: {'stable' if is_stable(data) else 'candidate'} ({passed}/{len(CHECKS)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
