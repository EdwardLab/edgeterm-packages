#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tomllib
from pathlib import Path


def locked_registry_versions(lockfile: Path) -> dict[str, set[str]]:
    data = tomllib.loads(lockfile.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for package in data.get("package", []):
        source = package.get("source", "")
        if not source.startswith("registry+"):
            continue
        name = package.get("name")
        version = package.get("version")
        if isinstance(name, str) and isinstance(version, str):
            result.setdefault(name, set()).add(version)
    return result


def crate_metadata(source: Path) -> tuple[str, str]:
    manifest = source / "Cargo.toml"
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    package = data.get("package", {})
    name = package.get("name")
    version = package.get("version")
    if not isinstance(name, str) or not isinstance(version, str):
        raise SystemExit(f"Invalid compatibility crate manifest: {manifest}")
    return name, version


def registry_source(cargo_home: Path, name: str, version: str) -> Path:
    matches = sorted((cargo_home / "registry" / "src").glob(f"*/{name}-{version}"))
    if len(matches) != 1:
        raise SystemExit(
            f"Expected exactly one downloaded {name}-{version} source directory, "
            f"found {len(matches)}"
        )
    return matches[0]


def expose_posix_target_dependencies(manifest: Path) -> bool:
    original = manifest.read_text(encoding="utf-8")
    rewritten = original.replace(
        '"cfg(unix)"', '"cfg(any(unix, target_os = \\"wasi\\"))"'
    ).replace(
        "'cfg(unix)'", "'cfg(any(unix, target_os = \"wasi\"))'"
    )
    if rewritten == original:
        return False
    manifest.write_text(rewritten, encoding="utf-8")
    return True


def apply_overlays(
    cargo_home: Path,
    lockfile: Path,
    posix_root: Path,
    profile: Path,
    output: Path,
) -> dict[str, object]:
    configuration = json.loads(profile.read_text(encoding="utf-8"))
    locked = locked_registry_versions(lockfile)
    applied: list[dict[str, object]] = []
    for name, settings in configuration.get("overlays", {}).items():
        versions = locked.get(name, set())
        if not versions:
            continue
        if len(versions) != 1:
            values = ", ".join(sorted(versions))
            raise SystemExit(f"Multiple locked versions of {name} are unsupported: {values}")
        version = next(iter(versions))
        destination = registry_source(cargo_home, name, version)
        paths: list[str] = []
        source_setting = settings.get("source")
        if source_setting:
            compatibility_source = posix_root / source_setting
            compatibility_name, compatibility_version = crate_metadata(compatibility_source)
            if (compatibility_name, compatibility_version) != (name, version):
                raise SystemExit(
                    f"Compatibility crate {compatibility_name}-{compatibility_version} "
                    f"does not match locked {name}-{version}"
                )
            for relative in settings.get("paths", []):
                source_path = compatibility_source / relative
                destination_path = destination / relative
                if source_path.is_dir():
                    shutil.rmtree(destination_path, ignore_errors=True)
                    shutil.copytree(source_path, destination_path, symlinks=True)
                elif source_path.is_file():
                    destination_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, destination_path)
                else:
                    raise SystemExit(
                        f"Compatibility overlay path does not exist: {source_path}"
                    )
                paths.append(relative)
        if settings.get("manifest_cfg_unix"):
            manifest = destination / "Cargo.toml"
            if expose_posix_target_dependencies(manifest):
                paths.append("Cargo.toml[target-cfg]")
        applied.append(
            {
                "crate": name,
                "version": version,
                "destination": str(destination),
                "paths": paths,
            }
        )
    result = {
        "schema": "org.edgeterm.posix.rust-overlay-result.v1",
        "applied": applied,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply build-local POSIX overlays to locked Rust dependencies"
    )
    parser.add_argument("--cargo-home", type=Path, required=True)
    parser.add_argument("--lockfile", type=Path, required=True)
    parser.add_argument("--posix-root", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = apply_overlays(
        args.cargo_home,
        args.lockfile,
        args.posix_root,
        args.profile,
        args.output,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
