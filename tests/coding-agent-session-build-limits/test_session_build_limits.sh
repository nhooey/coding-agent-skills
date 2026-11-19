#!/usr/bin/env bash
# Tests for session-build-limits.sh, against a temporary CLAUDE_ENV_FILE.
# Run with `skills-dev test coding-agent-session-build-limits`, or
# `bash test_session_build_limits.sh` from anywhere.

set -u
here=$(cd "$(dirname "$0")" && pwd)
hook="$here/../../skills/coding-agent-session-build-limits/scripts/session-build-limits.sh"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
passed=0
failed=0

check() { # description, then a command that succeeds when the test passes
  local what=$1
  shift
  if "$@"; then
    passed=$((passed + 1))
  else
    failed=$((failed + 1))
    echo "FAIL: $what"
  fi
}

VARS="MAKEFLAGS CARGO_MAKEFLAGS CARGO_BUILD_JOBS RUST_TEST_THREADS
PYTEST_XDIST_AUTO_NUM_WORKERS JAVA_TOOL_OPTIONS GOMAXPROCS GOFLAGS
npm_config_jobs UV_CONCURRENT_BUILDS CMAKE_BUILD_PARALLEL_LEVEL
DOTNET_PROCESSOR_COUNT SWIFT_BUILD_JOBS GRADLE_OPTS"
NVARS=$(echo $VARS | wc -w | tr -d ' ')

# An empty home and project, so no real preferences file is read.
mkdir -p "$tmp/nohome" "$tmp/noproject"

# run_hook <env file or ""> [NAME=value ...]: the hook in an environment with
# none of the variables it sets except those given.
run_hook() {
  local file=$1
  shift
  local unset_args=() v
  for v in $VARS CLAUDE_ENV_FILE; do unset_args+=(-u "$v"); done
  if [ -n "$file" ]; then
    env "${unset_args[@]}" HOME="$tmp/nohome" CLAUDE_PROJECT_DIR="$tmp/noproject" \
      CLAUDE_ENV_FILE="$file" "$@" bash "$hook"
  else
    env "${unset_args[@]}" HOME="$tmp/nohome" CLAUDE_PROJECT_DIR="$tmp/noproject" \
      "$@" bash "$hook"
  fi
}

# Source the file the way a session's Bash does, and print one variable.
loaded() { # file name
  (
    for v in $VARS; do unset "$v"; done
    # shellcheck disable=SC1090
    . "$1"
    printf '%s' "${!2-}"
  )
}

has_line() { grep -q "$1" "$2"; }
lacks_line() { ! grep -q "$1" "$2"; }

# expect <file> <name> <value>: the file, sourced, sets the variable to the value.
expect() { check "$2=$3" test "$(loaded "$1" "$2")" = "$3"; }

# 1. Sets every variable to a share of 3.
f="$tmp/all"
: >"$f"
run_hook "$f"
check "exits 0" test $? -eq 0
expect "$f" MAKEFLAGS "-j3"
expect "$f" CARGO_MAKEFLAGS "-j3"
expect "$f" CARGO_BUILD_JOBS 3
expect "$f" RUST_TEST_THREADS 3
expect "$f" PYTEST_XDIST_AUTO_NUM_WORKERS 3
expect "$f" JAVA_TOOL_OPTIONS "-XX:ActiveProcessorCount=3"
expect "$f" GOMAXPROCS 3
expect "$f" GOFLAGS "-p=3"
expect "$f" npm_config_jobs 3
expect "$f" UV_CONCURRENT_BUILDS 3
expect "$f" CMAKE_BUILD_PARALLEL_LEVEL 3
expect "$f" DOTNET_PROCESSOR_COUNT 3
expect "$f" SWIFT_BUILD_JOBS 3
expect "$f" GRADLE_OPTS "-Dorg.gradle.workers.max=3"
check "one export line each" test "$(grep -c '^export ' "$f")" -eq "$NVARS"

# 2. Appends, keeping what the file held.
f="$tmp/append"
echo "export KEEP=1" >"$f"
run_hook "$f"
check "keeps earlier lines" has_line '^export KEEP=1$' "$f"
check "appends after them" test "$(grep -c '^export ' "$f")" -eq $((NVARS + 1))

# 3. A variable already set is left alone; the rest are set.
f="$tmp/preset"
: >"$f"
run_hook "$f" MAKEFLAGS=-j99 JAVA_TOOL_OPTIONS=-Xmx1g CARGO_BUILD_JOBS=8 \
  GOMAXPROCS=8 npm_config_jobs=8 UV_CONCURRENT_BUILDS=8 \
  CMAKE_BUILD_PARALLEL_LEVEL=8 DOTNET_PROCESSOR_COUNT=8 SWIFT_BUILD_JOBS=8
for v in MAKEFLAGS JAVA_TOOL_OPTIONS CARGO_BUILD_JOBS GOMAXPROCS npm_config_jobs \
  UV_CONCURRENT_BUILDS CMAKE_BUILD_PARALLEL_LEVEL DOTNET_PROCESSOR_COUNT SWIFT_BUILD_JOBS; do
  check "no $v line" lacks_line "^export $v=" "$f"
done
check "CARGO_MAKEFLAGS still set" has_line '^export CARGO_MAKEFLAGS=' "$f"
expect "$f" RUST_TEST_THREADS 3

# 4. GOFLAGS and GRADLE_OPTS are appended to, keeping their options, and an
# option already in them isn't added twice.
f="$tmp/options"
: >"$f"
run_hook "$f" GOFLAGS="-mod=mod -trimpath" GRADLE_OPTS="-Xmx2g -Dfile.encoding=UTF-8"
expect "$f" GOFLAGS "-mod=mod -trimpath -p=3"
expect "$f" GRADLE_OPTS "-Xmx2g -Dfile.encoding=UTF-8 -Dorg.gradle.workers.max=3"

f="$tmp/options-held"
: >"$f"
run_hook "$f" GOFLAGS="-p=8 -mod=mod" GRADLE_OPTS="-Dorg.gradle.workers.max=2 -Xmx2g"
check "no GOFLAGS line when -p is set" lacks_line '^export GOFLAGS=' "$f"
check "no GRADLE_OPTS line when workers.max is set" lacks_line '^export GRADLE_OPTS=' "$f"

f="$tmp/options-glob"
: >"$f"
(cd "$tmp" && run_hook "$f" GOFLAGS="*")
expect "$f" GOFLAGS "* -p=3"

# 5. The share is read from the preferences files, the project's over the
# user's, and a value that isn't a positive whole number is ignored.
prefs_name=coding-agent-session-build-limits.preferences.md
mkdir -p "$tmp/home5/.agents/skills" "$tmp/project5/.agents/skills"
printf '# Preferences\n\n- Share: 5\n' >"$tmp/home5/.agents/skills/$prefs_name"
f="$tmp/share-user"
: >"$f"
run_hook "$f" HOME="$tmp/home5"
expect "$f" MAKEFLAGS "-j5"
expect "$f" CARGO_BUILD_JOBS 5
expect "$f" GOFLAGS "-p=5"
expect "$f" GRADLE_OPTS "-Dorg.gradle.workers.max=5"
expect "$f" JAVA_TOOL_OPTIONS "-XX:ActiveProcessorCount=5"

printf -- '- Share: `2`\n' >"$tmp/project5/.agents/skills/$prefs_name"
f="$tmp/share-project"
: >"$f"
run_hook "$f" HOME="$tmp/home5" CLAUDE_PROJECT_DIR="$tmp/project5"
expect "$f" SWIFT_BUILD_JOBS 2

for bad in 0 -4 three "3 cores"; do
  printf -- '- Share: %s\n' "$bad" >"$tmp/project5/.agents/skills/$prefs_name"
  f="$tmp/share-bad"
  : >"$f"
  run_hook "$f" CLAUDE_PROJECT_DIR="$tmp/project5"
  check "Share: $bad falls back to 3" test "$(loaded "$f" GOMAXPROCS)" = 3
done

# 6. CLAUDE_ENV_FILE unset or empty: exits 0, prints nothing, and writes no
# file under its working directory, HOME, TMPDIR or XDG directories.
for how in unset empty; do
  box="$tmp/box-$how"
  mkdir -p "$box/cwd" "$box/home" "$box/tmp"
  if [ "$how" = empty ]; then extra=(CLAUDE_ENV_FILE=); else extra=(); fi
  out=$(cd "$box/cwd" && run_hook "" ${extra[@]+"${extra[@]}"} HOME="$box/home" TMPDIR="$box/tmp" \
    XDG_STATE_HOME="$box/home/.local/state" XDG_CONFIG_HOME="$box/home/.config" 2>&1)
  check "$how: exits 0" test $? -eq 0
  check "$how: prints nothing" test -z "$out"
  check "$how: writes nothing" test -z "$(find "$box" -mindepth 2 -print)"
done

echo "$passed passed, $failed failed"
test "$failed" -eq 0
