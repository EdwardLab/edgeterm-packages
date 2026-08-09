#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
PACKAGE=${1:?Package name is required}
PORT="$ROOT/ports/$PACKAGE/port.toml"
EVIDENCE_DIR="$ROOT/evidence/$PACKAGE"
mkdir -p "$EVIDENCE_DIR"

IFS=$'\t' read -r VERSION EXPECTED_SOURCE_SHA DECLARED_LICENSE < <(python3 - "$PORT" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as handle:
    port = tomllib.load(handle)
print(
    f"{port['package']['version']}-{port['package']['revision']}",
    port['source']['sha256'],
    port['package']['license'],
    sep="\t",
)
PY
)

SOURCE=$(find "$ROOT/.cache/sources" -maxdepth 1 -name "$PACKAGE-*" -type f -print -quit)
if [[ -z "$SOURCE" ]]; then
  python3 "$ROOT/scripts/ports.py" fetch "$PACKAGE" >/dev/null
  SOURCE=$(find "$ROOT/.cache/sources" -maxdepth 1 -name "$PACKAGE-*" -type f -print -quit)
fi
ACTUAL_SOURCE_SHA=$(shasum -a 256 "$SOURCE" | awk '{print $1}')
if [[ "$ACTUAL_SOURCE_SHA" != "$EXPECTED_SOURCE_SHA" ]]; then
  echo "Source checksum mismatch for $PACKAGE." >&2
  exit 1
fi
printf 'source=%s\nsha256=%s\n' "$SOURCE" "$ACTUAL_SOURCE_SHA" > "$EVIDENCE_DIR/source-checksum.txt"
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" source_checksum "$EVIDENCE_DIR/source-checksum.txt" >/dev/null

FIRST=$(python3 "$ROOT/scripts/ports.py" package "$PACKAGE" | tail -n 1)
FIRST_SHA=$(shasum -a 256 "$FIRST" | awk '{print $1}')
cp "$FIRST" "$EVIDENCE_DIR/first-build.deb"
SECOND=$(python3 "$ROOT/scripts/ports.py" package "$PACKAGE" | tail -n 1)
SECOND_SHA=$(shasum -a 256 "$SECOND" | awk '{print $1}')
if [[ "$FIRST_SHA" != "$SECOND_SHA" ]]; then
  echo "Reproducibility check failed for $PACKAGE." >&2
  exit 1
fi
printf 'first=%s\nsecond=%s\n' "$FIRST_SHA" "$SECOND_SHA" > "$EVIDENCE_DIR/reproducible-build.txt"
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" reproducible_build "$EVIDENCE_DIR/reproducible-build.txt" >/dev/null

EXTRACTED=$(mktemp -d "/tmp/edgeterm-license-${PACKAGE}.XXXXXX")
docker run --rm --platform linux/arm64 \
  --volume "$SECOND:/input/package.deb:ro" \
  --volume "$EXTRACTED:/output" \
  edgeterm-packages:2026-08-05 \
  dpkg-deb -x /input/package.deb /output
COPYRIGHT="$EXTRACTED/usr/share/doc/$PACKAGE/copyright"
SBOM="$EXTRACTED/usr/share/doc/$PACKAGE/sbom.cdx.json"
if [[ ! -s "$COPYRIGHT" || ! -s "$SBOM" ]] || ! grep -Fq "\"id\": \"$DECLARED_LICENSE\"" "$SBOM"; then
  echo "License evidence is incomplete for $PACKAGE." >&2
  exit 1
fi
{
  printf 'license=%s\n' "$DECLARED_LICENSE"
  shasum -a 256 "$COPYRIGHT" "$SBOM"
} > "$EVIDENCE_DIR/license.txt"
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" license "$EVIDENCE_DIR/license.txt" >/dev/null

echo "Build acceptance passed for $PACKAGE."
