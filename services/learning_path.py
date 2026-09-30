"""Build the beginner reading order, the confusion map and the skip-for-now list.

The learning path follows a simple idea a senior developer would use:
  1. README first (what is this project?)
  2. The likely entry point (where does it start?)
  3. Files the entry point imports, closest first (how does it connect?)
  4. At most one template the code renders (what does the user see?)
Only a handful of files are recommended - never the whole repository.
"""

from __future__ import annotations

from models.repo_models import CodeSymbol, FileInsight, LearningStep, PythonFileInfo, SkipItem
from utils.scoring import is_glue_file
from utils.helpers import (
    basename,
    confusion_level,
    depth,
    difficulty_label,
    human_join,
    path_parts,
    reachable_depths,
    resolve_template_path,
    round_to_time_bucket,
)

MAX_STEPS = 6
MAX_PER_CATEGORY = 2  # e.g. at most two route files, so models/database also get a turn
MIN_STEP_IMPORTANCE = 40
MIN_UNCONNECTED_IMPORTANCE = 60  # higher bar for files the entry point doesn't import
MAX_IMPORT_DEPTH = 3
UNREACHABLE = 99
MAX_RELEVANT_SYMBOLS = 4
MAX_SKIP_ITEMS = 12
MAX_FOLDERS_PER_NAME = 2  # more 'migrations/' folders than this are shown as one line

# Reading speed assumptions for a beginner (deliberately generous).
BASE_MINUTES = 3
PYTHON_LINES_PER_MINUTE = 15
BRANCHES_PER_EXTRA_MINUTE = 10
TEMPLATE_LINES_PER_MINUTE = 25
README_CHARS_PER_MINUTE = 1200
AVERAGE_README_LINE_CHARS = 60

CODE_CATEGORIES = {"entry_point", "routes", "models", "database", "core_logic", "ui", "utility"}
IMPORTANT_FUNCTION_NAMES = {"main", "create_app", "run", "app", "setup", "init_app", "start", "cli"}

CATEGORY_PURPOSE = {
    "routes": "This is where incoming requests are handled.",
    "models": "It describes the data the application works with.",
    "database": "It handles storing and loading data.",
    "core_logic": "It contains core logic that other files rely on.",
    "ui": "It builds part of the user interface.",
    "utility": "It provides helper functions used elsewhere.",
}


# ---------------------------------------------------------------------------
# Learning path
# ---------------------------------------------------------------------------


def build_learning_path(
    insights: dict[str, FileInsight],
    python_files: dict[str, PythonFileInfo],
    entry_points: list[str],
    import_graph: dict[str, list[str]],
    tree_paths: list[str],
) -> list[LearningStep]:
    if not python_files:
        return []

    ordered: list[str] = []
    readme = find_root_readme(insights)
    if readme:
        ordered.append(readme)

    entry = entry_points[0] if entry_points else None
    glue = {path for path, info in python_files.items() if is_glue_file(info)}
    depths = reachable_depths(entry, import_graph, free=glue) if entry else {}
    if entry:
        ordered.append(entry)

    def is_code_candidate(path: str, min_importance: int) -> bool:
        insight = insights[path]
        return (
            path in python_files
            and path != entry
            and path not in glue
            and insight.category in CODE_CATEGORIES
            and insight.importance >= min_importance
        )

    def sort_key(path: str) -> tuple:
        return (depths.get(path, UNREACHABLE), -insights[path].importance, insights[path].difficulty, path)

    # Files reachable from the entry point come first, closest imports first.
    connected = [p for p in insights if is_code_candidate(p, MIN_STEP_IMPORTANCE)
                 and depths.get(p, UNREACHABLE) <= MAX_IMPORT_DEPTH]
    # Frameworks like Django wire files together by name, not imports, so we
    # also allow clearly important files that are not reachable via imports.
    min_unconnected = MIN_STEP_IMPORTANCE if not entry else MIN_UNCONNECTED_IMPORTANCE
    unconnected = [p for p in insights if is_code_candidate(p, min_unconnected) and p not in connected]
    candidates = _limit_per_category(sorted(connected, key=sort_key) + sorted(unconnected, key=sort_key), insights)

    # Keep one slot for a template rendered by the chosen code, if there is one.
    code_slots = max(MAX_STEPS - len(ordered) - 1, 0)
    ordered.extend(candidates[:code_slots])
    template = _main_template(ordered, python_files, tree_paths)
    if template:
        ordered.append(template)
    elif len(candidates) > code_slots:
        ordered.append(candidates[code_slots])

    return _make_steps(ordered, insights, python_files, import_graph, entry, template)


def _limit_per_category(paths: list[str], insights: dict[str, FileInsight]) -> list[str]:
    """Keep at most MAX_PER_CATEGORY files of each kind so the path covers different layers."""
    counts: dict[str, int] = {}
    kept = []
    for path in paths:
        category = insights[path].category
        if counts.get(category, 0) < MAX_PER_CATEGORY:
            kept.append(path)
            counts[category] = counts.get(category, 0) + 1
    return kept


def find_root_readme(insights: dict[str, FileInsight]) -> str | None:
    for path in insights:
        if depth(path) == 0 and basename(path).lower().startswith("readme"):
            return path
    return None


def _main_template(paths: list[str], python_files: dict[str, PythonFileInfo], tree_paths: list[str]) -> str | None:
    """The first template rendered by one of the chosen code files, if any."""
    for path in paths:
        info = python_files.get(path)
        for ref in info.template_refs if info else []:
            resolved = resolve_template_path(ref, tree_paths)
            if resolved:
                return resolved
    return None


def _make_steps(
    ordered: list[str],
    insights: dict[str, FileInsight],
    python_files: dict[str, PythonFileInfo],
    import_graph: dict[str, list[str]],
    entry: str | None,
    template: str | None,
) -> list[LearningStep]:
    step_number = {path: index + 1 for index, path in enumerate(ordered)}
    steps: list[LearningStep] = []
    for path in ordered:
        insight = insights.get(path)
        info = python_files.get(path)
        number = step_number[path]
        importers = [src for src, targets in import_graph.items()
                     if path in targets and step_number.get(src, number) < number]
        renderers = [p for p in ordered if template == path and python_files.get(p)
                     and any(resolve_template_path(r, [path]) for r in python_files[p].template_refs)]

        prerequisites = sorted({step_number[p] for p in importers + renderers} | ({1} if number > 1 else set()))
        why, evidence = _explain(path, insight, info, entry, importers, renderers)
        score = insight.difficulty if insight else 25
        steps.append(
            LearningStep(
                number=number,
                path=path,
                why=why,
                difficulty_label=difficulty_label(score),
                difficulty_score=score,
                minutes=estimate_minutes(path, insight, info),
                relevant_code=relevant_symbols(info) if info else [],
                prerequisites=prerequisites,
                evidence=evidence,
            )
        )
    return steps


def _explain(
    path: str,
    insight: FileInsight | None,
    info: PythonFileInfo | None,
    entry: str | None,
    importers: list[str],
    renderers: list[str],
) -> tuple[str, list[str]]:
    """A short, evidence-based reason to read this file, plus citations."""
    evidence: list[str] = []
    category = insight.category if insight else "unknown"

    if category == "documentation":
        return "Start here to learn what the project does and how to run it, before reading any code.", [path]

    if category == "template":
        sentence = f"This is a page template rendered by {human_join(renderers)}." if renderers else \
            "This is a page template the user sees."
        return sentence + " It shows how data from the Python code is displayed.", [path]

    sentences: list[str] = []
    if path == entry and insight:
        sentences.append("Likely entry point: " + "; ".join(r[0].lower() + r[1:] for r in insight.entry_reasons[:3]) + ".")
        evidence.extend(_citations_in(insight.entry_reasons))
    elif category in CATEGORY_PURPOSE:
        sentences.append(CATEGORY_PURPOSE[category])

    if info and info.routes:
        names = [f"{r.function}()" for r in info.routes]
        sentences.append(f"It defines {len(info.routes)} route handler(s) such as {human_join(names)}.")
        evidence.extend(f"{path}:{r.lineno}-{r.end_lineno}" for r in info.routes[:3])
    elif info and info.classes and category == "models":
        sentences.append(f"It defines {human_join([c.name for c in info.classes])}.")
        evidence.extend(f"{path}:{c.line_range}" for c in info.classes[:3])

    if importers:
        sentences.append(f"It is imported by {human_join(importers)}, which you will have read already.")
    if not evidence:
        evidence.append(path)
    return " ".join(sentences) or "It is one of the most connected files in the project.", evidence


def _citations_in(reasons: list[str]) -> list[str]:
    """Extract 'path:line' citations embedded in scoring reasons."""
    found = []
    for reason in reasons:
        for word in reason.replace("`", " ").split():
            if ":" in word and word.rsplit(":", 1)[-1].isdigit():
                found.append(word)
    return found


def relevant_symbols(info: PythonFileInfo) -> list[str]:
    """The few functions/classes worth reading first, with line ranges."""
    by_name = {fn.name: fn for fn in info.functions}
    chosen: list[CodeSymbol] = []

    def add(symbol: CodeSymbol | None) -> None:
        if symbol and symbol not in chosen and len(chosen) < MAX_RELEVANT_SYMBOLS:
            chosen.append(symbol)

    for route in info.routes:
        add(by_name.get(route.function))
    for fn in info.functions:
        if fn.name in IMPORTANT_FUNCTION_NAMES:
            add(fn)
    for cls in sorted(info.classes, key=lambda c: c.end_lineno - c.lineno, reverse=True):
        add(cls)
    public = [fn for fn in info.functions if fn.kind == "function" and not fn.name.startswith("_")]
    for fn in sorted(public, key=lambda f: f.end_lineno - f.lineno, reverse=True):
        add(fn)
    return [f"{sym.display_name} (lines {sym.line_range})" for sym in sorted(chosen, key=lambda s: s.lineno)]


def estimate_minutes(path: str, insight: FileInsight | None, info: PythonFileInfo | None) -> int:
    """Rough reading time, rounded up to 5/10/15/20/30 minutes."""
    if info:
        minutes = BASE_MINUTES + info.line_count / PYTHON_LINES_PER_MINUTE + info.branch_count / BRANCHES_PER_EXTRA_MINUTE
    elif insight and insight.category == "documentation":
        minutes = BASE_MINUTES + (insight.line_count * AVERAGE_README_LINE_CHARS) / README_CHARS_PER_MINUTE
    else:
        lines = insight.line_count if insight else 0
        minutes = BASE_MINUTES + lines / TEMPLATE_LINES_PER_MINUTE
    return round_to_time_bucket(minutes)


# ---------------------------------------------------------------------------
# Confusion map
# ---------------------------------------------------------------------------


def build_confusion_map(insights: dict[str, FileInsight]) -> dict[str, list[str]]:
    """Group files into Easy / Moderate / Advanced, most important first."""
    buckets: dict[str, list[str]] = {"Easy": [], "Moderate": [], "Advanced": []}
    for path, insight in sorted(insights.items(), key=lambda item: (-item[1].importance, item[0])):
        buckets[confusion_level(insight.difficulty)].append(path)
    return buckets


# ---------------------------------------------------------------------------
# Skip for now
# ---------------------------------------------------------------------------

# (kind, match, reason). kind "dir" matches any directory with that name;
# kind "file" matches a file name; kind "suffix" matches the end of a file name.
SKIP_RULES = (
    ("dir", ".github", "CI/CD workflows and GitHub settings. They control automated testing/deployment, "
                       "not the application's runtime behaviour."),
    ("file", "dockerfile", "Container setup for deployment. You can understand and run the app without it first."),
    ("file", "docker-compose.yml", "Runs the app with other services in containers - a deployment concern."),
    ("file", "docker-compose.yaml", "Runs the app with other services in containers - a deployment concern."),
    ("dir", "migrations", "Database migration history. Read the current models instead of past changes."),
    ("dir", "alembic", "Database migration history. Read the current models instead of past changes."),
    ("dir", "tests", "Tests are valuable later - read them once you understand the code they check."),
    ("dir", "test", "Tests are valuable later - read them once you understand the code they check."),
    ("dir", "docs", "Extended documentation. The README is enough to get started."),
    ("dir", "static", "CSS, JavaScript and images. Not needed to follow the Python flow."),
    ("dir", "scripts", "Helper scripts, usually for maintenance tasks rather than the main app."),
    ("dir", "examples", "Example usage. Useful later, but not part of the core application."),
    ("dir", "benchmarks", "Performance measurements, not application behaviour."),
    ("suffix", ".lock", "Auto-generated lock file that pins exact library versions."),
    ("suffix", ".ipynb", "Notebook experiments, not the application itself."),
    ("file", "setup.cfg", "Packaging/tooling configuration."),
    ("file", "tox.ini", "Test-runner configuration."),
    ("file", "noxfile.py", "Test/automation session configuration."),
    ("file", ".pre-commit-config.yaml", "Code-style checks that run before commits."),
    ("file", "makefile", "Shortcut commands for developers; the README usually explains how to run the app."),
    ("file", "procfile", "Tells a hosting platform how to start the app - a deployment concern."),
    ("file", "manifest.in", "Packaging configuration."),
    ("file", ".gitignore", "Tells Git which files to ignore."),
    ("file", "license", "Legal licence text."),
    ("file", "changelog.md", "History of changes between releases."),
    ("file", "contributing.md", "Contribution guidelines - read before your first pull request, not before the code."),
)


def build_skip_list(tree_paths: list[str], keep: set[str]) -> list[SkipItem]:
    """Files/folders that can safely be ignored at first. Never includes files in `keep`."""
    groups: dict[str, SkipItem] = {}
    blocked_groups: set[str] = set()

    for path in tree_paths:
        match = _match_skip_rule(path)
        if not match:
            continue
        group, reason = match
        if path in keep:
            blocked_groups.add(group)
            continue
        if group in groups:
            groups[group].file_count += 1
        else:
            groups[group] = SkipItem(path=group, reason=reason, file_count=1)

    items = _collapse_repeated_folders([item for group, item in groups.items() if group not in blocked_groups])
    rule_order = {rule[1]: index for index, rule in enumerate(SKIP_RULES)}
    items.sort(key=lambda item: (rule_order.get(_rule_key(item.path), len(SKIP_RULES)), item.path))
    return items[:MAX_SKIP_ITEMS]


def _collapse_repeated_folders(items: list[SkipItem]) -> list[SkipItem]:
    """Turn many 'x/migrations/', 'y/migrations/'... entries into one line."""
    by_name: dict[str, list[SkipItem]] = {}
    for item in items:
        if item.path.endswith("/"):
            by_name.setdefault(item.path.rstrip("/").split("/")[-1], []).append(item)

    collapsed = [item for item in items if not item.path.endswith("/")]
    for name, folders in by_name.items():
        if len(folders) > MAX_FOLDERS_PER_NAME:
            total = sum(f.file_count for f in folders)
            collapsed.append(SkipItem(path=f"{name}/", reason=f"{folders[0].reason} ({len(folders)} folders "
                                      "with this name)", file_count=total))
        else:
            collapsed.extend(folders)
    return collapsed


def _match_skip_rule(path: str) -> tuple[str, str] | None:
    parts = path_parts(path)
    lower = [p.lower() for p in parts]
    name = lower[-1]
    for kind, key, reason in SKIP_RULES:
        if kind == "dir" and key in lower[:-1]:
            index = lower.index(key)
            return "/".join(parts[: index + 1]) + "/", reason
        if kind == "file" and (name == key or (key == "dockerfile" and name.startswith("dockerfile"))):
            return path, reason
        if kind == "suffix" and name.endswith(key):
            return path, reason
    return None


def _rule_key(group: str) -> str:
    name = group.rstrip("/").split("/")[-1].lower()
    for _, key, _ in SKIP_RULES:
        if name == key or name.endswith(key) or (key == "dockerfile" and name.startswith("dockerfile")):
            return key
    return name
