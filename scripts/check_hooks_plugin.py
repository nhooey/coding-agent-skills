#!/usr/bin/env python3
"""Check a built hooks plugin: its manifest, its hooks.json, and its scripts.

Usage: check_hooks_plugin.py <plugin folder>

Every hook must be a command hook that runs one of the plugin's own scripts as
`bash "${CLAUDE_PLUGIN_ROOT}/scripts/<name>"`, every script under scripts/
must be run by some hook, and each script must parse as bash. Prints one line
per problem and exits 1 if there are any.
"""

import json
import pathlib
import re
import subprocess
import sys

EVENTS = {
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "PermissionRequest",
    "Notification",
    "UserPromptSubmit",
    "SessionStart",
    "SessionEnd",
    "Stop",
    "SubagentStart",
    "SubagentStop",
    "PreCompact",
}
COMMAND = re.compile(r'^bash "\$\{CLAUDE_PLUGIN_ROOT\}/scripts/([^"/]+)"$')


def load_json(path, problems):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as err:
        problems.append(f"{path.name}: {err}")
        return None


def check_manifest(root, problems):
    manifest = load_json(root / ".claude-plugin" / "plugin.json", problems)
    if manifest is None:
        return
    for key in ("name", "version"):
        if not isinstance(manifest.get(key), str) or not manifest[key]:
            problems.append(f"plugin.json: no {key}")


def check_hooks(root, problems):
    """Check hooks.json and return the script names its hooks run."""
    config = load_json(root / "hooks" / "hooks.json", problems)
    if config is None:
        return set()
    hooks = config.get("hooks") if isinstance(config, dict) else None
    if not isinstance(hooks, dict) or not hooks:
        problems.append("hooks.json: no hooks object")
        return set()
    run = set()
    for event, groups in hooks.items():
        if event not in EVENTS:
            problems.append(f"hooks.json: unknown event {event}")
        if not isinstance(groups, list) or not groups:
            problems.append(f"hooks.json: {event} is not a list of matcher groups")
            continue
        for i, group in enumerate(groups):
            where = f"hooks.json: {event}[{i}]"
            entries = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(entries, list) or not entries:
                problems.append(f"{where}: no hooks list")
                continue
            if "matcher" in group and not isinstance(group["matcher"], str):
                problems.append(f"{where}: matcher is not a string")
            for j, hook in enumerate(entries):
                if not isinstance(hook, dict) or hook.get("type") != "command":
                    problems.append(f"{where}.hooks[{j}]: not a command hook")
                    continue
                match = COMMAND.match(hook.get("command", ""))
                if not match:
                    problems.append(
                        f"{where}.hooks[{j}]: command is not "
                        '`bash "${CLAUDE_PLUGIN_ROOT}/scripts/<name>"`'
                    )
                    continue
                name = match.group(1)
                run.add(name)
                if not (root / "scripts" / name).is_file():
                    problems.append(f"{where}.hooks[{j}]: no scripts/{name}")
    return run


def check_scripts(root, run, problems):
    scripts = root / "scripts"
    present = {p.name for p in scripts.iterdir() if p.is_file()} if scripts.is_dir() else set()
    for name in sorted(present - run):
        problems.append(f"scripts/{name}: no hook runs it")
    for name in sorted(present & run):
        parsed = subprocess.run(["bash", "-n", str(scripts / name)], capture_output=True, text=True)
        if parsed.returncode != 0:
            problems.append(f"scripts/{name}: {parsed.stderr.strip()}")


def check(root):
    problems = []
    check_manifest(root, problems)
    run = check_hooks(root, problems)
    check_scripts(root, run, problems)
    return problems


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2], file=sys.stderr)
        return 2
    problems = check(pathlib.Path(argv[1]))
    for line in problems:
        print(line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
