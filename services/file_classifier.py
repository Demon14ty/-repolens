"""Put each file into one beginner-friendly category using simple, readable rules.

Rules are checked in order; the first match wins. Path-based rules come first
because they are the most reliable; AST-based rules refine Python files.
"""

from __future__ import annotations

from models.repo_models import PythonFileInfo
from services.framework_detector import is_dependency_file
from utils.helpers import basename, path_parts

CATEGORIES = (
    "documentation", "entry_point", "configuration", "dependency", "core_logic",
    "routes", "models", "database", "ui", "template", "test", "utility",
    "deployment", "unknown",
)

DOC_EXTENSIONS = (".md", ".rst", ".txt")
DOC_NAMES = ("readme", "changelog", "contributing", "license", "authors", "code_of_conduct", "history")
DOC_DIRS = {"docs", "doc"}

DEPLOYMENT_NAMES = {
    "dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
    "procfile", ".gitlab-ci.yml", "jenkinsfile", "vercel.json", "fly.toml", "app.yaml",
    "netlify.toml", "render.yaml", ".dockerignore", "runtime.txt",
}
DEPLOYMENT_DIRS = {".github", ".circleci", "deploy", "deployment", "k8s", "kubernetes", "helm", "terraform"}

TEST_DIRS = {"tests", "test", "testing"}
TEMPLATE_DIRS = {"templates", "template"}
TEMPLATE_EXTENSIONS = (".html", ".htm", ".jinja", ".jinja2", ".j2")
STATIC_EXTENSIONS = (".css", ".js", ".scss")
MIGRATION_DIRS = {"migrations", "alembic"}

CONFIG_EXTENSIONS = (".ini", ".cfg", ".toml", ".yaml", ".yml", ".json", ".conf")
CONFIG_NAMES = {"settings.py", "config.py", "conf.py", "configuration.py", ".env.example", "makefile"}

# Keyword -> category for Python file/directory names.
ROUTE_WORDS = ("route", "view", "endpoint", "api", "controller", "handler", "urls")
MODEL_WORDS = ("model", "schema", "entity", "entities")
DATABASE_WORDS = ("database", "db", "repository", "repositories", "crud", "dao", "storage", "sql")
UI_WORDS = ("ui", "gui", "widget", "window", "page", "component", "screen", "form", "frontend", "dialog")
UTILITY_WORDS = ("util", "utils", "helper", "helpers", "common", "tools", "lib", "misc")

DATABASE_PACKAGES = {"sqlalchemy", "sqlite3", "pymongo", "psycopg2", "psycopg", "mysql", "peewee", "tortoise", "motor"}
UI_PACKAGES = {"tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "streamlit", "kivy", "pygame"}
MODEL_BASES = {"Model", "Base", "BaseModel", "db.Model", "models.Model", "SQLModel", "DeclarativeBase"}


def classify_file(path: str, info: PythonFileInfo | None = None, is_entry_point: bool = False) -> str:
    """Return one of CATEGORIES for `path`."""
    parts = [p.lower() for p in path_parts(path)]
    name = basename(path).lower()
    dirs = set(parts[:-1])

    if dirs & DEPLOYMENT_DIRS or name in DEPLOYMENT_NAMES or name.startswith("dockerfile"):
        return "deployment"
    if is_dependency_file(path) or name in {"setup.py", "pipfile.lock", "poetry.lock", "environment.yml"}:
        return "dependency"
    if is_test_path(path):
        return "test"
    if name.startswith(DOC_NAMES) or (dirs & DOC_DIRS and name.endswith(DOC_EXTENSIONS)) or name.endswith((".md", ".rst")):
        return "documentation"
    if name.endswith(TEMPLATE_EXTENSIONS) or (dirs & TEMPLATE_DIRS and not name.endswith(".py")):
        return "template"
    if name.endswith(STATIC_EXTENSIONS):
        return "ui"
    if dirs & MIGRATION_DIRS:
        return "database"
    if name in CONFIG_NAMES or (name.endswith(CONFIG_EXTENSIONS) and not name.endswith(".py")):
        return "configuration"
    if name.endswith(".py"):
        return _classify_python(parts, info, is_entry_point)
    return "unknown"


def is_test_path(path: str) -> bool:
    name = basename(path).lower()
    dirs = {p.lower() for p in path_parts(path)[:-1]}
    return (
        bool(dirs & TEST_DIRS)
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name in {"conftest.py", "tests.py", "test.py"}
    )


def _classify_python(parts: list[str], info: PythonFileInfo | None, is_entry_point: bool) -> str:
    if is_entry_point:
        return "entry_point"

    # Split names like "task_routes" into words so "routes" matches "route".
    stem = parts[-1][: -len(".py")]
    words = {w for part in parts[:-1] + [stem] for w in part.replace("-", "_").split("_") if w}

    def mentions(keywords: tuple[str, ...]) -> bool:
        return any(kw in words or f"{kw}s" in words for kw in keywords)

    # Name-based rules first (most reliable), then rules based on file contents.
    if (info and info.routes) or mentions(ROUTE_WORDS):
        return "routes"
    for keywords, category in (
        (MODEL_WORDS, "models"), (DATABASE_WORDS, "database"), (UI_WORDS, "ui"), (UTILITY_WORDS, "utility"),
    ):
        if mentions(keywords):
            return category
    if info and _has_model_base(info):
        return "models"
    if info and info.top_level_packages & DATABASE_PACKAGES:
        return "database"
    if info and info.top_level_packages & UI_PACKAGES:
        return "ui"
    if info and (info.functions or info.classes):
        return "core_logic"
    return "unknown"


def _has_model_base(info: PythonFileInfo) -> bool:
    return any(base in MODEL_BASES for cls in info.classes for base in cls.bases)
