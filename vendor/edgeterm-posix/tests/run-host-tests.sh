#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
temporary=$(mktemp -d "${TMPDIR:-/tmp}/edgeterm-posix.XXXXXX")
trap 'find "$temporary" -depth -delete' EXIT HUP INT TERM

CC=${CC:-cc}
AR=${AR:-ar}
CFLAGS=${CFLAGS:-"-O2 -Wall -Wextra -Werror"}

EDGETERM_POSIX_BUILD_DIR="$temporary/build" \
    CC="$CC" AR="$AR" CFLAGS="$CFLAGS" \
    "$root/scripts/build.sh" --prefix "$temporary/prefix" >/dev/null

for source in "$root"/tests/conformance/*.c; do
    name=$(basename "$source" .c)
    "$CC" $CFLAGS -I"$temporary/prefix/include" \
        "$source" \
        -Wl,-force_load,"$temporary/prefix/lib/libedgeterm-posix.a" \
        -o "$temporary/$name"
    "$temporary/$name"
done

python3 -m json.tool "$root/profile/edgeterm-posix-v1.json" >/dev/null
python3 "$root/tests/check-profile.py"
python3 -m unittest "$root/tests/test-normalize-source.py"
python3 -m unittest "$root/tests/test-source-integrity.py"
python3 -m unittest "$root/tests/test-ensure-build-profile.py"
CONFIG_SITE="$root/config/config.site" sh -ceu '
    . "$CONFIG_SITE"
    test "$bash_cv_func_sigsetjmp" = missing
'
echo "EdgeTerm POSIX host conformance passed"
