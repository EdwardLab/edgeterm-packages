#!/usr/bin/env python3
"""Fetch the checksum-pinned Linux ARM64 toolchain used by this release."""
import shutil
import tarfile
import tempfile
from pathlib import Path

from ports import DEFAULT_TOOLCHAIN_CACHE, download_pinned_file

ASSETS = [
    ("wasi-sdk-33.0-arm64-linux", "https://github.com/WebAssembly/wasi-sdk/releases/download/wasi-sdk-33/wasi-sdk-33.0-arm64-linux.tar.gz", "4f98ee738c7abb45c81a94d1461fc53cc569d1cd01498951c8184d841a027844", "bin/clang"),
    ("binaryen-version_131-aarch64-linux", "https://github.com/WebAssembly/binaryen/releases/download/version_131/binaryen-version_131-aarch64-linux.tar.gz", "ba991f677edd9a21d2bc96c0144bc8ac5b112d4d98a3eb266e075e22e557df2a", "bin/wasm-opt"),
    ("wasix-sysroot-v2025-11-06.1", "https://github.com/wasix-org/wasix-libc/releases/download/v2025-11-06.1/sysroot.tar.gz", "45c00faa96ccdc7d35c7505453a61b64cea1857fe61fd3c7ee1242f4d55ae505", None),
]


def main():
    for name, url, sha256, executable in ASSETS:
        archive = DEFAULT_TOOLCHAIN_CACHE / f"{name}.tar.gz"
        download_pinned_file(url, sha256, archive)
        destination = DEFAULT_TOOLCHAIN_CACHE / name
        if executable and not (destination / executable).is_file():
            with tempfile.TemporaryDirectory(dir=DEFAULT_TOOLCHAIN_CACHE) as temporary:
                with tarfile.open(archive) as source:
                    source.extractall(temporary, filter="data")
                roots = list(Path(temporary).iterdir())
                if len(roots) != 1 or not (roots[0] / executable).is_file():
                    raise RuntimeError(f"Unexpected archive layout: {name}")
                shutil.copytree(roots[0], destination, dirs_exist_ok=True)
        print(f"Verified {name}")


if __name__ == "__main__":
    main()
