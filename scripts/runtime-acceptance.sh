#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
EDGETERM=${EDGETERM_CHECKOUT:-"$ROOT/../EdgeTerm"}
RUNTIME="$EDGETERM/runtime-packages/external-shell/edgeterm-posix-apt.webc"
DPKG_DATA="$EDGETERM/ports/apt-wasix/.cache/runtime-package/dpkg-data"
PACKAGE=${1:?Package name is required}
SANDBOX=${2:-$(mktemp -d /tmp/edgeterm-package-acceptance.XXXXXX)}
VERSION=$(python3 - "$ROOT/ports/$PACKAGE/port.toml" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as handle:
    port = tomllib.load(handle)
print(f"{port['package']['version']}-{port['package']['revision']}")
PY
)
EVIDENCE_DIR="$ROOT/evidence/$PACKAGE"
RUN_LOG="$EVIDENCE_DIR/runtime-acceptance.log"
mkdir -p "$EVIDENCE_DIR"
: > "$RUN_LOG"
exec > >(tee -a "$RUN_LOG") 2>&1

if [[ ! -f "$RUNTIME" ]]; then
  echo "APT runtime package is missing: $RUNTIME" >&2
  exit 1
fi

if [[ "${EDGETERM_REPOSITORY_READY:-0}" != "1" ]]; then
  python3 "$ROOT/scripts/repository.py" build --channel candidate
fi

mkdir -p \
  "$SANDBOX/home/user/repository" \
  "$SANDBOX/etc/apt/apt.conf.d" \
  "$SANDBOX/etc/apt/preferences.d" \
  "$SANDBOX/etc/apt/sources.list.d" \
  "$SANDBOX/etc/dpkg/dpkg.cfg.d" \
  "$SANDBOX/usr/share" \
  "$SANDBOX/var/cache/apt/archives/partial" \
  "$SANDBOX/var/lib/apt/lists/partial" \
  "$SANDBOX/var/lib/dpkg/info" \
  "$SANDBOX/var/lib/dpkg/parts" \
  "$SANDBOX/var/lib/dpkg/triggers" \
  "$SANDBOX/var/lib/dpkg/updates" \
  "$SANDBOX/var/log/apt" \
  "$SANDBOX/tmp"
mkdir -p "$SANDBOX/usr/local/etc"
touch "$SANDBOX/usr/local/etc/gitconfig"
mkdir -p "$SANDBOX/home/user/.config/git"
touch "$SANDBOX/home/user/.gitconfig" "$SANDBOX/home/user/.config/git/config"
cat > "$SANDBOX/etc/passwd" <<'EOF'
root:x:0:0:root:/home/user:/bin/ash
EOF
cat > "$SANDBOX/etc/group" <<'EOF'
root:x:0:
EOF

cp -R "$DPKG_DATA/." "$SANDBOX/usr/share/"
cp -R "$ROOT/repository/." "$SANDBOX/home/user/repository/"

CURRENT_DEB=$(find "$ROOT/dist" -maxdepth 1 -name "${PACKAGE}_*_wasm32-wasix.deb" -print -quit)
if [[ -z "$CURRENT_DEB" ]]; then
  echo "Package archive is missing for $PACKAGE." >&2
  exit 1
fi
BASELINE_VERSION="0.0.0-0edgeterm1"
docker run --rm --platform linux/arm64 \
  --volume "$CURRENT_DEB:/input/current.deb:ro" \
  --volume "$SANDBOX/home/user:/output" \
  edgeterm-packages:2026-08-05 \
  bash -ec 'dpkg-deb -R /input/current.deb /tmp/baseline; sed -i "s/^Version: .*/Version: '$BASELINE_VERSION'/" /tmp/baseline/DEBIAN/control; dpkg-deb --root-owner-group --build /tmp/baseline /output/baseline.deb'
touch \
  "$SANDBOX/var/lib/dpkg/available" \
  "$SANDBOX/var/lib/dpkg/diversions" \
  "$SANDBOX/var/lib/dpkg/diversions-old" \
  "$SANDBOX/var/lib/dpkg/status" \
  "$SANDBOX/var/lib/dpkg/statoverride" \
  "$SANDBOX/var/lib/dpkg/statoverride-old" \
  "$SANDBOX/var/lib/dpkg/triggers/File" \
  "$SANDBOX/var/lib/dpkg/triggers/Unincorp"
printf '1\n' > "$SANDBOX/var/lib/dpkg/info/format"

cat > "$SANDBOX/etc/apt/apt.conf" <<'EOF'
Dpkg::Use-Pty "false";
Dpkg::Progress-Fancy "false";
APT::Architecture "wasm32-wasix";
APT::Architectures { "wasm32-wasix"; "all"; };
APT::Sandbox::User "root";
Acquire::Languages "none";
Acquire::AllowInsecureRepositories "true";
APT::Get::AllowUnauthenticated "true";
Dir::Bin::Methods "/bin";
Dir::Bin::dpkg "/bin/dpkg";
EOF
printf '%s\n' 'deb [trusted=yes] file:/home/user/repository candidate main' > "$SANDBOX/etc/apt/sources.list"

VOLUMES=(
  --volume "$SANDBOX/home:/home"
  --volume "$SANDBOX/etc:/etc"
  --volume "$SANDBOX/usr:/usr"
  --volume "$SANDBOX/var:/var"
  --volume "$SANDBOX/tmp:/tmp"
)

run_runtime() {
  local entrypoint=$1
  shift
  wasmer run "$RUNTIME" -e "$entrypoint" \
    "${VOLUMES[@]}" \
    --env HOME=/home/user \
    --env USER=root \
    --env LOGNAME=root \
    --env PATH=/usr/local/bin:/usr/local/sbin:/.edgeterm-bin:/bin:/usr/bin \
    -- "$@"
}

run_runtime_checked() {
  local log
  log=$(mktemp "$SANDBOX/tmp/runtime-output.XXXXXX")
  set +e
  run_runtime "$@" 2>&1 | tee "$log"
  local command_status=${PIPESTATUS[0]}
  set -e
  if grep -Eqi 'unrecoverable fatal error|error processing package|dpkg: error|E: Sub-process .* returned an error code' "$log"; then
    echo "Package manager reported a fatal error while running: $*" >&2
    return 1
  fi
  return "$command_status"
}

run_runtime_checked apt update
run_runtime_checked apt install -y /home/user/baseline.deb
run_runtime dpkg-query -W -f='${Version}' "$PACKAGE" | grep -q "^${BASELINE_VERSION}$"
run_runtime_checked apt upgrade -y
run_runtime dpkg-query -W -f='${Version}' "$PACKAGE" | grep -q "^${VERSION}$"
run_runtime dpkg-query -W -f='${Status}' "$PACKAGE" | grep -q '^install ok installed$'

python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" apt_install "$RUN_LOG" >/dev/null
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" apt_upgrade "$RUN_LOG" >/dev/null

BROWSER_THREAD_RUNTIME=0
while IFS= read -r command; do
  for candidate in "$SANDBOX/usr/local/bin/$command" "$SANDBOX/usr/local/sbin/$command"; do
    if [[ -f "$candidate" ]]; then
      inspection=$(wasmer inspect "$candidate" 2>/dev/null || true)
      if grep -q '"memory": shared' <<<"$inspection"; then
        BROWSER_THREAD_RUNTIME=1
        break 2
      fi
    fi
  done
done < <(python3 - "$ROOT/ports/$PACKAGE/port.toml" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as handle:
    for command in tomllib.load(handle)["runtime"]["commands"]:
        print(command)
PY
)

if [[ "$BROWSER_THREAD_RUNTIME" == "1" ]]; then
  echo "Command execution requires the browser threaded runtime; CLI functional checks are deferred."
else

SMOKE_COMMAND=$(python3 - "$ROOT/ports/$PACKAGE/port.toml" <<'PY'
import re
import sys
import tomllib

with open(sys.argv[1], "rb") as handle:
    port = tomllib.load(handle)
command = port["tests"]["smoke"][0]
for executable in sorted(port["runtime"]["commands"], key=len, reverse=True):
    command = re.sub(
        rf"(?<![A-Za-z0-9_./-]){re.escape(executable)}(?=\s|$)",
        f"/usr/local/bin/{executable}",
        command,
    )
print(command)
PY
)
run_runtime ash -c "$SMOKE_COMMAND"
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" version "$RUN_LOG" >/dev/null

case "$PACKAGE" in
  bzip2)
    printf 'EdgeTerm package round trip\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/bzip2 -k /home/user/input.txt'
    rm "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/bzip2 -d /home/user/input.txt.bz2'
    grep -q '^EdgeTerm package round trip$' "$SANDBOX/home/user/input.txt"
    ;;
  grep)
    printf 'alpha\nbeta\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/grep beta /home/user/input.txt' | grep -q '^beta$'
    ;;
  tree)
    mkdir -p "$SANDBOX/home/user/project/src"
    printf 'main\n' > "$SANDBOX/home/user/project/src/main.txt"
    run_runtime ash -c '/usr/local/bin/tree /home/user/project' | grep -q 'main.txt'
    ;;
  bc)
    printf 'scale=2; 5/2\n' > "$SANDBOX/home/user/input.bc"
    run_runtime ash -c '/usr/local/bin/bc -q /home/user/input.bc' | grep -q '^2.50$'
    ;;
  file)
    printf 'EdgeTerm text fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/file /home/user/input.txt' | grep -Eq 'text|ASCII'
    ;;
  sqlite3)
    touch "$SANDBOX/home/user/test.db"
    printf "create table items(value text); insert into items values('ready');\n" > "$SANDBOX/home/user/input.sql"
    run_runtime ash -c '/usr/local/bin/sqlite3 /home/user/test.db < /home/user/input.sql'
    run_runtime ash -c "/usr/local/bin/sqlite3 -batch -noheader /home/user/test.db 'select value from items;'" | grep -q '^ready$'
    ;;
  lz4)
    printf 'EdgeTerm lz4 round trip\n' > "$SANDBOX/home/user/in"
    run_runtime ash -c '/usr/local/bin/lz4 -f /home/user/in /home/user/arc'
    run_runtime ash -c '/usr/local/bin/lz4 -d -c < /home/user/arc > /home/user/out'
    cmp "$SANDBOX/home/user/in" "$SANDBOX/home/user/out"
    ;;
  xxhash)
    printf 'EdgeTerm xxHash fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c 'cd /home/user && /usr/local/bin/xxhsum input.txt > input.txt.xxh'
    run_runtime ash -c 'cd /home/user && /usr/local/bin/xxhsum --check input.txt.xxh' | grep -q '^input.txt: OK$'
    ;;
  brotli)
    printf 'EdgeTerm Brotli round trip\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c 'cd /home/user && /usr/local/bin/brotli input.txt -o input.br'
    rm "$SANDBOX/home/user/input.txt"
    run_runtime ash -c 'cd /home/user && /usr/local/bin/brotli -d input.br -o output.txt'
    grep -q '^EdgeTerm Brotli round trip$' "$SANDBOX/home/user/output.txt"
    ;;
  gzip)
    printf 'EdgeTerm gzip round trip\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c 'cd /home/user && /usr/local/bin/gzip -c input.txt > input.gz'
    run_runtime ash -c 'cd /home/user && /usr/local/bin/gzip -dc input.gz > output.txt'
    cmp "$SANDBOX/home/user/input.txt" "$SANDBOX/home/user/output.txt"
    ;;
  xz-utils)
    printf 'EdgeTerm xz round trip\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c 'cd /home/user && /usr/local/bin/xz -c input.txt > input.xz'
    run_runtime ash -c 'cd /home/user && /usr/local/bin/xz -dc input.xz > output.txt'
    cmp "$SANDBOX/home/user/input.txt" "$SANDBOX/home/user/output.txt"
    ;;
  zstd)
    printf 'EdgeTerm zstd round trip\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c 'cd /home/user && /usr/local/bin/zstd -q -c input.txt > input.zst'
    run_runtime ash -c 'cd /home/user && /usr/local/bin/zstd -q -d -c input.zst > output.txt'
    cmp "$SANDBOX/home/user/input.txt" "$SANDBOX/home/user/output.txt"
    ;;
  m4)
    printf 'define(X,ready)X\n' > "$SANDBOX/home/user/input.m4"
    run_runtime ash -c '/usr/local/bin/m4 /home/user/input.m4' | grep -q '^ready$'
    ;;
  sed)
    printf 'alpha\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c "/usr/local/bin/sed 's/alpha/beta/' /home/user/input.txt" | grep -q '^beta$'
    ;;
  diffutils)
    printf 'same\n' > "$SANDBOX/home/user/a.txt"
    cp "$SANDBOX/home/user/a.txt" "$SANDBOX/home/user/b.txt"
    run_runtime ash -c '/usr/local/bin/diff /home/user/a.txt /home/user/b.txt'
    printf 'changed\n' > "$SANDBOX/home/user/b.txt"
    set +e
    diff_output=$(run_runtime ash -c '/usr/local/bin/diff /home/user/a.txt /home/user/b.txt')
    diff_status=$?
    set -e
    [[ "$diff_status" == "1" ]]
    grep -q '^< same$' <<<"$diff_output"
    ;;
  patch)
    printf 'before\n' > "$SANDBOX/home/user/value.txt"
    cat > "$SANDBOX/home/user/value.patch" <<'EOF'
--- value.txt
+++ value.txt
@@ -1 +1 @@
-before
+after
EOF
    run_runtime ash -c 'cd /home/user && /usr/local/bin/patch < value.patch'
    grep -q '^after$' "$SANDBOX/home/user/value.txt"
    ;;
  tar)
    mkdir -p "$SANDBOX/home/user/archive/source" "$SANDBOX/home/user/archive/output"
    printf 'tar fixture\n' > "$SANDBOX/home/user/archive/source/value.txt"
    run_runtime ash -c 'cd /home/user/archive && /usr/local/bin/tar -cf value.tar source'
    run_runtime ash -c 'cd /home/user/archive/output && /usr/local/bin/tar -xf ../value.tar'
    grep -q '^tar fixture$' "$SANDBOX/home/user/archive/output/source/value.txt"
    ;;
  cpio)
    mkdir -p "$SANDBOX/home/user/cpio/source" "$SANDBOX/home/user/cpio/output"
    printf 'cpio fixture\n' > "$SANDBOX/home/user/cpio/source/value.txt"
    printf 'value.txt\n' > "$SANDBOX/home/user/cpio/source/files.txt"
    run_runtime ash -c 'cd /home/user/cpio/source && /usr/local/bin/cpio -o -F /home/user/cpio/value.cpio < /home/user/cpio/source/files.txt'
    run_runtime ash -c 'cd /home/user/cpio/output && /usr/local/bin/cpio -id -F /home/user/cpio/value.cpio'
    grep -q '^cpio fixture$' "$SANDBOX/home/user/cpio/output/value.txt"
    ;;
  jq)
    printf '{"ready":true}\n' > "$SANDBOX/home/user/input.json"
    run_runtime ash -c '/usr/local/bin/jq -M -r .ready /home/user/input.json' | grep -q '^true$'
    ;;
  yq)
    printf 'ready: true\n' > "$SANDBOX/home/user/input.yml"
    run_runtime ash -c '/usr/local/bin/yq -r .ready /home/user/input.yml' | grep -q '^true$'
    ;;
  lua)
    run_runtime ash -c "/usr/local/bin/lua -e 'print(6 * 7)'" | grep -q '^42$'
    ;;
  shfmt)
    printf 'if true;then echo ready;fi\n' > "$SANDBOX/home/user/input.sh"
    run_runtime ash -c '/usr/local/bin/shfmt /home/user/input.sh > /home/user/output.sh'
    grep -q '^if true; then echo ready; fi$' "$SANDBOX/home/user/output.sh"
    ;;
  ripgrep)
    mkdir -p "$SANDBOX/home/user/search"
    printf 'alpha\nneedle\nomega\n' > "$SANDBOX/home/user/search/input.txt"
    run_runtime ash -c '/usr/local/bin/rg --fixed-strings needle /home/user/search' | grep -q 'needle'
    ;;
  pkgconf)
    mkdir -p "$SANDBOX/home/user/pkgconfig"
    cat > "$SANDBOX/home/user/pkgconfig/sample.pc" <<'EOF'
prefix=/home/user/sample
Name: sample
Description: EdgeTerm package fixture
Version: 1.2.3
Libs: -L${prefix}/lib -lsample
Cflags: -I${prefix}/include
EOF
    run_runtime ash -c 'PKG_CONFIG_PATH=/home/user/pkgconfig /usr/local/bin/pkgconf --modversion sample' | grep -q '^1.2.3$'
    ;;
  make)
    cat > "$SANDBOX/home/user/Makefile" <<'EOF'
all:
	printf 'ready\n' > result.txt
EOF
    run_runtime ash -c 'cd /home/user && /usr/local/bin/make'
    grep -q '^ready$' "$SANDBOX/home/user/result.txt"
    ;;
  ninja-build)
    cat > "$SANDBOX/home/user/build.ninja" <<'EOF'
rule generate
  command = /bin/ash -c "printf ready > /home/user/output.txt"
build /home/user/output.txt: generate
EOF
    run_runtime ash -c '/usr/local/bin/ninja -f /home/user/build.ninja'
    grep -q '^ready$' "$SANDBOX/home/user/output.txt"
    ;;
  bash)
    cat > "$SANDBOX/home/user/script.sh" <<'EOF'
set -eu
items=(alpha beta)
printf '%s\n' "${items[1]}"
EOF
    run_runtime ash -c '/usr/local/bin/bash /home/user/script.sh' | grep -q '^beta$'
    ;;
  dash)
    printf 'set -eu\nprintf "%s\\n" ready\n' > "$SANDBOX/home/user/script.sh"
    run_runtime ash -c '/usr/local/bin/dash /home/user/script.sh' | grep -q '^ready$'
    ;;
  coreutils)
    printf 'coreutils fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/cp /home/user/input.txt /home/user/output.txt'
    run_runtime ash -c '/usr/local/bin/sha256sum /home/user/output.txt' | grep -Eq '^[a-f0-9]{64}  /home/user/output.txt$'
    ;;
  findutils)
    mkdir -p "$SANDBOX/home/user/find/nested"
    printf 'ready\n' > "$SANDBOX/home/user/find/nested/result.txt"
    run_runtime ash -c '/usr/local/bin/find /home/user/find -name result.txt' | grep -q '/home/user/find/nested/result.txt'
    ;;
  gawk)
    printf 'alpha 6\nbeta 7\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c "/usr/local/bin/gawk '{ total += \$2 } END { print total }' /home/user/input.txt" | grep -q '^13$'
    ;;
  gettext)
    run_runtime ash -c "NAME=EdgeTerm /usr/local/bin/envsubst '\$NAME' <<'EOF'
Hello \$NAME
EOF" | grep -q '^Hello EdgeTerm$'
    ;;
  bat)
    printf 'const answer = 42;\n' > "$SANDBOX/home/user/input.js"
    run_runtime ash -c '/usr/local/bin/bat --paging=never --style=plain /home/user/input.js' | grep -q 'answer'
    ;;
  cmake)
    printf 'cmake fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/cmake -E copy /home/user/input.txt /home/user/output.txt'
    cmp "$SANDBOX/home/user/input.txt" "$SANDBOX/home/user/output.txt"
    ;;
  eza)
    mkdir -p "$SANDBOX/home/user/eza-fixture"
    printf 'ready\n' > "$SANDBOX/home/user/eza-fixture/result.txt"
    run_runtime ash -c '/usr/local/bin/eza --oneline /home/user/eza-fixture' | grep -q '^result.txt$'
    ;;
  fd-find)
    mkdir -p "$SANDBOX/home/user/fd-fixture/nested"
    printf 'ready\n' > "$SANDBOX/home/user/fd-fixture/nested/result.txt"
    run_runtime ash -c '/usr/local/bin/fd --threads 1 --absolute-path result /home/user/fd-fixture' | grep -q '/nested/result.txt$'
    ;;
  hyperfine)
    run_runtime ash -c '/usr/local/bin/hyperfine --warmup 0 --runs 2 /bin/true' | grep -q 'Time'
    ;;
  just)
    cat > "$SANDBOX/home/user/justfile" <<'EOF'
ready:
    printf 'ready\n'
EOF
    run_runtime ash -c '/usr/local/bin/just --justfile /home/user/justfile --list' | grep -q '^    ready$'
    ;;
  git)
    run_runtime ash -c 'cd /home/user && /usr/local/bin/git init --quiet git-fixture && cd git-fixture && /usr/local/bin/git config user.name EdgeTerm && /usr/local/bin/git config user.email packages@digitalplat.org && printf ready > value.txt && /usr/local/bin/git add value.txt && /usr/local/bin/git commit --quiet -m initial && /usr/local/bin/git diff --exit-code HEAD'
    ;;
  rhash)
    printf 'EdgeTerm RHash fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/rhash --sha256 /home/user/input.txt' | grep -Eq '[a-f0-9]{64}'
    ;;
  zip)
    printf 'zip fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c 'cd /home/user && /usr/local/bin/zip -q /home/user/fixture.zip /home/user/input.txt'
    python3 - "$SANDBOX/home/user/fixture.zip" <<'PY'
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1]) as archive:
    assert archive.testzip() is None
    assert archive.read("home/user/input.txt") == b"zip fixture\n"
PY
    ;;
  unzip)
    python3 - "$SANDBOX/home/user/fixture.zip" <<'PY'
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1], "w") as archive:
    archive.writestr("value.txt", "unzip fixture\n")
PY
    mkdir -p "$SANDBOX/home/user/unzip-output"
    run_runtime ash -c '/usr/local/bin/unzip -q /home/user/fixture.zip -d /home/user/unzip-output'
    grep -q '^unzip fixture$' "$SANDBOX/home/user/unzip-output/value.txt"
    ;;
  p7zip)
    printf 'p7zip fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c 'cd /home/user && /usr/local/bin/7za a -bd fixture.7z input.txt >/dev/null && /usr/local/bin/7za t -bd fixture.7z >/dev/null'
    ;;
  curl)
    run_runtime ash -c "/usr/local/bin/curl --silent 'data:text/plain,ready'" | grep -q '^ready$'
    ;;
  wget)
    printf 'wget fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/wget -q -O /home/user/output.txt file:///home/user/input.txt'
    cmp "$SANDBOX/home/user/input.txt" "$SANDBOX/home/user/output.txt"
    ;;
  openssl)
    printf 'openssl fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/openssl dgst -sha256 /home/user/input.txt' | grep -Eq '[a-f0-9]{64}'
    ;;
  openssh-client)
    run_runtime ash -c "/usr/local/bin/ssh-keygen -q -t ed25519 -N '' -f /home/user/test-key"
    test -s "$SANDBOX/home/user/test-key"
    test -s "$SANDBOX/home/user/test-key.pub"
    ;;
  rsync)
    mkdir -p "$SANDBOX/home/user/rsync-source" "$SANDBOX/home/user/rsync-output"
    printf 'rsync fixture\n' > "$SANDBOX/home/user/rsync-source/value.txt"
    run_runtime ash -c '/usr/local/bin/rsync -a /home/user/rsync-source/ /home/user/rsync-output/'
    grep -q '^rsync fixture$' "$SANDBOX/home/user/rsync-output/value.txt"
    ;;
  dnsutils)
    run_runtime ash -c '/usr/local/bin/dig -h' 2>&1 | grep -q 'Usage:'
    ;;
  netcat-openbsd)
    run_runtime ash -c '/usr/local/bin/nc -h' 2>&1 | grep -q 'usage:'
    ;;
  *)
    echo "No functional runtime fixture is defined for $PACKAGE." >&2
    exit 2
    ;;
esac

python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" functional "$RUN_LOG" >/dev/null
fi

if [[ "${EDGETERM_KEEP_INSTALLED:-0}" == "1" ]]; then
  echo "Installed package retained for inspection: $SANDBOX"
  exit 0
fi

run_runtime_checked apt remove -y "$PACKAGE"
if remove_status=$(run_runtime dpkg-query -W -f='${Status}' "$PACKAGE" 2>/dev/null); then
  printf '%s\n' "$remove_status" | grep -q '^deinstall ok config-files$'
fi
while IFS= read -r command; do
  if [[ -e "$SANDBOX/usr/local/bin/$command" || -e "$SANDBOX/usr/local/sbin/$command" ]]; then
    echo "Package command remains after removal: $command" >&2
    exit 1
  fi
done < <(python3 - "$ROOT/ports/$PACKAGE/port.toml" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as handle:
    for command in tomllib.load(handle)["runtime"]["commands"]:
        print(command)
PY
)
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" apt_remove "$RUN_LOG" >/dev/null
run_runtime_checked apt purge -y "$PACKAGE"
if run_runtime dpkg-query -W -f='${Status}' "$PACKAGE" >/dev/null 2>&1; then
  echo "Purged package is still present in the package database." >&2
  exit 1
fi
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" apt_purge "$RUN_LOG" >/dev/null

echo "Runtime acceptance passed for $PACKAGE."
echo "Persistent sandbox: $SANDBOX"
