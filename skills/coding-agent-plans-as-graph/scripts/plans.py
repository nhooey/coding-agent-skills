#!/usr/bin/env python3
"""Check a project's plan graph and write its overview.

A plan is a folder of Markdown nodes, `agents/plans/` by default:

  open/<id>.md     nodes still to do: proposed, approved or in-progress
  closed/<id>.md   nodes finished: implemented, rejected, abandoned or superseded
  README.md        the overview this script writes; never edited by hand

Each node opens on a frontmatter block between `---` lines, one `key: value`
per line, lists in brackets: `needs: [a, b]`. The node's id is its file name
without `.md`. SKILL.md lists the keys.

Commands:
  check      report every problem, exit 1 if there is any
  overview   rewrite README.md from the nodes (runs check first)
  ready      print the ids of approved nodes whose needs are all implemented

Standard library only, so it runs anywhere Python 3.9+ does.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

OPEN_STATES = ("proposed", "approved", "in-progress")
CLOSED_STATES = ("implemented", "rejected", "abandoned", "superseded")
KINDS = ("end-state", "implementation", "schedule")
LINK_KEYS = ("part-of", "needs", "after", "superseded-by")
LIST_KEYS = ("needs", "after", "touches")
KNOWN_KEYS = {"title", "state", "kind", "owner", "implemented-by", "cost", *LINK_KEYS, *LIST_KEYS}
ID = re.compile(r"[a-z0-9][a-z0-9-]*")
OVERVIEW_MARK = "<!-- Written by plans.py overview; edit the nodes, not this file. -->"


@dataclass
class Node:
    id: str
    path: Path
    folder: str
    meta: dict = field(default_factory=dict)

    def links(self, key: str) -> list[str]:
        value = self.meta.get(key)
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    @property
    def state(self) -> str:
        return self.meta.get("state", "")

    @property
    def title(self) -> str:
        return self.meta.get("title", self.id)


def parse_frontmatter(text: str) -> tuple[dict, list[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, ["no frontmatter: the file must open on a `---` line"]
    meta, problems = {}, []
    for n, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return meta, problems
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not sep or not key:
            problems.append(f"line {n}: not `key: value`")
            continue
        if value.startswith("[") and value.endswith("]"):
            meta[key] = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
        else:
            meta[key] = value.strip("\"'")
    return {}, ["frontmatter never closed with a `---` line"]


def load(root: Path) -> tuple[dict[str, Node], list[str]]:
    nodes, problems = {}, []
    for folder in ("open", "closed"):
        for path in sorted((root / folder).glob("*.md")):
            node = Node(path.stem, path, folder)
            node.meta, errors = parse_frontmatter(path.read_text(encoding="utf-8"))
            problems += [f"{folder}/{path.name}: {e}" for e in errors]
            if node.id in nodes:
                problems.append(f"{folder}/{path.name}: id `{node.id}` is also {nodes[node.id].folder}/{path.name}")
            nodes[node.id] = node
    for path in sorted(root.glob("*.md")):
        if path.name != "README.md":
            problems.append(f"{path.name}: a node goes in open/ or closed/, not the plan's root")
    return nodes, problems


def check(nodes: dict[str, Node]) -> list[str]:
    problems = []
    for node in nodes.values():
        where = f"{node.folder}/{node.id}.md"
        if not ID.fullmatch(node.id):
            problems.append(f"{where}: id must be lower-case letters, digits and dashes")
        for key in node.meta:
            if key not in KNOWN_KEYS:
                problems.append(f"{where}: unknown key `{key}`")
        for key in ("title", "state", "kind"):
            if not node.meta.get(key):
                problems.append(f"{where}: missing `{key}`")
        allowed = OPEN_STATES if node.folder == "open" else CLOSED_STATES
        if node.state and node.state not in allowed:
            other = "closed" if node.folder == "open" else "open"
            hint = f"; move it to {other}/" if node.state in OPEN_STATES + CLOSED_STATES else ""
            problems.append(f"{where}: state `{node.state}` doesn't belong in {node.folder}/{hint}")
        if node.meta.get("kind") and node.meta["kind"] not in KINDS:
            problems.append(f"{where}: kind must be one of {', '.join(KINDS)}")
        for key in LINK_KEYS:
            for target in node.links(key):
                if target not in nodes:
                    problems.append(f"{where}: `{key}` names `{target}`, which has no node")
                elif target == node.id:
                    problems.append(f"{where}: `{key}` names the node itself")
        if node.state == "superseded" and not node.links("superseded-by"):
            problems.append(f"{where}: a superseded node names its replacement in `superseded-by`")
        if node.links("after") and node.meta.get("kind") != "schedule":
            problems.append(f"{where}: `after` is run order, so only schedule nodes carry it")
        if isinstance(node.meta.get("part-of"), list):
            problems.append(f"{where}: `part-of` names one parent")
    for key in ("part-of", "needs", "after"):
        cycle = find_cycle(nodes, key)
        if cycle:
            problems.append(f"`{key}` cycle: {' → '.join(cycle)}")
    return problems


def find_cycle(nodes: dict[str, Node], key: str) -> list[str] | None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(n: str) -> list[str] | None:
        state[n] = 1
        stack.append(n)
        for m in nodes[n].links(key):
            if m not in nodes:
                continue
            if state.get(m) == 1:
                return stack[stack.index(m):] + [m]
            if m not in state:
                found = visit(m)
                if found:
                    return found
        stack.pop()
        state[n] = 2
        return None

    for n in sorted(nodes):
        if n not in state:
            found = visit(n)
            if found:
                return found
    return None


def waiting_on(node: Node, nodes: dict[str, Node]) -> list[str]:
    return [n for n in node.links("needs") if n in nodes and nodes[n].state != "implemented"]


def ready(nodes: dict[str, Node]) -> list[Node]:
    return [n for n in nodes.values() if n.state == "approved" and not waiting_on(n, nodes)]


def overview(nodes: dict[str, Node], root: Path) -> str:
    def line(n: Node, extra: str = "") -> str:
        parent = n.meta.get("part-of")
        part = f", part of [{nodes[parent].title}]({nodes[parent].folder}/{parent}.md)" if parent in nodes else ""
        return f"- [{n.title}]({n.folder}/{n.id}.md) `{n.id}`{part}{extra}"

    open_nodes = sorted((n for n in nodes.values() if n.folder == "open"), key=lambda n: n.id)
    groups = [
        ("In progress", [line(n, f", {n.meta['owner']}" if n.meta.get("owner") else "")
                         for n in open_nodes if n.state == "in-progress"]),
        ("Ready", [line(n) for n in ready(nodes)]),
        ("Blocked", [line(n, ", waiting on " + ", ".join(f"`{w}`" for w in waiting_on(n, nodes)))
                     for n in open_nodes if n.state == "approved" and waiting_on(n, nodes)]),
        ("Proposed", [line(n) for n in open_nodes if n.state == "proposed"]),
    ]
    closed = [n for n in nodes.values() if n.folder == "closed"]
    counts = ", ".join(f"{sum(n.state == s for n in closed)} {s}" for s in CLOSED_STATES)
    out = [f"# Plans", "", OVERVIEW_MARK, ""]
    for heading, items in groups:
        out += [f"## {heading} ({len(items)})", ""] + (items or ["None."]) + [""]
    out += ["## Closed", "", f"{len(closed)} in [closed/](closed/): {counts}.", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["check", "overview", "ready"])
    p.add_argument("--plans", type=Path, default=Path("agents/plans"), help="the plan folder (default: agents/plans)")
    args = p.parse_args(argv)
    if not args.plans.is_dir():
        print(f"error: no plan folder at {args.plans}", file=sys.stderr)
        return 2
    nodes, problems = load(args.plans)
    problems += check(nodes)
    if args.command == "ready":
        for n in ready(nodes):
            print(n.id)
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        return 1
    if args.command == "overview":
        (args.plans / "README.md").write_text(overview(nodes, args.plans), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
