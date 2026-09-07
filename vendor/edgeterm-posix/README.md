# EdgeTerm POSIX

EdgeTerm POSIX is the versioned compatibility boundary between portable
software and the browser runtime used by EdgeTerm. It provides a sysroot
overlay, a small static compatibility library, build-system integration, and
conformance tests.

The project has one rule: fix a missing platform contract here before adding
source changes to an application port. Package-specific patches remain valid
only when an application relies on behavior outside the declared profile.

## Layout

- `include/` contains header overlays loaded through normal application includes.
- `src/` contains weak fallback implementations and process startup fixes.
- `profile/edgeterm-posix-v1.json` is the machine-readable contract.
- `scripts/build.sh` builds and installs the static library.
- `scripts/normalize-source.py` centralizes source-level compatibility for
  vendored portability modules that reject an otherwise supported target
  before link time.
- `scripts/source-integrity.py` proves that pristine builds reach configure
  without package patches or preparation scripts changing upstream files.
- `scripts/cc` and `scripts/c++` apply the overlay without changing sources.
- `scripts/prepare-rust-libc-overlay.py` aligns Rust's WASI libc declarations
  with the WASIX ABI in a build-local dependency overlay.
- `scripts/prepare-rust-std-overlay.py` adds missing process extension traits
  and filesystem metadata contracts to a build-local copy of the pinned WASIX
  Rust standard library modules.
- `scripts/rustc-posix-wrapper.py` exposes the POSIX compile-time profile only
  to selected application and dependency crates. It does not change the target
  family for the rest of the dependency graph.
- `scripts/prepare-rust-crate-overlays.py` applies version-checked compatibility
  crates to Cargo's disposable build cache after a locked fetch. Application
  manifests, lock files, and checksum-pinned source archives remain unchanged.
- `config/rust-overlays.json` is the central registry for Rust dependency
  compatibility. A package port must not carry its own copy of these overlays.
- `cmake/wasm32-wasix.cmake` integrates the profile with CMake.
- `config/config.site` provides conservative cross-build answers for Autoconf.
- Cross-build answers may select an application's own portable fallback when
  a configure probe cannot run and the target does not provide the full
  contract. They must not claim that an unavailable interface works.
- `tests/conformance/` verifies behavior promised by the profile.

## Build

```sh
CC=/path/to/clang AR=/path/to/llvm-ar \
  scripts/build.sh --prefix /tmp/edgeterm-posix
```

The compiler wrappers expect these variables:

```sh
export EDGETERM_POSIX_PREFIX=/tmp/edgeterm-posix
export EDGETERM_WASIX_CC='/path/to/clang --target=wasm32-wasi --sysroot=/path/to/sysroot'
export EDGETERM_WASIX_CXX='/path/to/clang++ --target=wasm32-wasi --sysroot=/path/to/sysroot'
```

Then build pristine upstream sources with `scripts/cc` and `scripts/c++`. The
wrappers do not force a precompiled header; applications receive declarations
when they include the corresponding standard header.

## Compatibility policy

- `native`: supplied by the target libc or runtime.
- `compat`: supplied here with tested semantics.
- `advisory`: a successful result preserves the documented advisory contract.
- `unsupported`: fails with a stable error and never pretends to succeed.

The profile is not a certification claim. A capability is promoted only after
it has a runtime test in the supported browser environment.

## Current compatibility contracts

- Directory descriptors retain enough process-local state for `openat`,
  `fchdir`, `dup`, and `dup2` to preserve working-directory behavior.
- `chdir` and `getcwd` share a normalized absolute path model, including
  relative paths and `.` or `..` components.
- Standard temporary-name and timestamp interfaces are available through the
  normal `stdio.h`, `time.h`, and `utime.h` overlays.
- Header adaptations use named compatibility entry points instead of changing
  application sources. Weak library symbols keep repeated static linking safe.
- Rust applications can opt into the same ABI contract without editing their
  source tree or vendored dependencies.
- Rust compatibility is selected by locked crate name and version. A mismatch
  fails before compilation instead of silently applying an old overlay.
- Rust target artifacts are keyed by the target specification and compatibility
  ABI. An ABI change invalidates only the affected target cache.
