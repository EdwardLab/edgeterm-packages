#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import ports


ROOT = Path(__file__).resolve().parents[1]
MUTATING_COMMAND = re.compile(
    r"(?:^|[;&|]\s*)(?:sed|perl|patch|python3?|cp|mv|rm|install)\b"
)
SOURCE_REFERENCE = re.compile(
    r"\$SOURCE_DIR|\$CARGO_HOME|cargo-home|registry/src|/port/[^ ]+\.(?:py|patch|c|h|rs)"
)
COMMAND_KEYS = (
    "pre",
    "post_fetch",
    "post_configure",
    "commands",
    "post",
)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def command_values(build: dict) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for key in COMMAND_KEYS:
        entries = build.get(key, [])
        if isinstance(entries, str):
            entries = [entries]
        values.extend((key, entry) for entry in entries if isinstance(entry, str))
    return values


def mutation_hints(port: ports.Port) -> list[str]:
    hints = [path.name for path in sorted(port.path.glob("*.patch"))]
    for key, command in command_values(port.data["build"]):
        if MUTATING_COMMAND.search(command) and SOURCE_REFERENCE.search(command):
            hints.append(f"{key}: {command}")
    return hints


def acceptance_matches(port: ports.Port, artifact: Path) -> bool:
    state_path = ROOT / "acceptance" / f"{port.name}.json"
    if not state_path.is_file() or not artifact.is_file():
        return False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    check = state.get("checks", {}).get("pristine_source", {})
    digest = file_sha256(artifact)
    return (
        state.get("version") == port.deb_version
        and state.get("artifact_sha256") == digest
        and check.get("passed") is True
        and check.get("artifact_sha256") == digest
    )


def audit_port(port: ports.Port) -> dict:
    marker_path = ROOT / "build" / port.name / "build-complete.json"
    marker = json.loads(marker_path.read_text(encoding="utf-8")) if marker_path.is_file() else {}
    artifact = ROOT / "dist" / f"{port.name}_{port.deb_version}_wasm32-wasix.deb"
    locked = bool(port.data["build"].get("pristine_source"))
    built_pristine = (
        marker.get("version") == port.deb_version
        and marker.get("pristine_source") is True
    )
    accepted_pristine = acceptance_matches(port, artifact)
    return {
        "package": port.name,
        "version": port.deb_version,
        "locked": locked,
        "built_pristine": built_pristine,
        "accepted_pristine": accepted_pristine,
        "mutation_hints": mutation_hints(port),
        "status": "verified" if locked and built_pristine and accepted_pristine else "unproven",
    }


def build_report() -> list[dict]:
    catalog = ports.load_ports()
    ports.validate_catalog(catalog)
    return [audit_port(port) for port in catalog.values() if port.user_visible]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit immutable-source package evidence")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        verified = [item for item in report if item["status"] == "verified"]
        print(f"Verified immutable-source packages: {len(verified)}/{len(report)}")
        for item in report:
            hints = f", mutation hints: {len(item['mutation_hints'])}" if item["mutation_hints"] else ""
            print(
                f"{item['package']}: {item['status']} "
                f"(locked={item['locked']}, built={item['built_pristine']}, "
                f"accepted={item['accepted_pristine']}{hints})"
            )
    return 1 if args.require_complete and any(item["status"] != "verified" for item in report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
