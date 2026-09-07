#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
packages=${EDGETERM_PACKAGES_CHECKOUT:-"$root/../EdgeTerm-Packages"}
cache=${EDGETERM_TOOLCHAIN_CACHE:-"$packages/.cache/edgeterm-apt-wasix"}
sdk=${EDGETERM_WASI_SDK:-}
sysroot=${EDGETERM_WASIX_SYSROOT:-"$cache/wasix-sysroot-v2025-11-06.1.tar.gz"}
image=${EDGETERM_BUILD_IMAGE:-edgeterm-packages:2026-08-05}
output="$root/build/wasix-tests"

command -v docker >/dev/null
command -v wasmer >/dev/null
if [ -z "$sdk" ]; then
    for candidate in "$cache"/wasi-sdk-33.0-*; do
        if [ -x "$candidate/bin/clang" ]; then
            sdk=$candidate
            break
        fi
    done
fi
test -x "$sdk/bin/clang"
test -f "$sysroot"
mkdir -p "$output"

docker run --rm \
    -v "$root:/source:ro" \
    -v "$output:/output" \
    -v "$sdk:/wasi-sdk:ro" \
    -v "$sysroot:/toolchain/sysroot.tar.gz:ro" \
    "$image" sh -ceu '
        mkdir -p /toolchain/sysroot /output/objects /output/prefix
        tar -xzf /toolchain/sysroot.tar.gz -C /toolchain/sysroot
        sysroot=$(find /toolchain/sysroot -mindepth 2 -maxdepth 2 -type d -name sysroot -print -quit)
        /source/scripts/prepare-sysroot.sh "$sysroot"
        EDGETERM_POSIX_BUILD_DIR=/output/objects \
            CC=/wasi-sdk/bin/clang AR=/wasi-sdk/bin/llvm-ar \
            CFLAGS="--target=wasm32-wasip1 --sysroot=$sysroot -O2" \
            /source/scripts/build.sh --prefix /output/prefix >/dev/null
        EDGETERM_POSIX_BUILD_DIR=/output/objects-threads \
            CC=/wasi-sdk/bin/clang AR=/wasi-sdk/bin/llvm-ar \
            CFLAGS="--target=wasm32-wasip1 --sysroot=$sysroot -O2 -pthread -DEDGETERM_POSIX_THREADS" \
            /source/scripts/build.sh --prefix /output/prefix-threads >/dev/null
        for source in /source/tests/conformance/*.c; do
            name=$(basename "$source" .c)
            /wasi-sdk/bin/clang --target=wasm32-wasip1 --sysroot="$sysroot" \
                -O2 -D_WASI_EMULATED_PROCESS_CLOCKS \
                -isystem /output/prefix/include \
                "$source" \
                -Wl,--whole-archive /output/prefix/lib/libedgeterm-posix.a \
                -Wl,--no-whole-archive \
                -Wl,--wrap=open -Wl,--wrap=openat -Wl,--wrap=poll \
                -lwasi-emulated-process-clocks \
                -o "/output/$name.wasm"
        done
        for source in /source/tests/conformance/*.cpp; do
            name=$(basename "$source" .cpp)
            /wasi-sdk/bin/clang++ --target=wasm32-wasip1 --sysroot="$sysroot" \
                -O2 -isystem /output/prefix/include \
                "$source" \
                -Wl,--whole-archive /output/prefix/lib/libedgeterm-posix.a \
                -Wl,--no-whole-archive \
                -Wl,--wrap=open -Wl,--wrap=openat -Wl,--wrap=poll \
                -o "/output/$name.wasm"
        done
        /wasi-sdk/bin/clang --target=wasm32-wasip1 --sysroot="$sysroot" \
            -O2 -isystem /output/prefix/include \
            /source/tests/conformance/standard_headers.c \
            -Wl,--whole-archive /output/prefix/lib/libedgeterm-posix.a \
            /output/prefix/lib/libedgeterm-posix.a \
            /output/prefix/lib/libedgeterm-posix.a \
            -Wl,--no-whole-archive \
            -Wl,--wrap=open -Wl,--wrap=openat -Wl,--wrap=poll \
            -o /output/repeated-link.wasm
        /wasi-sdk/bin/clang --target=wasm32-wasip1 --sysroot="$sysroot" \
            -O2 -pthread -DEDGETERM_POSIX_THREADS \
            -isystem /output/prefix-threads/include \
            /source/tests/conformance/filesystem_mutation.c \
            -Wl,--whole-archive /output/prefix-threads/lib/libedgeterm-posix.a \
            -Wl,--no-whole-archive \
            -Wl,--wrap=open -Wl,--wrap=openat -Wl,--wrap=poll \
            -Wl,--initial-memory=16777216 -Wl,--max-memory=268435456 \
            -o /output/filesystem_mutation_threads.wasm
    '

for executable in "$output"/*.wasm; do
    [ "$(basename "$executable")" = process_spawn.wasm ] && continue
    wasmer run "$executable" --env USER=edgeterm-test --env LOGNAME=edgeterm-test
done

spawn_package="$output/process-spawn-package"
rm -rf "$spawn_package"
mkdir -p "$spawn_package"
cp "$output/process_spawn.wasm" "$spawn_package/process_spawn.wasm"
cat >"$spawn_package/wasmer.toml" <<'EOF'
[package]
name = "digitalplat/edgeterm-posix-spawn-test"
version = "0.1.0"
description = "Process spawn conformance test"
entrypoint = "edgeterm-posix-spawn"

[[module]]
name = "process-spawn"
source = "process_spawn.wasm"
abi = "wasi"

[[command]]
name = "edgeterm-posix-spawn"
module = "process-spawn"
EOF
rm -f "$output/process-spawn.webc"
wasmer package build "$spawn_package/wasmer.toml" \
    --out "$output/process-spawn.webc"
wasmer run "$output/process-spawn.webc" -e edgeterm-posix-spawn

mounted_test=$(mktemp -d "$output/mounted-rmdir.XXXXXX")
mkdir -p "$mounted_test/home/user/existing"
wasmer run "$output/filesystem_mutation_threads.wasm" \
    --volume "$mounted_test/home:/home" \
    --env EDGETERM_POSIX_TEST_RMDIR_EXISTING=/home/user/existing
test ! -e "$mounted_test/home/user/existing"

wasmer run "$output/filesystem_mutation_threads.wasm" \
    --volume "$mounted_test/home:/home" \
    --env EDGETERM_POSIX_TEST_FILE_BASE=/home/user

echo "EdgeTerm POSIX WASIX conformance passed"
