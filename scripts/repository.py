#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import io
import lzma
import os
import subprocess
import sys
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
REPOSITORY = ROOT / "repository"
COMPONENT = "main"
ARCHITECTURE = "wasm32-wasix"
BUILD_IMAGE = os.environ.get("EDGETERM_BUILD_IMAGE", "edgeterm-packages:2026-08-05")
sys.path.insert(0, str(ROOT / "scripts"))
from acceptance import is_stable, read_state
from ports import load_ports


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


def debian_archive_members(path: Path) -> dict[str, bytes]:
    data = path.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise ValueError(f"Invalid Debian archive: {path}")
    members: dict[str, bytes] = {}
    offset = 8
    while offset < len(data):
        header = data[offset : offset + 60]
        if len(header) != 60 or header[58:60] != b"`\n":
            raise ValueError(f"Invalid archive member in {path}")
        name = header[:16].decode("ascii").strip().rstrip("/")
        size = int(header[48:58].decode("ascii").strip())
        offset += 60
        members[name] = data[offset : offset + size]
        offset += size + (size % 2)
    return members


def package_control(path: Path) -> str:
    members = debian_archive_members(path)
    control_name = next((name for name in members if name.startswith("control.tar")), None)
    if control_name is None:
        raise ValueError(f"Debian control archive is missing: {path}")
    control_bytes = members[control_name]
    if control_name.endswith(".zst"):
        try:
            from compression import zstd
            control_bytes = zstd.decompress(control_bytes)
        except ImportError:
            try:
                import zstandard
            except ImportError as exc:
                raise RuntimeError("Reading zstd Debian archives requires Python 3.14 or the zstandard package. Install requirements.txt.") from exc
            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(control_bytes)) as reader:
                control_bytes = reader.read(8 * 1024 * 1024 + 1)
        if len(control_bytes) > 8 * 1024 * 1024:
            raise ValueError(f"Debian control archive exceeds the size limit: {path}")
    with tarfile.open(fileobj=io.BytesIO(control_bytes), mode="r:*") as archive:
        member = next(
            (item for item in archive.getmembers() if item.name.lstrip("./") == "control"),
            None,
        )
        if member is None:
            raise ValueError(f"Debian control file is missing: {path}")
        handle = archive.extractfile(member)
        if handle is None:
            raise ValueError(f"Debian control file is unreadable: {path}")
        return handle.read().decode("utf-8").strip()


def write_packages_index(repository_root: Path, package_directory: Path, output: Path) -> None:
    entries: list[str] = []
    for package in sorted(package_directory.glob("*.deb")):
        relative = package.relative_to(repository_root).as_posix()
        entries.append(
            "\n".join(
                (
                    package_control(package),
                    f"Filename: {relative}",
                    f"Size: {package.stat().st_size}",
                    f"MD5sum: {digest(package, 'md5')}",
                    f"SHA1: {digest(package, 'sha1')}",
                    f"SHA256: {digest(package, 'sha256')}",
                )
            )
        )
    output.write_text("\n\n".join(entries) + "\n", encoding="utf-8")


def build_repository(channel: str, *, local_flat: bool = False) -> Path:
    suite = channel
    pool = REPOSITORY / "pool" / channel
    binary = REPOSITORY / "dists" / suite / COMPONENT / f"binary-{ARCHITECTURE}"
    pool.mkdir(parents=True, exist_ok=True)
    binary.mkdir(parents=True, exist_ok=True)
    ports = load_ports()
    packages_to_publish: list[tuple[str, Path]] = []
    for package_name, port in sorted(ports.items()):
        if not port.user_visible:
            continue
        package = DIST / f"{package_name}_{port.deb_version}_{ARCHITECTURE}.deb"
        if not package.exists():
            raise FileNotFoundError(f"Current package artifact is missing: {package}")
        package_control(package)
        packages_to_publish.append((package_name, package))
    for stale_package in pool.glob("*.deb"):
        stale_package.unlink()
    for package_name, package in packages_to_publish:
        if channel == "stable":
            state = read_state(package_name, ports[package_name].deb_version)
            if not is_stable(state) or state.get("artifact_sha256") != digest(package, "sha256"):
                continue
        target = pool / package.name
        if not target.exists() or digest(target, "sha256") != digest(package, "sha256"):
            target.write_bytes(package.read_bytes())
    packages = binary / "Packages"
    write_packages_index(REPOSITORY, pool, packages)
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
        f"Valid-Until: {(dt.datetime.now(dt.UTC) + dt.timedelta(days=180)).strftime('%a, %d %b %Y %H:%M:%S +0000')}",
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
    if local_flat:
        flat = REPOSITORY / "local-flat"
        flat_pool = flat / "current"
        flat_pool.mkdir(parents=True, exist_ok=True)
        for stale_package in flat_pool.glob("*.deb"):
            stale_package.unlink()
        for package in sorted(pool.glob("*.deb")):
            target = flat_pool / package.name
            target.write_bytes(package.read_bytes())
        write_packages_index(flat, flat_pool, flat / "Packages")
        flat_index = flat / "Packages"
        flat_release = flat / "Release"
        flat_release.write_text("\n".join([
            "Origin: DigitalPlat",
            "Label: EdgeTerm Packages",
            f"Suite: {suite}",
            f"Date: {dt.datetime.now(dt.UTC).strftime('%a, %d %b %Y %H:%M:%S +0000')}",
            f"Valid-Until: {(dt.datetime.now(dt.UTC) + dt.timedelta(days=180)).strftime('%a, %d %b %Y %H:%M:%S +0000')}",
            "Architectures: wasm32-wasix all",
            "SHA256:",
            f" {digest(flat_index, 'sha256')} {flat_index.stat().st_size} Packages",
            "",
        ]), encoding="utf-8")
        if key:
            run(["gpg", "--batch", "--yes", "--local-user", key, "--clearsign", "--digest-algo", "SHA256", "--output", str(flat / "InRelease"), str(flat_release)])
    return release.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the EdgeTerm APT repository")
    parser.add_argument("action", choices=["build"])
    parser.add_argument("--channel", choices=["candidate", "stable"], default="candidate")
    parser.add_argument("--local-flat", action="store_true", help="Refresh the local browser test repository from this channel")
    args = parser.parse_args()
    print(build_repository(args.channel, local_flat=args.local_flat))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
