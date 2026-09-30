"""First 30 Minutes mode: a short, focused reading plan built on the full learning path.

The plan picks 3-5 files in a fixed, beginner-friendly order:
  1. README (what is this project?)
  2. One dependency file (what does it need?)
  3. The likely entry point (where does it start?)
  4. Core logic (where does the real work happen?)
  5. A route / model / UI / template file (how does it reach the user?)
Files, reading-time estimates, difficulty and evidence all come from the
existing deterministic analysis; nothing here downloads or guesses new files.
"""

from __future__ import annotations

from models.repo_models import FileInsight, FirstThirtyPlan, FirstThirtyStep, LearningStep, RepoAnalysis
from services.framework_detector import UNKNOWN_FRAMEWORK, parse_dependencies
from services.learning_path import CATEGORY_PURPOSE, estimate_minutes, find_root_readme
from utils.helpers import basename, depth, difficulty_label, human_join

MAX_STEPS = 5
MAX_TOTAL_MINUTES = 35
MIN_FULL_PLAN_STEPS = 3
LIMITED_NOTICE = "RepoLens found limited source material, so this is a shorter learning path."

# In this mode the learner skims for the big picture, so each file gets a time box.
MINUTE_CAPS = {"documentation": 5, "dependency": 3, "entry_point": 10}
DEFAULT_MINUTE_CAP = 8
MIN_STEP_MINUTES = 2

DEPENDENCY_PRIORITY = ("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "pipfile")
CORE_CATEGORIES = ("core_logic", "database", "models", "utility")
SURFACE_CATEGORIES = ("routes", "ui", "template", "models", "database", "core_logic")
EXCLUDED_CATEGORIES = {"test", "deployment", "unknown", "configuration"}
GENERATED_SUFFIXES = ("_pb2.py", "_pb2_grpc.py", ".min.js", ".min.css", ".lock")
UNKNOWN_FRAMEWORKS = {"Not determined", UNKNOWN_FRAMEWORK}

LOOK_FOR = {
    "routes": "The route decorators (the URLs) and what each handler function returns.",
    "models": "The classes and their fields - this is the data the application works with.",
    "database": "How data is saved and loaded: connections, queries or ORM sessions.",
    "core_logic": "The main public functions and classes, and what they return.",
    "utility": "Small helper functions that other files reuse.",
    "ui": "How the interface is laid out and which inputs the user can change.",
    "template": "Where values from the Python code are displayed ({{ ... }} placeholders and loops).",
}
OUTCOMES = {
    "routes": "Which URLs the application responds to and where each request is handled.",
    "models": "What data the application stores and how it is structured.",
    "database": "How the application saves and loads its data.",
    "core_logic": "Where the main work of the application happens.",
    "utility": "Which shared helpers the rest of the code relies on.",
    "ui": "How the user interface is put together.",
    "template": "How the application turns data into the page the user sees.",
}
ENTRY_LOOK_FOR = {
    "Flask": "Where `Flask(...)` (or `create_app()`) builds the app, which routes/blueprints are registered, "
             "and how the server is started.",
    "FastAPI": "Where `FastAPI(...)` builds the app, which routers are included, and how the server is started.",
    "Django": "Which settings module it points to and how Django commands are dispatched.",
    "Streamlit": "The Streamlit page from top to bottom (`st.*` calls): titles, widgets, and what happens when an "
                 "input changes.",
    "Tkinter": "Where the main window is created and where the event loop (`mainloop()`) starts.",
    "PySide / PyQt": "Where `QApplication` and the main window are created and where the event loop starts.",
}
DEFAULT_ENTRY_LOOK_FOR = "The `main()` function or the `if __name__ == \"__main__\"` block, and the first functions it calls."


def build_first_30_minutes(analysis: RepoAnalysis) -> FirstThirtyPlan:
    """Build the short reading plan from an existing analysis (no new downloads)."""
    by_step = {step.path: step for step in analysis.learning_path}
    chosen: list[str] = []

    def usable(path: str | None) -> bool:
        return bool(path) and path not in chosen and _is_recommendable(path, analysis)

    readme = find_root_readme(analysis.files)
    if usable(readme):
        chosen.append(readme)

    dependency = _pick_dependency_file(analysis)
    if usable(dependency):
        chosen.append(dependency)

    entry = analysis.entry_points[0] if analysis.entry_points else None
    if usable(entry):
        chosen.append(entry)

    code_order = _code_candidates(analysis)
    core = next((p for p in code_order if usable(p) and analysis.files[p].category in CORE_CATEGORIES), None)
    core = core or next((p for p in code_order if usable(p)), None)
    if core:
        chosen.append(core)
    surface = next((p for p in code_order if usable(p) and analysis.files[p].category in SURFACE_CATEGORIES), None)
    if surface:
        chosen.append(surface)

    steps: list[FirstThirtyStep] = []
    total = 0
    for path in chosen[:MAX_STEPS]:
        step = _make_step(len(steps) + 1, path, analysis, by_step.get(path), entry)
        if total + step.minutes > MAX_TOTAL_MINUTES:
            continue
        steps.append(step)
        total += step.minutes

    has_code = any(s.category not in ("documentation", "dependency") for s in steps)
    return FirstThirtyPlan(
        steps=steps,
        total_minutes=total,
        outcomes=_outcomes(steps, analysis),
        is_limited=len(steps) < MIN_FULL_PLAN_STEPS or not has_code,
    )


# ---------------------------------------------------------------------------
# Choosing files
# ---------------------------------------------------------------------------


def _is_recommendable(path: str, analysis: RepoAnalysis) -> bool:
    """Only analysed, readable, non-skipped files that a beginner should actually open."""
    insight = analysis.files.get(path)
    if insight is None or insight.category in EXCLUDED_CATEGORIES:
        return False
    if path not in analysis.file_contents and path not in analysis.python_files:
        return False  # never downloaded (binary, too large, or over the limit)
    if path.endswith(GENERATED_SUFFIXES):
        return False
    return not _is_skipped(path, analysis)


def _is_skipped(path: str, analysis: RepoAnalysis) -> bool:
    for item in analysis.skip_for_now:
        if path == item.path or (item.path.endswith("/") and path.startswith(item.path)):
            return True
    return False


def _pick_dependency_file(analysis: RepoAnalysis) -> str | None:
    candidates = [p for p, insight in analysis.files.items() if insight.category == "dependency"]

    def priority(path: str) -> tuple:
        name = basename(path).lower()
        rank = DEPENDENCY_PRIORITY.index(name) if name in DEPENDENCY_PRIORITY else len(DEPENDENCY_PRIORITY)
        return depth(path), rank, path

    for path in sorted(candidates, key=priority):
        if _is_recommendable(path, analysis):
            return path
    return None


def _code_candidates(analysis: RepoAnalysis) -> list[str]:
    """Learning-path files first (already ordered by import distance), then other important files."""
    ordered = [s.path for s in analysis.learning_path if s.path in analysis.files]
    extra = sorted(
        (p for p, insight in analysis.files.items()
         if p not in ordered and (p in analysis.python_files or insight.category == "template")),
        key=lambda p: (-analysis.files[p].importance, p),
    )
    code = ordered + extra
    return [p for p in code if analysis.files[p].category not in ("documentation", "dependency", "entry_point")
            and p not in analysis.entry_points[:1]]


# ---------------------------------------------------------------------------
# Describing a step
# ---------------------------------------------------------------------------


def _make_step(
    number: int, path: str, analysis: RepoAnalysis, learning_step: LearningStep | None, entry: str | None
) -> FirstThirtyStep:
    insight = analysis.files[path]
    category = "entry_point" if path == entry else insight.category
    full_minutes = learning_step.minutes if learning_step else estimate_minutes(
        path, insight, analysis.python_files.get(path))
    minutes = max(min(full_minutes, MINUTE_CAPS.get(category, DEFAULT_MINUTE_CAP)), MIN_STEP_MINUTES)
    label = learning_step.difficulty_label if learning_step else difficulty_label(insight.difficulty)
    why, look_for, outcome = _describe(path, category, insight, analysis, learning_step)
    if minutes < full_minutes:
        look_for += " Skim it - you do not need to understand every line yet."
    evidence = list(learning_step.evidence) if learning_step and learning_step.evidence else [path]
    return FirstThirtyStep(number=number, path=path, category=category, minutes=minutes, difficulty_label=label,
                           why=why, look_for=look_for, outcome=outcome, evidence=evidence)


def _describe(
    path: str, category: str, insight: FileInsight, analysis: RepoAnalysis, learning_step: LearningStep | None
) -> tuple[str, str, str]:
    """Return (why this file matters, what to look for, learning outcome)."""
    framework = analysis.framework.name
    if category == "documentation":
        return ("Learn what the project does, how to install it, and how to start it.",
                "Installation commands, environment variables, and example usage.",
                "The purpose of the project and its basic setup process.")

    if category == "dependency":
        packages = parse_dependencies(path, analysis.file_contents.get(path, ""))
        listed = f" (for example {human_join([f'`{p}`' for p in packages[:4]], limit=4)})" if packages else ""
        return (f"It lists the libraries this project needs{listed}.",
                "The main framework, the most important libraries, and any pinned versions.",
                "Which libraries the project depends on and how they are installed.")

    if category == "entry_point":
        reasons = insight.entry_reasons[:2]
        because = ("; ".join(r[0].lower() + r[1:] for r in reasons)) if reasons else "its name and position"
        why = f"This is the likely entry point - where the application starts ({because})."
        look_for = ENTRY_LOOK_FOR.get(framework, DEFAULT_ENTRY_LOOK_FOR)
        if learning_step and learning_step.relevant_code:
            look_for += " Start with " + human_join([f"`{c}`" for c in learning_step.relevant_code[:2]]) + "."
        return why, look_for, "Where the application starts and what it does first."

    why = learning_step.why if learning_step else _fallback_why(category)
    look_for = LOOK_FOR.get(category, LOOK_FOR["core_logic"])
    if learning_step and learning_step.relevant_code:
        look_for += " Start with " + human_join([f"`{c}`" for c in learning_step.relevant_code[:2]]) + "."
    return why, look_for, OUTCOMES.get(category, OUTCOMES["core_logic"])


def _fallback_why(category: str) -> str:
    return CATEGORY_PURPOSE.get(category, "It is one of the most important files in the project.")


def _outcomes(steps: list[FirstThirtyStep], analysis: RepoAnalysis) -> list[str]:
    categories = {s.category for s in steps}
    outcomes: list[str] = []
    if "documentation" in categories:
        outcomes.append("What the project does")
    framework = analysis.framework.name
    if framework not in UNKNOWN_FRAMEWORKS and categories & {"dependency", "entry_point"}:
        outcomes.append(f"Which Python framework it uses ({framework})")
    if "dependency" in categories:
        outcomes.append("How dependencies are managed")
    if "entry_point" in categories:
        outcomes.append("Where the application starts")
    if categories & {"core_logic", "database", "utility"}:
        outcomes.append("Where the core logic is likely located")
    if "routes" in categories:
        outcomes.append("Where requests are handled")
    if "models" in categories:
        outcomes.append("What data the application works with")
    if categories & {"ui", "template"}:
        outcomes.append("Where the user interface is built")
    return outcomes
