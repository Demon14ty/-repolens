"""Coordinate the deterministic analysis of a repository.

Pipeline (no LLM involved):
  1. choose_files_to_download - decide what is worth downloading (with limits)
  2. analyze_snapshot         - parse Python, detect framework, classify and
                                score files, build the import graph, then hand
                                off to the learning-path, code-flow and quest
                                builders.
"""

from __future__ import annotations

from models.repo_models import FileInsight, FrameworkResult, PythonFileInfo, RepoAnalysis, RepoSnapshot, TreeEntry
from services.challenge_generator import generate_quest
from services.code_flow import build_flow
from services.file_classifier import classify_file, is_test_path
from services.framework_detector import collect_dependencies, detect_framework, is_dependency_file
from services.learning_path import build_confusion_map, build_learning_path, build_skip_list
from services.python_analyzer import analyze_python_source
from utils.helpers import basename, depth, module_names_for_path, path_parts
from utils.scoring import (
    ENTRY_POINT_NAMES,
    difficulty_score,
    entry_point_score,
    importance_score,
    is_likely_entry_point,
)

# --- Download limits (keep big repositories fast and polite to GitHub) -------
MAX_FILE_BYTES = 100_000  # bigger files are usually generated or data
MAX_TOTAL_BYTES = 1_500_000
MAX_PYTHON_FILES = 60
MAX_TEST_FILES = 10  # only used to see which functions already have tests
MAX_TEMPLATE_FILES = 10
MAX_DEPENDENCY_DEPTH = 1  # dependency files at root or one folder down
MAX_SCORED_FILES = 200

# Directories that never contain code a learner should read first.
IGNORED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "env", ".env", "__pycache__", "dist", "build", "coverage",
    ".idea", ".vscode", "site-packages", ".tox", ".nox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".eggs", "htmlcov", ".ipynb_checkpoints",
}
GENERATED_SUFFIXES = ("_pb2.py", "_pb2_grpc.py", ".min.js", ".min.css")
PLACEHOLDER_FILES = {".keep", ".gitkeep", ".gitignore", ".DS_Store"}
VISIBLE_DOT_DIRS = {".github"}  # hidden folders worth mentioning (as "skip for now")
README_NAMES = ("readme.md", "readme.rst", "readme.txt", "readme")
TEMPLATE_EXTENSIONS = (".html", ".htm", ".jinja", ".jinja2", ".j2")


# ---------------------------------------------------------------------------
# 1. Choosing files
# ---------------------------------------------------------------------------


def is_ignored(path: str) -> bool:
    parts = path_parts(path)
    return any(part in IGNORED_DIRS or part.endswith(".egg-info") for part in parts[:-1])


def _is_noise(path: str) -> bool:
    """Placeholder files and files in hidden tool folders (.devcontainer/, .agents/...)."""
    parts = path_parts(path)
    hidden_dir = any(p.startswith(".") and p not in VISIBLE_DOT_DIRS for p in parts[:-1])
    return hidden_dir or parts[-1] in PLACEHOLDER_FILES


def _python_priority(entry: TreeEntry) -> tuple:
    """Sort key: likely entry points first, then shallow files, then alphabetical."""
    return (basename(entry.path) not in ENTRY_POINT_NAMES, depth(entry.path), entry.path)


def choose_files_to_download(tree: list[TreeEntry]) -> tuple[list[str], list[str]]:
    """Return (paths to download, notes for the user)."""
    notes: list[str] = []
    usable = [e for e in tree if not is_ignored(e.path)]
    too_big = [e for e in usable if e.size > MAX_FILE_BYTES or e.path.endswith(GENERATED_SUFFIXES)]
    small = [e for e in usable if e not in too_big]

    readmes = [e for e in small if basename(e.path).lower() in README_NAMES and depth(e.path) == 0]
    dependencies = [e for e in small if is_dependency_file(e.path) and depth(e.path) <= MAX_DEPENDENCY_DEPTH]
    python = sorted((e for e in small if e.path.endswith(".py") and not is_test_path(e.path)), key=_python_priority)
    tests = sorted((e for e in small if e.path.endswith(".py") and is_test_path(e.path)), key=_python_priority)
    templates = sorted((e for e in small if e.path.lower().endswith(TEMPLATE_EXTENSIONS)), key=_python_priority)

    if len(python) > MAX_PYTHON_FILES:
        notes.append(
            f"This repository has {len(python)} Python files; RepoLens analysed the "
            f"{MAX_PYTHON_FILES} most likely to matter (shallowest and entry-point-like first)."
        )
    if too_big:
        notes.append(f"Skipped {len(too_big)} file(s) larger than {MAX_FILE_BYTES // 1000} KB or generated.")

    chosen: list[str] = []
    total = 0
    groups = (readmes[:1], dependencies, python[:MAX_PYTHON_FILES], templates[:MAX_TEMPLATE_FILES], tests[:MAX_TEST_FILES])
    for group in groups:
        for entry in group:
            if total + entry.size > MAX_TOTAL_BYTES:
                notes.append("Stopped downloading because the total source size limit was reached.")
                return chosen, notes
            chosen.append(entry.path)
            total += entry.size
    return chosen, notes


# ---------------------------------------------------------------------------
# 2. Import graph
# ---------------------------------------------------------------------------


def build_module_index(paths: list[str]) -> tuple[dict[str, str], dict[str, str]]:
    """Map dotted module names to file paths.

    Returns (full, suffix): `full` uses the complete path ('src.pkg.mod'),
    `suffix` holds shorter names ('pkg.mod') only when they are unambiguous.
    """
    full: dict[str, str] = {}
    suffix_owners: dict[str, set[str]] = {}
    for path in paths:
        names = module_names_for_path(path)
        if not names:
            continue
        full[names[0]] = path
        for name in names[1:]:
            suffix_owners.setdefault(name, set()).add(path)
    suffix = {name: next(iter(owners)) for name, owners in suffix_owners.items() if len(owners) == 1}
    return full, suffix


def resolve_imports(path: str, info: PythonFileInfo, full: dict[str, str], suffix: dict[str, str]) -> list[str]:
    """Project files imported by `path` (third-party imports are ignored)."""

    def lookup(module: str) -> str | None:
        return full.get(module) or suffix.get(module)

    package = path_parts(path)[:-1]
    targets: list[str] = []
    for imp in info.imports:
        if imp.level:
            base = package[: len(package) - (imp.level - 1)] if imp.level > 1 else package
            prefix = ".".join(base + ([imp.module] if imp.module else []))
        else:
            prefix = imp.module

        found = [lookup(f"{prefix}.{name}" if prefix else name) for name in imp.names]
        found = [f for f in found if f]
        if not found and prefix:
            module_target = lookup(prefix)
            found = [module_target] if module_target else []
        targets.extend(t for t in found if t != path and t not in targets)
    return targets


def build_import_graph(python_files: dict[str, PythonFileInfo]) -> dict[str, list[str]]:
    full, suffix = build_module_index(list(python_files))
    return {path: resolve_imports(path, info, full, suffix) for path, info in python_files.items()}


# ---------------------------------------------------------------------------
# 3. Full analysis
# ---------------------------------------------------------------------------


def analyze_snapshot(snapshot: RepoSnapshot) -> RepoAnalysis:
    """Turn downloaded repository data into a complete, evidence-based analysis."""
    files = snapshot.files
    tree_paths = [e.path for e in snapshot.tree]

    all_python = {p: analyze_python_source(p, text) for p, text in files.items() if p.endswith(".py")}
    app_python = {p: info for p, info in all_python.items() if not is_test_path(p)}
    test_python = {p: info for p, info in all_python.items() if is_test_path(p)}

    dependency_map = collect_dependencies(files)
    dependencies = sorted({pkg for pkgs in dependency_map.values() for pkg in pkgs})
    framework = detect_framework(dependency_map, app_python) if app_python else FrameworkResult(
        name="Not determined", confidence="Low", evidence=["No Python application code was found to analyse."]
    )
    import_graph = build_import_graph(app_python)

    entry_scores = {path: entry_point_score(path, info) for path, info in app_python.items()}
    entry_points = sorted(
        (p for p, (score, _) in entry_scores.items() if is_likely_entry_point(score)),
        key=lambda p: (-entry_scores[p][0], depth(p), p),
    )

    insights = _score_files(snapshot, app_python, test_python, import_graph, entry_scores, set(entry_points))

    learning_path = build_learning_path(insights, app_python, entry_points, import_graph, tree_paths)
    flow = build_flow(framework, insights, app_python, entry_points, import_graph, tree_paths)
    skip = build_skip_list(tree_paths, {s.path for s in learning_path} | {f.path for f in flow if f.path})
    quest = generate_quest(insights, app_python, test_python, files, entry_points, tree_paths, framework)         if app_python else None

    notes = list(snapshot.notes)
    language = snapshot.metadata.language
    if language not in ("Python", "Unknown", "Jupyter Notebook"):
        notes.append(f"GitHub reports this repository's main language as {language}. "
                     "RepoLens Version 1 only analyses Python code, so results may be limited.")
    if not app_python:
        notes.append(
            "We found the repository, but RepoLens could not identify enough Python application code "
            "to build a reliable learning path."
        )
    elif not entry_points:
        notes.append("RepoLens could not find a likely entry point, so the reading order is based on file importance.")
    if not any(basename(p).lower() in README_NAMES and depth(p) == 0 for p in tree_paths):
        notes.append("This repository has no README at its root.")
    if not dependency_map:
        notes.append("No dependency file (requirements.txt, pyproject.toml, Pipfile) was found.")

    return RepoAnalysis(
        metadata=snapshot.metadata,
        framework=framework,
        dependencies=dependencies,
        files=insights,
        python_files=app_python,
        entry_points=entry_points,
        import_graph=import_graph,
        learning_path=learning_path,
        flow=flow,
        confusion_map=build_confusion_map(insights),
        skip_for_now=skip,
        quest=quest,
        estimated_minutes=sum(step.minutes for step in learning_path),
        notes=notes,
        tree_paths=tree_paths,
    )


def _score_files(
    snapshot: RepoSnapshot,
    app_python: dict[str, PythonFileInfo],
    test_python: dict[str, PythonFileInfo],
    import_graph: dict[str, list[str]],
    entry_scores: dict[str, tuple[int, list[str]]],
    entry_points: set[str],
) -> dict[str, FileInsight]:
    """Classify and score every file a learner might look at."""
    importers: dict[str, list[str]] = {}
    for source, targets in import_graph.items():
        for target in targets:
            importers.setdefault(target, []).append(source)

    insights: dict[str, FileInsight] = {}
    for entry in snapshot.tree:
        path = entry.path
        if is_ignored(path) or _is_noise(path) or len(insights) >= MAX_SCORED_FILES:
            continue
        info = app_python.get(path) or test_python.get(path)
        if path.endswith(".py") and info is None:
            continue  # not analysed (over the limit or too large) - don't guess
        category = classify_file(path, info, is_entry_point=path in entry_points)
        if info is None and category == "unknown":
            continue  # images, data files, etc.
        if category == "documentation" and path not in snapshot.files:
            continue  # only the main README matters at first

        difficulty, difficulty_reasons = difficulty_score(category, info)
        importance, importance_reasons = importance_score(
            path, category, info, importers.get(path, []), import_graph.get(path, [])
        )
        entry_score, entry_reasons = entry_scores.get(path, (0, []))
        insights[path] = FileInsight(
            path=path,
            category=category,
            line_count=info.line_count if info else snapshot.files.get(path, "").count("\n"),
            difficulty=difficulty,
            difficulty_reasons=difficulty_reasons,
            importance=importance,
            importance_reasons=importance_reasons,
            entry_score=entry_score,
            entry_reasons=entry_reasons,
        )
    return insights
