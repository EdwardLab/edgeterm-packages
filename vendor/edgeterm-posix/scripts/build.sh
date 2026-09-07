#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
prefix=${EDGETERM_POSIX_PREFIX:-}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --prefix)
            prefix=$2
            shift 2
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

: "${prefix:?Pass --prefix or set EDGETERM_POSIX_PREFIX}"
: "${CC:=cc}"
: "${AR:=ar}"
: "${CFLAGS:=-O2}"

build_dir=${EDGETERM_POSIX_BUILD_DIR:-"$root/build"}
mkdir -p "$build_dir" "$prefix/include" "$prefix/lib" "$prefix/share/edgeterm-posix/cmake"

common_flags="-DEDGETERM_POSIX_INTERNAL=1 -I$root/include $CFLAGS"
"$CC" $common_flags -c "$root/src/compat.c" -o "$build_dir/compat.o"
"$CC" $common_flags -c "$root/src/descriptors.c" -o "$build_dir/descriptors.o"
"$CC" $common_flags -c "$root/src/time.c" -o "$build_dir/time.o"
"$CC" $common_flags -c "$root/src/filesystem.c" -o "$build_dir/filesystem.o"
"$CC" $common_flags -c "$root/src/mounts.c" -o "$build_dir/mounts.o"
"$CC" $common_flags -c "$root/src/startup.c" -o "$build_dir/startup.o"
"$CC" $common_flags -c "$root/src/capabilities.c" -o "$build_dir/capabilities.o"
"$CC" $common_flags -c "$root/src/io.c" -o "$build_dir/io.o"
"$CC" $common_flags -c "$root/src/main_env.c" -o "$build_dir/main_env.o"
rm -f "$prefix/lib/libedgeterm-posix.a"
"$AR" rcs "$prefix/lib/libedgeterm-posix.a" \
    "$build_dir/compat.o" "$build_dir/descriptors.o" "$build_dir/time.o" \
    "$build_dir/filesystem.o" "$build_dir/mounts.o" \
    "$build_dir/startup.o" "$build_dir/capabilities.o" "$build_dir/io.o"
rm -f "$prefix/lib/libedgeterm-main-env.a"
"$AR" rcs "$prefix/lib/libedgeterm-main-env.a" "$build_dir/main_env.o"

cp -R "$root/include/." "$prefix/include/"
cp "$root/cmake/project-platform.cmake" "$prefix/share/edgeterm-posix/cmake/"
cp "$root/profile/edgeterm-posix-v1.json" "$prefix/share/edgeterm-posix/"
cp "$root/VERSION" "$prefix/share/edgeterm-posix/"
printf '%s\n' "$prefix"
