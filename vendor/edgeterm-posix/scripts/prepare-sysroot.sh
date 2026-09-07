#!/bin/sh
set -eu

sysroot=${1:?WASIX sysroot path is required}

if [ ! -d "$sysroot/include" ] || [ ! -d "$sysroot/lib/wasm32-wasi" ]; then
    echo "The selected WASIX sysroot is incomplete: $sysroot" >&2
    exit 1
fi

if [ ! -e "$sysroot/lib/wasm32-wasip1" ]; then
    ln -s wasm32-wasi "$sysroot/lib/wasm32-wasip1"
fi

if [ ! -e "$sysroot/lib/wasm32-wasip1-threads" ] && \
   [ -d "$sysroot/lib/wasm32-wasi-threads" ]; then
    ln -s wasm32-wasi-threads "$sysroot/lib/wasm32-wasip1-threads"
fi
