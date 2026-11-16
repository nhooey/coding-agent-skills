#!/usr/bin/env bash
# SessionStart hook: give the session a fixed share of the machine.
#
# Appends `export` lines to the file named in $CLAUDE_ENV_FILE, which Claude
# Code loads into every Bash command of the session, setting the variables
# that build and test tools read to limit their parallelism. A variable that
# is already set is left alone, except GOFLAGS and GRADLE_OPTS, which hold
# options: the limit's option is appended to them unless they already hold
# it. Does nothing, and exits 0, when CLAUDE_ENV_FILE is unset.
#
# The share is the `Share` line in
# `.agents/skills/coding-agent-session-build-limits.preferences.md`, the
# project's (under $CLAUDE_PROJECT_DIR) over the user's (under ~), and 3
# when neither holds a positive whole number.

set -u

[ -n "${CLAUDE_ENV_FILE:-}" ] || exit 0

# The share: how many cores, test threads and workers one session may use.
SHARE=3
name=coding-agent-session-build-limits.preferences.md
for prefs in "${HOME:-}/.agents/skills/$name" "${CLAUDE_PROJECT_DIR:-}/.agents/skills/$name"; do
  [ -f "$prefs" ] || continue
  while IFS= read -r line || [ -n "$line" ]; do
    if [[ "$line" =~ ^[-*[:space:]]*[Ss]hare:[[:space:]]*\`?([0-9]+)\`?[[:space:]]*$ ]] &&
      [ "$((10#${BASH_REMATCH[1]}))" -gt 0 ]; then
      SHARE=$((10#${BASH_REMATCH[1]}))
    fi
  done <"$prefs"
done

emit() { # name value
  [ -n "${!1:-}" ] && return 0
  printf 'export %s=%q\n' "$1" "$2" >>"$CLAUDE_ENV_FILE"
}

# append name option-prefix value: add the option to a variable of
# space-separated options, unless an option with that prefix is already in it.
append() {
  local current=${!1:-} word words
  read -ra words <<<"$current"
  for word in ${words[@]+"${words[@]}"}; do
    [[ "$word" == "$2"* ]] && return 0
  done
  printf 'export %s=%q\n' "$1" "${current:+$current }$3" >>"$CLAUDE_ENV_FILE"
}

emit MAKEFLAGS "-j${SHARE}"
emit CARGO_MAKEFLAGS "-j${SHARE}"
emit CARGO_BUILD_JOBS "${SHARE}"
emit RUST_TEST_THREADS "${SHARE}"
emit PYTEST_XDIST_AUTO_NUM_WORKERS "${SHARE}"
emit JAVA_TOOL_OPTIONS "-XX:ActiveProcessorCount=${SHARE}"
emit GOMAXPROCS "${SHARE}"
append GOFLAGS "-p=" "-p=${SHARE}"
emit npm_config_jobs "${SHARE}"
emit UV_CONCURRENT_BUILDS "${SHARE}"
emit CMAKE_BUILD_PARALLEL_LEVEL "${SHARE}"
emit DOTNET_PROCESSOR_COUNT "${SHARE}"
emit SWIFT_BUILD_JOBS "${SHARE}"
append GRADLE_OPTS "-Dorg.gradle.workers.max=" "-Dorg.gradle.workers.max=${SHARE}"
exit 0
