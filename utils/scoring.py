"""Transparent heuristic scores. Every point added comes with a human-readable reason.

Three separate scores, on purpose:
  difficulty  - how hard a file is for a beginner to read (0-100)
  importance  - how much it matters for understanding the app (0-100)
  entry score - how likely it is where the program starts (0-100)
A file can be important and hard (a big models.py) or easy and unimportant
(.gitignore). The learning path uses importance to pick files and difficulty
to order and label them.

These are RepoLens beginner difficulty estimates, not validated measurements.
"""

from __future__ import annotations

from models.repo_models import PythonFileInfo
from utils.helpers import basename, depth

# --- Difficulty thresholds --------------------------------------------------
# (upper limit, points, reason) - the first matching row applies.
LENGTH_RULES = (
    (50, 0, "Small file ({n} lines)"),
    (150, 10, "Medium-length file ({n} lines)"),
    (300, 20, "Long file ({n} lines)"),
    (600, 30, "Very long file ({n} lines)"),
    (float("inf"), 40, "Very long file ({n} lines) - skim it, don't read line by line"),
)
FUNCTION_RULES = ((7, 0, "Few functions ({n})"), (15, 5, "Several functions ({n})"), (float("inf"), 10, "Many functions ({n})"))
CLASS_RULES = ((0, 0, "No classes"), (2, 5, "{n} class(es)"), (float("inf"), 10, "Many classes ({n})"))
IMPORT_RULES = ((7, 0, "Few imports ({n})"), (15, 8, "Several imports ({n})"), (float("inf"), 15, "Many imports ({n})"))
BRANCH_RULES = (
    (15, 0, "Simple control flow"),
    (40, 8, "Moderate branching ({n} decision points)"),
    (float("inf"), 15, "Lots of branching ({n} decision points)"),
)
DEEP_NESTING = 5
MEDIUM_NESTING = 4
ASYNC_POINTS = 5
PARSE_ERROR_SCORE = 50

# Base difficulty for files RepoLens does not parse, by category.
NON_PYTHON_DIFFICULTY = {
    "documentation": (10, "Plain-language documentation"),
    "dependency": (10, "A list of libraries the project needs"),
    "template": (25, "HTML template mixed with template syntax"),
    "ui": (30, "Front-end styling/scripts"),
    "configuration": (35, "Configuration values - meaning depends on the code that reads them"),
    "deployment": (55, "Assumes knowledge of Docker/CI/deployment tools"),
    "test": (45, "Tests use fixtures and assertions about other code"),
    "database": (55, "Database migrations/scripts assume knowledge of the schema history"),
    "unknown": (35, "Purpose not clear from its name"),
}
CATEGORY_DIFFICULTY_BONUS = {
    "test": (5, "Test code - easier once you know the code it tests"),
    "configuration": (5, "Configuration - depends on how other code reads it"),
    "deployment": (15, "Deployment-related"),
}

# --- Importance -------------------------------------------------------------
CATEGORY_IMPORTANCE = {
    "documentation": 40, "entry_point": 80, "routes": 55, "models": 55, "database": 50,
    "core_logic": 45, "ui": 45, "template": 40, "dependency": 35, "utility": 30,
    "configuration": 30, "unknown": 25, "test": 20, "deployment": 10,
}
ROOT_README_IMPORTANCE = 90
POINTS_PER_IMPORTER = 5
MAX_IMPORTER_POINTS = 20
POINTS_PER_INTERNAL_IMPORT = 3
MAX_INTERNAL_IMPORT_POINTS = 12
POINTS_PER_ROUTE = 3
MAX_ROUTE_POINTS = 15
GLUE_MAX_LINES = 15
GLUE_MAX_IMPORTANCE = 30

# --- Entry points -----------------------------------------------------------
ENTRY_POINT_NAMES = {"app.py", "main.py", "run.py", "server.py", "manage.py", "wsgi.py", "asgi.py", "__main__.py",
                     "streamlit_app.py", "cli.py", "bot.py"}
ENTRY_NAME_POINTS = 30
MAIN_GUARD_POINTS = 30
FRAMEWORK_INIT_POINTS = 35
STREAMLIT_SCRIPT_POINTS = 30
ROOT_LEVEL_POINTS = 10
SHALLOW_LEVEL_POINTS = 5
ENTRY_POINT_THRESHOLD = 40
FRAMEWORK_INIT_CALLS = (
    "Flask", "FastAPI", "execute_from_command_line", "QApplication", "Tk", "get_wsgi_application",
    "create_app",  # the Flask "application factory" pattern: app = create_app()
)


def _apply_rule(rules, value: int) -> tuple[int, str]:
    for limit, points, reason in rules:
        if value <= limit:
            return points, reason.format(n=value)
    return 0, ""


def clamp(score: float) -> int:
    return max(0, min(100, int(round(score))))


# ---------------------------------------------------------------------------
# Difficulty
# ---------------------------------------------------------------------------


def difficulty_score(category: str, info: PythonFileInfo | None = None) -> tuple[int, list[str]]:
    """RepoLens beginner difficulty estimate (0-100) with reasons."""
    if info is None:
        base, reason = NON_PYTHON_DIFFICULTY.get(category, NON_PYTHON_DIFFICULTY["unknown"])
        return base, [reason]
    if info.syntax_error:
        return PARSE_ERROR_SCORE, ["RepoLens could not parse this file, so its difficulty is a rough guess"]

    score = 0
    reasons: list[str] = []
    for rules, value in (
        (LENGTH_RULES, info.line_count),
        (FUNCTION_RULES, len(info.functions)),
        (CLASS_RULES, len(info.classes)),
        (IMPORT_RULES, len(info.imports)),
        (BRANCH_RULES, info.branch_count),
    ):
        points, reason = _apply_rule(rules, value)
        score += points
        reasons.append(reason)

    if info.max_nesting >= DEEP_NESTING:
        score += 10
        reasons.append(f"Deeply nested code ({info.max_nesting} levels)")
    elif info.max_nesting >= MEDIUM_NESTING:
        score += 5
        reasons.append(f"Some nested blocks ({info.max_nesting} levels)")

    if any(fn.is_async for fn in info.functions):
        score += ASYNC_POINTS
        reasons.append("Uses async/await")

    if category in CATEGORY_DIFFICULTY_BONUS:
        points, reason = CATEGORY_DIFFICULTY_BONUS[category]
        score += points
        reasons.append(reason)
    if category == "entry_point":
        reasons.append("Likely application entry point")
    return clamp(score), reasons


# ---------------------------------------------------------------------------
# Importance
# ---------------------------------------------------------------------------


def importance_score(
    path: str,
    category: str,
    info: PythonFileInfo | None = None,
    importers: list[str] | None = None,
    internal_imports: list[str] | None = None,
) -> tuple[int, list[str]]:
    """How much this file matters for understanding the main application flow."""
    importers = importers or []
    internal_imports = internal_imports or []

    if category == "documentation" and basename(path).lower().startswith("readme") and depth(path) == 0:
        return ROOT_README_IMPORTANCE, ["Main README - explains what the project is"]

    score = CATEGORY_IMPORTANCE.get(category, CATEGORY_IMPORTANCE["unknown"])
    reasons = [f"Category: {category.replace('_', ' ')}"]

    if importers:
        points = min(len(importers) * POINTS_PER_IMPORTER, MAX_IMPORTER_POINTS)
        score += points
        reasons.append(f"Imported by {len(importers)} other file(s)")
    if internal_imports:
        points = min(len(internal_imports) * POINTS_PER_INTERNAL_IMPORT, MAX_INTERNAL_IMPORT_POINTS)
        score += points
        reasons.append(f"Connects {len(internal_imports)} other project file(s)")
    if info and info.routes:
        score += min(len(info.routes) * POINTS_PER_ROUTE, MAX_ROUTE_POINTS)
        reasons.append(f"Defines {len(info.routes)} route handler(s)")
    if info and is_glue_file(info):
        score = min(score, GLUE_MAX_IMPORTANCE)
        reasons.append("Short wiring file with no functions or classes")
    return clamp(score), reasons


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def entry_point_score(path: str, info: PythonFileInfo) -> tuple[int, list[str]]:
    """Likelihood (0-100) that the program starts in this file, with reasons."""
    score = 0
    reasons: list[str] = []
    name = basename(path)

    if name in ENTRY_POINT_NAMES:
        score += ENTRY_NAME_POINTS
        reasons.append(f"Named `{name}`, a common entry-point name")
    if info.has_main_guard:
        score += MAIN_GUARD_POINTS
        reasons.append(f"Has `if __name__ == \"__main__\"` at {path}:{info.main_guard_line}")
    for call_name in FRAMEWORK_INIT_CALLS:
        calls = info.calls_named(call_name)
        if calls:
            score += FRAMEWORK_INIT_POINTS
            reasons.append(f"Creates `{call_name}(...)` at {path}:{calls[0].lineno}")
            break
    if "streamlit" in info.top_level_packages and info.top_level_statements > 0:
        score += STREAMLIT_SCRIPT_POINTS
        reasons.append("Streamlit script with top-level code (Streamlit runs files top to bottom)")

    if score and depth(path) == 0:
        score += ROOT_LEVEL_POINTS
        reasons.append("Located at the repository root")
    elif score and depth(path) == 1:
        score += SHALLOW_LEVEL_POINTS
    return clamp(score), reasons


def is_glue_file(info: PythonFileInfo) -> bool:
    """A short file with no functions, classes or routes - usually package wiring."""
    return not (info.functions or info.classes or info.routes) and info.line_count <= GLUE_MAX_LINES


def is_likely_entry_point(score: int) -> bool:
    return score >= ENTRY_POINT_THRESHOLD
