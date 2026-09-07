# EdgeTerm package repository

This branch contains 101 candidate packages and 75 packages in the stable suite.
A port directory alone is not counted as a delivered package.

Production URL: https://packages.digitalplat.org/

- `dists/stable` contains packages that satisfy the current artifact acceptance gates.
- `dists/candidate` contains the complete candidate catalog, including experimental capabilities.
- `local-flat` is the signed browser transport for the candidate catalog.
- `catalog.json` lists exact versions, artifact hashes, licenses, and pinned upstream source archives.

EdgeTerm verifies the signed `InRelease`, the index hash, and every downloaded package.
The signing public key fingerprint is `6165B5AE16F62EE3D31837905CECF54DFEE8CFBD`.
Metadata expires after 14 days and must be refreshed by the signed publish job.

Port sources, build scripts, and compatibility changes: https://github.com/EdwardLab/edgeterm-packages
Runtime sources and patches: https://github.com/EdwardLab/EdgeTerm/tree/main/ports/apt-wasix

Generated repository changes are published without rewriting branch history.
