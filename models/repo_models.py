"""Plain data containers shared by every part of RepoLens.

Dataclasses are used (instead of dicts) so that each piece of analysis has a
clear, documented shape. They are also picklable, which lets Streamlit cache
them between reruns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Raw repository data (what we fetched from GitHub)
# ---------------------------------------------------------------------------


@dataclass
class RepoMetadata:
    owner: str
    name: str
    full_name: str
    description: str
    stars: int
    language: str
    default_branch: str
    html_url: str


@dataclass
class TreeEntry:
    """One file in the repository tree (directories are not stored)."""

    path: str
    size: int


@dataclass
class RepoSnapshot:
    """Everything RepoLens downloaded. The analyzer works only from this.

    Keeping downloads separate from analysis means the analysis can be unit
    tested with a hand-written snapshot and no network access.
    """

    metadata: RepoMetadata
    tree: list[TreeEntry]
    files: dict[str, str]  # path -> text content (only files we downloaded)
    tree_truncated: bool = False
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Python AST analysis
# ---------------------------------------------------------------------------


@dataclass
class ImportInfo:
    module: str  # "flask", "app.routes", "" for `from . import x`
    names: list[str]  # names imported with `from x import a, b`
    level: int  # 0 = absolute import, 1 = `from .`, 2 = `from ..`
    lineno: int


@dataclass
class CodeSymbol:
    """A top-level function, class, or a method inside a class."""

    name: str
    kind: str  # "function" | "class" | "method"
    lineno: int
    end_lineno: int
    decorators: list[str] = field(default_factory=list)
    is_async: bool = False
    branch_count: int = 0
    parent: str = ""  # class name for methods
    bases: list[str] = field(default_factory=list)  # base classes (classes only)
    has_docstring: bool = False

    @property
    def line_range(self) -> str:
        return f"{self.lineno}-{self.end_lineno}"

    @property
    def display_name(self) -> str:
        if self.kind == "class":
            return self.name
        prefix = f"{self.parent}." if self.parent else ""
        return f"{prefix}{self.name}()"


@dataclass
class RouteInfo:
    """A function registered as a web route, e.g. `@app.route("/")`."""

    function: str
    decorator: str
    lineno: int
    end_lineno: int


@dataclass
class CallSite:
    name: str  # dotted call name, e.g. "Flask", "st.title", "db.session.add"
    lineno: int


@dataclass
class PythonFileInfo:
    path: str
    line_count: int
    imports: list[ImportInfo] = field(default_factory=list)
    functions: list[CodeSymbol] = field(default_factory=list)  # incl. methods
    classes: list[CodeSymbol] = field(default_factory=list)
    calls: list[CallSite] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    routes: list[RouteInfo] = field(default_factory=list)
    template_refs: list[str] = field(default_factory=list)  # render_template("x.html")
    branch_count: int = 0
    max_nesting: int = 0
    has_main_guard: bool = False
    main_guard_line: int = 0
    top_level_statements: int = 0  # executable statements outside defs/imports
    syntax_error: str = ""

    @property
    def imported_modules(self) -> set[str]:
        return {imp.module for imp in self.imports if imp.module}

    @property
    def top_level_packages(self) -> set[str]:
        """First segment of every absolute import: `flask.views` -> `flask`."""
        return {imp.module.split(".")[0] for imp in self.imports if imp.module and imp.level == 0}

    def calls_named(self, name: str) -> list[CallSite]:
        """Calls whose last dotted segment equals `name` (`x.Flask` matches `Flask`)."""
        return [c for c in self.calls if c.name.split(".")[-1] == name]


# ---------------------------------------------------------------------------
# Derived insights
# ---------------------------------------------------------------------------


@dataclass
class FrameworkResult:
    name: str
    confidence: str  # "High" | "Medium" | "Low"
    evidence: list[str]
    others: list[str] = field(default_factory=list)  # other frameworks also seen


@dataclass
class FileInsight:
    """Per-file scores. Importance and difficulty are deliberately separate."""

    path: str
    category: str
    line_count: int = 0
    difficulty: int = 0
    difficulty_reasons: list[str] = field(default_factory=list)
    importance: int = 0
    importance_reasons: list[str] = field(default_factory=list)
    entry_score: int = 0
    entry_reasons: list[str] = field(default_factory=list)


@dataclass
class LearningStep:
    number: int
    path: str
    why: str
    difficulty_label: str
    difficulty_score: int
    minutes: int
    relevant_code: list[str] = field(default_factory=list)  # "create_app() (lines 5-20)"
    prerequisites: list[int] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)  # citations like "app.py:5"


@dataclass
class FlowStep:
    label: str
    path: str = ""
    detail: str = ""


@dataclass
class SkipItem:
    path: str  # a file or a directory ending with "/"
    reason: str
    file_count: int = 1


@dataclass
class Quest:
    title: str
    difficulty: str
    minutes: int
    problem: str
    why_useful: str
    likely_files: list[str]
    concepts: list[str]
    success_criteria: list[str]
    hint: str = ""
    evidence: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# First 30 Minutes mode
# ---------------------------------------------------------------------------


@dataclass
class FirstThirtyStep:
    """One file in the short "first 30 minutes" reading plan."""

    number: int
    path: str
    category: str
    minutes: int
    difficulty_label: str  # "Beginner" | "Intermediate" | "Advanced"
    why: str
    look_for: str
    outcome: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class FirstThirtyPlan:
    steps: list[FirstThirtyStep]
    total_minutes: int
    outcomes: list[str]  # "What you should understand after 30 minutes"
    is_limited: bool = False  # too little source material for a full plan


# ---------------------------------------------------------------------------
# README quality
# ---------------------------------------------------------------------------


@dataclass
class ReadmeCheck:
    """One rubric line of the README Onboarding Score."""

    key: str
    label: str
    max_points: int
    points: int = 0
    evidence: list[str] = field(default_factory=list)  # headings / snippets that earned the points
    suggestion: str = ""  # what to add when the check fails

    @property
    def passed(self) -> bool:
        return self.points > 0


@dataclass
class ReadmeQuality:
    path: str | None
    score: int  # 0-100, heuristic
    label: str  # "Needs major improvement" | "Basic onboarding" | "Good onboarding" | "Excellent onboarding"
    interpretation: str
    checks: list[ReadmeCheck]
    notes: list[str] = field(default_factory=list)

    @property
    def strengths(self) -> list[ReadmeCheck]:
        return [check for check in self.checks if check.passed]

    @property
    def missing(self) -> list[ReadmeCheck]:
        return [check for check in self.checks if not check.passed]


# ---------------------------------------------------------------------------
# Ask RepoLens (deterministic Q&A)
# ---------------------------------------------------------------------------


class QuestionIntent(str, Enum):
    ENTRY_POINT = "entry_point"
    FRAMEWORK = "framework"
    DEPENDENCIES = "dependencies"
    TESTS = "tests"
    DATABASE = "database"
    READ_FIRST = "read_first"
    RUN = "run"
    ROUTES = "routes"
    UI = "ui"
    CODE_FLOW = "code_flow"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Citation:
    """A file and an inclusive 1-based line range in the analysed repository."""

    path: str
    start_line: int
    end_line: int

    @property
    def display(self) -> str:
        if self.start_line == self.end_line:
            return f"`{self.path}` (line {self.start_line})"
        return f"`{self.path}` (lines {self.start_line}–{self.end_line})"


@dataclass
class QAAnswer:
    question: str
    intent: QuestionIntent
    answer: str
    confidence: str  # "High" | "Medium" | "Low" | "No reliable answer"
    citations: list[Citation] = field(default_factory=list)
    limitations: str = ""


@dataclass
class RepoAnalysis:
    metadata: RepoMetadata
    framework: FrameworkResult
    dependencies: list[str]
    files: dict[str, FileInsight]  # every file RepoLens scored
    python_files: dict[str, PythonFileInfo]
    entry_points: list[str]  # most likely first
    import_graph: dict[str, list[str]]  # file -> internal files it imports
    learning_path: list[LearningStep]
    flow: list[FlowStep]
    confusion_map: dict[str, list[str]]  # "Easy" | "Moderate" | "Advanced" -> paths
    skip_for_now: list[SkipItem]
    quest: Quest | None
    estimated_minutes: int
    notes: list[str] = field(default_factory=list)  # e.g. "tree truncated"
    tree_paths: list[str] = field(default_factory=list)
    file_contents: dict[str, str] = field(default_factory=dict)  # downloaded text files (README, configs, code)
    readme_quality: ReadmeQuality | None = None
    first_30_minutes: FirstThirtyPlan | None = None

    def importers_of(self, path: str) -> list[str]:
        """Internal files that import `path` (useful for a future impact simulator)."""
        return sorted(src for src, targets in self.import_graph.items() if path in targets)
