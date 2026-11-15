#!/usr/bin/env bash
# SessionStart hook: give the session a fixed share of the machine.
#
# Appends `export` lines to the file named in $CLAUDE_ENV_FILE, which Claude
# Code loads into every Bash command of the session, setting the variables
# that build and test tools read to limit their parallelism. A variable that
# is already set is left alone. Does nothing, and exits 0, when
# CLAUDE_ENV_FILE is unset.

set -u

# The share: how many cores, test threads and workers one session may use.
SHARE=3

[ -n "${CLAUDE_ENV_FILE:-}" ] || exit 0

emit() { # name value
  [ -n "${!1:-}" ] && return 0
  printf 'export %s=%q\n' "$1" "$2" >>"$CLAUDE_ENV_FILE"
}

emit MAKEFLAGS "-j${SHARE}"
emit CARGO_MAKEFLAGS "-j${SHARE}"
emit RUST_TEST_THREADS "${SHARE}"
emit PYTEST_XDIST_AUTO_NUM_WORKERS "${SHARE}"
emit JAVA_TOOL_OPTIONS "-XX:ActiveProcessorCount=${SHARE}"
exit 0
