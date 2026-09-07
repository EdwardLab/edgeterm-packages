#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import inspect
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
DEFAULT_POSIX = ROOT / "vendor/edgeterm-posix"
DEFAULT_TOOLCHAIN_CACHE = ROOT / ".cache/edgeterm-apt-wasix"
DEFAULT_IMAGE = "edgeterm-packages:2026-08-05"
WASIX_RUST_RELEASE = "v2026-08-06.1+rust-1.97"
WASIX_RUST_COMMIT = "c232cba7f1b5eed80cab239ff39cbc2399e76d9d"
WASIX_RUST_ARCHIVE_SHA256 = "f2afe91abc89eee333a9963394b6d5ac1dc61b790b4b4eefe3c73644cb11a8c5"
WASIX_RUST_ARCHIVE_URL = (
    "https://github.com/wasix-org/rust/releases/download/"
    "v2026-08-06.1%2Brust-1.97/rust-toolchain-aarch64-unknown-linux-gnu.tar.gz"
)
WASIX_RUST_CACHE = CACHE / "wasix-rust"
WASIX_RUST_ARCHIVE = WASIX_RUST_CACHE / (
    "rust-toolchain-aarch64-unknown-linux-gnu-v2026-08-06.1-rust-1.97.tar.gz"
)
WASIX_RUST_ROOT = WASIX_RUST_CACHE / "v2026-08-06.1-rust-1.97-aarch64-linux"
WASIX_RUST_SOURCE = WASIX_RUST_CACHE / "rust-src-v2026-08-06.1-rust-1.97"
SOURCE_DATE_EPOCH = "1704067200"
PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9+.-]*$")
COMMAND_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9+._-]*$")
CPP_MACRO_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SOURCE_SUBDIRECTORY = re.compile(r"^[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)*$")
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
    source_subdirectory = build.get("source_subdirectory")
    if source_subdirectory is not None and (
        not isinstance(source_subdirectory, str)
        or not SOURCE_SUBDIRECTORY.fullmatch(source_subdirectory)
        or any(part in {".", ".."} for part in source_subdirectory.split("/"))
    ):
        raise PortError(f"{port.path}: build.source_subdirectory must be a safe relative path")
    if "shadow_source" in build and not isinstance(build["shadow_source"], bool):
        raise PortError(f"{port.path}: build.shadow_source must be a boolean")
    if "main_with_environment" in build and not isinstance(build["main_with_environment"], bool):
        raise PortError(f"{port.path}: build.main_with_environment must be a boolean")
    config_undefines = build.get("config_undefines", [])
    if not isinstance(config_undefines, list) or not all(
        isinstance(item, str) and CPP_MACRO_NAME.fullmatch(item)
        for item in config_undefines
    ):
        raise PortError(f"{port.path}: build.config_undefines must contain C macro names")
    config_defines = build.get("config_defines", {})
    if not isinstance(config_defines, dict) or not all(
        isinstance(name, str)
        and CPP_MACRO_NAME.fullmatch(name)
        and isinstance(value, str)
        and "\n" not in value
        for name, value in config_defines.items()
    ):
        raise PortError(f"{port.path}: build.config_defines must map C macro names to single-line values")
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
        exec_dependencies = runtime.get(
            "exec_dependencies",
            runtime.get("bundle_dependencies", []),
        )
        if not isinstance(exec_dependencies, list) or not all(
            isinstance(item, str) and PACKAGE_NAME.fullmatch(item) for item in exec_dependencies
        ):
            raise PortError(f"{port.path}: runtime.exec_dependencies must contain package names")
        aliases = runtime.get("command_aliases", {})
        if not isinstance(aliases, dict):
            raise PortError(f"{port.path}: runtime.command_aliases must be a table")
        for command, alias in aliases.items():
            if command not in commands or not isinstance(alias, dict):
                raise PortError(f"{port.path}: invalid runtime command alias {command}")
            target = alias.get("target")
            arguments = alias.get("args", [])
            if target not in commands or target == command:
                raise PortError(f"{port.path}: invalid target for runtime command alias {command}")
            if not isinstance(arguments, list) or not all(
                isinstance(argument, str) and argument and "\n" not in argument
                for argument in arguments
            ):
                raise PortError(f"{port.path}: invalid arguments for runtime command alias {command}")
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
    if len(visible_ports) < 100:
        raise PortError(f"Expected at least 100 user-visible packages, found {len(visible_ports)}")
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
        runtime = port.data.get("runtime", {})
        exec_dependencies = runtime.get(
            "exec_dependencies",
            runtime.get("bundle_dependencies", []),
        )
        for dependency in exec_dependencies:
            if dependency not in ports:
                raise PortError(f"{port.name}: unknown runtime executable dependency {dependency}")
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


def refresh_rust_target_cache(
    build_root: Path,
    target_name: str,
    compatibility_inputs: list[Path],
) -> bool:
    digest = hashlib.sha256()
    digest.update(WASIX_RUST_RELEASE.encode("utf-8"))
    for path in sorted(set(compatibility_inputs), key=str):
        if not path.is_file():
            continue
        digest.update(str(path).encode("utf-8"))
        digest.update(path.read_bytes())
    fingerprint = digest.hexdigest()
    marker = build_root / "rust-target-abi.json"
    previous: dict[str, object] = {}
    if marker.is_file():
        try:
            previous = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            previous = {}
    changed = (
        previous.get("fingerprint") != fingerprint
        or previous.get("target") != target_name
    )
    if changed:
        shutil.rmtree(build_root / "cargo-target" / target_name, ignore_errors=True)
    marker.write_text(
        json.dumps(
            {
                "schema": "edgeterm.rust-target-abi.v1",
                "target": target_name,
                "fingerprint": fingerprint,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return changed


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


def download_pinned_file(url: str, sha256: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and hash_file(destination) == sha256:
        return
    destination.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "EdgeTerm-Packages/1"})
    with urllib.request.urlopen(request, timeout=300) as response, tempfile.NamedTemporaryFile(
        dir=destination.parent, delete=False
    ) as output:
        shutil.copyfileobj(response, output)
        temporary = Path(output.name)
    actual = hash_file(temporary)
    if actual != sha256:
        temporary.unlink(missing_ok=True)
        raise PortError(f"Pinned toolchain checksum mismatch: expected {sha256}, received {actual}")
    temporary.replace(destination)


def ensure_wasix_rust_toolchain() -> Path:
    rustc = WASIX_RUST_ROOT / "bin/rustc"
    library = WASIX_RUST_ROOT / "lib/rustlib/src/rust/library"
    process_module = library / "std/src/os/wasi/process.rs"
    backtrace = library / "backtrace/src/lib.rs"
    if rustc.is_file() and process_module.is_file() and backtrace.is_file():
        return WASIX_RUST_ROOT

    download_pinned_file(WASIX_RUST_ARCHIVE_URL, WASIX_RUST_ARCHIVE_SHA256, WASIX_RUST_ARCHIVE)
    WASIX_RUST_ROOT.mkdir(parents=True, exist_ok=True)
    with tarfile.open(WASIX_RUST_ARCHIVE, "r:gz") as archive:
        archive.extractall(WASIX_RUST_ROOT, filter="data")
    for executable in (WASIX_RUST_ROOT / "bin").iterdir():
        executable.chmod(executable.stat().st_mode | 0o111)

    if not (WASIX_RUST_SOURCE / ".git").is_dir():
        WASIX_RUST_SOURCE.mkdir(parents=True, exist_ok=True)
        run(["git", "init"], cwd=WASIX_RUST_SOURCE)
        run(["git", "remote", "add", "origin", "https://github.com/wasix-org/rust.git"], cwd=WASIX_RUST_SOURCE)
        run(["git", "sparse-checkout", "init", "--cone"], cwd=WASIX_RUST_SOURCE)
        run(["git", "sparse-checkout", "set", "library"], cwd=WASIX_RUST_SOURCE)
        run(["git", "fetch", "--depth", "1", "origin", WASIX_RUST_COMMIT], cwd=WASIX_RUST_SOURCE)
        run(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=WASIX_RUST_SOURCE)
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=WASIX_RUST_SOURCE, text=True
    ).strip()
    if source_commit != WASIX_RUST_COMMIT:
        raise PortError(f"WASIX Rust source cache is at unexpected commit {source_commit}")
    run(["git", "submodule", "update", "--init", "--depth", "1", "library/backtrace"], cwd=WASIX_RUST_SOURCE)
    shutil.copytree(WASIX_RUST_SOURCE / "library", library, dirs_exist_ok=True, symlinks=True)
    if not rustc.is_file() or not process_module.is_file() or not backtrace.is_file():
        raise PortError("Pinned WASIX Rust toolchain is incomplete")
    return WASIX_RUST_ROOT


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def run_logged(command: list[str], log_path: Path) -> None:
    print("+", " ".join(command), flush=True)
    print(f"  build log: {log_path}", flush=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def runtime_semver(version: str) -> str:
    numeric_parts = [str(int(part)) for part in re.findall(r"\d+", version)]
    if not numeric_parts:
        raise PortError(f"runtime bundle version has no numeric component: {version}")
    core = (numeric_parts + ["0", "0"])[:3]
    suffix = numeric_parts[3:]
    normalized = ".".join(core)
    if suffix:
        normalized += "-" + ".".join(suffix)
    return normalized


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
        if not os.access(resolved, os.X_OK):
            invalid.append(f"{command} (not executable)")
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


def extraction_command(archive: Path, raw: bool = False) -> str:
    name = archive.name
    if raw:
        return f"cp /input/source /build/source-root/{shlex.quote(name)}"
    if name.endswith(".zip"):
        return "unzip -q /input/source -d /build/source-root"
    if name.endswith(".tar.lz"):
        return "tar --lzip -xf /input/source -C /build/source-root"
    return "tar -xf /input/source -C /build/source-root"


def configure_script(port: Port) -> str:
    build = port.data["build"]
    source_subdirectory = build.get("source_subdirectory", "")
    shadow_source = build.get("shadow_source", False)
    build_in_source_copy = build.get("build_in_source_copy", False)
    configure_args = " ".join(build.get("configure_args", []))
    make_args = " ".join(build.get("make_args", []))
    install_args = " ".join(build.get("install_args", []))
    build_commands = "\n".join(build.get("build_commands", []))
    install_commands = "\n".join(build.get("install_commands", []))
    pre = "\n".join(build.get("pre", []))
    post_configure = "\n".join(build.get("post_configure", []))
    post_fetch = "\n".join(build.get("post_fetch", []))
    post = "\n".join(build.get("post", []))
    config_override_lines: list[str] = []
    for name in build.get("config_undefines", []):
        config_override_lines.append(f"#undef {name}")
    for name, value in build.get("config_defines", {}).items():
        config_override_lines.extend((f"#undef {name}", f"#define {name} {value}"))
    config_overrides = ""
    if config_override_lines:
        payload = "\\n".join(config_override_lines) + "\\n"
        config_overrides = (
            'test -n "$EDGETERM_CONFIG_HEADER"\n'
            f"printf '%b' {shlex.quote(payload)} >> \"$EDGETERM_CONFIG_HEADER\""
        )
    if build.get("asyncify", False) and build.get("asyncify_safe", False):
        asyncify_flags = ""
    elif build.get("asyncify", False):
        asyncify_flags = r'''\
    --pass-arg=asyncify-ignore-indirect \
    --pass-arg=asyncify-addlist@edgeterm_vfork \
    --pass-arg=asyncify-propagate-addlist'''
    else:
        asyncify_flags = "    --pass-arg=asyncify-ignore-indirect"
    asyncify = r'''
while IFS= read -r executable; do
  transform=__EDGETERM_FORCE_ASYNCIFY__
  if [ "$transform" != 1 ]; then
    inspection="${executable}.wat"
    if /binaryen/bin/wasm-dis "$executable" -o "$inspection" 2>/dev/null && \
       grep -q '"stack_checkpoint"' "$inspection"; then
      transform=1
    fi
    rm -f "$inspection"
  fi
  [ "$transform" = 1 ] || continue
  transformed="${executable}.asyncify"
  if ! /binaryen/bin/wasm-opt \
    --enable-reference-types \
    --enable-bulk-memory \
    __EDGETERM_ASYNCIFY_FLAGS__ \
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
  chmod --reference="$executable" "$transformed"
  mv "$transformed" "$executable"
done < <(find /build/stage/usr/local/bin /build/stage/usr/local/sbin \
  -type f -perm -0100 -exec file {} \; 2>/dev/null | sed -n 's/: WebAssembly.*//p')
'''.replace("__EDGETERM_ASYNCIFY_FLAGS__", asyncify_flags).replace(
        "__EDGETERM_FORCE_ASYNCIFY__",
        "1" if build.get("asyncify", False) else "0",
    )
    posix_link = "-Wl,--whole-archive /build/edgeterm-posix/lib/libedgeterm-posix.a -Wl,--no-whole-archive -Wl,--wrap=open -Wl,--wrap=openat -Wl,--wrap=poll"
    posix_include = "-isystem /build/edgeterm-posix/include"
    thread_flags = "-pthread" if build.get("threads", False) else ""
    thread_ldflags = (
        "-pthread -Wl,--initial-memory=16777216 -Wl,--max-memory=268435456"
        if build.get("threads", False)
        else ""
    )
    compat_thread_define = "-DEDGETERM_POSIX_THREADS" if build.get("threads", False) else ""
    mman_cflags = "-D_WASI_EMULATED_MMAN" if build.get("emulated_mman", False) else ""
    mman_ldflags = "-lwasi-emulated-mman" if build.get("emulated_mman", False) else ""
    rust_posix_source = build.get("rust_unix", False)
    rust_libc_wasix = build.get("rust_libc_wasix", False)
    rust_rand_os_wasi = build.get("rust_rand_os_wasi", False)
    rust_wasix_toolchain = build.get("rust_wasix_toolchain", False)
    main_env_post_configure = ""
    if build.get("main_with_environment", False):
        main_env_post_configure = r'''
find /build/work -name Makefile -type f -exec \
  sed -i 's|^CPPFLAGS =\(.*\)$|CPPFLAGS =\1 -Dmain=edgeterm_main_with_env|' {} +
find /build/work -name Makefile -type f -exec \
  sed -i 's|^LDFLAGS =\(.*\)$|LDFLAGS =\1 /build/edgeterm-posix/lib/libedgeterm-main-env.a|' {} +
'''
    common = """
set -euo pipefail
mkdir -p /build/source-root /build/work /build/stage /build/prefix /toolchain/sysroot
find /build/source-root /build/work /build/stage \
  -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
__EDGETERM_EXTRACT__
SOURCE_ROOT=/build/source-root
TOP_LEVEL_DIRECTORY=$(find /build/source-root -mindepth 1 -maxdepth 1 -type d -print -quit)
TOP_LEVEL_FILE=$(find /build/source-root -mindepth 1 -maxdepth 1 -type f -print -quit)
TOP_LEVEL_DIRECTORY_COUNT=$(find /build/source-root -mindepth 1 -maxdepth 1 -type d | wc -l)
if [ "$TOP_LEVEL_DIRECTORY_COUNT" -eq 1 ] && [ -z "$TOP_LEVEL_FILE" ]; then
  SOURCE_ROOT=$TOP_LEVEL_DIRECTORY
fi
if [ "${EDGETERM_PRISTINE_SOURCE:-0}" = 1 ]; then
  python3 /toolchain/edgeterm-posix/scripts/source-integrity.py \
    snapshot "$SOURCE_ROOT" /build/source-integrity.json
else
  python3 /toolchain/edgeterm-posix/scripts/normalize-source.py "$SOURCE_ROOT"
  for patch_file in /port/*.patch; do
    [ -f "$patch_file" ] || continue
    case ",${EDGETERM_SKIP_PATCHES:-}," in
      *,"$(basename "$patch_file")",*) continue ;;
    esac
    patch -d "$SOURCE_ROOT" -p1 < "$patch_file"
  done
fi
SOURCE_DIR="$SOURCE_ROOT"
BUILD_DIR=/build/work
if [ -n "__EDGETERM_SOURCE_SUBDIRECTORY__" ]; then
  SOURCE_DIR="$SOURCE_ROOT/__EDGETERM_SOURCE_SUBDIRECTORY__"
  [ -d "$SOURCE_DIR" ] || {
    echo "Declared source subdirectory does not exist: __EDGETERM_SOURCE_SUBDIRECTORY__" >&2
    exit 1
  }
fi
if [ "__EDGETERM_SHADOW_SOURCE__" = 1 ]; then
  SHADOW_SOURCE=/build/work/source
  mkdir -p "$SHADOW_SOURCE"
  cp -a "$SOURCE_DIR"/. "$SHADOW_SOURCE"/
  SOURCE_DIR="$SHADOW_SOURCE"
fi
if [ "__EDGETERM_BUILD_IN_SOURCE_COPY__" = 1 ]; then
  [ "__EDGETERM_SHADOW_SOURCE__" = 1 ] || {
    echo "build_in_source_copy requires shadow_source" >&2
    exit 1
  }
  BUILD_DIR="$SOURCE_DIR"
fi
tar -xzf /toolchain/sysroot.tar.gz -C /toolchain/sysroot
export WASIX_SYSROOT=$(find /toolchain/sysroot -mindepth 2 -maxdepth 2 -type d -name sysroot -print -quit)
/toolchain/edgeterm-posix/scripts/prepare-sysroot.sh "$WASIX_SYSROOT"
export WASI_SDK_BIN=/wasi-sdk/bin
export EDGETERM_PREFIX=/build/prefix
export CARGO_HOME=/build/cargo-home
export SOURCE_DATE_EPOCH=__EDGETERM_SOURCE_DATE_EPOCH__
export CC="$WASI_SDK_BIN/clang --target=wasm32-wasip1 --sysroot=$WASIX_SYSROOT"
export CXX="$WASI_SDK_BIN/clang++ --target=wasm32-wasip1 --sysroot=$WASIX_SYSROOT"
export AR="$WASI_SDK_BIN/llvm-ar"
export RANLIB="$WASI_SDK_BIN/llvm-ranlib"
export STRIP="$WASI_SDK_BIN/llvm-strip"
export MAKEINFO=true
export PKG_CONFIG_PATH=/build/prefix/lib/pkgconfig:/build/prefix/share/pkgconfig
export PKG_CONFIG_SYSROOT_DIR="$WASIX_SYSROOT"
export PKG_CONFIG_LIBDIR=/build/prefix/lib/pkgconfig:/build/prefix/share/pkgconfig:$WASIX_SYSROOT/lib/wasm32-wasip1/pkgconfig:$WASIX_SYSROOT/share/pkgconfig
EDGETERM_POSIX_BUILD_DIR=/build/edgeterm-posix-build \
CC="$WASI_SDK_BIN/clang" AR="$WASI_SDK_BIN/llvm-ar" \
CFLAGS="--target=wasm32-wasip1 --sysroot=$WASIX_SYSROOT -O2 __EDGETERM_THREAD_FLAGS__ __EDGETERM_COMPAT_THREAD_DEFINE__" \
  /toolchain/edgeterm-posix/scripts/build.sh --prefix /build/edgeterm-posix
export EDGETERM_POSIX_PREFIX=/build/edgeterm-posix
export EDGETERM_POSIX_FLAGS_IN_ENV=1
export CPPFLAGS="${CPPFLAGS:-} -I/build/prefix/include -isystem $EDGETERM_POSIX_PREFIX/include"
export CFLAGS="${CFLAGS:-} -O2 -I/build/prefix/include -D_WASI_EMULATED_PROCESS_CLOCKS __EDGETERM_THREAD_FLAGS__ __EDGETERM_MMAN_CFLAGS__ __EDGETERM_POSIX_INCLUDE__"
export CXXFLAGS="${CXXFLAGS:-} -O2 -I/build/prefix/include -D_WASI_EMULATED_PROCESS_CLOCKS __EDGETERM_THREAD_FLAGS__ __EDGETERM_MMAN_CFLAGS__ __EDGETERM_POSIX_INCLUDE__"
export LDFLAGS="${LDFLAGS:-} -static -L/build/prefix/lib __EDGETERM_THREAD_LDFLAGS__ -Wl,--export=__stack_pointer -Wl,--export=__heap_base -Wl,--export=__data_end __EDGETERM_POSIX_LDFLAGS__ -lwasi-emulated-process-clocks __EDGETERM_MMAN_LDFLAGS__"
cd "$BUILD_DIR"
__EDGETERM_PRE__
if [ "${EDGETERM_PRISTINE_SOURCE:-0}" = 1 ]; then
  python3 /toolchain/edgeterm-posix/scripts/source-integrity.py \
    verify "$SOURCE_ROOT" /build/source-integrity.json
fi
""".replace(
        "__EDGETERM_EXTRACT__",
        extraction_command(source_path(port), port.data["source"].get("raw", False)),
    ).replace(
        "__EDGETERM_PRE__", pre
    ).replace(
        "__EDGETERM_SOURCE_SUBDIRECTORY__", source_subdirectory
    ).replace(
        "__EDGETERM_SHADOW_SOURCE__", "1" if shadow_source else "0"
    ).replace(
        "__EDGETERM_BUILD_IN_SOURCE_COPY__", "1" if build_in_source_copy else "0"
    ).replace("__EDGETERM_POSIX_LDFLAGS__", posix_link).replace(
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
    ).replace("__EDGETERM_POSIX_INCLUDE__", posix_include)
    if port.build_system == "autotools":
        autotools_build = build_commands or f'make -j"${{BUILD_JOBS:-4}}" MAKEINFO=true {make_args}'
        autotools_install = install_commands or f'make MAKEINFO=true DESTDIR=/build/stage install {install_args}'
        body = f"""
export LIBS="${{LIBS:-}}"
if [ ! -x "$SOURCE_DIR/configure" ]; then
  AUTORECONF_SOURCE=/build/work/autoreconf-source
  mkdir -p "$AUTORECONF_SOURCE"
  cp -a "$SOURCE_DIR"/. "$AUTORECONF_SOURCE"/
  SOURCE_DIR="$AUTORECONF_SOURCE"
  (cd "$SOURCE_DIR" && autoreconf -fi)
fi
if [ "${{EDGETERM_PRISTINE_SOURCE:-0}}" = 1 ] && \
   find "$SOURCE_DIR" -type f -name config.sub -print -quit | grep -q .; then
  case "$SOURCE_DIR" in
    /build/work/*) ;;
    *)
      CONFIG_SUB_SOURCE=/build/work/config-sub-source
      mkdir -p "$CONFIG_SUB_SOURCE"
      cp -a "$SOURCE_DIR"/. "$CONFIG_SUB_SOURCE"/
      SOURCE_DIR="$CONFIG_SUB_SOURCE"
      ;;
  esac
  find "$SOURCE_DIR" -type f -name config.sub -exec \
    install -m 755 /usr/share/misc/config.sub {{}} \\;
fi
CONFIG_GUESS=$(find "$SOURCE_DIR" -type f -name config.guess -print -quit)
if [ -n "$CONFIG_GUESS" ]; then
  if [ -x "$CONFIG_GUESS" ]; then
    BUILD_TRIPLET=$("$CONFIG_GUESS")
  else
    BUILD_TRIPLET=$(sh "$CONFIG_GUESS")
  fi
else
  BUILD_TRIPLET=aarch64-unknown-linux-gnu
fi
CONFIG_SITE=/toolchain/edgeterm-posix/config/config.site "$SOURCE_DIR/configure" \
  --build="$BUILD_TRIPLET" --host=wasm32-wasi \
  --prefix=/usr/local --disable-shared --enable-static {configure_args}
if [ "${{EDGETERM_PRISTINE_SOURCE:-0}}" != 1 ]; then
  python3 /toolchain/patch-gnulib.py "$SOURCE_DIR"
fi
{post_configure}
{main_env_post_configure}
python3 /toolchain/edgeterm-posix/scripts/ensure-build-profile.py "$BUILD_DIR" \
  --link-flags "-Wl,--initial-memory=16777216 -Wl,--max-memory=268435456 \
  -Wl,--export=__stack_pointer -Wl,--export=__heap_base -Wl,--export=__data_end \
  {posix_link} -lwasi-emulated-process-clocks {mman_ldflags}"
# Gnulib's compiler-warning probe can mistake WASIX preprocessor output for
# warning flags while cross-compiling. The value only controls diagnostics, so
# clear a malformed result before invoking make.
find /build/work -name Makefile -type f -exec sed -i 's/^GL_CFLAG_GNULIB_WARNINGS =.*/GL_CFLAG_GNULIB_WARNINGS =/' {{}} +
if [ "${{EDGETERM_PRISTINE_SOURCE:-0}}" = 1 ]; then
  find "$SOURCE_DIR" -type f -name '*.info' -exec touch {{}} +
fi
EDGETERM_CONFIG_HEADER=""
if [ -f "$BUILD_DIR/config.h" ]; then
  EDGETERM_CONFIG_HEADER="$BUILD_DIR/config.h"
else
  EDGETERM_CONFIG_HEADER=$(find "$BUILD_DIR" -maxdepth 3 -name config.h -type f -print -quit)
fi
{config_overrides}
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
        cargo_install_args = install_args.replace("target/", '"$CARGO_TARGET_DIR"/')
        cargo_target_prepare = (
            f"rustup target add {cargo_target}"
            if cargo_target != "wasm32-wasip1" and not rust_wasix_toolchain
            else ":"
        )
        rust_toolchain_env = ""
        cargo_unstable_flags = ""
        if rust_wasix_toolchain:
            rust_toolchain_env = r'''
export RUSTC=/wasix-rust/bin/rustc
export RUSTDOC=/wasix-rust/bin/rustdoc
export RUSTC_BOOTSTRAP=1
'''
            cargo_unstable_flags = "-Z build-std=std,panic_abort -Z build-std-features="
            if cargo_target.endswith(".json"):
                cargo_unstable_flags += " -Z json-target-spec"
        rust_libc_prepare = ""
        rust_libc_config = ""
        rust_rand_os_prepare = ""
        rust_singlethread_prepare = ""
        rust_singlethread_flags = ""
        rust_singlethread_env = ""
        rust_threaded_prepare = ""
        rust_threaded_flags = ""
        rust_threaded_env = ""
        if cargo_target.endswith("/singlethread/wasm32-wasmer-wasi.json"):
            rust_singlethread_prepare = r'''
mkdir -p /build/rust-wasix-sysroot
tar -xzf /toolchain/sysroot.tar.gz -C /build/rust-wasix-sysroot
/wasi-sdk/bin/clang --target=wasm32-wasi -O2 -c \
  /toolchain/edgeterm-posix/src/rust/wasix-singlethread.s \
  -o /build/wasix-singlethread.o
/wasi-sdk/bin/clang --target=wasm32-wasi -O2 -nostdlib -c \
  /toolchain/edgeterm-posix/src/rust/wasix-singlethread-crt1.c \
  -o /build/edgeterm-rust-crt1.o
'''
            rust_singlethread_flags = (
                "-L native=/build/rust-wasix-sysroot/wasix-sysroot/sysroot/lib/wasm32-wasi "
                "-C link-arg=/build/edgeterm-rust-crt1.o "
                "-C link-arg=/build/wasix-singlethread.o"
            )
            rust_singlethread_env = (
                'export RUSTFLAGS="${RUSTFLAGS:-} --cfg edgeterm_singlethread '
                '-Aunexpected_cfgs -C link-self-contained=no '
                '-L native=/build/rust-wasix-sysroot/wasix-sysroot/sysroot/lib/wasm32-wasi '
                '-C link-arg=/build/edgeterm-rust-crt1.o '
                '-C link-arg=/build/wasix-singlethread.o"'
            )
        elif cargo_target.endswith("/threaded/wasm32-wasmer-wasi.json"):
            rust_threaded_prepare = r'''
mkdir -p /build/rust-wasix-sysroot
tar -xzf /toolchain/sysroot.tar.gz -C /build/rust-wasix-sysroot
'''
            rust_threaded_flags = (
                "-L native=/build/rust-wasix-sysroot/wasix-sysroot/sysroot/lib/wasm32-wasi "
                "-C link-arg=/build/rust-wasix-sysroot/wasix-sysroot/sysroot/lib/wasm32-wasi/crt1-command.o"
            )
            rust_threaded_env = (
                'export RUSTFLAGS="${RUSTFLAGS:-} -C link-self-contained=no '
                '-L native=/build/rust-wasix-sysroot/wasix-sysroot/sysroot/lib/wasm32-wasi '
                '-C link-arg=/build/rust-wasix-sysroot/wasix-sysroot/sysroot/lib/wasm32-wasi/crt1-command.o"'
            )
        if rust_libc_wasix:
            rust_libc_extra_path = (
                " --extra-path /build/rust-compat/rand_os" if rust_rand_os_wasi else ""
            )
            rust_libc_prepare = r'''
python3 /toolchain/edgeterm-posix/scripts/prepare-rust-libc-overlay.py \
  --cargo-home "$CARGO_HOME" \
  --lockfile "$SOURCE_DIR/Cargo.lock" \
  --output-root /build/rust-compat/libc \
  --apply-in-place__EDGETERM_LIBC_EXTRA_PATH__
'''.replace("__EDGETERM_LIBC_EXTRA_PATH__", rust_libc_extra_path)
            rust_libc_config = "--config /build/rust-compat/libc/cargo-config.toml"
        if rust_rand_os_wasi:
            rust_rand_os_prepare = r'''
python3 /toolchain/edgeterm-posix/scripts/prepare-rust-rand-os-overlay.py \
  --cargo-home "$CARGO_HOME" \
  --output /build/rust-compat/rand_os
'''
            if not rust_libc_wasix:
                rust_libc_config = "--config 'paths=[\"/build/rust-compat/rand_os\"]'"
        rust_posix_env = ""
        rust_posix_manifest_prepare = ""
        rust_posix_dependency_prepare = ""
        if rust_posix_source:
            rust_posix_env = (
                "export RUSTC_WRAPPER=/toolchain/edgeterm-posix/scripts/rustc-posix-wrapper.py\n"
                'export EDGETERM_RUST_WORKSPACE="$SOURCE_DIR"'
            )
            rust_posix_manifest_prepare = (
                "python3 /toolchain/edgeterm-posix/scripts/prepare-rust-posix-source.py "
                '"$SOURCE_DIR"'
            )
            rust_posix_dependency_prepare = r'''
python3 /toolchain/edgeterm-posix/scripts/prepare-rust-crate-overlays.py \
  --cargo-home "$CARGO_HOME" \
  --lockfile "$SOURCE_DIR/Cargo.lock" \
  --posix-root /toolchain/edgeterm-posix \
  --profile /toolchain/edgeterm-posix/config/rust-overlays.json \
  --output /build/rust-compat/dependency-overlays.json
'''
        cargo_build = (
            f"cargo build {cargo_unstable_flags} {rust_libc_config} {cargo_locked} --release "
            f"--target {cargo_target} {make_args}"
        )
        body = f"""
cd "$SOURCE_DIR"
export CARGO_TARGET_DIR=/build/cargo-target
{rust_toolchain_env}
{cargo_target_prepare}
{rust_posix_manifest_prepare}
cargo fetch {cargo_locked}
{rust_posix_dependency_prepare}
{post_fetch}
{rust_libc_prepare}
{rust_rand_os_prepare}
{rust_singlethread_prepare}
{rust_threaded_prepare}
{rust_singlethread_env}
{rust_threaded_env}
{rust_posix_env}
{cargo_build}
mkdir -p /build/stage/usr/local/bin
{cargo_install_args}
"""
    elif port.build_system == "go":
        go_module_prepare = "go mod download" if build.get("modules", True) else ":"
        go_module_mode = "" if build.get("modules", True) else "GO111MODULE=off"
        body = f"""
cd "$SOURCE_DIR"
{go_module_prepare}
{post_fetch}
{go_module_mode} GOOS=wasip1 GOARCH=wasm go build -trimpath {make_args}
mkdir -p /build/stage/usr/local/bin
{install_args}
"""
    else:
        commands = build.get("commands", [])
        if not commands:
            raise PortError(f"{port.name}: custom build requires build.commands")
        body = "\n".join(commands) + "\n"
    final_integrity = """
if [ "${EDGETERM_PRISTINE_SOURCE:-0}" = 1 ]; then
  python3 /toolchain/edgeterm-posix/scripts/source-integrity.py \
    verify "$SOURCE_ROOT" /build/source-integrity.json
fi
"""
    return common + body + post + "\n" + final_integrity + asyncify


def build_pipeline_sources() -> tuple[object, ...]:
    return (
        extraction_command,
        configure_script,
        build_port,
    )


def port_fingerprint(port: Port) -> str:
    digest = hashlib.sha256()
    digest.update(os.environ.get("EDGETERM_SKIP_PATCHES", "").encode("utf-8"))
    for function in build_pipeline_sources():
        digest.update(function.__name__.encode("utf-8"))
        digest.update(inspect.getsource(function).encode("utf-8"))
    paths = [
        port.path / "port.toml",
        *sorted(path for path in port.path.iterdir() if path.is_file() and path.name != "port.toml"),
        ROOT / "pipeline/wasix-toolchain.cmake",
        ROOT / "pipeline/patch-gnulib.py",
    ]
    posix = Path(os.environ.get("EDGETERM_POSIX_CHECKOUT", DEFAULT_POSIX))
    for directory in ("cmake", "config", "include", "scripts", "src", "targets"):
        root = posix / directory
        if root.is_dir():
            paths.extend(sorted(path for path in root.rglob("*") if path.is_file()))
    for path in paths:
        digest.update(str(path.relative_to(path.anchor)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def requires_pristine_source(port: Port) -> bool:
    return bool(port.data["build"].get("pristine_source", False)) or (
        os.environ.get("EDGETERM_PRISTINE_SOURCE", "0") == "1"
    )


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
    legacy_cache = edge_term / "ports/apt-wasix/.cache"
    toolchain_cache = DEFAULT_TOOLCHAIN_CACHE if DEFAULT_TOOLCHAIN_CACHE.is_dir() else legacy_cache
    sdk = Path(os.environ.get("EDGETERM_WASI_SDK", toolchain_cache / "wasi-sdk-33.0-arm64-linux"))
    sysroot = Path(os.environ.get("EDGETERM_WASIX_SYSROOT", toolchain_cache / "wasix-sysroot-v2025-11-06.1.tar.gz"))
    binaryen = Path(os.environ.get("EDGETERM_BINARYEN", toolchain_cache / "binaryen-version_131-aarch64-linux"))
    posix = Path(os.environ.get("EDGETERM_POSIX_CHECKOUT", DEFAULT_POSIX))
    if not (sdk / "bin/clang").exists():
        raise PortError(f"WASI SDK 33 was not found: {sdk}")
    if not sysroot.exists():
        raise PortError(f"WASIX sysroot was not found: {sysroot}")
    if not (posix / "scripts/build.sh").exists():
        raise PortError(f"EdgeTerm POSIX checkout was not found: {posix}")
    if not (binaryen / "bin/wasm-opt").exists() or not (binaryen / "bin/wasm-dis").exists():
        raise PortError(f"Binaryen 131 was not found: {binaryen}")
    build_root = BUILD / port.name
    build_root.mkdir(parents=True, exist_ok=True)
    rust_toolchain: Path | None = None
    rust_std_overlay: Path | None = None
    rust_std_fs_overlay: Path | None = None
    if port.data["build"].get("rust_wasix_toolchain", False):
        rust_toolchain = ensure_wasix_rust_toolchain()
        rust_std_overlay = build_root / "rust-std-overlay/process.rs"
        rust_std_fs_overlay = build_root / "rust-std-overlay/fs.rs"
        run([
            sys.executable,
            str(posix / "scripts/prepare-rust-std-overlay.py"),
            "--source",
            str(rust_toolchain / "lib/rustlib/src/rust/library/std/src/os/wasi/process.rs"),
            "--output",
            str(rust_std_overlay),
            "--fs-source",
            str(rust_toolchain / "lib/rustlib/src/rust/library/std/src/os/wasix/fs.rs"),
            "--fs-output",
            str(rust_std_fs_overlay),
        ])
        rust_singlethread_overlay = build_root / "rust-singlethread-overlay"
        if str(port.data["build"].get("target", "")).endswith("/singlethread/wasm32-wasmer-wasi.json"):
            run([
                sys.executable,
                str(posix / "scripts/prepare-rust-singlethread-overlay.py"),
                "--source-root",
                str(rust_toolchain / "lib/rustlib/src/rust/library/std/src"),
                "--output-root",
                str(rust_singlethread_overlay),
            ])
        target_setting = str(port.data["build"].get("target", ""))
        target_name = Path(target_setting).stem
        target_source = (
            posix / target_setting.removeprefix("/toolchain/edgeterm-posix/")
            if target_setting.startswith("/toolchain/edgeterm-posix/")
            else Path(target_setting)
        )
        rust_compatibility_inputs = [
            rust_std_overlay,
            rust_std_fs_overlay,
            target_source,
            *sorted((posix / "config").glob("rust-*.json")),
            *sorted((posix / "scripts").glob("*rust*.py")),
            *sorted(path for path in (posix / "rust").rglob("*") if path.is_file()),
        ]
        refresh_rust_target_cache(build_root, target_name, rust_compatibility_inputs)
    stage = build_root / "stage"
    marker = build_root / "build-complete.json"
    fingerprint = port_fingerprint(port)
    pristine_source = requires_pristine_source(port)
    if pristine_source:
        fingerprint = f"{fingerprint}:pristine-source-v1"
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
    docker_command = [
        "docker", "run", "--rm", "--platform", "linux/arm64",
        "-e", f"BUILD_JOBS={os.environ.get('BUILD_JOBS', '4')}",
        "-e", f"EDGETERM_SKIP_PATCHES={os.environ.get('EDGETERM_SKIP_PATCHES', '')}",
        "-e", f"EDGETERM_PRISTINE_SOURCE={int(pristine_source)}",
        "-v", f"{archive}:/input/source:ro",
        "-v", f"{build_root}:/build",
        "-v", f"{sdk}:/wasi-sdk:ro",
        "-v", f"{sysroot}:/toolchain/sysroot.tar.gz:ro",
        "-v", f"{binaryen}:/binaryen:ro",
        "-v", f"{posix}:/toolchain/edgeterm-posix:ro",
        "-v", f"{posix / 'cmake/wasm32-wasix.cmake'}:/toolchain/wasix-toolchain.cmake:ro",
        "-v", f"{ROOT / 'pipeline/patch-gnulib.py'}:/toolchain/patch-gnulib.py:ro",
        "-v", f"{port.path}:/port:ro",
    ]
    if rust_toolchain is not None and rust_std_overlay is not None and rust_std_fs_overlay is not None:
        docker_command.extend([
            "-v", f"{rust_toolchain}:/wasix-rust:ro",
            "-v",
            f"{rust_std_overlay}:/wasix-rust/lib/rustlib/src/rust/library/std/src/os/wasi/process.rs:ro",
            "-v",
            f"{rust_std_fs_overlay}:/wasix-rust/lib/rustlib/src/rust/library/std/src/os/wasix/fs.rs:ro",
        ])
        if str(port.data["build"].get("target", "")).endswith("/singlethread/wasm32-wasmer-wasi.json"):
            docker_command.extend([
                "-v",
                f"{rust_singlethread_overlay / 'thread-mod.rs'}:/wasix-rust/lib/rustlib/src/rust/library/std/src/sys/thread/mod.rs:ro",
                "-v",
                f"{rust_singlethread_overlay / 'thread-unsupported.rs'}:/wasix-rust/lib/rustlib/src/rust/library/std/src/sys/thread/unsupported.rs:ro",
                "-v",
                f"{rust_singlethread_overlay / 'thread-parking-mod.rs'}:/wasix-rust/lib/rustlib/src/rust/library/std/src/sys/sync/thread_parking/mod.rs:ro",
                "-v",
                f"{rust_singlethread_overlay / 'exit.rs'}:/wasix-rust/lib/rustlib/src/rust/library/std/src/sys/exit.rs:ro",
            ])
    docker_command.extend([image, "bash", "/build/build.sh"])
    run_logged(docker_command, build_root / "build.log")
    if not stage.exists():
        raise PortError(f"{port.name}: build did not create a package staging directory")
    validate_stage(port, stage)
    marker.write_text(json.dumps({
        "schema": "edgeterm.package-build.v1",
        "package": port.name,
        "version": port.deb_version,
        "fingerprint": fingerprint,
        "pristine_source": pristine_source,
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


def runtime_bundle_dependencies(port: Port, ports: dict[str, Port]) -> list[Port]:
    ordered: list[Port] = []
    visited: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str, chain: tuple[str, ...]) -> None:
        if name in visiting:
            raise PortError(f"Circular runtime dependency: {' -> '.join((*chain, name))}")
        if name in visited:
            return
        dependency = resolve_port(name, ports)
        if not dependency.user_visible:
            raise PortError(f"{port.name}: runtime dependency has no commands: {name}")
        visiting.add(name)
        runtime = dependency.data.get("runtime", {})
        nested = runtime.get(
            "exec_dependencies",
            runtime.get("bundle_dependencies", []),
        )
        for child in nested:
            visit(child, (*chain, name))
        visiting.remove(name)
        visited.add(name)
        ordered.append(dependency)

    runtime = port.data.get("runtime", {})
    direct = runtime.get(
        "exec_dependencies",
        runtime.get("bundle_dependencies", []),
    )
    for name in direct:
        visit(name, (port.name,))
    return ordered


def build_runtime_bundle(port: Port, package_root: Path, ports: dict[str, Port]) -> str | None:
    commands = port.data["runtime"]["commands"]
    aliases = port.data["runtime"].get("command_aliases", {})
    dependencies = runtime_bundle_dependencies(port, ports)
    if len(commands) == 1 and not dependencies:
        return None
    entrypoint = commands[0]

    with tempfile.TemporaryDirectory(prefix=f"edgeterm-{port.name}-runtime-") as temporary:
        bundle_root = Path(temporary)
        command_binaries: list[tuple[str, Path]] = []
        for command in commands:
            target = aliases.get(command, {}).get("target", command)
            binary = package_root / "usr/local/bin" / target
            if not binary.is_file():
                raise PortError(f"{port.name}: runtime bundle command was not installed: {command}")
            command_binaries.append((command, binary))
        for dependency in dependencies:
            dependency_stage = build_port(dependency, ports=ports, allow_cached=True)
            dependency_commands = dependency.data.get("runtime", {}).get("commands", [])
            if not dependency_commands:
                raise PortError(f"{port.name}: bundled dependency has no runtime command: {dependency.name}")
            for command in dependency_commands:
                binary = dependency_stage / "usr/local/bin" / command
                if not binary.is_file():
                    raise PortError(f"{port.name}: bundled dependency command was not built: {command}")
                command_binaries.append((command, binary))

        command_names = [command for command, _ in command_binaries]
        duplicates = sorted({name for name in command_names if command_names.count(name) > 1})
        if duplicates:
            raise PortError(f"{port.name}: runtime bundle command collision: {', '.join(duplicates)}")

        manifest_lines = [
            "[package]",
            f'name = "digitalplat/{port.name}-runtime"',
            f'version = "{runtime_semver(port.version)}"',
            f'description = "Optional runtime bundle for {port.name}"',
            f'license = "{port.data["package"]["license"]}"',
            f'entrypoint = "{entrypoint}"',
            "",
        ]
        modules_by_digest: dict[str, str] = {}
        command_modules: dict[str, str] = {}
        for command, binary_path in command_binaries:
            digest = hash_file(binary_path)
            module_name = modules_by_digest.get(digest)
            if module_name is None:
                module_name = f"module-{len(modules_by_digest) + 1}"
                modules_by_digest[digest] = module_name
                staged_name = f"{module_name}.wasm"
                shutil.copy2(binary_path, bundle_root / staged_name)
                manifest_lines.extend([
                    "[[module]]",
                    f'name = "{module_name}"',
                    f'source = "{staged_name}"',
                    'abi = "wasi"',
                    "",
                ])
            command_modules[command] = module_name
        for command, module_name in command_modules.items():
            command_lines = [
                "[[command]]",
                f'name = "{command}"',
                f'module = "{module_name}"',
            ]
            alias_arguments = aliases.get(command, {}).get("args", [])
            if alias_arguments:
                command_lines.append(
                    f"main_args = {json.dumps(shlex.join(alias_arguments))}"
                )
            command_lines.append("")
            manifest_lines.extend(command_lines)
        manifest = bundle_root / "wasmer.toml"
        manifest.write_text("\n".join(manifest_lines), encoding="utf-8")
        destination = package_root / "usr/local/lib/edgeterm/runtime" / f"{port.name}.webc"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.unlink(missing_ok=True)
        run(["wasmer", "package", "build", str(manifest), "--out", str(destination)])
    return f"/usr/local/lib/edgeterm/runtime/{port.name}.webc"


def package_port(port: Port) -> Path:
    force_rebuild = os.environ.get("EDGETERM_FORCE_REBUILD", "0") == "1"
    ports = load_ports()
    stage = build_port(port, ports=ports, allow_cached=not force_rebuild)
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
    runtime_bundle = build_runtime_bundle(port, package_root, ports)
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
    runtime_env = port.data["runtime"].get("env", {})
    if not isinstance(runtime_env, dict) or any(
        not isinstance(key, str)
        or not key.replace("_", "A").isalnum()
        or not key[0].isalpha()
        or not isinstance(value, str)
        or len(key) > 128
        or len(value) > 4096
        for key, value in runtime_env.items()
    ):
        raise PortError(f"{port.name}: [runtime].env must contain safe string environment variables")
    command_metadata = {
        "schema": "edgeterm.package-commands.v1",
        "package": port.name,
        "version": port.deb_version,
        "commands": port.data["runtime"]["commands"],
        "mode": port.data["runtime"]["mode"],
        "capability": port.data["runtime"]["capability"],
        "adapter": str(port.data["runtime"].get("adapter", "")),
        "threaded": bool(port.data["build"].get("threads", False)),
    }
    if runtime_env:
        command_metadata["env"] = runtime_env
    if runtime_bundle:
        command_metadata["bundle"] = runtime_bundle
    (metadata / f"{port.name}.json").write_text(
        json.dumps(command_metadata, indent=2) + "\n",
        encoding="utf-8",
    )
    sbom = package_root / "usr/share/doc" / port.name
    sbom.mkdir(parents=True, exist_ok=True)
    source_root = BUILD / port.name / "source-root"
    source_directory = next((path for path in source_root.iterdir() if path.is_dir()), source_root)
    declared_license = port.data["package"].get("license_file")
    if declared_license:
        if declared_license.startswith("port:"):
            license_root = port.path.resolve()
            license_path = (license_root / declared_license.removeprefix("port:")).resolve()
        else:
            license_root = source_directory.resolve()
            license_path = (license_root / declared_license).resolve()
        if license_root not in license_path.parents or not license_path.is_file():
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
    applied_patches = [] if requires_pristine_source(port) else [
        {"name": patch.name, "sha256": hash_file(patch)}
        for patch in sorted(port.path.glob("*.patch"))
    ]
    (sbom / "patches.json").write_text(
        json.dumps(applied_patches, indent=2) + "\n",
        encoding="utf-8",
    )
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
