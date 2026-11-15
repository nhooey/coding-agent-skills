#!/usr/bin/env bash
# Checks this repository's mods the way their READMEs say: `claude plugin
# validate`, `tsc -p` and `claude plugin test`, one mod after another.
#
# Usage: check-mods.sh [MOD ...]
#   MOD is a mod's folder, or its name under plugins/. With none, every mod
#   under plugins/ (each folder holding .claude-plugin/plugin.json).
#
# tsc needs the Claude Code API declarations in <mod>/.claude-plugin/types/,
# which the engine lays there when it loads the mod from a folder it watches.
# Where no engine has, this copies them from the ones the running build wrote
# for its plugin-authoring skill, under /tmp/claude-<uid>/bundled-skills/<version>/.
# Needs `claude` and `tsc` on PATH; the repository's dev shell has tsc.

set -euo pipefail

plugins=$(cd "$(dirname "$0")" && pwd)

lay_types() {
  local mod=$1 laid=$2 version newest candidate
  version=$(claude --version | cut -d' ' -f1)
  newest=
  for candidate in /tmp/claude-"$(id -u)"/bundled-skills/"$version"/*/plugin-authoring/types/claude-code.d.ts; do
    if [[ -f $candidate && (-z $newest || $candidate -nt $newest) ]]; then
      newest=$candidate
    fi
  done
  if [[ -z $newest ]]; then
    echo "check-mods.sh: no Claude Code $version API types to lay in $mod/.claude-plugin/types/." >&2
    echo "check-mods.sh: load the plugin-authoring skill in a Claude Code session once, which writes them, or start one with --plugin-dir $mod, then run this again." >&2
    exit 1
  fi
  mkdir -p "$(dirname "$laid")"
  cp "$newest" "$laid"
  echo "check-mods.sh: laid $newest" >&2
}

check() {
  local mod laid
  mod=$(cd "$1" && pwd)
  laid=$mod/.claude-plugin/types/claude-code/index.d.ts
  [[ -f $laid ]] || lay_types "$mod" "$laid"
  echo "==== $(basename "$mod")"
  echo "== claude plugin validate"
  claude plugin validate "$mod"
  echo "== tsc -p"
  tsc -p "$mod"
  echo "== claude plugin test"
  claude plugin test "$mod"
}

mods=()
if (($# == 0)); then
  for manifest in "$plugins"/*/.claude-plugin/plugin.json; do
    mods+=("$(dirname "$(dirname "$manifest")")")
  done
else
  for arg in "$@"; do
    if [[ -d $arg ]]; then mods+=("$arg"); else mods+=("$plugins/$arg"); fi
  done
fi

for mod in "${mods[@]}"; do
  check "$mod"
done
