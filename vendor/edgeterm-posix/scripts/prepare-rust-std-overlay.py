#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


IMPORT_MARKER = "use crate::process;\n"
CONTRACT_MARKER = "pub trait ExitStatusExt: crate::sealed::Sealed"
EXIT_STATUS_EXTENSION = r'''
#[cfg(target_vendor = "wasmer")]
use crate::sys::{AsInner, FromInner};

#[cfg(target_vendor = "wasmer")]
#[stable(feature = "rust1", since = "1.0.0")]
pub trait ExitStatusExt: crate::sealed::Sealed {
    #[stable(feature = "exit_status_from", since = "1.12.0")]
    fn from_raw(raw: i32) -> Self;

    #[stable(feature = "rust1", since = "1.0.0")]
    fn signal(&self) -> Option<i32>;

    #[stable(feature = "unix_process_wait_more", since = "1.58.0")]
    fn core_dumped(&self) -> bool;

    #[stable(feature = "unix_process_wait_more", since = "1.58.0")]
    fn stopped_signal(&self) -> Option<i32>;

    #[stable(feature = "unix_process_wait_more", since = "1.58.0")]
    fn continued(&self) -> bool;

    #[stable(feature = "unix_process_wait_more", since = "1.58.0")]
    fn into_raw(self) -> i32;
}

#[cfg(target_vendor = "wasmer")]
#[stable(feature = "rust1", since = "1.0.0")]
impl ExitStatusExt for process::ExitStatus {
    fn from_raw(raw: i32) -> Self {
        let signal = (raw & 0x7f) as u8;
        let status = if signal == 0 {
            wasi::JoinStatus {
                tag: wasi::JOIN_STATUS_TYPE_EXIT_NORMAL.raw(),
                u: wasi::JoinStatusU { exit_normal: (((raw >> 8) & 0xff) as u16).into() },
            }
        } else {
            wasi::JoinStatus {
                tag: wasi::JOIN_STATUS_TYPE_EXIT_SIGNAL.raw(),
                u: wasi::JoinStatusU {
                    exit_signal: wasi::ErrnoSignal {
                        exit_code: (0_u16).into(),
                        signal: signal.into(),
                    },
                },
            }
        };
        process::ExitStatus::from_inner(crate::sys::process::ExitStatus::new(status))
    }

    fn signal(&self) -> Option<i32> {
        self.as_inner().signal()
    }

    fn core_dumped(&self) -> bool {
        self.as_inner().core_dumped()
    }

    fn stopped_signal(&self) -> Option<i32> {
        self.as_inner().stopped_signal()
    }

    fn continued(&self) -> bool {
        self.as_inner().continued()
    }

    fn into_raw(self) -> i32 {
        self.signal().unwrap_or_else(|| self.code().unwrap_or(0) << 8)
    }
}
'''

PERMISSIONS_MARKER = "/// WASI-specific extensions to [`fs::Metadata`].\n"
PERMISSIONS_EXTENSION = r'''
/// POSIX permission extensions supplied by the EdgeTerm runtime profile.
pub trait PermissionsExt {
    fn mode(&self) -> u32;
    fn set_mode(&mut self, mode: u32);
}

impl PermissionsExt for fs::Permissions {
    fn mode(&self) -> u32 {
        if self.readonly() { 0o444 } else { 0o666 }
    }

    fn set_mode(&mut self, mode: u32) {
        self.set_readonly(mode & 0o222 == 0);
    }
}

'''
METADATA_TRAIT_END = "    fn ctim(&self) -> u64;\n}"
METADATA_TRAIT_POSIX = """    fn ctim(&self) -> u64;
    fn mode(&self) -> u32;
    fn uid(&self) -> u32;
    fn gid(&self) -> u32;
    fn rdev(&self) -> u64;
    fn atime(&self) -> i64;
    fn atime_nsec(&self) -> i64;
    fn mtime(&self) -> i64;
    fn mtime_nsec(&self) -> i64;
    fn ctime(&self) -> i64;
    fn ctime_nsec(&self) -> i64;
    fn blksize(&self) -> u64;
    fn blocks(&self) -> u64;
}"""
METADATA_IMPL_END = """    fn ctim(&self) -> u64 {
        self.as_inner().as_wasi().ctim
    }
}"""
METADATA_IMPL_POSIX = """    fn ctim(&self) -> u64 {
        self.as_inner().as_wasi().ctim
    }
    fn mode(&self) -> u32 {
        let kind = if self.is_dir() { 0o040000 } else { 0o100000 };
        kind | self.permissions().mode()
    }
    fn uid(&self) -> u32 { 0 }
    fn gid(&self) -> u32 { 0 }
    fn rdev(&self) -> u64 { 0 }
    fn atime(&self) -> i64 { (self.as_inner().as_wasi().atim / 1_000_000_000) as i64 }
    fn atime_nsec(&self) -> i64 { (self.as_inner().as_wasi().atim % 1_000_000_000) as i64 }
    fn mtime(&self) -> i64 { (self.as_inner().as_wasi().mtim / 1_000_000_000) as i64 }
    fn mtime_nsec(&self) -> i64 { (self.as_inner().as_wasi().mtim % 1_000_000_000) as i64 }
    fn ctime(&self) -> i64 { (self.as_inner().as_wasi().ctim / 1_000_000_000) as i64 }
    fn ctime_nsec(&self) -> i64 { (self.as_inner().as_wasi().ctim % 1_000_000_000) as i64 }
    fn blksize(&self) -> u64 { 4096 }
    fn blocks(&self) -> u64 { self.len().div_ceil(512) }
}"""
FILETYPE_SOCKET = """    fn is_socket(&self) -> bool {
        self.is_socket_stream() || self.is_socket_dgram()
    }
}"""
FILETYPE_POSIX = """    fn is_socket(&self) -> bool {
        self.is_socket_stream() || self.is_socket_dgram()
    }
    fn is_fifo(&self) -> bool { false }
}"""


def prepare_overlay(source: Path, output: Path) -> dict[str, object]:
    body = source.read_text(encoding="utf-8")
    changed = False
    if CONTRACT_MARKER not in body:
        if body.count(IMPORT_MARKER) != 1:
            raise SystemExit("The Rust standard library process module has an unknown layout")
        body = body.replace(IMPORT_MARKER, IMPORT_MARKER + EXIT_STATUS_EXTENSION, 1)
        changed = True
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")
    manifest = {
        "schema": "org.edgeterm.posix.rust-std-overlay.v1",
        "source": str(source),
        "output": str(output),
        "changed": changed,
        "contracts": ["wasix-exit-status-ext"],
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def prepare_fs_overlay(source: Path, output: Path) -> dict[str, object]:
    body = source.read_text(encoding="utf-8")
    changed = False
    contracts: list[str] = []
    if PERMISSIONS_EXTENSION not in body:
        if body.count(PERMISSIONS_MARKER) != 1:
            raise SystemExit("The Rust standard library filesystem module has an unknown layout")
        body = body.replace(PERMISSIONS_MARKER, PERMISSIONS_EXTENSION + PERMISSIONS_MARKER, 1)
        changed = True
    contracts.append("posix-permissions-ext")
    if METADATA_TRAIT_POSIX not in body:
        if body.count(METADATA_TRAIT_END) != 1 or body.count(METADATA_IMPL_END) != 1:
            raise SystemExit("The Rust standard library metadata extension has an unknown layout")
        body = body.replace(METADATA_TRAIT_END, METADATA_TRAIT_POSIX, 1)
        body = body.replace(METADATA_IMPL_END, METADATA_IMPL_POSIX, 1)
        changed = True
    contracts.append("posix-metadata-ext")
    if FILETYPE_POSIX not in body:
        if body.count(FILETYPE_SOCKET) != 1:
            raise SystemExit("The Rust standard library file type extension has an unknown layout")
        body = body.replace(FILETYPE_SOCKET, FILETYPE_POSIX, 1)
        changed = True
    contracts.append("posix-file-type-ext")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(body, encoding="utf-8")
    manifest = {
        "schema": "org.edgeterm.posix.rust-std-fs-overlay.v1",
        "source": str(source),
        "output": str(output),
        "changed": changed,
        "contracts": contracts,
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the EdgeTerm Rust std ABI overlay")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fs-source", type=Path)
    parser.add_argument("--fs-output", type=Path)
    args = parser.parse_args()
    results = [prepare_overlay(args.source, args.output)]
    if bool(args.fs_source) != bool(args.fs_output):
        raise SystemExit("Both --fs-source and --fs-output are required together")
    if args.fs_source and args.fs_output:
        results.append(prepare_fs_overlay(args.fs_source, args.fs_output))
    print(json.dumps(results, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
