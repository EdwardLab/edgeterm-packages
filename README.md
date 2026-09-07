# EdgeTerm Packages

This repository builds optional third-party software for the EdgeTerm browser runtime. It is intentionally separate from the MPL-licensed EdgeTerm application.

The catalog contains 101 user-installable packages. The second wave adds small
language runtimes, terminal programs, source and data tools, and modern command-line
utilities. Packages remain in the candidate channel until their browser acceptance
record is complete.

## Branches

- `main` contains port manifests, build tooling, patches, tests, and documentation. Generated packages are not committed here.
- `apt-repo` contains the generated static APT repository published to clients. It is maintained independently so package updates do not add binary history to the source branch.
- `legacy-packages` preserves the repository content that predates the APT/WASIX packaging system.

Each port is described by `ports/<package>/port.toml`. Source locations, versions, checksums, licenses, commands, capabilities, build settings, and acceptance tests are pinned. Published artifacts use the Debian architecture `wasm32-wasix` and are consumed by the unmodified APT and dpkg ports in EdgeTerm.

## Trust model

- Source archives are downloaded only over HTTPS and must match the pinned SHA-256.
- Build containers have no signing key. Repository signing happens in a separate publish job.
- A package is `stable` only after reproducible build, install, functional, upgrade, remove, purge, and Chrome tests pass.
- Network programs remain `preview` until the applicable browser-host capability has a real remote end-to-end test.
- Browser package storage and workspace storage are independent. Cache cleanup never removes workspace files.

## Immutable upstream sources

Ports that set `build.pristine_source = true` are built from the verified source
archive without normalization, port patches, or source-tree rewrites. The build
pipeline snapshots the extracted tree before configuration and verifies it again
after installation. A package is counted as verified only when the manifest lock,
the pristine build marker, and acceptance evidence all refer to the current package
artifact.

Portable compatibility belongs in `vendor/edgeterm-posix`, a source snapshot of
the EdgeTerm-POSIX project with its MIT license and per-file SHA-256 manifest.
Set `EDGETERM_POSIX_CHECKOUT` to use a separate development checkout. C and C++
ports consume its headers and static library; Rust ports consume its version-checked
standard-library, libc, and dependency overlays. Port manifests may select these
profiles, but must not duplicate compatibility source rewrites. Cargo lock files and
application source archives remain authoritative and unchanged.

```sh
python3 scripts/source_audit.py
python3 scripts/source_audit.py --require-complete
```

The second command is the release gate. It remains non-zero until every user-visible
package has current immutable-source evidence.

## Local workflow

```sh
python3 scripts/ports.py validate
python3 scripts/ports.py list
python3 scripts/ports.py fetch grep
python3 scripts/ports.py build grep
python3 scripts/ports.py package grep
python3 scripts/ports.py build-batch base
python3 scripts/ports.py package-batch base
python3 scripts/repository.py build --channel candidate
python3 scripts/repository.py build --channel stable
python3 -m unittest discover -s tests
```

The build driver uses `EDGETERM_WASI_SDK`, `EDGETERM_WASIX_SYSROOT`, and `EDGETERM_BUILD_IMAGE` when set. Defaults point to the sibling EdgeTerm development checkout and its existing pinned WASI SDK 33 toolchain.

## Publication

`https://packages.digitalplat.org` is the production origin. The current release
contains 101 candidate packages and 75 stable packages; Git and PHP are stable.
The browser consumes the signed `local-flat` index. The static repository must be served with CORS enabled and immutable caching for `.deb` files. `InRelease`, `Release`, and package indexes use short cache lifetimes. Private signing material is never committed.

The production signing key fingerprint is
`6165 B5AE 16F6 2EE3 D318 3790 5CEC F54D FEE8 CFBD`. Its private material is
kept outside both source repositories. Release jobs must set `GNUPGHOME` and
`EDGETERM_APT_SIGNING_KEY` explicitly.

## Reproducing the release toolchain

Package builds currently target a Linux ARM64 container (including Docker on
Apple Silicon). Python 3.14 is supported; Python 3.11-3.13 also need the dependencies
in `requirements.txt`. The driver uses the checked-in POSIX source snapshot by
default, so a sibling unpublished checkout is no longer required.

```sh
python3 -m pip install -r requirements.txt
python3 scripts/prepare-toolchain.py
docker build --platform linux/arm64 -t edgeterm-packages:2026-08-05 -f pipeline/Dockerfile .
python3 scripts/ports.py build tree
python3 scripts/ports.py package tree
```

The preparation command downloads and verifies WASI SDK 33, Binaryen 131, and
the WASIX sysroot. Rust ports fetch their separately pinned WASIX Rust toolchain
when required. The published binaries have artifact-bound acceptance records;
a fresh clone does not inherit local evidence and must rerun acceptance before
publishing a new stable artifact.

Signed metadata expires after 14 days. A publisher must regenerate and sign the
repository before `Valid-Until`; clients deliberately reject expired metadata.
The signing key remains on the publisher machine and is not stored in CI.
