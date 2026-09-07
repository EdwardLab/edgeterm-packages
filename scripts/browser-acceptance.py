#!/usr/bin/env python3
"""Validate browser execution evidence for the current package artifact."""
import argparse
import json
from pathlib import Path


CHECKS = {
    "php": ["PHP executable", "PHP program", "PHP HTTP preview", "Installed PHP survives reload"],
    "git": ["Git executable", "Git repository transaction", "Installed Git survives reload"],
}


def validate(report_path, package, artifact_sha256):
    report = json.loads(Path(report_path).read_text())
    if "Chrome/" not in report.get("userAgent", ""):
        raise ValueError("Chrome browser evidence is required")
    if report.get("artifacts", {}).get(package, {}).get("sha256") != artifact_sha256:
        raise ValueError("Browser evidence belongs to a different package artifact")
    results = {item["name"]: item for item in report.get("results", [])}
    for name in CHECKS[package]:
        if results.get(name, {}).get("passed") is not True:
            raise ValueError(f"Browser acceptance did not pass: {name}")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--package", required=True, choices=CHECKS)
    parser.add_argument("--artifact-sha256", required=True)
    args = parser.parse_args()
    validate(args.report, args.package, args.artifact_sha256)
    print(f"Validated Chrome functional and persistence evidence for {args.package}")


if __name__ == "__main__":
    main()
