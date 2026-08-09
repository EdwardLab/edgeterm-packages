#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import lzma
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
REPOSITORY = ROOT / "repository"
COMPONENT = "main"
ARCHITECTURE = "wasm32-wasix"
BUILD_IMAGE = os.environ.get("EDGETERM_BUILD_IMAGE", "edgeterm-packages:2026-08-05")
sys.path.insert(0, str(ROOT / "scripts"))
from acceptance import is_stable, read_state


def digest(path: Path, algorithm: str) -> str:
    value = hashlib.new(algorithm)
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def run(command: list[str], *, cwd: Path | None = None, output: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    if output:
        with output.open("wb") as handle:
            subprocess.run(command, cwd=cwd, stdout=handle, check=True)
    else:
        subprocess.run(command, cwd=cwd, check=True)


def build_repository(channel: str) -> Path:
    suite = channel
    pool = REPOSITORY / "pool" / channel
    binary = REPOSITORY / "dists" / suite / COMPONENT / f"binary-{ARCHITECTURE}"
    pool.mkdir(parents=True, exist_ok=True)
    binary.mkdir(parents=True, exist_ok=True)
    for stale_package in pool.glob("*.deb"):
        stale_package.unlink()
    for package in sorted(DIST.glob("*.deb")):
        package_name = package.name.split("_", 1)[0]
        if channel == "stable" and not is_stable(read_state(package_name)):
            continue
        target = pool / package.name
        if not target.exists() or digest(target, "sha256") != digest(package, "sha256"):
            target.write_bytes(package.read_bytes())
    packages = binary / "Packages"
    run([
        "docker", "run", "--rm", "--platform", "linux/arm64",
        "-v", f"{REPOSITORY}:/repository",
        "-w", "/repository",
        BUILD_IMAGE,
        "dpkg-scanpackages", "--arch", ARCHITECTURE, f"pool/{channel}", "/dev/null",
    ], output=packages)
    with packages.open("rb") as source, lzma.open(binary / "Packages.xz", "wb", preset=9) as target:
        target.write(source.read())
    release = REPOSITORY / "dists" / suite / "Release"
    metadata = [packages, binary / "Packages.xz"]
    lines = [
        "Origin: DigitalPlat",
        "Label: EdgeTerm Packages",
        f"Suite: {suite}",
        f"Codename: {suite}",
        f"Date: {dt.datetime.now(dt.UTC).strftime('%a, %d %b %Y %H:%M:%S +0000')}",
        f"Architectures: {ARCHITECTURE}",
        f"Components: {COMPONENT}",
        "Description: Optional third-party packages for EdgeTerm",
        "Acquire-By-Hash: yes",
        "SHA256:",
    ]
    for path in metadata:
        relative = path.relative_to(release.parent)
        lines.append(f" {digest(path, 'sha256')} {path.stat().st_size:16d} {relative}")
    release.write_text("\n".join(lines) + "\n", encoding="utf-8")
    key = os.environ.get("EDGETERM_APT_SIGNING_KEY", "").strip()
    if key:
        run(["gpg", "--batch", "--yes", "--local-user", key, "--clearsign", "--digest-algo", "SHA256", "--output", str(release.parent / "InRelease"), str(release)])
        run(["gpg", "--batch", "--yes", "--local-user", key, "--detach-sign", "--armor", "--digest-algo", "SHA256", "--output", str(release.parent / "Release.gpg"), str(release)])
    return release.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the EdgeTerm APT repository")
    parser.add_argument("action", choices=["build"])
    parser.add_argument("--channel", choices=["candidate", "stable"], default="candidate")
    args = parser.parse_args()
    print(build_repository(args.channel))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
