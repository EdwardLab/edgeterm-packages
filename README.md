# EdgeTerm Packages

This repository builds optional third-party software for the EdgeTerm browser runtime. It is intentionally separate from the MPL-licensed EdgeTerm application.

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

`packages.digitalplat.org` is the intended production origin. The static repository must be served with CORS enabled and immutable caching for `.deb` files. `InRelease`, `Release`, and package indexes use short cache lifetimes. Private signing material is never committed.

The production signing key fingerprint is
`6165 B5AE 16F6 2EE3 D318 3790 5CEC F54D FEE8 CFBD`. Its private material is
kept outside both source repositories. Release jobs must set `GNUPGHOME` and
`EDGETERM_APT_SIGNING_KEY` explicitly.
