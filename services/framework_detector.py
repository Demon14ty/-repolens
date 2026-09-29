"""Detect the Python framework a repository uses, with evidence.

Evidence comes from three places, each worth a fixed number of points:
  dependency files (requirements.txt, pyproject.toml, Pipfile)
  imports found by the AST analyzer
  framework initialisation calls such as Flask(...)
A framework is only reported when at least one piece of evidence exists.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass

from models.repo_models import FrameworkResult, PythonFileInfo
from utils.helpers import basename

DEPENDENCY_POINTS = 3
FIRST_IMPORT_POINTS = 2
EXTRA_IMPORT_POINTS = 1
MAX_EXTRA_IMPORT_POINTS = 3
INIT_CALL_POINTS = 3
HIGH_CONFIDENCE_POINTS = 6
MEDIUM_CONFIDENCE_POINTS = 3

UNKNOWN_FRAMEWORK = "Plain Python (no framework detected)"
CLI_FRAMEWORK = "Python CLI / script"


@dataclass(frozen=True)
class FrameworkSignature:
    name: str
    packages: tuple[str, ...]  # names as they appear in dependency files
    imports: tuple[str, ...]  # top-level import names
    init_calls: tuple[str, ...]  # calls that create/start the framework app


SIGNATURES = (
    FrameworkSignature("Flask", ("flask",), ("flask",), ("Flask",)),
    FrameworkSignature("FastAPI", ("fastapi",), ("fastapi",), ("FastAPI",)),
    FrameworkSignature(
        "Django", ("django",), ("django",), ("execute_from_command_line", "get_wsgi_application", "get_asgi_application")
    ),
    FrameworkSignature("Streamlit", ("streamlit",), ("streamlit",), ()),
    FrameworkSignature("Tkinter", (), ("tkinter", "Tkinter"), ("Tk",)),
    FrameworkSignature(
        "PySide / PyQt",
        ("pyside6", "pyside2", "pyqt5", "pyqt6"),
        ("PySide6", "PySide2", "PyQt5", "PyQt6"),
        ("QApplication",),
    ),
)
CLI_IMPORTS = ("argparse", "click", "typer", "fire")
CLI_PACKAGES = ("click", "typer", "fire")

DEPENDENCY_FILENAMES = {"requirements.txt", "requirements-dev.txt", "pyproject.toml", "pipfile", "setup.cfg"}
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


def is_dependency_file(path: str) -> bool:
    name = basename(path).lower()
    return name in DEPENDENCY_FILENAMES or (name.startswith("requirements") and name.endswith(".txt"))


# ---------------------------------------------------------------------------
# Dependency parsing
# ---------------------------------------------------------------------------


def parse_dependencies(path: str, text: str) -> list[str]:
    """Return normalised (lower-case) package names declared in one dependency file."""
    name = basename(path).lower()
    if name.endswith(".txt"):
        return _parse_requirements_txt(text)
    if name == "pyproject.toml":
        return _parse_pyproject(text)
    if name == "pipfile":
        return _parse_pipfile(text)
    return []


def _normalise(package: str) -> str:
    return package.strip().lower().replace("_", "-")


def _parse_requirement_line(line: str) -> str:
    line = line.split("#", 1)[0].strip()
    if not line or line.startswith(("-", "git+", "http")):
        return ""
    match = _REQUIREMENT_NAME.match(line)
    return _normalise(match.group(1)) if match else ""


def _parse_requirements_txt(text: str) -> list[str]:
    return [pkg for pkg in (_parse_requirement_line(line) for line in text.splitlines()) if pkg]


def _parse_pyproject(text: str) -> list[str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    packages: list[str] = []
    project = data.get("project", {})
    for requirement in project.get("dependencies", []) or []:
        packages.append(_parse_requirement_line(requirement))
    for group in (project.get("optional-dependencies") or {}).values():
        packages.extend(_parse_requirement_line(req) for req in group)
    poetry = data.get("tool", {}).get("poetry", {})
    packages.extend(_normalise(pkg) for pkg in (poetry.get("dependencies") or {}) if pkg.lower() != "python")
    return [pkg for pkg in packages if pkg]


def _parse_pipfile(text: str) -> list[str]:
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return []
    names = list(data.get("packages", {})) + list(data.get("dev-packages", {}))
    return [_normalise(name) for name in names]


def collect_dependencies(files: dict[str, str]) -> dict[str, list[str]]:
    """{dependency file path: [packages]} for every dependency file we downloaded."""
    return {path: parse_dependencies(path, text) for path, text in files.items() if is_dependency_file(path)}


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def detect_framework(
    dependencies: dict[str, list[str]], python_files: dict[str, PythonFileInfo]
) -> FrameworkResult:
    """Score every known framework and return the best-supported one."""
    scored = []
    for signature in SIGNATURES:
        points, evidence = _score_signature(signature, dependencies, python_files)
        if points:
            scored.append((points, signature.name, evidence))

    if scored:
        scored.sort(key=lambda item: item[0], reverse=True)
        points, name, evidence = scored[0]
        return FrameworkResult(
            name=name,
            confidence=_confidence(points, evidence),
            evidence=evidence,
            others=[other for _, other, _ in scored[1:]],
        )

    cli = _detect_cli(dependencies, python_files)
    if cli:
        return cli
    return FrameworkResult(
        name=UNKNOWN_FRAMEWORK,
        confidence="Low",
        evidence=["No known framework was found in dependency files or imports."],
    )


def _score_signature(
    signature: FrameworkSignature, dependencies: dict[str, list[str]], python_files: dict[str, PythonFileInfo]
) -> tuple[int, list[str]]:
    points = 0
    evidence: list[str] = []

    for dep_path, packages in sorted(dependencies.items()):
        found = [pkg for pkg in signature.packages if pkg in packages]
        if found:
            points += DEPENDENCY_POINTS
            evidence.append(f"{dep_path} lists `{found[0]}`")
            break  # one dependency file is enough evidence

    importing_files = sorted(
        path for path, info in python_files.items() if info.top_level_packages & set(signature.imports)
    )
    if importing_files:
        extra = min(len(importing_files) - 1, MAX_EXTRA_IMPORT_POINTS) * EXTRA_IMPORT_POINTS
        points += FIRST_IMPORT_POINTS + extra
        shown = ", ".join(importing_files[:3])
        more = f" (+{len(importing_files) - 3} more)" if len(importing_files) > 3 else ""
        evidence.append(f"imported in {shown}{more}")

    for path, info in sorted(python_files.items()):
        for call_name in signature.init_calls:
            calls = info.calls_named(call_name)
            if calls:
                points += INIT_CALL_POINTS
                evidence.append(f"{path}:{calls[0].lineno} calls `{call_name}(...)`")
                return points, evidence  # one initialisation is enough
    return points, evidence


def _confidence(points: int, evidence: list[str]) -> str:
    if points >= HIGH_CONFIDENCE_POINTS and len(evidence) >= 2:
        return "High"
    if points >= MEDIUM_CONFIDENCE_POINTS:
        return "Medium"
    return "Low"


def _detect_cli(dependencies: dict[str, list[str]], python_files: dict[str, PythonFileInfo]) -> FrameworkResult | None:
    evidence: list[str] = []
    for dep_path, packages in sorted(dependencies.items()):
        found = [pkg for pkg in CLI_PACKAGES if pkg in packages]
        if found:
            evidence.append(f"{dep_path} lists `{found[0]}`")
    for path, info in sorted(python_files.items()):
        cli_imports = sorted(info.top_level_packages & set(CLI_IMPORTS))
        if cli_imports:
            evidence.append(f"{path} imports `{cli_imports[0]}`")
        if info.has_main_guard:
            evidence.append(f"{path}:{info.main_guard_line} has an `if __name__ == \"__main__\"` block")
    if not evidence:
        return None
    confidence = "Medium" if len(evidence) >= 2 else "Low"
    return FrameworkResult(name=CLI_FRAMEWORK, confidence=confidence, evidence=evidence[:5])
