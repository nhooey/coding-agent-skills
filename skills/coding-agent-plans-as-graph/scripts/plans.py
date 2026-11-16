#!/usr/bin/env python3
"""Check a project's plan graph and write its overview.

A plan is a folder of Markdown nodes, `agents/plans/` by default:

  open/<id>.md            nodes still to do: proposed, approved or in-progress
  closed/<id>.md          nodes finished: implemented, rejected, abandoned or superseded
  <plan>/open/<id>.md     the same, for the nodes of one plan, grouped in its folder
  <plan>/closed/<id>.md
  README.md               the overview this script writes; never edited by hand

Each node opens on a frontmatter block between `---` lines, one `key: value`
per line, lists in brackets: `needs: [a, b]`; an indented line continues the
one above, as a formatter wraps a long list. The node's id is its file name
without `.md`, unique across every plan. SKILL.md lists the keys.

Commands:
  check      report every problem, exit 1 if there is any
  overview   rewrite README.md from the nodes (runs check first)
  ready      print the ids of approved nodes whose needs are all implemented

Standard library only, so it runs anywhere Python 3.9+ does. Everything but
`read_plan` and `main` is pure: it takes values and returns new ones.
"""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from functools import reduce
from itertools import accumulate, chain, groupby, islice, repeat
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

OPEN_STATES = ("proposed", "approved", "in-progress")
CLOSED_STATES = ("implemented", "rejected", "abandoned", "superseded")
FOLDERS = ("open", "closed")
KINDS = ("end-state", "implementation", "schedule")
LINK_KEYS = ("part-of", "needs", "after", "superseded-by")
CYCLE_KEYS = ("part-of", "needs", "after")
LIST_KEYS = ("needs", "after", "touches")
KNOWN_KEYS = frozenset({"title", "state", "kind", "owner", "implemented-by", "cost", *LINK_KEYS, *LIST_KEYS})
ID = re.compile(r"[a-z0-9][a-z0-9-]*")
OVERVIEW_MARK = "<!-- Written by plans.py overview; edit the nodes, not this file. -->"

Meta = Mapping[str, object]
Problems = Tuple[str, ...]


@dataclass(frozen=True)
class Node:
    id: str
    folder: str
    meta: Meta
    plan: str = ""

    @property
    def where(self) -> str:
        return f"{self.plan}/{self.folder}/{self.id}.md" if self.plan else f"{self.folder}/{self.id}.md"

    @property
    def state(self) -> str:
        return str(self.meta.get("state", ""))

    @property
    def title(self) -> str:
        return str(self.meta.get("title", self.id))


@dataclass(frozen=True)
class RawPlan:
    """What the shell read: (plan, folder, file stem, text) per node, and stray file paths."""

    files: Tuple[Tuple[str, str, str, str], ...]
    strays: Tuple[str, ...]


Graph = Mapping[str, Node]


# Parsing


def parse_value(value: str) -> object:
    if value.startswith("[") and value.endswith("]"):
        return tuple(v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip())
    return value.strip("\"'")


def parse_line(number: int, line: str) -> Tuple[Optional[Tuple[str, object]], Problems]:
    key, sep, value = (part.strip() for part in line.partition(":"))
    return ((key, parse_value(value)), ()) if sep and key else (None, (f"line {number}: not `key: value`",))


def fold(lines: Tuple[str, ...]) -> Tuple[Tuple[int, str], ...]:
    """Each logical line with its first line's number: an indented line joins the one above,
    unless it is a comment, which stays a line of its own for the caller to drop."""

    def step(acc: Tuple[Tuple[int, str], ...], numbered: Tuple[int, str]) -> Tuple[Tuple[int, str], ...]:
        n, line = numbered
        joins = acc and line[:1].isspace() and line.strip() and not line.lstrip().startswith("#")
        return acc[:-1] + ((acc[-1][0], f"{acc[-1][1]} {line.strip()}"),) if joins else acc + ((n, line),)

    return reduce(step, enumerate(lines, start=2), ())


def parse_frontmatter(text: str) -> Tuple[Meta, Problems]:
    lines = tuple(text.splitlines())
    if not lines or lines[0].strip() != "---":
        return MappingProxyType({}), ("no frontmatter: the file must open on a `---` line",)
    end = next((i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if end is None:
        return MappingProxyType({}), ("frontmatter never closed with a `---` line",)
    parsed = tuple(
        parse_line(n, line)
        for n, line in fold(lines[1:end])
        if line.strip() and not line.lstrip().startswith("#")
    )
    return (
        MappingProxyType(dict(pair for pair, _ in parsed if pair)),
        tuple(chain.from_iterable(problems for _, problems in parsed)),
    )


def build(raw: RawPlan) -> Tuple[Graph, Problems]:
    """The graph by node id, and the problems found while reading it."""
    parsed = tuple((Node(stem, folder, MappingProxyType({}), plan), parse_frontmatter(text)) for plan, folder, stem, text in raw.files)
    nodes = tuple(Node(n.id, n.folder, meta, n.plan) for n, (meta, _) in parsed)
    duplicates = tuple(
        f"{later.where}: id `{node_id}` is also {first.where}"
        for node_id, group in groupby(sorted(nodes, key=lambda n: n.id), key=lambda n: n.id)
        for first, *rest in (tuple(group),)
        for later in rest
    )
    return (
        MappingProxyType({n.id: n for n in nodes}),
        tuple(f"{n.where}: {p}" for n, (_, problems) in parsed for p in problems)
        + duplicates
        + tuple(f"{name}: a node goes in an open/ or closed/ folder" for name in raw.strays),
    )


# Checking


def links(node: Node, key: str) -> Tuple[str, ...]:
    value = node.meta.get(key)
    return () if value is None else value if isinstance(value, tuple) else (str(value),)


def state_problems(node: Node) -> Problems:
    allowed = OPEN_STATES if node.folder == "open" else CLOSED_STATES
    other = "closed" if node.folder == "open" else "open"
    hint = f"; move it to {other}/" if node.state in OPEN_STATES + CLOSED_STATES else ""
    return (
        (f"{node.where}: state `{node.state}` doesn't belong in {node.folder}/{hint}",)
        if node.state and node.state not in allowed
        else ()
    )


def link_problems(node: Node, graph: Graph) -> Problems:
    return tuple(
        f"{node.where}: `{key}` names `{target}`, which has no node"
        if target not in graph
        else f"{node.where}: `{key}` names the node itself"
        for key in LINK_KEYS
        for target in links(node, key)
        if target not in graph or target == node.id
    )


def node_problems(node: Node, graph: Graph) -> Problems:
    w = node.where
    kind = node.meta.get("kind")
    rules = (
        (not ID.fullmatch(node.id), f"{w}: id must be lower-case letters, digits and dashes"),
        (kind not in (None, "", *KINDS), f"{w}: kind must be one of {', '.join(KINDS)}"),
        (node.state == "superseded" and not links(node, "superseded-by"),
         f"{w}: a superseded node names its replacement in `superseded-by`"),
        (bool(links(node, "after")) and kind != "schedule", f"{w}: `after` is run order, so only schedule nodes carry it"),
        (isinstance(node.meta.get("part-of"), tuple), f"{w}: `part-of` names one parent"),
    )
    return (
        tuple(message for broken, message in rules[:1] if broken)
        + tuple(f"{w}: unknown key `{key}`" for key in node.meta if key not in KNOWN_KEYS)
        + tuple(f"{w}: missing `{key}`" for key in ("title", "state", "kind") if not node.meta.get(key))
        + state_problems(node)
        + tuple(message for broken, message in rules[1:2] if broken)
        + link_problems(node, graph)
        + tuple(message for broken, message in rules[2:] if broken)
    )


def edges(graph: Graph, key: str, node_id: str, within: frozenset) -> Tuple[str, ...]:
    return tuple(m for m in links(graph[node_id], key) if m in within)


def cyclic_core(graph: Graph, key: str) -> frozenset:
    """The nodes left after repeatedly dropping every node with no `key` edge into the rest."""

    def prune(remaining: frozenset, _: object) -> frozenset:
        return frozenset(n for n in remaining if edges(graph, key, n, remaining))

    def step(pair: Tuple[Optional[frozenset], frozenset], _: object) -> Tuple[frozenset, frozenset]:
        return pair[1], prune(pair[1], None)

    pairs = accumulate(repeat(None), step, initial=(None, frozenset(graph)))
    return next(after for before, after in pairs if before == after)


def find_cycle(graph: Graph, key: str) -> Optional[Tuple[str, ...]]:
    """One cycle along `key` links, from its smallest node, or None."""
    core = cyclic_core(graph, key)
    if not core:
        return None
    step = lambda node_id, _: edges(graph, key, node_id, core)[0]  # noqa: E731
    walk = tuple(islice(accumulate(repeat(None), step, initial=min(core)), len(core) + 1))
    end = next(j for j in range(len(walk)) if walk[j] in walk[:j])
    return walk[walk.index(walk[end]) : end + 1]


def check(graph: Graph) -> Problems:
    cycles = tuple((key, find_cycle(graph, key)) for key in CYCLE_KEYS)
    return tuple(chain.from_iterable(node_problems(n, graph) for n in graph.values())) + tuple(
        f"`{key}` cycle: {' → '.join(cycle)}" for key, cycle in cycles if cycle
    )


# Reading the graph


def waiting_on(node: Node, graph: Graph) -> Tuple[str, ...]:
    return tuple(n for n in links(node, "needs") if n in graph and graph[n].state != "implemented")


def ready(graph: Graph) -> Tuple[Node, ...]:
    return tuple(n for n in graph.values() if n.state == "approved" and not waiting_on(n, graph))


def overview_line(node: Node, graph: Graph, extra: str = "") -> str:
    parent = node.meta.get("part-of")
    part = f", part of [{graph[parent].title}]({graph[parent].where})" if parent in graph else ""
    return f"- [{node.title}]({node.where}) `{node.id}`{part}{extra}"


def overview(graph: Graph) -> str:
    open_nodes = tuple(sorted((n for n in graph.values() if n.folder == "open"), key=lambda n: n.id))
    closed = tuple(n for n in graph.values() if n.folder == "closed")
    groups = (
        ("In progress", tuple(
            overview_line(n, graph, f", {n.meta['owner']}" if n.meta.get("owner") else "")
            for n in open_nodes
            if n.state == "in-progress"
        )),
        ("Ready", tuple(overview_line(n, graph) for n in ready(graph))),
        ("Blocked", tuple(
            overview_line(n, graph, ", waiting on " + ", ".join(f"`{w}`" for w in waiting_on(n, graph)))
            for n in open_nodes
            if n.state == "approved" and waiting_on(n, graph)
        )),
        ("Proposed", tuple(overview_line(n, graph) for n in open_nodes if n.state == "proposed")),
    )
    counts = ", ".join(f"{sum(n.state == s for n in closed)} {s}" for s in CLOSED_STATES)
    sections = chain.from_iterable(
        (f"## {heading} ({len(items)})", "", *(items or ("None.",)), "") for heading, items in groups
    )
    return "\n".join(
        ("# Plans", "", OVERVIEW_MARK, "", *sections, "## Closed", "", f"{len(closed)} in [closed/](closed/): {counts}.", "")
    )


# The shell: the only functions that touch the file system or the streams


def read_plan(root: Path) -> RawPlan:
    plans = ("",) + tuple(p.name for p in sorted(root.iterdir()) if p.is_dir() and p.name not in FOLDERS)
    return RawPlan(
        files=tuple(
            (plan, folder, path.stem, path.read_text(encoding="utf-8"))
            for plan in plans
            for folder in FOLDERS
            for path in sorted((root / plan / folder).glob("*.md"))
        ),
        strays=tuple(
            str(path.relative_to(root))
            for plan in plans
            for path in sorted((root / plan).glob("*.md"))
            if path.name != "README.md"
        ),
    )


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["check", "overview", "ready"])
    p.add_argument("--plans", type=Path, default=Path("agents/plans"), help="the plan folder (default: agents/plans)")
    args = p.parse_args(argv)
    if not args.plans.is_dir():
        print(f"error: no plan folder at {args.plans}", file=sys.stderr)
        return 2
    graph, load_problems = build(read_plan(args.plans))
    problems = load_problems + check(graph)
    if args.command == "ready":
        print("".join(f"{n.id}\n" for n in ready(graph)), end="")
    print("".join(f"{problem}\n" for problem in problems), end="", file=sys.stderr)
    if problems:
        return 1
    if args.command == "overview":
        (args.plans / "README.md").write_text(overview(graph), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
