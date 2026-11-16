#!/usr/bin/env bash
# Tests for session-build-limits.sh, against a temporary CLAUDE_ENV_FILE.
# Run with `bash test_session_build_limits.sh`.

set -u
here=$(cd "$(dirname "$0")" && pwd)
hook="$here/session-build-limits.sh"
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

VARS="MAKEFLAGS CARGO_MAKEFLAGS RUST_TEST_THREADS PYTEST_XDIST_AUTO_NUM_WORKERS JAVA_TOOL_OPTIONS"

# run_hook <env file or ""> [NAME=value ...]: the hook in an environment with
# none of the five variables except those given.
run_hook() {
  local file=$1
  shift
  local unset_args=() v
  for v in $VARS CLAUDE_ENV_FILE; do unset_args+=(-u "$v"); done
  if [ -n "$file" ]; then
    env "${unset_args[@]}" CLAUDE_ENV_FILE="$file" "$@" bash "$hook"
  else
    env "${unset_args[@]}" "$@" bash "$hook"
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

# 1. Sets all five to a share of 3.
f="$tmp/all"
: >"$f"
run_hook "$f"
check "exits 0" test $? -eq 0
check "MAKEFLAGS" test "$(loaded "$f" MAKEFLAGS)" = "-j3"
check "CARGO_MAKEFLAGS" test "$(loaded "$f" CARGO_MAKEFLAGS)" = "-j3"
check "RUST_TEST_THREADS" test "$(loaded "$f" RUST_TEST_THREADS)" = "3"
check "PYTEST_XDIST_AUTO_NUM_WORKERS" test "$(loaded "$f" PYTEST_XDIST_AUTO_NUM_WORKERS)" = "3"
check "JAVA_TOOL_OPTIONS" test "$(loaded "$f" JAVA_TOOL_OPTIONS)" = "-XX:ActiveProcessorCount=3"
check "five export lines" test "$(grep -c '^export ' "$f")" -eq 5

# 2. Appends, keeping what the file held.
f="$tmp/append"
echo "export KEEP=1" >"$f"
run_hook "$f"
check "keeps earlier lines" has_line '^export KEEP=1$' "$f"
check "appends after them" test "$(grep -c '^export ' "$f")" -eq 6

# 3. A variable already set is left alone; the rest are set.
f="$tmp/preset"
: >"$f"
run_hook "$f" MAKEFLAGS=-j99 JAVA_TOOL_OPTIONS=-Xmx1g
check "no MAKEFLAGS line" lacks_line '^export MAKEFLAGS=' "$f"
check "no JAVA_TOOL_OPTIONS line" lacks_line '^export JAVA_TOOL_OPTIONS=' "$f"
check "CARGO_MAKEFLAGS still set" has_line '^export CARGO_MAKEFLAGS=' "$f"
check "RUST_TEST_THREADS still set" test "$(loaded "$f" RUST_TEST_THREADS)" = "3"

# 4. CLAUDE_ENV_FILE unset or empty: exits 0, prints nothing, and writes no
# file under its working directory, HOME, TMPDIR or XDG directories.
for how in unset empty; do
  box="$tmp/box-$how"
  mkdir -p "$box/cwd" "$box/home" "$box/tmp"
  if [ "$how" = empty ]; then extra=(CLAUDE_ENV_FILE=); else extra=(); fi
  out=$(cd "$box/cwd" && run_hook "" "${extra[@]}" HOME="$box/home" TMPDIR="$box/tmp" \
    XDG_STATE_HOME="$box/home/.local/state" XDG_CONFIG_HOME="$box/home/.config" 2>&1)
  check "$how: exits 0" test $? -eq 0
  check "$how: prints nothing" test -z "$out"
  check "$how: writes nothing" test -z "$(find "$box" -mindepth 2 -print)"
done

echo "$passed passed, $failed failed"
test "$failed" -eq 0
