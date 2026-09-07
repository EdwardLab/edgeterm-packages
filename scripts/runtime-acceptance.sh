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
CURRENT_DEB="$ROOT/dist/${PACKAGE}_${VERSION}_wasm32-wasix.deb"
mkdir -p "$EVIDENCE_DIR"
: > "$RUN_LOG"
exec > >(tee -a "$RUN_LOG") 2>&1

if [[ ! -f "$RUNTIME" ]]; then
  echo "APT runtime package is missing: $RUNTIME" >&2
  exit 1
fi

if [[ "${EDGETERM_ACCEPTANCE_CURRENT_PACKAGE_ONLY:-0}" != "1" && \
      "${EDGETERM_REPOSITORY_READY:-0}" != "1" ]]; then
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

if [[ ! -f "$CURRENT_DEB" ]]; then
  echo "Package archive is missing for $PACKAGE." >&2
  exit 1
fi
cp -R "$DPKG_DATA/." "$SANDBOX/usr/share/"
if [[ "${EDGETERM_ACCEPTANCE_CURRENT_PACKAGE_ONLY:-0}" == "1" ]]; then
  python3 - "$ROOT" "$SANDBOX/home/user/repository" "$PACKAGE" <<'PY'
import sys
import shutil
from pathlib import Path

root = Path(sys.argv[1])
repository = Path(sys.argv[2])
package_name = sys.argv[3]
sys.path.insert(0, str(root / "scripts"))
from repository import write_packages_index
from ports import load_ports

ports = load_ports()
pending = [package_name]
selected = set()
while pending:
    current = pending.pop()
    if current in selected:
        continue
    port = ports[current]
    selected.add(current)
    pending.extend(port.data["package"].get("depends", []))

for current in sorted(selected):
    port = ports[current]
    source = root / "dist" / f"{current}_{port.deb_version}_wasm32-wasix.deb"
    if not source.is_file():
        raise FileNotFoundError(f"Dependency artifact is missing: {source}")
    shutil.copy2(source, repository / source.name)

write_packages_index(repository, repository, repository / "Packages")
PY
  APT_SOURCE='deb [trusted=yes] file:/home/user/repository ./'
else
  cp -R "$ROOT/repository/dists" "$ROOT/repository/pool" "$SANDBOX/home/user/repository/"
  APT_SOURCE='deb [trusted=yes] file:/home/user/repository candidate main'
fi
ARTIFACT_SHA256=$(shasum -a 256 "$CURRENT_DEB" | awk '{print $1}')
python3 "$ROOT/scripts/acceptance.py" bind-artifact "$PACKAGE" "$VERSION" "$ARTIFACT_SHA256" >/dev/null
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
printf '%s\n' "$APT_SOURCE" > "$SANDBOX/etc/apt/sources.list"

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
  local trace_open=()
  if [[ -n "${EDGETERM_POSIX_TRACE_OPEN:-}" ]]; then
    trace_open=(--env EDGETERM_POSIX_TRACE_OPEN="$EDGETERM_POSIX_TRACE_OPEN")
  fi
  wasmer run "$RUNTIME" -e "$entrypoint" \
    "${VOLUMES[@]}" \
    "${trace_open[@]}" \
    --env HOME=/home/user \
    --env USER=root \
    --env LOGNAME=root \
    --env PATH=/usr/local/bin:/usr/local/sbin:/.edgeterm-bin:/bin:/usr/bin \
    --env EDGETERM_STDIN_MODE=pipe \
    --env EDGETERM_STDOUT_MODE=pipe \
    --env EDGETERM_STDERR_MODE=pipe \
    --env TERM=xterm \
    --env TERMINFO=/usr/local/share/terminfo \
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

run_runtime_matches() {
  local pattern=$1
  shift
  local log
  log=$(mktemp "$SANDBOX/tmp/runtime-match.XXXXXX")
  if ! run_runtime "$@" >"$log" 2>&1; then
    cat "$log"
    return 1
  fi
  cat "$log"
  grep -Eq "$pattern" "$log"
}

run_runtime_checked apt update
run_runtime_checked apt install -y /home/user/baseline.deb
run_runtime_matches "^${BASELINE_VERSION}$" dpkg-query -W -f='${Version}' "$PACKAGE"
run_runtime_checked apt upgrade -y
run_runtime_matches "^${VERSION}$" dpkg-query -W -f='${Version}' "$PACKAGE"
run_runtime_matches '^install ok installed$' dpkg-query -W -f='${Status}' "$PACKAGE"

python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" apt_install "$RUN_LOG" --artifact-sha256 "$ARTIFACT_SHA256" >/dev/null
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" apt_upgrade "$RUN_LOG" --artifact-sha256 "$ARTIFACT_SHA256" >/dev/null

BROWSER_THREAD_RUNTIME=$(python3 - "$ROOT/ports/$PACKAGE/port.toml" <<'PY'
import sys
import tomllib

with open(sys.argv[1], "rb") as handle:
    print(1 if tomllib.load(handle)["runtime"].get("browser_only", False) else 0)
PY
)
while IFS= read -r command; do
  if [[ "$BROWSER_THREAD_RUNTIME" == "1" ]]; then
    break
  fi
  for candidate in \
    "$SANDBOX/usr/local/bin/$command" \
    "$SANDBOX/usr/local/sbin/$command" \
    "$SANDBOX/usr/local/sbin/${command}-real"; do
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
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" version "$RUN_LOG" --artifact-sha256 "$ARTIFACT_SHA256" >/dev/null

case "$PACKAGE" in
  bash)
    cat > "$SANDBOX/home/user/bash-loop.sh" <<'EOF'
for value in 40 41 42; do
  :
done
printf 'BASH_%s\n' "$value"
EOF
    run_runtime ash -c '/usr/local/bin/bash /home/user/bash-loop.sh' | grep -q '^BASH_42$'
    ;;
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
  unzip)
    mkdir -p "$SANDBOX/home/user/unzip/output"
    python3 - "$SANDBOX/home/user/unzip/value.zip" <<'PY'
import sys
import zipfile

with zipfile.ZipFile(sys.argv[1], "w") as archive:
    archive.writestr("nested/value.txt", "unzip fixture\n")
PY
    run_runtime ash -c 'cd /home/user/unzip/output && /usr/local/bin/unzip ../value.zip'
    grep -q '^unzip fixture$' "$SANDBOX/home/user/unzip/output/nested/value.txt"
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
  gettext)
    printf 'Hello $NAME\n' > "$SANDBOX/home/user/message.txt"
    run_runtime ash -c 'NAME=EdgeTerm /usr/local/bin/envsubst < /home/user/message.txt' | grep -q '^Hello EdgeTerm$'
    ;;
  datamash)
    printf '1\n2\n3\n' > "$SANDBOX/home/user/numbers.txt"
    run_runtime ash -c '/usr/local/bin/datamash sum 1 < /home/user/numbers.txt' | grep -q '^6$'
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
    printf 'set -eu\nprintf "%%s\\n" ready\n' > "$SANDBOX/home/user/script.sh"
    run_runtime_matches '^ready$' ash -c '/usr/local/bin/dash /home/user/script.sh'
    ;;
  coreutils)
    printf 'coreutils fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/cp /home/user/input.txt /home/user/output.txt'
    run_runtime ash -c '/usr/local/bin/sha256sum /home/user/output.txt' | grep -Eq '^[a-f0-9]{64}  /home/user/output.txt$'
    run_runtime ash -c '/usr/local/bin/ls -1 /home/user' | grep -q '^input.txt$'
    run_runtime ash -c '/usr/local/bin/mkdir /home/user/removable && /usr/local/bin/rmdir /home/user/removable'
    test ! -e "$SANDBOX/home/user/removable"
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
  php)
    python3 "$ROOT/scripts/browser-acceptance.py" \
      --report "${EDGETERM_PHP_BROWSER_REPORT:?Set EDGETERM_PHP_BROWSER_REPORT to the completed Chrome acceptance report}" \
      --package php --artifact-sha256 "$ARTIFACT_SHA256"
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
    printf 'ready\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c "/usr/local/bin/curl --silent 'file:///home/user/input.txt'" | grep -q '^ready$'
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
  quickjs)
    run_runtime ash -c "/usr/local/bin/qjs -e 'console.log(6 * 7)'" | grep -q '^42$'
    ;;
  fennel)
    run_runtime ash -c "/usr/local/bin/fennel -e '(print (* 6 7))'" | grep -q '^42$'
    ;;
  wabt)
    run_runtime ash -c "printf '(module)' > /tmp/empty.wat && /usr/local/bin/wat2wasm /tmp/empty.wat -o /tmp/empty.wasm && /usr/local/bin/wasm-validate /tmp/empty.wasm"
    ;;
  tcl)
    run_runtime ash -c "/usr/local/bin/tclsh <<'EOF'
puts [expr {6 * 7}]
EOF" | grep -q '^42$'
    ;;
  wasm3)
    run_runtime ash -c '/usr/local/bin/wasm3 --help' 2>&1 | grep -qi 'wasm3'
    ;;
  mujs)
    printf 'print(6 * 7);\n' > "$SANDBOX/home/user/input.js"
    run_runtime ash -c '/usr/local/bin/mujs /home/user/input.js' | grep -q '^42$'
    ;;
  chibi-scheme)
    run_runtime ash -c "/usr/local/bin/chibi-scheme -e '(display (* 6 7)) (newline)'" | grep -q '^42$'
    ;;
  squirrel)
    printf 'print(6 * 7);\n' > "$SANDBOX/home/user/input.nut"
    run_runtime ash -c '/usr/local/bin/sq /home/user/input.nut' | grep -q '42'
    ;;
  ncurses)
    run_runtime_matches '^[0-9]+$' ash -c 'TERM=xterm /usr/local/bin/tput cols'
    run_runtime_matches '^80$' ash -c 'TERM=xterm COLUMNS=80 /usr/local/bin/tput cols'
    ;;
  nano)
    run_runtime ash -c '/usr/local/bin/nano --help' | grep -qi 'usage'
    ;;
  less)
    printf 'less fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c 'TERM=dumb /usr/local/bin/less -F -X /home/user/input.txt' | grep -q '^less fixture$'
    ;;
  ed)
    printf 'a\ned fixture\n.\nw /home/user/output.txt\nq\n' > "$SANDBOX/home/user/commands.ed"
    run_runtime ash -c '/usr/local/bin/ed < /home/user/commands.ed'
    grep -q '^ed fixture$' "$SANDBOX/home/user/output.txt"
    ;;
  dos2unix)
    printf 'first\r\nsecond\r\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/dos2unix /home/user/input.txt'
    printf 'first\nsecond\n' > "$SANDBOX/home/user/expected.txt"
    cmp "$SANDBOX/home/user/expected.txt" "$SANDBOX/home/user/input.txt"
    ;;
  pv)
    printf 'pv fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/pv -q /home/user/input.txt > /home/user/output.txt'
    cmp "$SANDBOX/home/user/input.txt" "$SANDBOX/home/user/output.txt"
    ;;
  flex)
    cat > "$SANDBOX/home/user/input.l" <<'EOF'
%%
ready ECHO;
%%
EOF
    run_runtime ash -c 'cd /home/user && /usr/local/bin/flex-real input.l --preproc=0 -o lex.yy.m4'
    run_runtime ash -c 'cd /home/user && /usr/local/bin/m4 -P lex.yy.m4 > lex.yy.c'
    test -s "$SANDBOX/home/user/lex.yy.c"
    ;;
  ncdu)
    mkdir -p "$SANDBOX/home/user/ncdu-fixture"
    printf 'ready\n' > "$SANDBOX/home/user/ncdu-fixture/value.txt"
    run_runtime ash -c 'cd /home/user && /usr/local/bin/ncdu --ignore-config -0 -o ncdu.json ncdu-fixture'
    grep -q 'value.txt' "$SANDBOX/home/user/ncdu.json"
    ;;
  cmark)
    printf '# Ready\n' > "$SANDBOX/home/user/input.md"
    run_runtime ash -c '/usr/local/bin/cmark /home/user/input.md' | grep -q '<h1>Ready</h1>'
    ;;
  hexyl)
    printf 'ABC' > "$SANDBOX/home/user/input.bin"
    run_runtime ash -c '/usr/local/bin/hexyl --plain /home/user/input.bin' | grep -q '41 42 43'
    ;;
  mawk)
    printf '6\n7\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c "/usr/local/bin/mawk '{ total += \$1 } END { print total }' /home/user/input.txt" | grep -q '^13$'
    ;;
  sd)
    printf 'before\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c "/usr/local/bin/sd before after /home/user/input.txt"
    grep -q '^after$' "$SANDBOX/home/user/input.txt"
    ;;
  choose)
    printf 'alpha beta gamma\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/choose 1 < /home/user/input.txt' | grep -q '^beta$'
    ;;
  grex)
    run_runtime ash -c "/usr/local/bin/grex alpha alps" | grep -q 'al'
    ;;
  bison)
    cat > "$SANDBOX/home/user/input.y" <<'EOF'
%token VALUE
%%
input: VALUE ;
%%
EOF
    run_runtime ash -c 'cd /home/user && /usr/local/bin/bison -o parser.c input.y'
    test -s "$SANDBOX/home/user/parser.c"
    ;;
  byacc)
    cat > "$SANDBOX/home/user/input.y" <<'EOF'
%token VALUE
%%
input: VALUE ;
%%
EOF
    run_runtime ash -c 'cd /home/user && /usr/local/bin/byacc -o parser.c input.y'
    test -s "$SANDBOX/home/user/parser.c"
    ;;
  re2c)
    cat > "$SANDBOX/home/user/input.re" <<'EOF'
/*!re2c
    "ready" { return 0; }
    *       { return 1; }
*/
EOF
    run_runtime ash -c 'cd /home/user && /usr/local/bin/re2c -o output.c input.re'
    grep -q 'return 0;' "$SANDBOX/home/user/output.c"
    ;;
  gperf)
    printf 'ready,1\nsteady,2\n' > "$SANDBOX/home/user/input.gperf"
    run_runtime ash -c '/usr/local/bin/gperf /home/user/input.gperf > /home/user/output.c'
    grep -q 'in_word_set' "$SANDBOX/home/user/output.c"
    ;;
  indent)
    printf 'int main(){return 0;}\n' > "$SANDBOX/home/user/input.c"
    run_runtime ash -c '/usr/local/bin/indent /home/user/input.c -o /home/user/output.c'
    grep -q 'return 0;' "$SANDBOX/home/user/output.c"
    ;;
  universal-ctags)
    printf 'int ready(void) { return 1; }\n' > "$SANDBOX/home/user/input.c"
    run_runtime ash -c 'cd /home/user && /usr/local/bin/ctags --sort=no -f tags input.c'
    grep -q '^ready' "$SANDBOX/home/user/tags"
    ;;
  pcre2)
    printf 'alpha\nready42\nomega\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c "/usr/local/bin/pcre2grep 'ready[0-9]+' /home/user/input.txt" | grep -q '^ready42$'
    ;;
  picoc)
    printf '#include <stdio.h>\nint main(void) { printf("42\\n"); return 0; }\n' > "$SANDBOX/home/user/input.c"
    run_runtime ash -c '/usr/local/bin/picoc /home/user/input.c' | grep -q '^42$'
    ;;
  zoxide)
    run_runtime ash -c '/usr/local/bin/zoxide init posix' | grep -q '_zoxide_z'
    ;;
  hexedit)
    run_runtime ash -c '/usr/local/bin/hexedit --help' 2>&1 | grep -qi 'usage'
    ;;
  libdeflate)
    printf 'libdeflate fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/libdeflate-gzip -f -c /home/user/input.txt > /home/user/input.gz && /usr/local/bin/libdeflate-gunzip -f -c /home/user/input.gz > /home/user/output.txt'
    cmp "$SANDBOX/home/user/input.txt" "$SANDBOX/home/user/output.txt"
    ;;
  dialog)
    run_runtime ash -c 'TERM=xterm /usr/local/bin/dialog --stdout --inputbox Prompt 8 40 ready' </dev/null >/dev/null 2>&1 || true
    run_runtime ash -c '/usr/local/bin/dialog --help' 2>&1 | grep -qi 'usage'
    ;;
  wasm-tools)
    printf '(module (func (export "ready")))\n' > "$SANDBOX/home/user/input.wat"
    run_runtime ash -c '/usr/local/bin/wasm-tools parse /home/user/input.wat -o /home/user/output.wasm && /usr/local/bin/wasm-tools validate /home/user/output.wasm'
    test -s "$SANDBOX/home/user/output.wasm"
    ;;
  ncompress)
    printf 'compress fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/compress -c /home/user/input.txt > /home/user/input.Z && /usr/local/bin/compress -d -c /home/user/input.Z > /home/user/output.txt'
    cmp "$SANDBOX/home/user/input.txt" "$SANDBOX/home/user/output.txt"
    ;;
  htmlq)
    printf '<main><p class="ready">42</p></main>\n' > "$SANDBOX/home/user/input.html"
    run_runtime ash -c '/usr/local/bin/htmlq --text .ready < /home/user/input.html' | grep -q '^42$'
    ;;
  pastel)
    run_runtime ash -c '/usr/local/bin/pastel format hex red' | grep -qi '#ff0000'
    ;;
  xdelta3)
    printf 'before\n' > "$SANDBOX/home/user/source.txt"
    printf 'after\n' > "$SANDBOX/home/user/target.txt"
    run_runtime ash -c '/usr/local/bin/xdelta3 -e -s /home/user/source.txt /home/user/target.txt /home/user/change.xd3 && /usr/local/bin/xdelta3 -d -s /home/user/source.txt /home/user/change.xd3 /home/user/output.txt'
    cmp "$SANDBOX/home/user/target.txt" "$SANDBOX/home/user/output.txt"
    ;;
  ruplacer)
    printf 'before\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/ruplacer --go before after /home/user/input.txt'
    grep -q '^after$' "$SANDBOX/home/user/input.txt"
    ;;
  lzip)
    printf 'lzip fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/lzip -f -o /home/user/input.lz /home/user/input.txt && /usr/local/bin/lzip -d -f -o /home/user/output.txt /home/user/input.lz'
    cmp "$SANDBOX/home/user/input.txt" "$SANDBOX/home/user/output.txt"
    ;;
  libarchive)
    mkdir -p "$SANDBOX/home/user/archive/source" "$SANDBOX/home/user/archive/output"
    printf 'archive fixture\n' > "$SANDBOX/home/user/archive/source/value.txt"
    tar -C "$SANDBOX/home/user/archive" -cf "$SANDBOX/home/user/archive/value.tar" source
    run_runtime ash -c '/usr/local/bin/bsdtar -tf /home/user/archive/value.tar' | grep -q 'source/value.txt'
    run_runtime ash -c '/usr/local/bin/bsdtar -xOf /home/user/archive/value.tar source/value.txt' | grep -q '^archive fixture$'
    ;;
  cflow)
    printf 'int helper(void) { return 1; }\nint main(void) { return helper(); }\n' > "$SANDBOX/home/user/input.c"
    run_runtime ash -c '/usr/local/bin/cflow --profile=/usr/local/share/cflow/1.8/gcc.cfo --no-preprocess /home/user/input.c' | grep -q 'helper'
    ;;
  datamash)
    printf '1\n2\n3\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/datamash sum 1 < /home/user/input.txt' | grep -q '^6$'
    ;;
  expat)
    printf '<root><ready /></root>\n' > "$SANDBOX/home/user/input.xml"
    run_runtime ash -c '/usr/local/bin/xmlwf /home/user/input.xml'
    ;;
  actionlint)
    mkdir -p "$SANDBOX/home/user/.github/workflows"
    printf 'name: test\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ready\n' > "$SANDBOX/home/user/.github/workflows/test.yml"
    run_runtime ash -c '/usr/local/bin/actionlint /home/user/.github/workflows/test.yml'
    ;;
  yamlfmt)
    printf 'root:\n- one\n- two\n' > "$SANDBOX/home/user/input.yml"
    run_runtime ash -c '/usr/local/bin/yamlfmt /home/user/input.yml'
    grep -q '^  - one$' "$SANDBOX/home/user/input.yml"
    ;;
  gojq)
    printf '{"ready":42}\n' > "$SANDBOX/home/user/input.json"
    run_runtime ash -c '/usr/local/bin/gojq -r .ready /home/user/input.json' | grep -q '^42$'
    ;;
  zopfli)
    printf 'zopfli fixture\n' > "$SANDBOX/home/user/input.txt"
    run_runtime ash -c '/usr/local/bin/zopfli --gzip /home/user/input.txt && /usr/local/bin/zopflipng --help >/dev/null 2>&1 || true'
    test -s "$SANDBOX/home/user/input.txt.gz"
    ;;
  uncrustify)
    printf 'int main(){return 0;}\n' > "$SANDBOX/home/user/input.c"
    : > "$SANDBOX/home/user/uncrustify.cfg"
    run_runtime ash -c '/usr/local/bin/uncrustify -q -c /home/user/uncrustify.cfg -l C -f /home/user/input.c' | grep -q 'return 0;'
    ;;
  *)
    echo "No functional runtime fixture is defined for $PACKAGE." >&2
    exit 2
    ;;
esac

python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" functional "$RUN_LOG" --artifact-sha256 "$ARTIFACT_SHA256" >/dev/null
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
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" apt_remove "$RUN_LOG" --artifact-sha256 "$ARTIFACT_SHA256" >/dev/null
run_runtime_checked apt purge -y "$PACKAGE"
if run_runtime dpkg-query -W -f='${Status}' "$PACKAGE" >/dev/null 2>&1; then
  echo "Purged package is still present in the package database." >&2
  exit 1
fi
python3 "$ROOT/scripts/acceptance.py" record "$PACKAGE" "$VERSION" apt_purge "$RUN_LOG" --artifact-sha256 "$ARTIFACT_SHA256" >/dev/null

echo "Runtime acceptance passed for $PACKAGE."
echo "Persistent sandbox: $SANDBOX"
