#!/usr/bin/env bash
set -euo pipefail

source_root=$1
runtime_root=/build/stage/usr/local/share/edgeterm/runtime-packages/php
bin_root=/build/stage/usr/local/bin

launcher=$(find "$source_root" -path '*/jspi/php_8_4.js' -type f -print -quit)
wasm=$(find "$source_root" -path '*/jspi/8_4_23/php_8_4.wasm' -type f -print -quit)
intl=$(find "$source_root" -path '*/jspi/extensions/intl/intl.so' -type f -print -quit)

if [[ -z "$launcher" || -z "$wasm" || -z "$intl" ]]; then
  echo "The pinned PHP runtime archive is incomplete." >&2
  exit 1
fi

install -d "$runtime_root" "$bin_root"
install -m 0644 "$launcher" "$runtime_root/php_8_4.js"
install -m 0644 "$wasm" "$runtime_root/php_8_4.wasm"
install -m 0644 "$intl" "$runtime_root/intl.so"
install -m 0644 /port/package.json "$runtime_root/package.json"
install -m 0755 /port/php-runtime-info "$bin_root/php-runtime-info"
