# Repository signing keys

Only the public repository key may be committed here. Production private keys belong in the release secret store and are mounted into the signing job for the duration of a release.

The publisher accepts `EDGETERM_APT_SIGNING_KEY` as a key fingerprint. It never accepts private key material through a command-line argument.
