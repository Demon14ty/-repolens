"""Generate ONE small, repository-specific First Contribution Quest.

Each quest builder looks for concrete evidence in the analysed code (a template
loop without an empty state, a route reading form data, an untested function...)
and returns a Quest only when that evidence exists. Builders are tried in order
and the first match wins, so the quest is always grounded in real files.
"""

from __future__ import annotations

import re

from models.repo_models import CodeSymbol, FileInsight, FrameworkResult, PythonFileInfo, Quest
from utils.helpers import basename, dirname, resolve_template_path

TEMPLATE_FOR_LOOP = re.compile(r"{%-?\s*for\s+\w+(?:\s*,\s*\w+)?\s+in\s+([\w.()]+)")
TEMPLATE_EMPTY_BRANCH = re.compile(r"{%-?\s*(else|empty)\s*-?%}")

STREAMLIT_INPUT_WIDGETS = {"text_input", "text_area", "number_input", "file_uploader", "chat_input"}
STREAMLIT_FEEDBACK_CALLS = {"warning", "error", "info", "stop", "toast"}
REQUEST_DATA_MARKERS = ("request.form", "request.args", "request.get_json", "request.json", "request.values",
                        "request.POST", "request.GET")

TESTABLE_CATEGORIES = {"core_logic", "utility", "models"}
MIN_TESTABLE_LINES = 3
MAX_TESTABLE_LINES = 30
MAX_TESTABLE_BRANCHES = 5

README_NAMES = ("readme.md", "readme.rst", "readme.txt", "readme")
README_RUN_WORDS = ("install", "usage", "getting started", "how to run", "run ", "setup", "quickstart")


def generate_quest(
    insights: dict[str, FileInsight],
    python_files: dict[str, PythonFileInfo],
    test_files: dict[str, PythonFileInfo],
    file_texts: dict[str, str],
    entry_points: list[str],
    tree_paths: list[str],
    framework: FrameworkResult,
) -> Quest | None:
    """Return the most suitable quest, or None if there is no evidence for any."""
    builders = (
        lambda: _empty_state_quest(file_texts, python_files, tree_paths),
        lambda: _streamlit_input_quest(python_files),
        lambda: _route_validation_quest(python_files),
        lambda: _missing_test_quest(insights, python_files, test_files, file_texts),
        lambda: _readme_quest(file_texts, tree_paths, entry_points, framework),
        lambda: _docstring_quest(insights, python_files, entry_points),
    )
    for build in builders:
        quest = build()
        if quest:
            return quest
    return None


# ---------------------------------------------------------------------------
# Quest builders
# ---------------------------------------------------------------------------


def _empty_state_quest(file_texts: dict[str, str], python_files: dict[str, PythonFileInfo],
                       tree_paths: list[str]) -> Quest | None:
    for path, text in sorted(file_texts.items()):
        if not path.lower().endswith((".html", ".htm", ".jinja", ".jinja2", ".j2")):
            continue
        match = TEMPLATE_FOR_LOOP.search(text)
        if not match or TEMPLATE_EMPTY_BRANCH.search(text):
            continue
        line = text[: match.start()].count("\n") + 1
        collection = match.group(1)
        renderers = [p for p, info in sorted(python_files.items())
                     if any(resolve_template_path(ref, [path]) for ref in info.template_refs)]
        return Quest(
            title=f"Show a friendly message when `{collection}` is empty",
            difficulty="Beginner",
            minutes=20,
            problem=(
                f"{path} loops over `{collection}` (line {line}) but shows nothing when the list is empty. "
                "A new user sees a blank area and may think the app is broken."
            ),
            why_useful="Empty states are one of the most common small UX improvements in real projects.",
            likely_files=[path] + renderers[:1],
            concepts=["Template loops", "Conditional rendering", "Template variables"],
            success_criteria=[
                "A helpful message appears when the list is empty.",
                "Existing items still render exactly as before.",
                "No unrelated behaviour changes.",
            ],
            hint="Jinja2 lets you add `{% else %}` inside a `{% for %}` loop; it runs when the loop has no items.",
            evidence=[f"{path}:{line}"],
        )
    return None


def _streamlit_input_quest(python_files: dict[str, PythonFileInfo]) -> Quest | None:
    for path, info in sorted(python_files.items()):
        if "streamlit" not in info.top_level_packages:
            continue
        inputs = [c for c in info.calls if c.name.split(".")[-1] in STREAMLIT_INPUT_WIDGETS]
        has_feedback = any(c.name.split(".")[-1] in STREAMLIT_FEEDBACK_CALLS for c in info.calls)
        if not inputs or has_feedback:
            continue
        widget = inputs[0]
        return Quest(
            title=f"Warn the user when the `{widget.name.split('.')[-1]}` input is empty",
            difficulty="Beginner",
            minutes=20,
            problem=(
                f"{path}:{widget.lineno} asks the user for input with `{widget.name}(...)`, but RepoLens "
                "found no warning or error message in this file for missing input."
            ),
            why_useful="Clear feedback on invalid input makes an app feel reliable and is easy to review.",
            likely_files=[path],
            concepts=["Input validation", "Conditional logic", "Streamlit feedback widgets"],
            success_criteria=[
                "Submitting empty input shows a clear warning (e.g. with `st.warning`).",
                "Valid input still works as before.",
                "The app does not crash on empty input.",
            ],
            hint="Check the widget's return value with `if not value:` before using it.",
            evidence=[f"{path}:{widget.lineno}"],
        )
    return None


def _route_validation_quest(python_files: dict[str, PythonFileInfo]) -> Quest | None:
    for path, info in sorted(python_files.items()):
        for route in info.routes:
            reads = [c for c in info.calls
                     if route.lineno <= c.lineno <= route.end_lineno and c.name.startswith(REQUEST_DATA_MARKERS)]
            if not reads:
                continue
            first = reads[0]
            return Quest(
                title=f"Validate user input in `{route.function}()`",
                difficulty="Beginner",
                minutes=30,
                problem=(
                    f"`{route.function}()` in {path} reads user data with `{first.name}(...)` "
                    f"(line {first.lineno}). Check what happens when that value is missing or empty, "
                    "and return a clear error message instead of failing or saving bad data."
                ),
                why_useful="Validating input is a core habit for web developers and prevents confusing bugs.",
                likely_files=[path],
                concepts=["Request data", "Input validation", "Error messages", "HTTP status codes"],
                success_criteria=[
                    "Missing or empty input produces a friendly error message.",
                    "Valid input still behaves exactly as before.",
                    "No unrelated behaviour changes.",
                ],
                hint="Read the value into a variable first, then check it with `if not value:` before using it.",
                evidence=[f"{path}:{route.lineno}-{route.end_lineno}"],
            )
    return None


def _missing_test_quest(insights: dict[str, FileInsight], python_files: dict[str, PythonFileInfo],
                        test_files: dict[str, PythonFileInfo], file_texts: dict[str, str]) -> Quest | None:
    test_source = "\n".join(file_texts.get(p, "") for p in test_files)
    route_names = {r.function for info in python_files.values() for r in info.routes}

    candidates: list[tuple[str, CodeSymbol]] = []
    for path, info in python_files.items():
        insight = insights.get(path)
        if not insight or insight.category not in TESTABLE_CATEGORIES:
            continue
        for fn in info.functions:
            length = fn.end_lineno - fn.lineno + 1
            if (fn.kind == "function" and not fn.name.startswith("_") and fn.name not in route_names
                    and not fn.is_async and MIN_TESTABLE_LINES <= length <= MAX_TESTABLE_LINES
                    and fn.branch_count <= MAX_TESTABLE_BRANCHES and fn.name not in test_source):
                candidates.append((path, fn))
    if not candidates:
        return None

    # Prefer functions with a little logic (a branch or two) but not too much.
    path, fn = min(candidates, key=lambda c: (c[1].branch_count == 0, c[1].branch_count, c[0], c[1].lineno))
    module = basename(path)[: -len(".py")]
    has_tests = bool(test_files)
    test_dir = dirname(next(iter(sorted(test_files)))) if has_tests else "tests"
    test_file = f"{test_dir}/test_{module}.py" if test_dir else f"test_{module}.py"
    title = f"Add {'a missing' if has_tests else 'the first'} unit test for `{fn.name}()`"
    return Quest(
        title=title,
        difficulty="Beginner",
        minutes=30,
        problem=(
            f"`{fn.name}()` in {path} (lines {fn.line_range}) is not mentioned in any test file RepoLens analysed."
            + ("" if has_tests else " The project does not appear to have tests yet.")
        ),
        why_useful="Tests protect behaviour from future changes, and writing one forces you to understand the code.",
        likely_files=[path, f"{test_file} (new file to create)"],
        concepts=["Unit testing", "pytest", "Function inputs and outputs"],
        success_criteria=[
            f"A new test calls `{fn.name}()` with a normal input and checks the result.",
            "If the function has a branch, a second test covers the other case.",
            "`pytest` passes.",
        ],
        hint="Start with the simplest input you can think of and assert on the return value.",
        evidence=[f"{path}:{fn.line_range}"],
    )


def _readme_quest(file_texts: dict[str, str], tree_paths: list[str], entry_points: list[str],
                  framework: FrameworkResult) -> Quest | None:
    readme = next((p for p in tree_paths if basename(p).lower() in README_NAMES and "/" not in p), None)
    entry = entry_points[0] if entry_points else None
    if readme is None:
        return Quest(
            title="Write a short README for this project",
            difficulty="Beginner",
            minutes=30,
            problem="The repository has no README, so newcomers can't tell what it does or how to run it.",
            why_useful="A README is the first thing every contributor reads.",
            likely_files=["README.md (new file to create)"] + ([entry] if entry else []),
            concepts=["Technical writing", "Markdown", "Project setup"],
            success_criteria=[
                "README explains what the project does in 2-3 sentences.",
                "README lists the steps to install dependencies and run the project.",
            ],
            hint=f"Look at {entry} to see how the program starts." if entry else "",
            evidence=[entry] if entry else [],
        )
    text = file_texts.get(readme, "").lower()
    if text and not any(word in text for word in README_RUN_WORDS):
        return Quest(
            title="Add a 'How to run' section to the README",
            difficulty="Beginner",
            minutes=20,
            problem=f"{readme} does not explain how to install or run the project.",
            why_useful="Clear setup steps save every new contributor time.",
            likely_files=[readme] + ([entry] if entry else []),
            concepts=["Technical writing", "Markdown", "Project setup"],
            success_criteria=[
                "README has a section with the exact commands to install dependencies.",
                "README shows the exact command to start the project.",
                "You followed your own steps and they worked.",
            ],
            hint=(f"The project looks like a {framework.name} app; {entry} is the likely entry point."
                  if entry else ""),
            evidence=[readme],
        )
    return None


def _docstring_quest(insights: dict[str, FileInsight], python_files: dict[str, PythonFileInfo],
                     entry_points: list[str]) -> Quest | None:
    ranked = sorted(python_files, key=lambda p: (p not in entry_points, -insights[p].importance if p in insights else 0))
    for path in ranked:
        info = python_files[path]
        undocumented = [sym for sym in info.functions + info.classes
                        if not sym.has_docstring and not sym.name.startswith("_")]
        if not undocumented:
            continue
        fn = max(undocumented, key=lambda sym: (sym.end_lineno - sym.lineno, -sym.lineno))
        return Quest(
            title=f"Document `{fn.display_name}` with a clear docstring",
            difficulty="Beginner",
            minutes=15,
            problem=f"`{fn.display_name}` in {path} (lines {fn.line_range}) has no docstring explaining what it does.",
            why_useful="Good docstrings help the next beginner - and writing one proves you understood the code.",
            likely_files=[path],
            concepts=["Reading code", "Docstrings", "Technical writing"],
            success_criteria=[
                "The docstring says what the code does, what it expects and what it returns or provides.",
                "No code behaviour changes.",
            ],
            hint="Read the code and every place it is used before writing the docstring.",
            evidence=[f"{path}:{fn.line_range}"],
        )
    return None
