"""Small path and formatting helpers used across RepoLens."""

from __future__ import annotations

import posixpath
from collections import deque

# Reading-time buckets. We round up to one of these so we never show
# fake precision like "8 minutes 32 seconds".
TIME_BUCKETS = (5, 10, 15, 20, 30)


def basename(path: str) -> str:
    return posixpath.basename(path)


def dirname(path: str) -> str:
    return posixpath.dirname(path)


def path_parts(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def depth(path: str) -> int:
    """Number of directories above the file: 'app.py' -> 0, 'a/b.py' -> 1."""
    return len(path_parts(path)) - 1


def round_to_time_bucket(minutes: float) -> int:
    """Round up to the nearest reading-time bucket (max = largest bucket)."""
    for bucket in TIME_BUCKETS:
        if minutes <= bucket:
            return bucket
    return TIME_BUCKETS[-1]


def module_names_for_path(path: str) -> list[str]:
    """Possible import names for a Python file.

    'src/pkg/mod.py' -> ['src.pkg.mod', 'pkg.mod', 'mod'] so that imports work
    whether or not the repository uses a src/ layout.
    'pkg/__init__.py' -> ['pkg'].
    """
    parts = path_parts(path)
    if not parts or not parts[-1].endswith(".py"):
        return []
    parts[-1] = parts[-1][: -len(".py")]
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return [".".join(parts[i:]) for i in range(len(parts)) if parts[i:]]


def difficulty_label(score: int) -> str:
    """Learner-facing label for a 0-100 difficulty score."""
    if score <= 30:
        return "Beginner"
    if score <= 60:
        return "Intermediate"
    return "Advanced"


def confusion_level(score: int) -> str:
    """Confusion-map bucket for a 0-100 difficulty score."""
    if score <= 30:
        return "Easy"
    if score <= 60:
        return "Moderate"
    return "Advanced"


def human_join(items: list[str], limit: int = 3) -> str:
    """'a', 'a and b', 'a, b and c', 'a, b, c and 2 more'."""
    items = list(items)
    if not items:
        return ""
    if len(items) > limit:
        shown = items[:limit]
        return f"{', '.join(shown)} and {len(items) - limit} more"
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} and {items[-1]}"


def reachable_depths(start: str, graph: dict[str, list[str]], free: set[str] | None = None) -> dict[str, int]:
    """Distance from `start` along imports.

    Stepping into a node listed in `free` costs nothing, so thin "glue" files
    (e.g. an __init__.py that only re-exports) don't push real code further away.
    """
    free = free or set()
    depths = {start: 0}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for target in graph.get(current, []):
            cost = 0 if target in free else 1
            new_depth = depths[current] + cost
            if new_depth < depths.get(target, new_depth + 1):
                depths[target] = new_depth
                # Zero-cost moves go to the front so shortest distances are found first.
                (queue.appendleft if cost == 0 else queue.append)(target)
    return depths


def resolve_template_path(ref: str, tree_paths: list[str]) -> str | None:
    """Find the repository file for a template name like 'index.html'.

    Frameworks look templates up relative to a templates/ folder, so we match
    on the end of the path and prefer files inside a 'templates' directory.
    """
    ref = ref.lstrip("/")
    matches = [p for p in tree_paths if p == ref or p.endswith("/" + ref)]
    if not matches:
        return None
    matches.sort(key=lambda p: ("templates/" not in p, len(p)))
    return matches[0]
