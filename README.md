# EdgeTerm APT Repository

This branch is reserved for generated, signed APT repository snapshots consumed by EdgeTerm.

Published snapshots contain only:

- `dists/stable/` for packages that passed the full acceptance suite.
- `dists/candidate/` for packages still undergoing browser validation.
- `pool/` for immutable package artifacts.
- The public repository signing key and publication metadata.

Build recipes, source patches, tests, private signing material, and temporary acceptance artifacts do not belong on this branch. Release automation replaces the generated snapshot only after metadata and package signatures have been verified.
