"""Ask RepoLens: deterministic, source-cited answers to common beginner questions.

How it works (no LLM, no embeddings, no network):
  1. match_intent()    - a small keyword/phrase matcher maps the question to one
                         of ten supported intents.
  2. an answer builder - reads only facts RepoLens already extracted (parsed
                         imports, routes, entry-point evidence, dependency
                         files, README text...) and cites file + line ranges.
  3. validate_answer() - drops any citation whose file was not analysed or whose
                         line range is outside the file, and downgrades or
                         withholds the answer when evidence disappears.
When there is no evidence, the answer says so instead of guessing.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from models.repo_models import Citation, PythonFileInfo, QAAnswer, QuestionIntent, RepoAnalysis
from services.file_classifier import DATABASE_PACKAGES, UI_PACKAGES, is_test_path
from services.framework_detector import (
    CLI_FRAMEWORK,
    CLI_IMPORTS,
    SIGNATURES,
    UNKNOWN_FRAMEWORK,
    is_dependency_file,
    parse_dependencies,
)
from services.python_analyzer import analyze_python_source
from services.readme_quality import find_readme
from utils.helpers import basename, dirname, human_join, resolve_template_path

HIGH, MEDIUM, LOW, NO_ANSWER = "High", "Medium", "Low", "No reliable answer"
CONFIDENCE_LEVELS = (HIGH, MEDIUM, LOW, NO_ANSWER)

NO_EVIDENCE = "I could not find enough evidence in the analysed repository files to answer this reliably."
UNSUPPORTED = (
    "RepoLens currently supports beginner repository questions about entry points, frameworks, dependencies, "
    "tests, databases, routes, UI files, setup commands, reading order, and code flow."
)

MAX_CITATIONS = 6
MAX_FILES_LISTED = 4

PRESET_QUESTIONS = (
    "Where does the application start?",
    "Which framework does this project use?",
    "Where are dependencies defined?",
    "Where are the tests?",
    "Does this project use a database?",
    "Which file should I read first?",
    "How do I run this project?",
    "Where are API routes defined?",
    "Which file likely creates the user interface?",
    "What is the main code flow?",
)

# ---------------------------------------------------------------------------
# 1. Intent matching
# ---------------------------------------------------------------------------

STRONG, WEAK = 3, 1
FRAMEWORK_NAMES = r"(flask|django|fastapi|streamlit|tkinter|pyqt|pyside|a cli|a script)"

# (intent, pattern, weight). The highest total wins; ties go to the earlier intent in INTENT_PRIORITY.
INTENT_PATTERNS: tuple[tuple[QuestionIntent, str, int], ...] = (
    (QuestionIntent.READ_FIRST, r"\bread(ing)? first\b", STRONG),
    (QuestionIntent.READ_FIRST, r"\bstart reading\b", STRONG),
    (QuestionIntent.READ_FIRST, r"\bfirst file\b", STRONG),
    (QuestionIntent.READ_FIRST, r"\bwhere (should|do|can) (i|we) (begin|start)\b", STRONG),
    (QuestionIntent.READ_FIRST, r"\bwhat should (i|we) read\b", STRONG),
    (QuestionIntent.READ_FIRST, r"\breading (order|path)\b", STRONG),
    (QuestionIntent.READ_FIRST, r"\b(begin|start) with\b", WEAK),

    (QuestionIntent.RUN, r"\bhow (do|can|should|would) (i|we|you) (run|start|launch|execute|install|set ?up|use)\b",
     STRONG),
    (QuestionIntent.RUN, r"\bhow to (run|start|launch|execute|install|set ?up)\b", STRONG),
    (QuestionIntent.RUN, r"\b(run|start|launch|execute) (the |this )?(project|app|application|code|program|server|it)\b",
     STRONG),
    (QuestionIntent.RUN, r"\b(install|installation|setup|run) commands?\b", STRONG),
    (QuestionIntent.RUN, r"\binstall(ation)?\b", WEAK),

    (QuestionIntent.ENTRY_POINT, r"\bentry ?-?points?\b", STRONG),
    (QuestionIntent.ENTRY_POINT, r"\bmain (file|module|script)\b", STRONG),
    (QuestionIntent.ENTRY_POINT, r"\bwhere (does|is|do) (the |this )?(app|application|program|project|code|it|execution)"
                                 r"( \w+)? (start|begin|launch|boot)", STRONG),
    (QuestionIntent.ENTRY_POINT, r"\b(application|app|program) (is )?(started|launched|begins|starts)\b", STRONG),
    (QuestionIntent.ENTRY_POINT, r"\bhow does (the |this )?(app|application|program|project|it) (launch|start|boot)",
     STRONG),
    (QuestionIntent.ENTRY_POINT, r"\bstart(ing)? point\b", STRONG),

    (QuestionIntent.FRAMEWORK, r"\bframeworks?\b", STRONG),
    (QuestionIntent.FRAMEWORK, rf"\b(is|does) (this|it) (use )?(a )?{FRAMEWORK_NAMES}\b", STRONG),
    (QuestionIntent.FRAMEWORK, r"\bbuilt (with|on|using)\b", STRONG),
    (QuestionIntent.FRAMEWORK, r"\btech(nology)? stack\b", STRONG),

    (QuestionIntent.DEPENDENCIES, r"\bdependenc(y|ies)\b", STRONG),
    (QuestionIntent.DEPENDENCIES, r"\brequirements?(\.txt)?\b", STRONG),
    (QuestionIntent.DEPENDENCIES, r"\bpackages?\b", WEAK),
    (QuestionIntent.DEPENDENCIES, r"\blibrar(y|ies)( used)?\b", WEAK),
    (QuestionIntent.DEPENDENCIES, r"\bthird[ -]party\b", WEAK),
    (QuestionIntent.DEPENDENCIES, r"\bpyproject\b", STRONG),

    (QuestionIntent.TESTS, r"\btests?\b", STRONG),
    (QuestionIntent.TESTS, r"\btesting\b", STRONG),
    (QuestionIntent.TESTS, r"\btest files?\b", STRONG),
    (QuestionIntent.TESTS, r"\bpytest\b", STRONG),
    (QuestionIntent.TESTS, r"\bunit ?tests?\b", STRONG),

    (QuestionIntent.DATABASE, r"\bdatabases?\b", STRONG),
    (QuestionIntent.DATABASE, r"\bdb\b", STRONG),
    (QuestionIntent.DATABASE, r"\bsqlalchemy\b", STRONG),
    (QuestionIntent.DATABASE, r"\borm\b", STRONG),
    (QuestionIntent.DATABASE, r"\b(sql|sqlite|postgres\w*|mysql|mongo\w*)\b", STRONG),
    (QuestionIntent.DATABASE, r"\bmodels?\b", WEAK),
    (QuestionIntent.DATABASE, r"\b(store|save|persist)s? data\b", WEAK),

    (QuestionIntent.ROUTES, r"\broutes?\b", STRONG),
    (QuestionIntent.ROUTES, r"\bend ?points?\b", STRONG),
    (QuestionIntent.ROUTES, r"\bapis?\b", WEAK),
    (QuestionIntent.ROUTES, r"\bviews?\b", WEAK),
    (QuestionIntent.ROUTES, r"\b(urls?|http|request handl\w*)\b", WEAK),

    (QuestionIntent.UI, r"\bui\b", STRONG),
    (QuestionIntent.UI, r"\bgui\b", STRONG),
    (QuestionIntent.UI, r"\bfront ?-?end\b", STRONG),
    (QuestionIntent.UI, r"\btemplates?\b", STRONG),
    (QuestionIntent.UI, r"\buser interface\b", STRONG),
    (QuestionIntent.UI, r"\binterface\b", WEAK),
    (QuestionIntent.UI, r"\b(pages?|screens?|widgets?|layout)\b", WEAK),

    (QuestionIntent.CODE_FLOW, r"\bcode flow\b", STRONG),
    (QuestionIntent.CODE_FLOW, r"\b(data|main|execution|control|request) flow\b", STRONG),
    (QuestionIntent.CODE_FLOW, r"\bhow does (it|this|the (app|application|project|code|program)) work\b", STRONG),
    (QuestionIntent.CODE_FLOW, r"\bhow (is|are) .* (connected|wired|organi[sz]ed)\b", STRONG),
    (QuestionIntent.CODE_FLOW, r"\bflow\b", WEAK),
    (QuestionIntent.CODE_FLOW, r"\barchitecture\b", WEAK),
)

INTENT_PRIORITY = (
    QuestionIntent.READ_FIRST, QuestionIntent.RUN, QuestionIntent.ENTRY_POINT, QuestionIntent.FRAMEWORK,
    QuestionIntent.TESTS, QuestionIntent.DATABASE, QuestionIntent.ROUTES, QuestionIntent.UI,
    QuestionIntent.DEPENDENCIES, QuestionIntent.CODE_FLOW,
)
_COMPILED = tuple((intent, re.compile(pattern), weight) for intent, pattern, weight in INTENT_PATTERNS)


def normalize_question(question: str) -> str:
    """Lower-case, trim, and drop punctuation (keeping dots/dashes inside names like `requirements.txt`)."""
    text = (question or "").lower().strip()
    text = re.sub(r"[^\w\s./-]", " ", text)
    text = re.sub(r"(?<!\w)[./-]+|[./-]+(?!\w)", " ", text)  # stray punctuation, not name.ext
    return " ".join(text.split())


def match_intent(question: str) -> QuestionIntent:
    """Map a free-text question to a supported intent, or UNKNOWN."""
    text = normalize_question(question)
    if not text:
        return QuestionIntent.UNKNOWN
    scores: dict[QuestionIntent, int] = {}
    for intent, regex, weight in _COMPILED:
        if regex.search(text):
            scores[intent] = scores.get(intent, 0) + weight
    if not scores:
        return QuestionIntent.UNKNOWN
    best = max(scores.values())
    return next(intent for intent in INTENT_PRIORITY if scores.get(intent) == best)


# ---------------------------------------------------------------------------
# 2. Public entry point
# ---------------------------------------------------------------------------


def answer_question(question: str, analysis: RepoAnalysis) -> QAAnswer:
    """Answer a beginner question using only analysed repository data, with validated citations."""
    intent = match_intent(question)
    if intent is QuestionIntent.UNKNOWN:
        return QAAnswer(question=question, intent=intent, answer=UNSUPPORTED, confidence=NO_ANSWER)
    builder = _BUILDERS[intent]
    try:
        answer = builder(_Facts(analysis, question))
    except Exception:  # a malformed/partial analysis must never crash the UI
        answer = _no_evidence("RepoLens could not read enough of its analysis to answer this.")
    answer.question = question
    answer.intent = intent
    return validate_answer(answer, analysis)


# ---------------------------------------------------------------------------
# 3. Citation validation
# ---------------------------------------------------------------------------


def analysed_line_counts(analysis: RepoAnalysis) -> dict[str, int]:
    """{path: line count} for every file whose contents RepoLens actually analysed."""
    counts = {path: len(text.splitlines()) for path, text in analysis.file_contents.items()}
    for path, info in analysis.python_files.items():
        counts.setdefault(path, info.line_count)
    return {path: count for path, count in counts.items() if count > 0}


def is_valid_citation(citation: Citation, line_counts: dict[str, int]) -> bool:
    count = line_counts.get(citation.path)
    return count is not None and 1 <= citation.start_line <= citation.end_line <= count


def validate_answer(answer: QAAnswer, analysis: RepoAnalysis) -> QAAnswer:
    """Remove unverifiable citations and adjust confidence so the UI never shows invented sources."""
    line_counts = analysed_line_counts(analysis)
    valid: list[Citation] = []
    for citation in answer.citations:
        if is_valid_citation(citation, line_counts) and citation not in valid:
            valid.append(citation)
    removed = len(set(answer.citations)) - len(valid)
    confidence = answer.confidence if answer.confidence in CONFIDENCE_LEVELS else LOW

    if removed and not valid:
        return QAAnswer(
            question=answer.question, intent=answer.intent, answer=NO_EVIDENCE, confidence=NO_ANSWER,
            limitations=f"RepoLens removed {removed} source citation(s) it could not verify against the analysed "
                        "files, so it will not answer this reliably.",
        )

    notes = [answer.limitations] if answer.limitations else []
    if removed:
        notes.append(f"{removed} source citation(s) could not be verified and were removed.")
        if confidence == HIGH:
            confidence = MEDIUM
    if confidence == HIGH and not valid:
        confidence = MEDIUM  # High confidence always needs a verifiable source
    return QAAnswer(question=answer.question, intent=answer.intent, answer=answer.answer, confidence=confidence,
                    citations=valid[:MAX_CITATIONS], limitations=" ".join(notes))


# ---------------------------------------------------------------------------
# Shared evidence helpers
# ---------------------------------------------------------------------------


class _Facts:
    """Read-only helpers over one analysis (line counts, file text, citations)."""

    def __init__(self, analysis: RepoAnalysis, question: str = "") -> None:
        self.analysis = analysis
        self.question = normalize_question(question)
        self.line_counts = analysed_line_counts(analysis)

    def text(self, path: str) -> str:
        return self.analysis.file_contents.get(path, "")

    def lines(self, path: str) -> list[str]:
        return self.text(path).splitlines()

    def whole_file(self, path: str) -> Citation | None:
        count = self.line_counts.get(path)
        return Citation(path, 1, count) if count else None

    def span(self, path: str, line_numbers: list[int]) -> Citation | None:
        numbers = [n for n in line_numbers if n > 0]
        return Citation(path, min(numbers), max(numbers)) if numbers else None

    def category(self, path: str) -> str:
        insight = self.analysis.files.get(path)
        return insight.category if insight else "unknown"

    def dependency_files(self) -> list[str]:
        paths = [p for p in self.analysis.file_contents
                 if is_dependency_file(p) or basename(p).lower() == "setup.py"]
        return sorted(paths, key=lambda p: (p.count("/"), p))

    def package_lines(self, path: str, packages: tuple[str, ...] | list[str] | set[str]) -> list[int]:
        """Line numbers in a dependency file that declare one of `packages`."""
        wanted = {p.lower().replace("_", "-") for p in packages}
        found = []
        for number, line in enumerate(self.lines(path), start=1):
            code = line.split("#", 1)[0].lower().replace("_", "-")
            for name in re.findall(r"[a-z0-9][a-z0-9.-]*", code):
                if name in wanted:
                    found.append(number)
                    break
        return found


def _no_evidence(limitations: str = "") -> QAAnswer:
    return QAAnswer(question="", intent=QuestionIntent.UNKNOWN, answer=NO_EVIDENCE, confidence=NO_ANSWER,
                    limitations=limitations)


def _answer(text: str, confidence: str, citations: list[Citation | None], limitations: str = "") -> QAAnswer:
    return QAAnswer(question="", intent=QuestionIntent.UNKNOWN, answer=text, confidence=confidence,
                    citations=[c for c in citations if c], limitations=limitations)


def _code(path: str) -> str:
    return f"`{path}`"


def _import_lines(info: PythonFileInfo, packages: set[str]) -> list[int]:
    lines = []
    for imp in info.imports:
        if imp.level == 0 and imp.module and (imp.module.split(".")[0] in packages or imp.module in packages):
            lines.append(imp.lineno)
    return lines


def _entry_citation(facts: _Facts, path: str) -> tuple[Citation | None, bool]:
    """(citation, has direct evidence) for an entry point: init call, main guard, or Streamlit script."""
    info = facts.analysis.python_files.get(path)
    if info is None:
        return facts.whole_file(path), False
    lines: list[int] = []
    insight = facts.analysis.files.get(path)
    for reason in insight.entry_reasons if insight else []:
        lines.extend(int(n) for n in re.findall(rf"{re.escape(path)}:(\d+)", reason))
    end = max(lines) if lines else 0
    if info.has_main_guard:
        end = info.line_count  # the guarded block runs from the guard to (at most) the end of the file
    if "streamlit" in info.top_level_packages and info.top_level_statements:
        lines.extend(_import_lines(info, {"streamlit"}))
        end = info.line_count  # Streamlit runs the whole script top to bottom
    if not lines:
        return facts.whole_file(path), False
    return Citation(path, min(lines), max(end, max(lines))), True


# ---------------------------------------------------------------------------
# Answer builders (one per intent)
# ---------------------------------------------------------------------------


def _answer_entry_point(facts: _Facts) -> QAAnswer:
    analysis = facts.analysis
    if not analysis.entry_points:
        return _no_evidence("RepoLens looked for `if __name__ == \"__main__\"` blocks, framework start-up calls "
                            "such as `Flask(...)`, and common entry-point file names, but found no likely entry point.")
    entry = analysis.entry_points[0]
    citation, direct = _entry_citation(facts, entry)
    insight = analysis.files.get(entry)
    reasons = [r[0].lower() + r[1:] for r in (insight.entry_reasons if insight else [])[:3]]
    text = f"The likely application entry point is {_code(entry)}."
    if reasons:
        text += f" Evidence: {'; '.join(reasons)}."
    others = analysis.entry_points[1:3]
    if others:
        text += f" Other possible starting files: {human_join([_code(p) for p in others])}."
    citations = [citation]
    signature = next((s for s in SIGNATURES if s.name == analysis.framework.name), None)
    if signature and signature.packages:
        for dep in facts.dependency_files():
            citations.append(facts.span(dep, facts.package_lines(dep, signature.packages)))
            if citations[-1]:
                break
    confidence = HIGH if direct else MEDIUM
    note = "" if direct else "This is based on the file name and location, not on start-up code RepoLens could see."
    return _answer(text, confidence, citations, note)


def _answer_framework(facts: _Facts) -> QAAnswer:
    framework = facts.analysis.framework
    if framework.name == "Not determined":
        return _no_evidence("RepoLens did not find Python application code to check for a framework.")
    if framework.name == UNKNOWN_FRAMEWORK:
        return _answer(
            "RepoLens did not find a known framework (Flask, Django, FastAPI, Streamlit, Tkinter or PyQt/PySide) in "
            "the analysed dependency files or imports, so this looks like plain Python code.",
            LOW, [], "A framework RepoLens does not know about may still be in use.")

    citations: list[Citation | None] = []
    signature = next((s for s in SIGNATURES if s.name == framework.name), None)
    python_files = facts.analysis.python_files
    if signature:
        for dep in facts.dependency_files():
            citation = facts.span(dep, facts.package_lines(dep, signature.packages))
            if citation:
                citations.append(citation)
                break
        importers = sorted(p for p, info in python_files.items() if info.top_level_packages & set(signature.imports))
        for path in importers[:2]:
            citations.append(facts.span(path, _import_lines(python_files[path], set(signature.imports))))
        for path, info in sorted(python_files.items()):
            calls = [c for name in signature.init_calls for c in info.calls_named(name)]
            if calls:
                citations.append(Citation(path, calls[0].lineno, calls[0].lineno))
                break
    elif framework.name == CLI_FRAMEWORK:
        for path, info in sorted(python_files.items()):
            lines = _import_lines(info, set(CLI_IMPORTS)) + ([info.main_guard_line] if info.has_main_guard else [])
            citations.append(facts.span(path, lines))

    evidence = "; ".join(framework.evidence[:3])
    text = f"RepoLens detected **{framework.name}** ({framework.confidence.lower()} confidence). Evidence: {evidence}."
    text = _yes_no_prefix(facts.question, framework.name, framework.others) + text
    if framework.others:
        text += f" Also found: {', '.join(framework.others)}."
    confidence = framework.confidence if any(citations) else LOW
    return _answer(text, confidence, citations[:MAX_CITATIONS])


ASKED_FRAMEWORKS = {"flask": "Flask", "django": "Django", "fastapi": "FastAPI", "streamlit": "Streamlit",
                    "tkinter": "Tkinter", "pyqt": "PySide / PyQt", "pyside": "PySide / PyQt"}


def _yes_no_prefix(question: str, detected: str, others: list[str]) -> str:
    """Answer "is this Django?"-style questions directly before giving the evidence."""
    asked = [name for word, name in ASKED_FRAMEWORKS.items() if re.search(rf"\b{word}\b", question)]
    if not asked:
        return ""
    name = asked[0]
    if name == detected:
        return "Yes. "
    if name in others:
        return f"{name} was also found, but it is not the main framework. "
    return f"RepoLens found no evidence of {name}. "


def _answer_dependencies(facts: _Facts) -> QAAnswer:
    dep_files = facts.dependency_files()
    if not dep_files:
        return _no_evidence("RepoLens looked for requirements*.txt, pyproject.toml, setup.py, setup.cfg and Pipfile "
                            "but none were analysed.")
    parts, citations = [], []
    for path in dep_files[:MAX_FILES_LISTED]:
        packages = parse_dependencies(path, facts.text(path))
        if basename(path).lower() == "setup.py":
            lines = [n for n, line in enumerate(facts.lines(path), 1) if "install_requires" in line]
            citations.append(facts.span(path, lines) or facts.whole_file(path))
            parts.append(f"{_code(path)} (package setup script)")
            continue
        citations.append(facts.span(path, facts.package_lines(path, packages)) or facts.whole_file(path))
        if packages:
            shown = human_join([f"`{p}`" for p in packages[:5]], limit=5)
            parts.append(f"{_code(path)} ({len(packages)} package(s), e.g. {shown})")
        else:
            parts.append(f"{_code(path)} (no packages could be parsed)")
    text = "Dependencies are defined in " + human_join(parts, limit=MAX_FILES_LISTED) + "."
    return _answer(text, HIGH, citations)


def _answer_tests(facts: _Facts) -> QAAnswer:
    analysis = facts.analysis
    tree_tests = sorted(p for p in analysis.tree_paths if p.endswith(".py") and is_test_path(p))
    if not tree_tests:
        return _no_evidence("RepoLens looked for `tests/` folders and `test_*.py` / `*_test.py` files and found none.")

    citations, described = [], []
    downloaded = [p for p in tree_tests if p in analysis.file_contents]
    for path in downloaded:
        if len(citations) >= MAX_FILES_LISTED:
            break
        info = analyze_python_source(path, analysis.file_contents[path])
        tests = [fn for fn in info.functions if fn.name.startswith("test")]
        if tests:
            citations.append(Citation(path, min(t.lineno for t in tests), max(t.end_lineno for t in tests)))
            described.append(f"{_code(path)} ({len(tests)} test function(s))")
    folders = sorted({dirname(p) + "/" for p in tree_tests if dirname(p)})
    where = f" in {human_join([_code(f) for f in folders])}" if folders else ""
    text = f"RepoLens found {len(tree_tests)} test file(s){where}."
    if described:
        text += " For example: " + human_join(described) + "."
    runner = "pytest" if "pytest" in analysis.dependencies else ""
    if runner:
        text += " `pytest` is listed as a dependency, so the tests likely run with pytest."
    if citations:
        return _answer(text, HIGH, citations)
    if downloaded:
        return _answer(text, LOW, [facts.whole_file(p) for p in downloaded[:MAX_FILES_LISTED]],
                       "These files are named like tests, but RepoLens found no `test...` functions in them yet.")
    return _answer(text, MEDIUM, [], "The test files were not downloaded for analysis, so RepoLens cannot cite lines.")


DATABASE_IMPORTS = set(DATABASE_PACKAGES) | {
    "flask_sqlalchemy", "sqlmodel", "mongoengine", "asyncpg", "aiosqlite", "pymysql", "databases", "redis",
    "alembic", "django.db",
}
ORM_IMPORTS = {"sqlalchemy", "flask_sqlalchemy", "sqlmodel", "peewee", "tortoise", "mongoengine", "django.db"}
DATABASE_DEPENDENCIES = {
    "sqlalchemy", "flask-sqlalchemy", "sqlmodel", "pymongo", "psycopg2", "psycopg2-binary", "psycopg", "mysqlclient",
    "pymysql", "peewee", "tortoise-orm", "motor", "mongoengine", "asyncpg", "aiosqlite", "databases", "redis",
    "alembic",
}
DATABASE_DISPLAY = {
    "sqlalchemy": "SQLAlchemy", "flask_sqlalchemy": "Flask-SQLAlchemy", "sqlmodel": "SQLModel", "sqlite3": "sqlite3",
    "pymongo": "PyMongo", "django.db": "the Django ORM", "peewee": "Peewee", "tortoise": "Tortoise ORM",
    "mongoengine": "MongoEngine", "psycopg2": "psycopg2", "psycopg": "psycopg", "redis": "Redis",
}


def _database_module(module: str) -> str | None:
    if module.startswith("django.db"):
        return "django.db"
    top = module.split(".")[0]
    return top if top in DATABASE_IMPORTS else None


def _answer_database(facts: _Facts) -> QAAnswer:
    found: dict[str, list[int]] = {}  # path -> import lines
    libraries: list[str] = []
    for path, info in sorted(facts.analysis.python_files.items()):
        for imp in info.imports:
            library = _database_module(imp.module) if imp.level == 0 and imp.module else None
            if library:
                found.setdefault(path, []).append(imp.lineno)
                if library not in libraries:
                    libraries.append(library)

    dep_citations = []
    for dep in facts.dependency_files():
        dep_citations.append(facts.span(dep, facts.package_lines(dep, DATABASE_DEPENDENCIES)))

    if found:
        files = list(found)[:MAX_FILES_LISTED]
        names = human_join([DATABASE_DISPLAY.get(lib, lib) for lib in libraries])
        uses_orm = any(lib in ORM_IMPORTS for lib in libraries)
        how = "through an ORM (Object-Relational Mapper)" if uses_orm else "directly"
        text = (f"RepoLens found {names} imports in {human_join([_code(f) for f in files])}, which suggests this "
                f"project uses a database {how}.")
        citations = [facts.span(path, lines) for path, lines in found.items()][:MAX_FILES_LISTED] + dep_citations
        return _answer(text, HIGH, citations)

    if any(dep_citations):
        text = ("A database library is listed in the dependency files, but RepoLens did not find it imported in the "
                "analysed Python code.")
        return _answer(text, MEDIUM, dep_citations, "The library may be used in files RepoLens did not analyse.")
    return _no_evidence("RepoLens looked for database libraries such as SQLAlchemy, sqlite3, Django's ORM, PyMongo "
                        "and psycopg in the analysed imports and dependency files.")


def _answer_routes(facts: _Facts) -> QAAnswer:
    python_files = facts.analysis.python_files
    decorated = sorted((p for p, info in python_files.items() if info.routes),
                       key=lambda p: (-len(python_files[p].routes), p))
    if decorated:
        files = decorated[:MAX_FILES_LISTED]
        citations = [Citation(p, min(r.lineno for r in python_files[p].routes),
                              max(r.end_lineno for r in python_files[p].routes)) for p in files]
        example = python_files[files[0]].routes[0]
        total = sum(len(python_files[p].routes) for p in decorated)
        text = (f"RepoLens found {total} route decorator(s) in {human_join([_code(p) for p in decorated])}. These files "
                f"likely define the HTTP endpoints. For example, `@{example.decorator}` registers `{example.function}()`.")
        return _answer(text, HIGH, citations)

    url_files = []
    for path, info in sorted(python_files.items()):
        if facts.category(path) == "routes":
            calls = info.calls_named("path") + info.calls_named("re_path") + info.calls_named("url")
            url_files.append((path, facts.span(path, [c.lineno for c in calls])))
    with_calls = [(p, c) for p, c in url_files if c]
    if with_calls:
        text = (f"RepoLens found URL patterns (`path(...)` calls) in {human_join([_code(p) for p, _ in with_calls])}. "
                "This is where the application maps URLs to view functions.")
        return _answer(text, HIGH, [c for _, c in with_calls[:MAX_FILES_LISTED]])
    if url_files:
        paths = [p for p, _ in url_files[:MAX_FILES_LISTED]]
        text = (f"RepoLens found no route decorators, but {human_join([_code(p) for p in paths])} "
                "are named like request-handling files (e.g. views/routes/api).")
        return _answer(text, MEDIUM, [facts.whole_file(p) for p in paths],
                       "This is based on file names, not on parsed route definitions.")
    return _no_evidence("RepoLens looked for route decorators such as `@app.route`, `@router.get` and Django URL "
                        "patterns.")


UI_DISPLAY = {"streamlit": "Streamlit", "tkinter": "Tkinter", "PyQt5": "PyQt5", "PyQt6": "PyQt6",
              "PySide2": "PySide2", "PySide6": "PySide6", "kivy": "Kivy", "pygame": "pygame"}


def _answer_ui(facts: _Facts) -> QAAnswer:
    analysis = facts.analysis
    citations: list[Citation | None] = []
    sentences: list[str] = []

    for path, info in sorted(analysis.python_files.items()):
        packages = sorted(info.top_level_packages & UI_PACKAGES)
        if not packages or len(citations) >= MAX_FILES_LISTED:
            continue
        start = _import_lines(info, set(packages))
        if packages == ["streamlit"]:
            ui_calls = [c.lineno for c in info.calls if c.name.startswith(("st.", "streamlit."))]
            end = max(ui_calls) if ui_calls else max(start)
            detail = f"calls {len(ui_calls)} Streamlit function(s) such as `st.*`" if ui_calls else "imports Streamlit"
        else:
            end = info.line_count
            detail = f"imports {human_join([UI_DISPLAY.get(p, p) for p in packages])}"
        citations.append(Citation(path, min(start), max(end, min(start))))
        sentences.append(f"{_code(path)} {detail}")

    rendered: list[tuple[str, str, int]] = []  # (template, referenced by, line that names it)
    for path in sorted(analysis.python_files):
        for ref in _template_refs(facts, path):
            template = resolve_template_path(ref, analysis.tree_paths)
            if template and template in facts.line_counts and template not in {t for t, _, _ in rendered}:
                line = next((n for n, text in enumerate(facts.lines(path), 1) if ref in text), 0)
                rendered.append((template, path, line))
    for template, renderer, line in rendered[:MAX_FILES_LISTED]:
        citations.append(facts.whole_file(template))
        if line:
            citations.append(Citation(renderer, line, line))
    if rendered:
        templates = human_join([_code(t) for t, _, _ in rendered])
        sentences.append(f"the page template(s) {templates} are rendered by the Python code")

    if sentences:
        text = "RepoLens found user-interface code: " + "; ".join(sentences) + "."
        return _answer(text, HIGH, citations)

    named = sorted((p for p, insight in analysis.files.items()
                    if insight.category in ("ui", "template") and p in facts.line_counts),
                   key=lambda p: (facts.category(p) != "template", p))[:MAX_FILES_LISTED]
    if named:
        text = (f"{human_join([_code(p) for p in named])} look like user-interface files based on their names or "
                "location (e.g. `templates/`, `ui/`, `pages/`).")
        return _answer(text, MEDIUM, [facts.whole_file(p) for p in named],
                       "RepoLens did not find code that renders or imports these files.")
    return _no_evidence("RepoLens looked for Streamlit/Tkinter/PyQt imports, rendered templates and UI-named files.")


TEMPLATE_NAME_ASSIGNMENT = re.compile(r"""\btemplate_name\s*=\s*["']([^"']+\.(?:html|htm|jinja2?|j2|txt))["']""")


def _template_refs(facts: _Facts, path: str) -> list[str]:
    """Templates named in render calls (parsed by the AST analyzer) or Django `template_name = "..."`."""
    info = facts.analysis.python_files[path]
    return list(dict.fromkeys(info.template_refs + TEMPLATE_NAME_ASSIGNMENT.findall(facts.text(path))))


SETUP_COMMAND = re.compile(
    r"(?<![\w/.-])(python3? -m pip install\b|pip3? install\b|python3? -m venv\b|poetry install\b|pipenv install\b"
    r"|uv (sync|pip install)\b|conda (env create|create|install)\b|git clone \S+|cp \.env\.example \.env"
    r"|python3? manage\.py (migrate|makemigrations|createsuperuser)\b|flask (--app \S+ )?db upgrade\b)",
    re.IGNORECASE,
)
RUN_COMMAND = re.compile(
    r"(?<![\w/.-])(streamlit run \S+|python3? -m (?!venv\b|pip\b|pytest\b|unittest\b)[\w.]+|python3? [\w./-]+\.py"
    r"|flask (--app \S+ )?run\b|uvicorn \S+|gunicorn \S+|hypercorn \S+|fastapi (dev|run)\b"
    r"|docker(-| )compose up\b|make run\b|(poetry|pipenv|uv) run (?!pytest\b)\S+)",
    re.IGNORECASE,
)
TEST_WORDS = re.compile(r"\b(pytest|unittest|tox|nox|test)\b", re.IGNORECASE)


def _extract_command(line: str, match: re.Match, in_fence: bool) -> str:
    """The exact command text as written, without prompts, comments or surrounding prose."""
    for span in re.finditer(r"`([^`]+)`", line):
        if span.start() <= match.start() < span.end():
            return span.group(1).strip()
    stripped = line.strip().lstrip("$>").strip()
    if in_fence or stripped.lower().startswith(match.group(0).lower()):
        command = line[match.start():].split(" #")[0]
        return command.strip().rstrip(".,;:")
    return match.group(0).strip().rstrip(".,;:")


def _find_commands(facts: _Facts) -> tuple[list[tuple[str, int, str]], list[tuple[str, int, str]]]:
    """(setup commands, run commands) as (path, line, command), from README and other analysed docs."""
    readme, _ = find_readme(facts.analysis.file_contents)
    docs = [readme] if readme else []
    docs += sorted(p for p in facts.analysis.file_contents
                   if p != readme and p.lower().endswith((".md", ".rst")) and facts.category(p) == "documentation")
    setup: list[tuple[str, int, str]] = []
    run: list[tuple[str, int, str]] = []
    for path in docs:
        in_fence = False
        for number, line in enumerate(facts.lines(path), start=1):
            if re.match(r"^\s*(```|~~~)", line):
                in_fence = not in_fence
                continue
            if match := SETUP_COMMAND.search(line):
                setup.append((path, number, _extract_command(line, match, in_fence)))
            elif (match := RUN_COMMAND.search(line)) and not TEST_WORDS.search(match.group(0)):
                command = _extract_command(line, match, in_fence)
                if not TEST_WORDS.search(command):
                    run.append((path, number, command))
    return _unique(setup), _unique(run)


def _unique(commands: list[tuple[str, int, str]]) -> list[tuple[str, int, str]]:
    seen: set[str] = set()
    kept = []
    for item in commands:
        if item[2] not in seen:
            seen.add(item[2])
            kept.append(item)
    return kept


def _answer_run(facts: _Facts) -> QAAnswer:
    setup, run = _find_commands(facts)
    if not setup and not run:
        return _no_evidence("RepoLens only reports run and setup commands that are written in the analysed README or "
                            "documentation, and it found none. It does not guess commands.")
    parts = []
    if setup:
        parts.append("Setup commands found: " + ", ".join(f"`{cmd}`" for _, _, cmd in setup[:3]) + ".")
    if run:
        parts.append("Run command(s) found: " + ", ".join(f"`{cmd}`" for _, _, cmd in run[:3]) + ".")
    text = "According to the project's documentation: " + " ".join(parts)
    citations = [Citation(path, line, line) for path, line, _ in (setup[:3] + run[:3])]
    if run:
        return _answer(text, HIGH, citations, "Commands are quoted from the documentation; RepoLens did not run them.")
    return _answer(text, MEDIUM, citations, "No explicit command to start the application was found in the "
                                            "documentation.")


def _answer_read_first(facts: _Facts) -> QAAnswer:
    plan = facts.analysis.first_30_minutes
    paths = [s.path for s in plan.steps] if plan and plan.steps else [s.path for s in facts.analysis.learning_path]
    if not paths:
        return _no_evidence("RepoLens could not build a reading order from the analysed files.")
    shown = paths[:3]
    text = f"Start with {_code(shown[0])}"
    if len(shown) > 1:
        text += ", then " + human_join([_code(p) for p in shown[1:]])
    text += ". This follows RepoLens's First 30 Minutes plan (README → dependencies → entry point → core logic)."
    citations = []
    for path in shown:
        if path in facts.analysis.entry_points[:1]:
            citations.append(_entry_citation(facts, path)[0])
        else:
            citations.append(facts.whole_file(path))
    has_entry = bool(set(shown) & set(facts.analysis.entry_points[:1]))
    confidence = HIGH if has_entry and len(paths) >= 2 else MEDIUM if len(paths) >= 2 else LOW
    return _answer(text, confidence, citations)


def _answer_code_flow(facts: _Facts) -> QAAnswer:
    flow = facts.analysis.flow
    with_paths = [step for step in flow if step.path]
    if not with_paths:
        return _no_evidence("RepoLens builds the flow only from imports, route decorators and render calls it can "
                            "see, and found too few of them.")
    arrows = []
    for step in flow:
        arrows.append(f"{step.label} ({_code(step.path)})" if step.path else step.label)
    text = "Main code flow found by RepoLens: " + " → ".join(arrows) + "."
    citations = []
    python_files = facts.analysis.python_files
    for step in with_paths:
        info = python_files.get(step.path)
        if step.path in facts.analysis.entry_points[:1]:
            citations.append(_entry_citation(facts, step.path)[0])
        elif info and info.routes:
            citations.append(Citation(step.path, min(r.lineno for r in info.routes),
                                      max(r.end_lineno for r in info.routes)))
        else:
            citations.append(facts.whole_file(step.path))
    confidence = HIGH if len(with_paths) >= 2 else MEDIUM
    return _answer(text, confidence, citations, "The flow is based on static analysis; the code was not executed.")


_BUILDERS: dict[QuestionIntent, Callable[[_Facts], QAAnswer]] = {
    QuestionIntent.ENTRY_POINT: _answer_entry_point,
    QuestionIntent.FRAMEWORK: _answer_framework,
    QuestionIntent.DEPENDENCIES: _answer_dependencies,
    QuestionIntent.TESTS: _answer_tests,
    QuestionIntent.DATABASE: _answer_database,
    QuestionIntent.READ_FIRST: _answer_read_first,
    QuestionIntent.RUN: _answer_run,
    QuestionIntent.ROUTES: _answer_routes,
    QuestionIntent.UI: _answer_ui,
    QuestionIntent.CODE_FLOW: _answer_code_flow,
}
