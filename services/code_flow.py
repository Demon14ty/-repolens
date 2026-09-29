"""Describe the main execution flow as a short list of steps.

Every step between the generic start/end labels must be backed by analysed
source code: an entry point we detected, route decorators we parsed, an import
we resolved, or a template name passed to a render call.
"""

from __future__ import annotations

from models.repo_models import FileInsight, FlowStep, FrameworkResult, PythonFileInfo
from utils.helpers import human_join, reachable_depths, resolve_template_path

MAX_SUPPORTING_FILES = 3
SUPPORTING_CATEGORIES = ("core_logic", "database", "models", "ui", "utility")

WEB = ("Flask", "FastAPI", "Django")
DESKTOP = ("Tkinter", "PySide / PyQt")

CATEGORY_LABELS = {
    "core_logic": "Core logic",
    "database": "Database access",
    "models": "Data models",
    "ui": "User interface code",
    "utility": "Helper functions",
    "routes": "Route handlers",
}


def _start_and_end(framework: str) -> tuple[str, str]:
    if framework in WEB:
        return "User sends an HTTP request (e.g. opens a page)", "Response is sent back to the user"
    if framework == "Streamlit":
        return "User opens the app or changes a widget", "Streamlit re-runs the script and redraws the page"
    if framework in DESKTOP:
        return "User starts the program and interacts with the window", "Window updates with the result"
    return "User runs the program", "Program prints output or finishes"


def build_flow(
    framework: FrameworkResult,
    insights: dict[str, FileInsight],
    python_files: dict[str, PythonFileInfo],
    entry_points: list[str],
    import_graph: dict[str, list[str]],
    tree_paths: list[str],
) -> list[FlowStep]:
    """Return flow steps, or [] when there is not enough evidence."""
    entry = entry_points[0] if entry_points else None
    # Files with route decorators, plus files named like request handlers
    # (Django connects views through urls.py instead of decorators).
    route_files = [p for p, info in python_files.items()
                   if info.routes or (insights.get(p) and insights[p].category == "routes")]
    if not entry and not route_files:
        return []

    start, end = _start_and_end(framework.name)
    steps = [FlowStep(label=start)]
    shown: set[str] = set()

    if entry:
        reason = insights[entry].entry_reasons[0] if insights.get(entry) and insights[entry].entry_reasons else ""
        steps.append(FlowStep(label="Entry point", path=entry, detail=reason))
        shown.add(entry)

    depths = reachable_depths(entry, import_graph) if entry else {}
    route_files.sort(key=lambda p: (depths.get(p, 99), -len(python_files[p].routes), -insights[p].importance, p))
    for path in route_files[:2]:
        names = [f"{r.function}()" for r in python_files[path].routes]
        if names:
            detail = f"Handles requests in {human_join(names)}"
        else:
            detail = "Likely request handling (based on its file name, e.g. views/urls)"
        steps.append(FlowStep(label="Route handlers", path=path, detail=detail))
        shown.add(path)

    for path, importer in _supporting_files(shown, insights, import_graph):
        category = insights[path].category
        steps.append(FlowStep(label=CATEGORY_LABELS.get(category, "Supporting code"), path=path,
                              detail=f"Imported by {importer}"))
        shown.add(path)

    for path in list(shown):
        for ref in python_files[path].template_refs if path in python_files else []:
            template = resolve_template_path(ref, tree_paths)
            if template and template not in shown:
                steps.append(FlowStep(label="Template rendering", path=template, detail=f"Rendered by {path}"))
                shown.add(template)
                break

    steps.append(FlowStep(label=end))
    return steps


def _supporting_files(
    shown: set[str], insights: dict[str, FileInsight], import_graph: dict[str, list[str]]
) -> list[tuple[str, str]]:
    """Project files imported directly by the entry point / route files."""
    found: list[tuple[str, str]] = []
    for source in sorted(shown):
        for target in import_graph.get(source, []):
            insight = insights.get(target)
            if insight and insight.category in SUPPORTING_CATEGORIES and target not in shown:
                if target not in {t for t, _ in found}:
                    found.append((target, source))
    order = {category: index for index, category in enumerate(("core_logic", "database", "models", "ui", "utility"))}
    found.sort(key=lambda item: (order.get(insights[item[0]].category, 9), -insights[item[0]].importance))
    return found[:MAX_SUPPORTING_FILES]
