# check-hooks-plugin PLUGIN: check a built hooks plugin with the tool that owns
# each rule, and exit 1 if any of them reports a problem.
#
# - check-jsonschema: plugin.json has a name and a version, and hooks.json has
#   the shape hooks.schema.json gives: every hook a command hook that runs one
#   of the plugin's scripts as `bash "${CLAUDE_PLUGIN_ROOT}/scripts/<name>"`.
# - bash -n: every script a hook runs is there and parses.
# - shfmt's syntax tree: every Python helper a hook script names outside its
#   comments is there.
# - ruff: every import in the plugin's Python sits at the top of its module, so
#   importing the module runs all of them.
# - python3 -E -s -S: every .py compiles, and finds every module it imports in
#   the standard library or beside it, as it must when a hook runs it with
#   `python3 -I -S`.
# - python3 -X importtime: every file under scripts/ is a hook, a helper a hook
#   names, or a module such a helper imports.
#
# The schemas' folder is HOOKS_PLUGIN_SCHEMAS.

shopt -s nullglob
status=0
problem() {
  echo "$1"
  status=1
}

cd "$1"
check-jsonschema --schemafile "$HOOKS_PLUGIN_SCHEMAS/plugin.schema.json" .claude-plugin/plugin.json || status=1
check-jsonschema --schemafile "$HOOKS_PLUGIN_SCHEMAS/hooks.schema.json" hooks/hooks.json || status=1

cd scripts
mapfile -t hooks < <(
  jq -r '.hooks[]?[]?.hooks[]?.command? // empty | capture("/scripts/(?<name>[^\"/]+)\"$").name' ../hooks/hooks.json | sort -u
)
for hook in "${hooks[@]}"; do
  bash -n "$hook" || problem "scripts/$hook: bash can't read it"
done

mapfile -t helpers < <(
  for hook in "${hooks[@]}"; do
    if [ -f "$hook" ]; then
      shfmt --to-json <"$hook"
    fi
  done | jq -r '.. | objects | select(.Type? == "Lit") | .Value | select(endswith(".py")) | split("/") | last' | sort -u
)
for helper in "${helpers[@]}"; do
  [ -f "$helper" ] || problem "scripts/$helper: a hook script runs it, but the plugin doesn't ship it"
done

ruff check --isolated --no-cache --quiet --select PLC0415 . || status=1
for module in *.py; do
  python3 -E -s -S -c "import ${module%.py}" </dev/null || problem "scripts/$module: python3 -S can't import it"
done

declare -A reached
for name in "${hooks[@]}" "${helpers[@]}"; do
  reached[$name]=1
done
for helper in "${helpers[@]}"; do
  if [ -f "$helper" ]; then
    while read -r name; do
      reached[$name.py]=1
    done < <(
      python3 -E -s -S -X importtime -c "import ${helper%.py}" 2>&1 >/dev/null </dev/null |
        awk -F'|' '/^import time:/ && !/imported package/ { gsub(/ /, "", $3); print $3 }'
    )
  fi
done
for file in *; do
  [ -n "${reached[$file]-}" ] || problem "scripts/$file: no hook runs it"
done

exit "$status"
