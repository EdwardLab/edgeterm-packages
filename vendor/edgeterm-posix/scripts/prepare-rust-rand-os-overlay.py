#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cargo-home", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    cargo_home = Path(args.cargo_home)
    matches = sorted(cargo_home.glob("registry/src/*/rand_os-0.1.3"))
    if len(matches) != 1:
        raise SystemExit("rand_os 0.1.3 was not found in the Cargo registry")

    output = Path(args.output)
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(matches[0], output)

    source_path = output / "src/lib.rs"
    source = source_path.read_text(encoding="utf-8")
    source = source.replace(
        'mod_use!(cfg(windows), windows);',
        'mod_use!(cfg(windows), windows);\nmod_use!(cfg(target_os = "wasi"), wasi);',
    )
    source = source.replace(
        'target_arch = "wasm32",\n    not(target_os = "emscripten"),',
        'target_arch = "wasm32",\n    not(target_os = "emscripten"),\n    not(target_os = "wasi"),',
        1,
    )
    source_path.write_text(source, encoding="utf-8")

    (output / "src/wasi.rs").write_text(
        '''use rand_core::{Error, ErrorKind};
use super::OsRngImpl;

#[link(wasm_import_module = "wasi_snapshot_preview1")]
extern "C" {
    fn random_get(buffer: *mut u8, length: usize) -> u16;
}

#[derive(Clone, Debug)]
pub struct OsRng;

impl OsRngImpl for OsRng {
    fn new() -> Result<OsRng, Error> {
        Ok(OsRng)
    }

    fn fill_chunk(&mut self, dest: &mut [u8]) -> Result<(), Error> {
        let errno = unsafe { random_get(dest.as_mut_ptr(), dest.len()) };
        if errno == 0 {
            Ok(())
        } else {
            Err(Error::new(ErrorKind::Unavailable, "random_get failed"))
        }
    }

    fn method_str(&self) -> &'static str {
        "wasi::random_get"
    }
}
''',
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
