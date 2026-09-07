#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tomllib
from pathlib import Path


RUSAGE_MINIMAL = """    pub struct rusage {
        pub ru_utime: timeval,
        pub ru_stime: timeval,
    }
"""

RUSAGE_WASIX = """    pub struct rusage {
        pub ru_utime: timeval,
        pub ru_stime: timeval,
        pub ru_maxrss: c_long,
        pub ru_ixrss: c_long,
        pub ru_idrss: c_long,
        pub ru_isrss: c_long,
        pub ru_minflt: c_long,
        pub ru_majflt: c_long,
        pub ru_nswap: c_long,
        pub ru_inblock: c_long,
        pub ru_oublock: c_long,
        pub ru_msgsnd: c_long,
        pub ru_msgrcv: c_long,
        pub ru_nsignals: c_long,
        pub ru_nvcsw: c_long,
        pub ru_nivcsw: c_long,
        pub __reserved: [c_long; 16],
    }
"""

DEVICE_HELPERS = """
pub const fn major(device: dev_t) -> c_uint {
    ((device >> 8) & 0xfff) as c_uint
}

pub const fn minor(device: dev_t) -> c_uint {
    (device & 0xff) as c_uint
}
"""

SIGNAL_SUPPORT = """
pub type sighandler_t = usize;
pub const SIG_DFL: sighandler_t = 0;
pub const SIGPIPE: c_int = 13;

extern \"C\" {
    pub fn signal(signum: c_int, handler: sighandler_t) -> sighandler_t;
}
"""

UNISTD_EXPORT = "        pub use unistd::*;\n"
WASI_UNISTD_EXPORT = """        #[cfg(target_os = "wasi")]
        pub use common::posix::unistd::*;
        #[cfg(not(target_os = "wasi"))]
        pub use unistd::*;
"""

UNIX_PLATFORM_BRANCH = '    } else if #[cfg(unix)] {\n'
WASI_SAFE_UNIX_PLATFORM_BRANCH = """    } else if #[cfg(all(
        unix,
        not(any(target_env = "wasi", target_os = "wasi")),
    ))] {
"""


def locked_libc_version(lockfile: Path) -> str:
    data = tomllib.loads(lockfile.read_text(encoding="utf-8"))
    versions = {
        package["version"]
        for package in data.get("package", [])
        if package.get("name") == "libc" and package.get("source", "").startswith("registry+")
    }
    if len(versions) != 1:
        values = ", ".join(sorted(versions)) or "none"
        raise SystemExit(f"Expected exactly one registry libc version in Cargo.lock, found: {values}")
    return versions.pop()


def registry_libc(cargo_home: Path, version: str) -> Path:
    matches = sorted((cargo_home / "registry" / "src").glob(f"*/libc-{version}"))
    if len(matches) != 1:
        raise SystemExit(
            f"Expected exactly one downloaded libc-{version} source directory, found {len(matches)}"
        )
    return matches[0]


def libc_metadata(source: Path) -> tuple[str, str] | None:
    manifest = source / "Cargo.toml"
    if not manifest.is_file():
        return None
    data = tomllib.loads(manifest.read_text(encoding="utf-8"))
    package = data.get("package", {})
    if package.get("name") != "libc" or not isinstance(package.get("version"), str):
        return None
    return package["name"], package["version"]


def cargo_libc_sources(cargo_home: Path) -> list[Path]:
    candidates = [
        *(cargo_home / "registry" / "src").glob("*/libc-*"),
        *(cargo_home / "git" / "checkouts").glob("libc-*/*"),
    ]
    sources = [path for path in candidates if path.is_dir() and libc_metadata(path)]
    return sorted(set(sources), key=lambda path: (libc_metadata(path)[1], str(path)))


def prepare_overlay(source: Path, output: Path) -> dict[str, object]:
    shutil.rmtree(output, ignore_errors=True)
    shutil.copytree(source, output, symlinks=True)
    changed = False
    contracts: list[str] = []
    crate_root = output / "src" / "lib.rs"
    if crate_root.is_file():
        body = crate_root.read_text(encoding="utf-8")
        if WASI_SAFE_UNIX_PLATFORM_BRANCH not in body:
            if body.count(UNIX_PLATFORM_BRANCH) != 1:
                raise SystemExit("The Rust libc platform dispatch has an unknown layout")
            body = body.replace(
                UNIX_PLATFORM_BRANCH,
                WASI_SAFE_UNIX_PLATFORM_BRANCH,
                1,
            )
            crate_root.write_text(body, encoding="utf-8")
            changed = True
        contracts.append("wasi-platform-precedes-forced-unix")

    wasi_module = output / "src" / "wasi" / "mod.rs"
    if wasi_module.is_file():
        body = wasi_module.read_text(encoding="utf-8")
        if "pub ru_maxrss: c_long," not in body:
            if body.count(RUSAGE_MINIMAL) != 1:
                raise SystemExit("The Rust libc WASI rusage declaration has an unknown layout")
            body = body.replace(RUSAGE_MINIMAL, RUSAGE_WASIX, 1)
            changed = True
        if "pub const RUSAGE_CHILDREN:" not in body:
            marker = "pub const STDERR_FILENO: c_int = 2;\n"
            if body.count(marker) != 1:
                raise SystemExit("The Rust libc WASI constant section has an unknown layout")
            body = body.replace(marker, marker + "pub const RUSAGE_CHILDREN: c_int = 2;\n", 1)
            changed = True
        if "pub const fn major(device: dev_t)" not in body:
            body += DEVICE_HELPERS
            changed = True
        if "pub const SIGPIPE: c_int" not in body:
            body += SIGNAL_SUPPORT
            changed = True
        wasi_module.write_text(body, encoding="utf-8")
        contracts.extend(
            [
                "rusage-full-layout",
                "rusage-children",
                "device-number-helpers",
                "signal-handler-api",
            ]
        )

    new_module = output / "src" / "new" / "mod.rs"
    if new_module.is_file():
        body = new_module.read_text(encoding="utf-8")
        if WASI_UNISTD_EXPORT not in body:
            export_count = body.count(UNISTD_EXPORT)
            if export_count > 1:
                raise SystemExit("The Rust libc unistd export has an unknown layout")
            if export_count == 1:
                body = body.replace(UNISTD_EXPORT, WASI_UNISTD_EXPORT, 1)
                new_module.write_text(body, encoding="utf-8")
                changed = True
        if WASI_UNISTD_EXPORT in body:
            contracts.append("wasi-unistd-export")

    metadata = libc_metadata(source)
    if metadata is None:
        raise SystemExit(f"Not a libc crate: {source}")
    manifest = {
        "schema": "org.edgeterm.posix.rust-libc-overlay.v1",
        "libc_version": metadata[1],
        "source": str(source),
        "output": str(output),
        "changed": changed,
        "contracts": contracts,
    }
    (output / "edgeterm-posix-overlay.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def prepare_all_overlays(
    cargo_home: Path,
    lockfile: Path,
    output_root: Path,
    extra_paths: list[Path] | None = None,
    apply_in_place: bool = False,
) -> dict[str, object]:
    locked_source = registry_libc(cargo_home, locked_libc_version(lockfile))
    sources = cargo_libc_sources(cargo_home)
    if locked_source not in sources:
        sources.append(locked_source)
    sources = sorted(set(sources), key=lambda path: (libc_metadata(path)[1], str(path)))

    shutil.rmtree(output_root, ignore_errors=True)
    output_root.mkdir(parents=True)
    overlays: list[dict[str, object]] = []
    paths: list[Path] = []
    for source in sources:
        version = libc_metadata(source)[1]
        suffix = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:8]
        output = output_root / f"libc-{version}-{suffix}"
        overlays.append(prepare_overlay(source, output))
        paths.append(output)
        if apply_in_place:
            shutil.copytree(output / "src", source / "src", dirs_exist_ok=True)
    paths.extend(extra_paths or [])

    config = "paths = [\n" + "".join(f"  {json.dumps(str(path))},\n" for path in paths) + "]\n"
    config_path = output_root / "cargo-config.toml"
    config_path.write_text(config, encoding="utf-8")
    result = {
        "schema": "org.edgeterm.posix.rust-libc-overlay-set.v1",
        "config": str(config_path),
        "applied_in_place": apply_in_place,
        "overlays": overlays,
    }
    (output_root / "manifest.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the EdgeTerm Rust libc ABI overlay")
    parser.add_argument("--cargo-home", type=Path, required=True)
    parser.add_argument("--lockfile", type=Path, required=True)
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--output", type=Path)
    output.add_argument("--output-root", type=Path)
    parser.add_argument("--extra-path", action="append", type=Path, default=[])
    parser.add_argument("--apply-in-place", action="store_true")
    args = parser.parse_args()

    if args.output_root:
        manifest = prepare_all_overlays(
            args.cargo_home,
            args.lockfile,
            args.output_root,
            args.extra_path,
            args.apply_in_place,
        )
    else:
        version = locked_libc_version(args.lockfile)
        source = registry_libc(args.cargo_home, version)
        manifest = prepare_overlay(source, args.output)
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
