#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PORTS = ROOT / "ports"
CACHE = ROOT / ".cache"
BUILD = ROOT / "build"
DIST = ROOT / "dist"
REPORTS = BUILD / "reports"
BATCH_FILE = ROOT / "batches.toml"
DEFAULT_EDGETERM = ROOT.parent / "EdgeTerm"
DEFAULT_IMAGE = "edgeterm-packages:2026-08-05"
SOURCE_DATE_EPOCH = "1704067200"
PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
COMMAND_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
CAPABILITIES = {"full", "http", "socket-preview"}
EXECUTION_MODES = {"buffered", "streaming", "interactive", "network-preview"}
BUILD_SYSTEMS = {"autotools", "cmake", "make", "cargo", "go", "custom"}


class PortError(RuntimeError):
    pass


@dataclass(frozen=True)
class Port:
    path: Path
    data: dict

    @property
    def name(self) -> str:
        return self.data["package"]["name"]

    @property
    def version(self) -> str:
        return self.data["package"]["version"]

    @property
    def revision(self) -> str:
        return self.data["package"].get("revision", "1edgeterm1")

    @property
    def deb_version(self) -> str:
        return f"{self.version}-{self.revision}"

    @property
    def source_url(self) -> str:
        return self.data["source"]["url"]

    @property
    def source_sha256(self) -> str:
        return self.data["source"]["sha256"]

    @property
    def build_system(self) -> str:
        return self.data["build"]["system"]

    @property
    def user_visible(self) -> bool:
        return self.data["package"].get("build_only", False) is not True


def load_ports() -> dict[str, Port]:
    ports: dict[str, Port] = {}
    for manifest in sorted(PORTS.glob("*/port.toml")):
        with manifest.open("rb") as handle:
            port = Port(manifest.parent, tomllib.load(handle))
        if port.name in ports:
            raise PortError(f"Duplicate package name: {port.name}")
        ports[port.name] = port
    return ports


def require_table(data: dict, key: str, path: Path) -> dict:
    value = data.get(key)
    if not isinstance(value, dict):
        raise PortError(f"{path}: missing [{key}] table")
    return value


def require_strings(table: dict, key: str, path: Path, minimum: int = 1) -> list[str]:
    value = table.get(key)
    if not isinstance(value, list) or len(value) < minimum or not all(isinstance(item, str) and item for item in value):
        raise PortError(f"{path}: {key} must contain at least {minimum} non-empty strings")
    return value


def validate_port(port: Port) -> None:
    package = require_table(port.data, "package", port.path)
    source = require_table(port.data, "source", port.path)
    build = require_table(port.data, "build", port.path)
    runtime = port.data.get("runtime")
    tests = port.data.get("tests")
    if not PACKAGE_NAME.fullmatch(str(package.get("name", ""))):
        raise PortError(f"{port.path}: invalid package name")
    for key in ("version", "revision", "license", "homepage", "description"):
        if not isinstance(package.get(key), str) or not package[key].strip():
            raise PortError(f"{port.path}: package.{key} is required")
    if not str(source.get("url", "")).startswith("https://"):
        raise PortError(f"{port.path}: source.url must use HTTPS")
    if not SHA256.fullmatch(str(source.get("sha256", ""))):
        raise PortError(f"{port.path}: source.sha256 must be a pinned checksum")
    if build.get("system") not in BUILD_SYSTEMS:
        raise PortError(f"{port.path}: unsupported build system {build.get('system')}")
    if port.user_visible:
        if not isinstance(runtime, dict):
            raise PortError(f"{port.path}: missing [runtime] table")
        if not isinstance(tests, dict):
            raise PortError(f"{port.path}: missing [tests] table")
        commands = require_strings(runtime, "commands", port.path)
        if any(not COMMAND_NAME.fullmatch(command) for command in commands):
            raise PortError(f"{port.path}: invalid command name")
        if runtime.get("capability") not in CAPABILITIES:
            raise PortError(f"{port.path}: invalid runtime capability")
        if runtime.get("mode") not in EXECUTION_MODES:
            raise PortError(f"{port.path}: invalid runtime mode")
        require_strings(tests, "smoke", port.path)
    elif package.get("build_only") is not True:
        raise PortError(f"{port.path}: package.build_only must be true when runtime metadata is omitted")
    dependencies = package.get("depends", [])
    if not isinstance(dependencies, list) or not all(PACKAGE_NAME.fullmatch(str(item)) for item in dependencies):
        raise PortError(f"{port.path}: package.depends must contain package names")
    build_dependencies = build.get("dependencies", [])
    if not isinstance(build_dependencies, list) or not all(PACKAGE_NAME.fullmatch(str(item)) for item in build_dependencies):
        raise PortError(f"{port.path}: build.dependencies must contain package names")


def validate_catalog(ports: dict[str, Port]) -> None:
    visible_ports = {name: port for name, port in ports.items() if port.user_visible}
    if len(visible_ports) != 50:
        raise PortError(f"Expected exactly 50 user-visible packages, found {len(visible_ports)}")
    commands: dict[str, str] = {}
    for port in ports.values():
        validate_port(port)
        for command in port.data.get("runtime", {}).get("commands", []):
            owner = commands.get(command)
            if owner and owner != port.name:
                raise PortError(f"Command {command} is provided by both {owner} and {port.name}")
            commands[command] = port.name
        for dependency in port.data["package"].get("depends", []):
            if dependency not in ports:
                raise PortError(f"{port.name}: unknown dependency {dependency}")
        for dependency in port.data["build"].get("dependencies", []):
            if dependency not in ports:
                raise PortError(f"{port.name}: unknown build dependency {dependency}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str, chain: tuple[str, ...]) -> None:
        if name in visiting:
            raise PortError(f"Circular build dependency: {' -> '.join((*chain, name))}")
        if name in visited:
            return
        visiting.add(name)
        for dependency in ports[name].data["build"].get("dependencies", []):
            visit(dependency, (*chain, name))
        visiting.remove(name)
        visited.add(name)

    for name in ports:
        visit(name, ())


def resolve_port(name: str, ports: dict[str, Port]) -> Port:
    try:
        return ports[name]
    except KeyError as error:
        raise PortError(f"Unknown port: {name}") from error


def load_batches(ports: dict[str, Port]) -> dict[str, list[str]]:
    with BATCH_FILE.open("rb") as handle:
        data = tomllib.load(handle)
    batches = data.get("batches")
    if not isinstance(batches, dict) or not batches:
        raise PortError("batches.toml must define a non-empty [batches] table")
    flattened: list[str] = []
    for name, packages in batches.items():
        if not isinstance(packages, list) or not packages or not all(isinstance(item, str) for item in packages):
            raise PortError(f"Batch {name} must contain package names")
        unknown = sorted(set(packages) - set(ports))
        if unknown:
            raise PortError(f"Batch {name} contains unknown packages: {', '.join(unknown)}")
        flattened.extend(packages)
    duplicates = sorted({name for name in flattened if flattened.count(name) > 1})
    if duplicates:
        raise PortError(f"Packages occur in more than one batch: {', '.join(duplicates)}")
    visible_ports = {name for name, port in ports.items() if port.user_visible}
    build_only_entries = sorted(set(flattened) - visible_ports)
    if build_only_entries:
        raise PortError(f"Build-only packages must not occur in batches: {', '.join(build_only_entries)}")
    missing = sorted(visible_ports - set(flattened))
    if missing:
        raise PortError(f"Packages missing from batches: {', '.join(missing)}")
    return batches


def source_path(port: Port) -> Path:
    suffix = ".tar.gz"
    for candidate in (".tar.xz", ".tar.bz2", ".tar.lz", ".tar.gz", ".tgz", ".zip"):
        if port.source_url.split("?", 1)[0].endswith(candidate):
            suffix = candidate
            break
    return CACHE / "sources" / f"{port.name}-{port.version}{suffix}"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_port(port: Port) -> Path:
    destination = source_path(port)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and hash_file(destination) == port.source_sha256:
        return destination
    destination.unlink(missing_ok=True)
    request = urllib.request.Request(port.source_url, headers={"User-Agent": "EdgeTerm-Packages/1"})
    last_error: Exception | None = None
    temporary: Path | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as response, tempfile.NamedTemporaryFile(
                dir=destination.parent, delete=False
            ) as output:
                shutil.copyfileobj(response, output)
                temporary = Path(output.name)
            break
        except Exception as error:
            last_error = error
            if attempt == 3:
                raise PortError(f"{port.name}: source download failed after four attempts: {error}") from error
            time.sleep(2**attempt)
    if temporary is None:
        raise PortError(f"{port.name}: source download failed: {last_error}")
    actual = hash_file(temporary)
    if actual != port.source_sha256:
        temporary.unlink(missing_ok=True)
        raise PortError(f"{port.name}: source checksum mismatch, expected {port.source_sha256}, received {actual}")
    temporary.replace(destination)
    return destination


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def run_logged(command: list[str], log_path: Path) -> None:
    print("+", " ".join(command), flush=True)
    print(f"  build log: {log_path}", flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def validate_stage(port: Port, stage: Path) -> None:
    if not port.user_visible:
        if not (stage / "usr/local").is_dir():
            raise PortError(f"{port.name}: build-only dependency did not stage /usr/local")
        return
    missing: list[str] = []
    invalid: list[str] = []
    for command in port.data["runtime"]["commands"]:
        candidates = (
            stage / "usr/local/bin" / command,
            stage / "usr/local/sbin" / command,
        )
        executable = next((path for path in candidates if path.is_file() or path.is_symlink()), None)
        if executable is None:
            missing.append(command)
            continue
        resolved = executable.resolve()
        if not resolved.is_file():
            invalid.append(f"{command} (broken symlink)")
            continue
        if resolved.read_bytes()[:4] != b"\x00asm" and not resolved.read_bytes()[:2] == b"#!":
            invalid.append(f"{command} (not WebAssembly or a script)")
    if missing or invalid:
        details = ", ".join([*(f"missing {name}" for name in missing), *invalid])
        raise PortError(f"{port.name}: invalid staging output: {details}")
    for link in stage.rglob("*"):
        if not link.is_symlink():
            continue
        target = os.readlink(link)
        if target.startswith("/build/") or target.startswith("/toolchain/"):
            raise PortError(f"{port.name}: build-only symlink escaped into staging: {link} -> {target}")


def build_image() -> None:
    image = os.environ.get("EDGETERM_BUILD_IMAGE", DEFAULT_IMAGE)
    run(["docker", "build", "--platform", "linux/arm64", "-t", image, "-f", str(ROOT / "pipeline/Dockerfile"), str(ROOT)])


def extraction_command(archive: Path) -> str:
    name = archive.name
    if name.endswith(".zip"):
        return "unzip -q /input/source -d /build/source-root"
    if name.endswith(".tar.lz"):
        return "tar --lzip -xf /input/source -C /build/source-root"
    return "tar -xf /input/source -C /build/source-root"


def configure_script(port: Port) -> str:
    build = port.data["build"]
    configure_args = " ".join(build.get("configure_args", []))
    make_args = " ".join(build.get("make_args", []))
    install_args = " ".join(build.get("install_args", []))
    build_commands = "\n".join(build.get("build_commands", []))
    install_commands = "\n".join(build.get("install_commands", []))
    pre = "\n".join(build.get("pre", []))
    post_configure = "\n".join(build.get("post_configure", []))
    post_fetch = "\n".join(build.get("post_fetch", []))
    post = "\n".join(build.get("post", []))
    asyncify = ""
    if build.get("asyncify", False):
        asyncify = r'''
while IFS= read -r executable; do
  transformed="${executable}.asyncify"
  if ! /binaryen/bin/wasm-opt \
    --enable-reference-types \
    --enable-bulk-memory \
    --pass-arg=asyncify-ignore-indirect \
    --pass-arg=asyncify-addlist@edgeterm_vfork \
    --pass-arg=asyncify-propagate-addlist \
    --asyncify \
    "$executable" \
    -o "$transformed"; then
    rm -f "$transformed"
    /binaryen/bin/wasm-opt \
      --enable-reference-types \
      --enable-bulk-memory \
      --asyncify \
      "$executable" \
      -o "$transformed"
  fi
  mv "$transformed" "$executable"
done < <(find /build/stage/usr/local/bin /build/stage/usr/local/sbin \
  -type f -perm -0100 -exec file {} \; 2>/dev/null | sed -n 's/: WebAssembly.*//p')
'''
    compat_link = (
        "-Wl,--whole-archive /build/libedgetermcompat.a -Wl,--no-whole-archive"
        if build.get("link_compat", False)
        else ""
    )
    compat_via_ldflags = build.get("link_compat_via_ldflags", False)
    compat_ldflags = (
        compat_link
        if port.build_system != "autotools" or compat_via_ldflags
        else ""
    )
    compat_libs = "" if compat_via_ldflags else compat_link
    compat_include = "-include /toolchain/wasix-compat.h" if build.get("include_compat", False) else ""
    # Autotools feature probes must see the platform headers before the
    # compatibility declarations. The generated config header is injected
    # together with the compatibility header only for the actual build.
    early_compat_include = "" if port.build_system == "autotools" else compat_include
    thread_flags = "-pthread" if build.get("threads", False) else ""
    thread_ldflags = (
        "-pthread -Wl,--initial-memory=16777216 -Wl,--max-memory=268435456"
        if build.get("threads", False)
        else ""
    )
    compat_thread_define = "-DEDGETERM_THREADS" if build.get("threads", False) else ""
    mman_cflags = "-D_WASI_EMULATED_MMAN" if build.get("emulated_mman", False) else ""
    mman_ldflags = "-lwasi-emulated-mman" if build.get("emulated_mman", False) else ""
    rust_flags = "--cfg unix -Aexplicit_builtin_cfgs_in_flags" if build.get("rust_unix", False) else ""
    make_cflags_assignment = "" if build.get("preserve_make_cflags", False) else 'CFLAGS="$EDGETERM_COMPILE_CFLAGS"'
    common = """
set -euo pipefail
mkdir -p /build/source-root /build/work /build/stage /build/prefix /toolchain/sysroot
rm -rf /build/source-root/* /build/work/* /build/stage/*
__EDGETERM_EXTRACT__
SOURCE_DIR=/build/source-root
TOP_LEVEL_DIRECTORY=$(find /build/source-root -mindepth 1 -maxdepth 1 -type d -print -quit)
TOP_LEVEL_FILE=$(find /build/source-root -mindepth 1 -maxdepth 1 -type f -print -quit)
TOP_LEVEL_DIRECTORY_COUNT=$(find /build/source-root -mindepth 1 -maxdepth 1 -type d | wc -l)
if [ "$TOP_LEVEL_DIRECTORY_COUNT" -eq 1 ] && [ -z "$TOP_LEVEL_FILE" ]; then
  SOURCE_DIR=$TOP_LEVEL_DIRECTORY
fi
for patch_file in /port/*.patch; do
  [ -f "$patch_file" ] || continue
  patch -d "$SOURCE_DIR" -p1 < "$patch_file"
done
tar -xzf /toolchain/sysroot.tar.gz -C /toolchain/sysroot
export WASIX_SYSROOT=$(find /toolchain/sysroot -mindepth 2 -maxdepth 2 -type d -name sysroot -print -quit)
export WASI_SDK_BIN=/wasi-sdk/bin
export EDGETERM_PREFIX=/build/prefix
export CARGO_HOME=/build/cargo-home
export SOURCE_DATE_EPOCH=__EDGETERM_SOURCE_DATE_EPOCH__
export CC="$WASI_SDK_BIN/clang --target=wasm32-wasi --sysroot=$WASIX_SYSROOT"
export CXX="$WASI_SDK_BIN/clang++ --target=wasm32-wasi --sysroot=$WASIX_SYSROOT"
export AR="$WASI_SDK_BIN/llvm-ar"
export RANLIB="$WASI_SDK_BIN/llvm-ranlib"
export STRIP="$WASI_SDK_BIN/llvm-strip"
export PKG_CONFIG_PATH=/build/prefix/lib/pkgconfig:/build/prefix/share/pkgconfig
"$WASI_SDK_BIN/clang" --target=wasm32-wasi --sysroot="$WASIX_SYSROOT" -O2 __EDGETERM_THREAD_FLAGS__ __EDGETERM_COMPAT_THREAD_DEFINE__ -c /toolchain/wasix-compat.c -o /build/wasix-compat.o
"$WASI_SDK_BIN/llvm-ar" rcs /build/libedgetermcompat.a /build/wasix-compat.o
export CPPFLAGS="${CPPFLAGS:-} -I/build/prefix/include"
export CFLAGS="${CFLAGS:-} -O2 -I/build/prefix/include -D_WASI_EMULATED_PROCESS_CLOCKS __EDGETERM_THREAD_FLAGS__ __EDGETERM_MMAN_CFLAGS__ __EDGETERM_COMPAT_INCLUDE__"
export CXXFLAGS="${CXXFLAGS:-} -O2 -I/build/prefix/include -D_WASI_EMULATED_PROCESS_CLOCKS __EDGETERM_THREAD_FLAGS__ __EDGETERM_MMAN_CFLAGS__ __EDGETERM_COMPAT_INCLUDE__"
export LDFLAGS="${LDFLAGS:-} -static -L/build/prefix/lib __EDGETERM_THREAD_LDFLAGS__ -Wl,--export=__stack_pointer -Wl,--export=__heap_base -Wl,--export=__data_end __EDGETERM_COMPAT_LDFLAGS__ -lwasi-emulated-process-clocks __EDGETERM_MMAN_LDFLAGS__"
cd /build/work
__EDGETERM_PRE__
""".replace("__EDGETERM_EXTRACT__", extraction_command(source_path(port))).replace(
        "__EDGETERM_PRE__", pre
    ).replace("__EDGETERM_COMPAT_LDFLAGS__", compat_ldflags).replace(
        "__EDGETERM_SOURCE_DATE_EPOCH__", SOURCE_DATE_EPOCH
    ).replace(
        "__EDGETERM_THREAD_FLAGS__", thread_flags
    ).replace(
        "__EDGETERM_THREAD_LDFLAGS__", thread_ldflags
    ).replace(
        "__EDGETERM_COMPAT_THREAD_DEFINE__", compat_thread_define
    ).replace(
        "__EDGETERM_MMAN_CFLAGS__", mman_cflags
    ).replace(
        "__EDGETERM_MMAN_LDFLAGS__", mman_ldflags
    ).replace(
        "__EDGETERM_COMPAT_INCLUDE__", early_compat_include
    )
    if port.build_system == "autotools":
        autotools_build = build_commands or f'make -j"${{BUILD_JOBS:-4}}" {make_cflags_assignment} {make_args}'
        autotools_install = install_commands or f'make DESTDIR=/build/stage install {install_args}'
        body = f"""
export LIBS="{compat_libs} ${{LIBS:-}}"
if [ ! -x "$SOURCE_DIR/configure" ]; then (cd "$SOURCE_DIR" && autoreconf -fi); fi
CONFIG_SITE=/dev/null "$SOURCE_DIR/configure" --host=wasm32-wasi --prefix=/usr/local --disable-shared --enable-static {configure_args}
python3 /toolchain/patch-gnulib.py "$SOURCE_DIR"
{post_configure}
# Gnulib's compiler-warning probe can mistake WASIX preprocessor output for
# warning flags while cross-compiling. The value only controls diagnostics, so
# clear a malformed result before invoking make.
find /build/work -name Makefile -type f -exec sed -i 's/^GL_CFLAG_GNULIB_WARNINGS =.*/GL_CFLAG_GNULIB_WARNINGS =/' {{}} +
EDGETERM_COMPILE_CFLAGS="$CFLAGS"
EDGETERM_CONFIG_HEADER=""
if [ -f /build/work/config.h ]; then
  EDGETERM_CONFIG_HEADER=/build/work/config.h
else
  EDGETERM_CONFIG_HEADER=$(find /build/work -maxdepth 3 -name config.h -type f -print -quit)
fi
if [ -n "$EDGETERM_CONFIG_HEADER" ] && [ -n "{compat_include}" ]; then
  printf '#include "%s"\n#include "/toolchain/wasix-compat.h"\n' "$EDGETERM_CONFIG_HEADER" > /build/edgeterm-autotools-compat.h
  EDGETERM_COMPILE_CFLAGS="$EDGETERM_COMPILE_CFLAGS -include /build/edgeterm-autotools-compat.h"
elif [ -n "{compat_include}" ]; then
  EDGETERM_COMPILE_CFLAGS="$EDGETERM_COMPILE_CFLAGS {compat_include}"
fi
{autotools_build}
{autotools_install}
"""
    elif port.build_system == "cmake":
        body = f"""
cmake -S "$SOURCE_DIR" -B /build/work/cmake -G Ninja -DCMAKE_TOOLCHAIN_FILE=/toolchain/wasix-toolchain.cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr/local -DBUILD_SHARED_LIBS=OFF {configure_args}
cmake --build /build/work/cmake --parallel "${{BUILD_JOBS:-4}}" {make_args}
DESTDIR=/build/stage cmake --install /build/work/cmake {install_args}
"""
    elif port.build_system == "make":
        install_body = install_commands or f'make -C "$SOURCE_DIR" CC="$CC" CXX="$CXX" AR="$AR" RANLIB="$RANLIB" STRIP="$STRIP" CFLAGS="$CFLAGS" CXXFLAGS="$CXXFLAGS" LDFLAGS="$LDFLAGS" DESTDIR=/build/stage PREFIX=/usr/local {make_args} install {install_args}'
        body = f"""
make -C "$SOURCE_DIR" -j"${{BUILD_JOBS:-4}}" CC="$CC" CXX="$CXX" AR="$AR" RANLIB="$RANLIB" STRIP="$STRIP" CFLAGS="$CFLAGS" CXXFLAGS="$CXXFLAGS" LDFLAGS="$LDFLAGS" {make_args}
{install_body}
"""
    elif port.build_system == "cargo":
        cargo_locked = "--locked" if build.get("locked", True) else ""
        cargo_target = build.get("target", "wasm32-wasip1")
        cargo_target_prepare = (
            f"rustup target add {cargo_target}"
            if cargo_target != "wasm32-wasip1"
            else ":"
        )
        body = f"""
cd "$SOURCE_DIR"
{cargo_target_prepare}
RUSTFLAGS="${{RUSTFLAGS:-}} {rust_flags}" cargo fetch {cargo_locked}
{post_fetch}
RUSTFLAGS="${{RUSTFLAGS:-}} {rust_flags}" cargo build {cargo_locked} --release --target {cargo_target} {make_args}
mkdir -p /build/stage/usr/local/bin
{install_args}
"""
    elif port.build_system == "go":
        body = f"""
cd "$SOURCE_DIR"
GOOS=wasip1 GOARCH=wasm go build -trimpath {make_args}
mkdir -p /build/stage/usr/local/bin
{install_args}
"""
    else:
        commands = build.get("commands", [])
        if not commands:
            raise PortError(f"{port.name}: custom build requires build.commands")
        body = "\n".join(commands) + "\n"
    return common + body + post + "\n" + asyncify


def port_fingerprint(port: Port) -> str:
    digest = hashlib.sha256()
    paths = [
        port.path / "port.toml",
        *sorted(path for path in port.path.iterdir() if path.is_file() and path.name != "port.toml"),
        ROOT / "pipeline/wasix-toolchain.cmake",
        ROOT / "pipeline/patch-gnulib.py",
    ]
    if port.data["build"].get("include_compat", False) or port.data["build"].get("link_compat", False):
        paths.extend([
            ROOT / "pipeline/wasix-compat.c",
            ROOT / "pipeline/wasix-compat.h",
        ])
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def build_port(
    port: Port,
    *,
    ports: dict[str, Port] | None = None,
    dependency_stack: tuple[str, ...] = (),
    allow_cached: bool = False,
) -> Path:
    ports = ports or load_ports()
    if port.name in dependency_stack:
        chain = " -> ".join((*dependency_stack, port.name))
        raise PortError(f"Circular build dependency: {chain}")
    archive = fetch_port(port)
    edge_term = Path(os.environ.get("EDGETERM_CHECKOUT", DEFAULT_EDGETERM))
    sdk = Path(os.environ.get("EDGETERM_WASI_SDK", edge_term / "ports/apt-wasix/.cache/wasi-sdk-33.0-arm64-linux"))
    sysroot = Path(os.environ.get("EDGETERM_WASIX_SYSROOT", edge_term / "ports/apt-wasix/.cache/wasix-sysroot-v2025-11-06.1.tar.gz"))
    binaryen = Path(os.environ.get("EDGETERM_BINARYEN", edge_term / "ports/apt-wasix/.cache/binaryen-version_131-aarch64-linux"))
    if not (sdk / "bin/clang").exists():
        raise PortError(f"WASI SDK 33 was not found: {sdk}")
    if not sysroot.exists():
        raise PortError(f"WASIX sysroot was not found: {sysroot}")
    if port.data["build"].get("asyncify", False) and not (binaryen / "bin/wasm-opt").exists():
        raise PortError(f"Binaryen 131 was not found: {binaryen}")
    build_root = BUILD / port.name
    build_root.mkdir(parents=True, exist_ok=True)
    stage = build_root / "stage"
    marker = build_root / "build-complete.json"
    fingerprint = port_fingerprint(port)
    if allow_cached and marker.is_file() and stage.is_dir():
        cached = json.loads(marker.read_text(encoding="utf-8"))
        if cached.get("fingerprint") == fingerprint:
            try:
                validate_stage(port, stage)
            except PortError:
                marker.unlink(missing_ok=True)
            else:
                return stage

    prefix = build_root / "prefix"
    if prefix.exists():
        shutil.rmtree(prefix)
    prefix.mkdir(parents=True)
    for dependency_name in port.data["build"].get("dependencies", []):
        dependency = ports[dependency_name]
        dependency_stage = build_port(
            dependency,
            ports=ports,
            dependency_stack=(*dependency_stack, port.name),
            allow_cached=True,
        )
        dependency_prefix = dependency_stage / "usr/local"
        if dependency_prefix.is_dir():
            shutil.copytree(dependency_prefix, prefix, dirs_exist_ok=True, symlinks=True)
    script = build_root / "build.sh"
    script.write_text(configure_script(port), encoding="utf-8")
    image = os.environ.get("EDGETERM_BUILD_IMAGE", DEFAULT_IMAGE)
    run_logged([
        "docker", "run", "--rm", "--platform", "linux/arm64",
        "-e", f"BUILD_JOBS={os.environ.get('BUILD_JOBS', '4')}",
        "-v", f"{archive}:/input/source:ro",
        "-v", f"{build_root}:/build",
        "-v", f"{sdk}:/wasi-sdk:ro",
        "-v", f"{sysroot}:/toolchain/sysroot.tar.gz:ro",
        "-v", f"{binaryen}:/binaryen:ro",
        "-v", f"{ROOT / 'pipeline/wasix-toolchain.cmake'}:/toolchain/wasix-toolchain.cmake:ro",
        "-v", f"{ROOT / 'pipeline/wasix-compat.c'}:/toolchain/wasix-compat.c:ro",
        "-v", f"{ROOT / 'pipeline/wasix-compat.h'}:/toolchain/wasix-compat.h:ro",
        "-v", f"{ROOT / 'pipeline/patch-gnulib.py'}:/toolchain/patch-gnulib.py:ro",
        "-v", f"{port.path}:/port:ro",
        image, "bash", "/build/build.sh",
    ], build_root / "build.log")
    if not stage.exists():
        raise PortError(f"{port.name}: build did not create a package staging directory")
    validate_stage(port, stage)
    marker.write_text(json.dumps({
        "schema": "edgeterm.package-build.v1",
        "package": port.name,
        "version": port.deb_version,
        "fingerprint": fingerprint,
    }, indent=2) + "\n", encoding="utf-8")
    return stage


def materialize_package_symlinks(package_root: Path) -> None:
    links = sorted(
        (path for path in package_root.rglob("*") if path.is_symlink()),
        key=lambda path: len(path.parts),
        reverse=True,
    )
    root = package_root.resolve()
    for link in links:
        target = Path(os.readlink(link))
        if target.is_absolute():
            source = package_root / target.relative_to("/")
        else:
            source = link.parent / target
        source = source.resolve()
        if source != root and root not in source.parents:
            raise PortError(f"{link}: package symlink escapes the package root")
        if not source.exists():
            raise PortError(f"{link}: package symlink target does not exist")
        link.unlink()
        if source.is_dir():
            shutil.copytree(source, link, symlinks=False)
        else:
            shutil.copy2(source, link)


def package_port(port: Port) -> Path:
    stage = build_port(port, ports=load_ports(), allow_cached=True)
    package_root = BUILD / port.name / "package-root"
    if package_root.exists():
        shutil.rmtree(package_root)
    copied_inodes: dict[tuple[int, int], Path] = {}

    def copy_preserving_hardlinks(source: str, destination: str) -> str:
        source_path = Path(source)
        destination_path = Path(destination)
        info = source_path.stat()
        key = (info.st_dev, info.st_ino)
        previous = copied_inodes.get(key)
        if previous is not None:
            os.link(previous, destination_path)
        else:
            shutil.copy2(source_path, destination_path)
            copied_inodes[key] = destination_path
        return str(destination_path)

    shutil.copytree(
        stage,
        package_root,
        symlinks=True,
        copy_function=copy_preserving_hardlinks,
    )
    if port.name == "git":
        git_binary = package_root / "usr/local/bin/git"
        git_info = git_binary.stat()
        git_inode = (git_info.st_dev, git_info.st_ino)
        for path in package_root.rglob("*"):
            if path == git_binary or not path.is_file():
                continue
            info = path.stat()
            if (info.st_dev, info.st_ino) != git_inode:
                continue
            command = path.name.removeprefix("git-")
            path.unlink()
            if command == "git":
                script = "#!/bin/sh\nexec /usr/local/bin/git \"$@\"\n"
            else:
                script = f"#!/bin/sh\nexec /usr/local/bin/git {shlex.quote(command)} \"$@\"\n"
            path.write_text(script, encoding="utf-8")
            path.chmod(0o755)
        canonical_files: dict[tuple[int, int], Path] = {}
        for path in sorted(package_root.rglob("*")):
            if not path.is_file():
                continue
            info = path.stat()
            inode = (info.st_dev, info.st_ino)
            canonical = canonical_files.get(inode)
            if canonical is None:
                canonical_files[inode] = path
                continue
            target = "/" + canonical.relative_to(package_root).as_posix()
            path.unlink()
            path.write_text(
                f"#!/bin/sh\nexec {shlex.quote(target)} \"$@\"\n",
                encoding="utf-8",
            )
            path.chmod(0o755)
    materialize_package_symlinks(package_root)
    control = package_root / "DEBIAN"
    control.mkdir(parents=True, exist_ok=True)
    depends = ", ".join(port.data["package"].get("depends", []))
    installed_inodes: set[tuple[int, int]] = set()
    installed_bytes = 0
    for path in package_root.rglob("*"):
        if not path.is_file():
            continue
        info = path.stat()
        key = (info.st_dev, info.st_ino)
        if key in installed_inodes:
            continue
        installed_inodes.add(key)
        installed_bytes += info.st_size
    installed_size = installed_bytes // 1024 + 1
    fields = [
        f"Package: {port.name}",
        f"Version: {port.deb_version}",
        "Architecture: wasm32-wasix",
        f"Installed-Size: {installed_size}",
        "Maintainer: DigitalPlat <packages@digitalplat.org>",
        f"Homepage: {port.data['package']['homepage']}",
        f"Description: {port.data['package']['description']}",
    ]
    if depends:
        fields.insert(3, f"Depends: {depends}")
    (control / "control").write_text("\n".join(fields) + "\n", encoding="utf-8")
    metadata = package_root / "usr/local/share/edgeterm/commands"
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / f"{port.name}.json").write_text(json.dumps({
        "schema": "edgeterm.package-commands.v1",
        "package": port.name,
        "version": port.deb_version,
        "commands": port.data["runtime"]["commands"],
        "mode": port.data["runtime"]["mode"],
        "capability": port.data["runtime"]["capability"],
    }, indent=2) + "\n", encoding="utf-8")
    sbom = package_root / "usr/share/doc" / port.name
    sbom.mkdir(parents=True, exist_ok=True)
    source_root = BUILD / port.name / "source-root"
    source_directory = next((path for path in source_root.iterdir() if path.is_dir()), source_root)
    declared_license = port.data["package"].get("license_file")
    if declared_license:
        license_path = (source_directory / declared_license).resolve()
        if source_directory.resolve() not in license_path.parents or not license_path.is_file():
            raise PortError(f"{port.name}: declared license file is invalid")
        license_candidates = [license_path]
    else:
        license_candidates = sorted(
            (
                path
                for pattern in ("COPYING*", "LICENSE*", "Copyright*")
                for path in source_root.rglob(pattern)
                if path.is_file() and not path.is_symlink()
            ),
            key=lambda path: (len(path.relative_to(source_root).parts), len(path.name), path.name),
        )
    if not license_candidates:
        raise PortError(f"{port.name}: upstream license file was not found")
    shutil.copyfile(license_candidates[0], sbom / "copyright")
    (sbom / "source.json").write_text(json.dumps({
        "url": port.source_url,
        "sha256": port.source_sha256,
        "version": port.version,
    }, indent=2) + "\n", encoding="utf-8")
    (sbom / "patches.json").write_text(json.dumps([
        {"name": patch.name, "sha256": hash_file(patch)}
        for patch in sorted(port.path.glob("*.patch"))
    ], indent=2) + "\n", encoding="utf-8")
    (sbom / "sbom.cdx.json").write_text(json.dumps({
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [{
            "type": "application",
            "name": port.name,
            "version": port.version,
            "licenses": [{"license": {"id": port.data["package"]["license"]}}],
            "externalReferences": [{"type": "distribution", "url": port.source_url}],
            "hashes": [{"alg": "SHA-256", "content": port.source_sha256}],
        }],
    }, indent=2) + "\n", encoding="utf-8")
    timestamp = int(SOURCE_DATE_EPOCH)
    for path in [package_root, *package_root.rglob("*")]:
        os.utime(path, (timestamp, timestamp), follow_symlinks=False)
    DIST.mkdir(parents=True, exist_ok=True)
    output = DIST / f"{port.name}_{port.deb_version}_wasm32-wasix.deb"
    image = os.environ.get("EDGETERM_BUILD_IMAGE", DEFAULT_IMAGE)
    run([
        "docker", "run", "--rm", "--platform", "linux/arm64",
        "-e", f"SOURCE_DATE_EPOCH={SOURCE_DATE_EPOCH}",
        "-v", f"{package_root}:/stage:ro",
        "-v", f"{DIST}:/dist",
        image, "dpkg-deb", "--root-owner-group", "--build", "/stage", f"/dist/{output.name}",
    ])
    return output


def list_ports(ports: dict[str, Port]) -> None:
    for port in ports.values():
        if not port.user_visible:
            continue
        runtime = port.data["runtime"]
        print(f"{port.name:20} {port.version:12} {runtime['capability']:14} {runtime['mode']:15} {', '.join(runtime['commands'])}")


def process_batch(action: str, batch_name: str, ports: dict[str, Port]) -> Path:
    batches = load_batches(ports)
    if batch_name not in batches:
        raise PortError(f"Unknown batch: {batch_name}")
    report = {"schema": "edgeterm.package-build-report.v1", "batch": batch_name, "action": action, "packages": []}
    failed = False
    for name in batches[batch_name]:
        entry = {"name": name, "status": "running"}
        report["packages"].append(entry)
        try:
            port = ports[name]
            output = build_port(port) if action == "build-batch" else package_port(port)
            entry.update(status="passed", output=str(output))
        except (PortError, subprocess.CalledProcessError) as error:
            failed = True
            entry.update(status="failed", error=str(error))
    REPORTS.mkdir(parents=True, exist_ok=True)
    output = REPORTS / f"{batch_name}-{action}.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if failed:
        raise PortError(f"Batch {batch_name} has failed packages; see {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build EdgeTerm WASIX packages")
    parser.add_argument("action", choices=["validate", "list", "fetch", "image", "build", "package", "build-batch", "package-batch"])
    parser.add_argument("package", nargs="?")
    args = parser.parse_args()
    ports = load_ports()
    validate_catalog(ports)
    load_batches(ports)
    if args.action == "validate":
        visible_count = sum(port.user_visible for port in ports.values())
        build_only_count = len(ports) - visible_count
        print(f"Validated {visible_count} user-visible package manifests and {build_only_count} build-only dependencies.")
    elif args.action == "list":
        list_ports(ports)
    elif args.action == "image":
        build_image()
    elif args.action in {"build-batch", "package-batch"}:
        if not args.package:
            raise PortError(f"{args.action} requires a batch name")
        print(process_batch(args.action, args.package, ports))
    else:
        if not args.package:
            raise PortError(f"{args.action} requires a package name")
        port = resolve_port(args.package, ports)
        if args.action == "fetch":
            print(fetch_port(port))
        elif args.action == "build":
            print(build_port(port))
        elif args.action == "package":
            print(package_port(port))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PortError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(2)
