#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


THREAD_SELECTOR = 'cfg_select! {\n'
THREAD_BRANCH = '''cfg_select! {
    edgeterm_singlethread => {
        mod unsupported;
        pub use unsupported::{Thread, available_parallelism, current_os_id, set_name, sleep, sleep_until, yield_now, DEFAULT_MIN_STACK_SIZE};
    }
'''
PARKING_SELECTOR = 'cfg_select! {\n'
PARKING_BRANCH = '''cfg_select! {
    edgeterm_singlethread => {
        mod unsupported;
        pub use unsupported::Parker;
    }
'''
EXIT_FUNCTION = '''pub fn exit(code: i32) -> ! {
    cfg_select! {
'''
SINGLETHREAD_EXIT = '''#[cfg(edgeterm_singlethread)]
#[link(wasm_import_module = "wasi_snapshot_preview1")]
unsafe extern "C" {
    #[link_name = "proc_exit"]
    fn edgeterm_proc_exit(code: u32) -> !;
}

pub fn exit(code: i32) -> ! {
    cfg_select! {
        edgeterm_singlethread => {
            unsafe { edgeterm_proc_exit(code as u32) }
        }
'''
PANIC_SLEEP = '''pub fn sleep(_dur: Duration) {
    panic!("can't sleep");
}
'''
SINGLETHREAD_SLEEP = '''pub fn sleep(dur: Duration) {
    let request = libc::timespec {
        tv_sec: dur.as_secs().try_into().unwrap_or(libc::time_t::MAX),
        tv_nsec: dur.subsec_nanos() as libc::c_long,
    };
    unsafe {
        libc::nanosleep(&request, crate::ptr::null_mut());
    }
}

pub fn sleep_until(deadline: crate::time::Instant) {
    while let Some(delay) = deadline.checked_duration_since(crate::time::Instant::now()) {
        sleep(delay);
    }
}
'''
UNKNOWN_PARALLELISM = '''pub fn available_parallelism() -> io::Result<NonZero<usize>> {
    Err(io::Error::UNKNOWN_THREAD_COUNT)
}
'''
SINGLE_PARALLELISM = '''pub fn available_parallelism() -> io::Result<NonZero<usize>> {
    Ok(NonZero::new(1).unwrap())
}
'''


def insert_branch(body: str, marker: str, branch: str, description: str) -> str:
    if "edgeterm_singlethread =>" in body:
        return body
    if body.count(marker) != 1:
        raise SystemExit(f"The Rust standard library {description} selector has an unknown layout")
    return body.replace(marker, branch, 1)


def prepare_overlay(source_root: Path, output_root: Path) -> dict[str, object]:
    thread_source = source_root / "sys/thread/mod.rs"
    unsupported_source = source_root / "sys/thread/unsupported.rs"
    parking_source = source_root / "sys/sync/thread_parking/mod.rs"
    exit_source = source_root / "sys/exit.rs"

    thread_body = insert_branch(
        thread_source.read_text(encoding="utf-8"),
        THREAD_SELECTOR,
        THREAD_BRANCH,
        "thread",
    )
    unsupported_body = unsupported_source.read_text(encoding="utf-8")
    if PANIC_SLEEP not in unsupported_body:
        raise SystemExit("The Rust standard library unsupported thread module has an unknown layout")
    unsupported_body = unsupported_body.replace(PANIC_SLEEP, SINGLETHREAD_SLEEP, 1)
    if UNKNOWN_PARALLELISM not in unsupported_body:
        raise SystemExit("The Rust standard library parallelism implementation has an unknown layout")
    unsupported_body = unsupported_body.replace(UNKNOWN_PARALLELISM, SINGLE_PARALLELISM, 1)
    parking_body = insert_branch(
        parking_source.read_text(encoding="utf-8"),
        PARKING_SELECTOR,
        PARKING_BRANCH,
        "thread parking",
    )
    exit_body = exit_source.read_text(encoding="utf-8")
    if exit_body.count(EXIT_FUNCTION) != 1:
        raise SystemExit("The Rust standard library exit module has an unknown layout")
    exit_body = exit_body.replace(EXIT_FUNCTION, SINGLETHREAD_EXIT, 1)

    outputs = {
        "thread-mod.rs": thread_body,
        "thread-unsupported.rs": unsupported_body,
        "thread-parking-mod.rs": parking_body,
        "exit.rs": exit_body,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    for name, body in outputs.items():
        (output_root / name).write_text(body, encoding="utf-8")

    manifest = {
        "schema": "org.edgeterm.posix.rust-singlethread-overlay.v1",
        "source": str(source_root),
        "output": str(output_root),
        "contracts": [
            "single-thread-runtime",
            "single-thread-parking",
            "single-core-parallelism",
            "duration-sleep",
            "standard-wasi-exit",
        ],
    }
    (output_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the EdgeTerm single-thread Rust std overlay")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare_overlay(args.source_root, args.output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
