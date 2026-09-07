# Porting policy

The default input is a pristine, checksum-pinned upstream archive. Apply fixes
in this order:

1. Confirm the program relies on a documented portable contract.
2. Add or correct the contract in the EdgeTerm POSIX headers, library, build
   configuration, or browser host adapter.
3. Add a conformance test that fails before the fix and passes after it.
4. Rebuild at least one unrelated package to check for regressions.
5. Add an application patch only when the application requires behavior that
   is outside the versioned profile.

When an upstream configure script makes an incorrect cross-build assumption,
record the truthful cache answer in `config/config.site` before modifying the
upstream source. Such entries select existing upstream code paths; they do not
emulate missing behavior.

Application patches must include a short `patch.toml` record with the upstream
version, reason, affected capability, and an upstream issue or a clear reason
why the change is target-specific. A package upgrade must re-test and remove
patches that upstream no longer needs.

## Error behavior

An unavailable operation returns a stable error. It must not report success
unless the observable contract is preserved. Advisory interfaces may return
success only when ignoring the hint cannot change program correctness.

## Upstream updates

1. Change the pinned source version and checksum.
2. Build with the current profile and no new application changes.
3. Run the package fixture and the full profile conformance suite.
4. If it fails, reduce the failure to a profile test before changing the port.
5. Record any unavoidable application patch in the audit inventory.

Rust packages that require WASIX declarations missing from Rust's upstream
WASI `libc` crate must use the version-checked build-local ABI overlay. Do not
edit the application's manifest, lock file, or source archive.

Rust packages that use Unix process extension traits must use the pinned WASIX
Rust target and the build-local standard library overlay. Apply `cfg(unix)` to
the application crate only; never change the target family because doing so
selects unrelated platform modules in transitive dependencies.

When a locked dependency lacks a WASI implementation, add a same-name,
same-version compatibility crate under `rust/` and register only the required
paths in `config/rust-overlays.json`. The build pipeline applies it to the
disposable Cargo cache after verifying the lockfile version. Keep this mechanism
generic: package ports must not copy files into Cargo registry directories or
rewrite dependency sources themselves.
