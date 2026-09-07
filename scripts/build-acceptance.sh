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

SOURCE=""
while IFS= read -r candidate; do
  if [[ $(shasum -a 256 "$candidate" | awk '{print $1}') == "$EXPECTED_SOURCE_SHA" ]]; then
    SOURCE=$candidate
    break
  fi
done < <(find "$ROOT/.cache/sources" -maxdepth 1 -name "$PACKAGE-*" -type f -print)
if [[ -z "$SOURCE" ]]; then
  python3 "$ROOT/scripts/ports.py" fetch "$PACKAGE" >/dev/null
  while IFS= read -r candidate; do
    if [[ $(shasum -a 256 "$candidate" | awk '{print $1}') == "$EXPECTED_SOURCE_SHA" ]]; then
      SOURCE=$candidate
      break
    fi
  done < <(find "$ROOT/.cache/sources" -maxdepth 1 -name "$PACKAGE-*" -type f -print)
fi
if [[ -z "$SOURCE" ]]; then
  echo "Source checksum mismatch for $PACKAGE." >&2
  exit 1
fi
ACTUAL_SOURCE_SHA=$EXPECTED_SOURCE_SHA
printf 'source=%s\nsha256=%s\n' "$SOURCE" "$ACTUAL_SOURCE_SHA" > "$EVIDENCE_DIR/source-checksum.txt"

FIRST=$(EDGETERM_PRISTINE_SOURCE=1 EDGETERM_FORCE_REBUILD=1 \
  python3 "$ROOT/scripts/ports.py" package "$PACKAGE" | tail -n 1)
FIRST_SHA=$(shasum -a 256 "$FIRST" | awk '{print $1}')
cp "$FIRST" "$EVIDENCE_DIR/first-build.deb"
SECOND=$(EDGETERM_PRISTINE_SOURCE=1 EDGETERM_FORCE_REBUILD=1 \
  python3 "$ROOT/scripts/ports.py" package "$PACKAGE" | tail -n 1)
SECOND_SHA=$(shasum -a 256 "$SECOND" | awk '{print $1}')
if [[ "$FIRST_SHA" != "$SECOND_SHA" ]]; then
  echo "Reproducibility check failed for $PACKAGE." >&2
  exit 1
fi
python3 "$ROOT/scripts/acceptance.py" bind-artifact "$PACKAGE" "$VERSION" "$SECOND_SHA" >/dev/null
printf 'mode=forced-root-rebuild-v1\nfirst=%s\nsecond=%s\n' \
  "$FIRST_SHA" "$SECOND_SHA" > "$EVIDENCE_DIR/reproducible-build.txt"
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" source_checksum "$EVIDENCE_DIR/source-checksum.txt" --artifact-sha256 "$SECOND_SHA" >/dev/null
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" reproducible_build "$EVIDENCE_DIR/reproducible-build.txt" --artifact-sha256 "$SECOND_SHA" >/dev/null

BUILD_MARKER="$ROOT/build/$PACKAGE/build-complete.json"
SOURCE_SNAPSHOT="$ROOT/build/$PACKAGE/source-integrity.json"
if [[ ! -s "$BUILD_MARKER" || ! -s "$SOURCE_SNAPSHOT" ]] || \
   ! grep -Fq '"pristine_source": true' "$BUILD_MARKER"; then
  echo "Pristine-source evidence is incomplete for $PACKAGE." >&2
  exit 1
fi
{
  printf 'mode=pristine-source-v1\n'
  shasum -a 256 "$BUILD_MARKER" "$SOURCE_SNAPSHOT"
} > "$EVIDENCE_DIR/pristine-source.txt"
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" pristine_source "$EVIDENCE_DIR/pristine-source.txt" --artifact-sha256 "$SECOND_SHA" >/dev/null

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
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" license "$EVIDENCE_DIR/license.txt" --artifact-sha256 "$SECOND_SHA" >/dev/null

echo "Build acceptance passed for $PACKAGE."
