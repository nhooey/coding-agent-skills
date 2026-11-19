#!/usr/bin/env python3
"""Check a project's plan graph and write its overview.

A plan is a folder of Markdown nodes, `agents/plans/` by default:

  open/<id>.md            nodes still to do: proposed, approved or in-progress
  closed/<id>.md          nodes finished: implemented, rejected, abandoned or superseded
  <plan>/open/<id>.md     the same, for the nodes of one plan, grouped in its folder
  <plan>/closed/<id>.md
  README.md               the overview this script writes; never edited by hand

Each node opens on a frontmatter block between `---` lines, a YAML mapping:
`key: value` lines, lists in brackets, such as `needs: [a, b]`. YAML reads
it, through yq (yq-go), so comments and a list wrapped onto an indented line
follow YAML's rules, and a value keeps the text it was written as, so
`cost: 1.50` stays `1.50`. The node's id is its file name without `.md`,
unique across every plan. SKILL.md lists the keys.

Commands:
  check      report every problem, exit 1 if there is any
  overview   rewrite README.md from the nodes (runs check first)
  ready      print the ids of approved nodes whose needs are all implemented

Its Python is standard library only, so it runs anywhere Python 3.9+ does,
with `yq` (yq-go) on PATH. Everything above `# The shell` is pure: it takes
values and returns new ones.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
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
# yq reads a JSON list of frontmatter blocks and parses each as YAML. Every scalar in a mapping is
# retagged as a string, so a value keeps the text it was written as: `1.50`, `true` and `null` stay
# as written. Without header preprocessing, yq's line numbers count from the block's opening `---`,
# which is the file's first line.
YQ = (
    "yq",
    "--header-preprocess=false",
    "--input-format=json",
    "--output-format=json",
    "--indent=0",
    '.[] |= from_yaml | (.[] | select(tag == "!!map") | .. | select(tag != "!!map" and tag != "!!seq")) tag = "!!str"',
)

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
    """What the shell read: (plan, folder, file stem, frontmatter as YAML read it, problems reading it)
    per node, and stray file paths."""

    files: Tuple[Tuple[str, str, str, object, Problems], ...]
    strays: Tuple[str, ...]


class NoYq(OSError):
    """yq, which reads the frontmatter, isn't on PATH."""


Graph = Mapping[str, Node]


# Parsing


def frontmatter(text: str) -> Tuple[Optional[str], Problems]:
    """The frontmatter block for YAML, from its opening `---` line to the line before the closing one."""
    lines = tuple(text.splitlines())
    if not lines or lines[0].strip() != "---":
        return None, ("no frontmatter: the file must open on a `---` line",)
    end = next((i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if end is None:
        return None, ("frontmatter never closed with a `---` line",)
    return "\n".join(("---",) + lines[1:end]) + "\n", ()


def text_of(value: object) -> str:
    """A value as text: a string as it is, a nested list or mapping as JSON."""
    return value if isinstance(value, str) else json.dumps(value)


def meta_of(document: object) -> Tuple[Meta, Problems]:
    """A node's keys from its frontmatter as YAML read it: each value a string or a tuple of strings."""
    if document is None:
        return MappingProxyType({}), ()
    if not isinstance(document, dict):
        return MappingProxyType({}), ("frontmatter isn't `key: value` pairs",)
    return (
        MappingProxyType(
            {str(k): tuple(map(text_of, v)) if isinstance(v, list) else text_of(v) for k, v in document.items()}
        ),
        (),
    )


def yaml_problem(stderr: str) -> str:
    """yq's complaint about a block, from its last line, without yq's own prefixes."""
    last = next((line for line in reversed(stderr.splitlines()) if line.strip()), "yq failed")
    return "frontmatter isn't YAML: " + last.strip().removeprefix("Error: ").removeprefix("yaml: ")


def build(raw: RawPlan) -> Tuple[Graph, Problems]:
    """The graph by node id, and the problems found while reading it."""
    parsed = tuple(
        (Node(stem, folder, meta, plan), problems + shape)
        for plan, folder, stem, document, problems in raw.files
        for meta, shape in (meta_of(document),)
    )
    nodes = tuple(n for n, _ in parsed)
    duplicates = tuple(
        f"{later.where}: id `{node_id}` is also {first.where}"
        for node_id, group in groupby(sorted(nodes, key=lambda n: n.id), key=lambda n: n.id)
        for first, *rest in (tuple(group),)
        for later in rest
    )
    return (
        MappingProxyType({n.id: n for n in nodes}),
        tuple(f"{n.where}: {p}" for n, problems in parsed for p in problems)
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


def run_yq(blocks: Tuple[str, ...]) -> Tuple[Optional[list], str]:
    """Each block as YAML reads it, or None and yq's complaint when any block isn't YAML."""
    try:
        done = subprocess.run(YQ, input=json.dumps(blocks), capture_output=True, text=True)
    except FileNotFoundError as error:
        raise NoYq("plans.py reads each node's frontmatter with `yq` (yq-go), which isn't on PATH") from error
    return (json.loads(done.stdout), "") if done.returncode == 0 else (None, done.stderr)


def read_yaml(blocks: Tuple[str, ...]) -> Tuple[Tuple[object, Problems], ...]:
    """Each block as YAML reads it, with its problem: all in one yq run, or one run each when a block
    isn't YAML, so the problem names its block."""
    documents, _ = run_yq(blocks) if blocks else ([], "")
    if documents is not None:
        return tuple((document, ()) for document in documents)
    alone = tuple(run_yq((block,)) for block in blocks)
    return tuple((None, (yaml_problem(stderr),)) if one is None else (one[0], ()) for one, stderr in alone)


def read_plan(root: Path) -> RawPlan:
    plans = ("",) + tuple(p.name for p in sorted(root.iterdir()) if p.is_dir() and p.name not in FOLDERS)
    paths = tuple(
        (plan, folder, path)
        for plan in plans
        for folder in FOLDERS
        for path in sorted((root / plan / folder).glob("*.md"))
    )
    found = tuple(frontmatter(path.read_text(encoding="utf-8")) for _, _, path in paths)
    with_block = tuple(i for i, (block, _) in enumerate(found) if block is not None)
    read = dict(zip(with_block, read_yaml(tuple(found[i][0] for i in with_block))))
    return RawPlan(
        files=tuple(
            (plan, folder, path.stem, *read.get(i, (None, found[i][1])))
            for i, (plan, folder, path) in enumerate(paths)
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
    try:
        graph, load_problems = build(read_plan(args.plans))
    except NoYq as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
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
